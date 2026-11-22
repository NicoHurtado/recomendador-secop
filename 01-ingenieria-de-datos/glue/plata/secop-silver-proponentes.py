"""
Fase E · Paso E4 · Job de plata: proponentes

Construye secop_silver.proponentes y secop_silver.proponentes_rechazados.
Cada fila válida es una participación: un proveedor que se presentó a un proceso.

Flujo (un solo camino para histórico e ingesta, igual que en procesos):
  1. Lee el histórico (secop_bronze.raw_proponentes_hist) y la ingesta (JSON en S3) y los une.
  2. Limpia: NIT normalizado, código de proveedor, proveedor_key con hash, persona jurídica.
     Si una fila trae código pero no NIT, el NIT se recupera de otras filas del mismo código
     (el código identifica al mismo proveedor que el NIT en el 99,99 % de los casos, Q10).
     Si el proveedor nunca aparece con NIT, se identifica por su código de SECOP (H05b).
     Corrección 2.1: consorcios, NIT de relleno (menos de 6 dígitos) y NIT compartidos por más
     de 5 códigos con nombres distintos también se identifican por código.
  3. Reglas en orden:
       R1 llave_incompleta        sin proceso, o sin NIT ni código de proveedor
       R2 proceso_fuera_de_alcance / proceso_inexistente   el proceso no está en secop_silver.procesos
       R3 duplicado               una fila por (proceso, proveedor): gana la ingesta y la más reciente
  4. Escribe válidos y rechazados, verifica el cuadre y registra la corrida en control_corridas.

Requiere que secop_silver.procesos ya esté cargada (paso E3).
Parámetros del job:  --datalake-formats iceberg  ·  Python library path: limpieza_secop.py
"""
import sys
from datetime import datetime, timezone

from pyspark.sql import Window
from pyspark.sql import functions as F

import limpieza_secop as L

BUCKET = "proyecto-integrador-bucket-01"
CAT = "glue_catalog"
TABLA = f"{CAT}.secop_silver.proponentes"
TABLA_RECH = f"{CAT}.secop_silver.proponentes_rechazados"
TABLA_PROC = f"{CAT}.secop_silver.procesos"
TABLA_PROC_RECH = f"{CAT}.secop_silver.procesos_rechazados"
TABLA_CONTROL = f"{CAT}.secop_control.control_corridas"
COLS_TECNICAS = ["fuente", "sys_updated_at_txt", "_fecha_ingesta"]


def bronce_unificado(hist, ing):
    h = (hist.withColumn("fuente", F.lit("historico"))
             .withColumn("sys_updated_at_txt", F.lit(None).cast("string"))
             .withColumn("_fecha_ingesta", F.lit(None).cast("string")))
    i = (ing.withColumnRenamed(":updated_at", "sys_updated_at_txt")
            .withColumnRenamed("fecha", "_fecha_ingesta")
            .drop(":id", ":created_at")
            .withColumn("fuente", F.lit("ingesta")))
    return h.unionByName(i, allowMissingColumns=True)


def construir(b, procesos_validos, procesos_rechazados, sal: str, id_corrida: str):
    """
    b                   bronce unificado de proponentes
    procesos_validos    secop_silver.procesos (id_proceso, fecha_publicacion)
    procesos_rechazados secop_silver.procesos_rechazados (id_proceso, motivo)
    Devuelve (validos, rechazados).
    """
    columnas_bronce = [c for c in b.columns if c not in COLS_TECNICAS]

    t = (b.withColumn("id_proceso", L.centinela_a_nulo("id_procedimiento"))
          .withColumn("codigo_proveedor", L.codigo_proveedor("codigo_proveedor"))
          .withColumn("_nit_propio", L.nit_confiable("nit_proveedor"))
          .withColumn("_consorcio", L.es_consorcio("proveedor"))
          .withColumn("sys_updated_at", L.utc_a_colombia("sys_updated_at_txt")))

    # Corrección 2.1: el NIT no se usa como identidad si es de un consorcio (siempre por código),
    # si es de relleno (menos de 6 dígitos, ya nulo por nit_confiable) o si está compartido por
    # muchos códigos con nombres distintos (NIT prestado). En esos casos manda el código de SECOP.
    compartidos = L.nits_compartidos(b).withColumnRenamed("nit", "_nit_propio") \
                   .withColumn("_nit_compartido", F.lit(True))
    t = (t.join(F.broadcast(compartidos), "_nit_propio", "left")
          .withColumn("_nit_propio", F.when(F.col("_nit_compartido").isNull() & ~F.col("_consorcio"),
                                            F.col("_nit_propio"))))

    # Recuperar el NIT por código: el NIT más frecuente entre las filas que traen ambos
    pares = (t.filter(F.col("codigo_proveedor").isNotNull() & F.col("_nit_propio").isNotNull())
              .groupBy("codigo_proveedor", "_nit_propio").count()
              .withColumn("_r", F.row_number().over(
                  Window.partitionBy("codigo_proveedor").orderBy(F.desc("count"), "_nit_propio")))
              .filter("_r = 1")
              .select("codigo_proveedor", F.col("_nit_propio").alias("_nit_por_codigo")))
    t = (t.join(pares, "codigo_proveedor", "left")
          .withColumn("_nit", F.when(~F.col("_consorcio"), F.coalesce("_nit_propio", "_nit_por_codigo")))
          .withColumn("_nit_recuperado", F.col("_nit_propio").isNull() & F.col("_nit_por_codigo").isNotNull()))

    # Estado del proceso en plata
    validos_ids = procesos_validos.select("id_proceso", F.col("fecha_publicacion").alias("_fecha_proceso"),
                                          F.lit(True).alias("_proceso_valido"))
    rech_ids = (procesos_rechazados.filter(F.col("id_proceso").isNotNull())
                .groupBy("id_proceso")
                .agg(F.max(F.when(F.col("motivo") == "fuera_de_alcance", 1).otherwise(0)).alias("_fuera"),
                     F.first("motivo").alias("_motivo_proceso")))
    t = t.join(validos_ids, "id_proceso", "left").join(rech_ids, "id_proceso", "left")

    t = (t.withColumn("regla",
                      F.when(F.col("id_proceso").isNull()
                             | (F.col("_nit").isNull() & F.col("codigo_proveedor").isNull()), "R1")
                       .when(F.col("_proceso_valido").isNull(), "R2"))
          .withColumn("motivo",
                      F.when(F.col("regla") == "R1", "llave_incompleta")
                       .when((F.col("regla") == "R2") & (F.col("_fuera") == 1), "proceso_fuera_de_alcance")
                       .when(F.col("regla") == "R2", "proceso_inexistente"))
          .withColumn("detalle",
                      F.when(F.col("regla") == "R1",
                             F.when(F.col("id_proceso").isNull(), F.lit("id_procedimiento nulo"))
                              .otherwise(F.lit("sin NIT y sin código de proveedor")))
                       .when(F.col("motivo") == "proceso_inexistente",
                             F.when(F.col("_motivo_proceso").isNotNull(),
                                    F.concat(F.lit("proceso rechazado en plata por: "), F.col("_motivo_proceso")))
                              .otherwise(F.lit("proceso no existe en procesos")))
                       .when(F.col("motivo") == "proceso_fuera_de_alcance", F.lit("proceso fuera del alcance"))))

    # Identidad del proveedor: por NIT (propio o recuperado por código). Si el proveedor nunca
    # aparece con NIT (consorcios y uniones temporales que aún no lo tienen, "No Definido"),
    # se identifica por su código de SECOP, presente en el 100 % de las filas (H05b).
    t = (t.withColumn("_llave_por_codigo", F.col("_nit").isNull() & F.col("codigo_proveedor").isNotNull())
          .withColumn("proveedor_key",
                      F.when(F.col("_llave_por_codigo"),
                             F.sha2(F.concat(F.lit(sal), F.lit("codigo:"), F.col("codigo_proveedor")), 256))
                       .otherwise(L.proveedor_key("_nit", sal))))

    # R3: una fila por (proceso, proveedor)
    orden = Window.partitionBy("id_proceso", "proveedor_key").orderBy(
        F.when(F.col("fuente") == "ingesta", 0).otherwise(1),
        F.col("sys_updated_at").desc_nulls_last(),
        F.col("_nit_recuperado").asc(),               # preferir la fila que trae su propio NIT
        F.col("codigo_proveedor").asc_nulls_last(),
    )
    pasan = t.filter(F.col("regla").isNull()).withColumn("_n", F.row_number().over(orden))
    v = pasan.filter("_n = 1")
    dup = (pasan.filter("_n > 1")
           .withColumn("regla", F.lit("R3")).withColumn("motivo", F.lit("duplicado"))
           .withColumn("detalle", F.concat(F.lit("participación repetida, fuente "), F.col("fuente"))))

    json_bronce = L.registro_json(b.select(*columnas_bronce), sal,
                                  columnas_hash=["nit_proveedor"], columnas_excluir=["proveedor"])
    rech = t.filter(F.col("regla").isNotNull()).unionByName(dup.drop("_n"))
    rechazados = rech.select(
        "id_proceso", "codigo_proveedor", "regla", "motivo", "detalle",
        F.when(F.col("motivo") == "proceso_fuera_de_alcance", F.lit(None).cast("string"))
         .otherwise(json_bronce).alias("registro_original"),
        "fuente", "sys_updated_at",
        F.lit(id_corrida).alias("id_corrida"),
        L.ahora_colombia().alias("fecha_carga"),
    )

    # Con NIT: empresa si es NIT de 9 dígitos que empieza por 8 o 9. Sin NIT: solo se marca como
    # persona jurídica si el nombre es de un consorcio o unión temporal; si no, queda nulo (desconocido).
    juridica = (F.when(F.col("_consorcio"), F.lit(True))
                 .when(F.col("_nit").isNotNull(), L.es_persona_juridica("_nit")))
    # tipo_proveedor provisional (2.4): E6 lo reemplaza por el del registro cuando el proveedor está ahí
    entidades = (procesos_validos.select(F.col("nit_entidad").alias("_nit")).filter(F.col("_nit").isNotNull())
                 .distinct().withColumn("_nit_es_entidad", F.lit(True)))
    v = v.join(F.broadcast(entidades), "_nit", "left")
    tipo = (F.when(F.col("_consorcio"), F.lit("consorcio"))
             .when(F.col("_nit_es_entidad").isNotNull(), F.lit("entidad_publica"))
             .when(juridica == False, F.lit("persona_natural")))  # noqa: E712
    validos = v.select(
        "id_proceso", "proveedor_key", "codigo_proveedor",
        tipo.alias("tipo_proveedor"),
        juridica.alias("es_persona_juridica"),
        F.when(juridica == True, L.centinela_a_nulo("proveedor")).alias("nombre_proveedor"),  # noqa: E712
        L.nit_normalizado("nit_entidad").alias("nit_entidad"),
        F.coalesce("_fecha_proceso", L.fecha("fecha_publicaci_n")).alias("fecha_publicacion"),
        F.lit(None).cast("boolean").alias("es_ganador"),   # lo calcula E6 (corrección 2.2)
        "fuente", "sys_updated_at",
        L.ahora_colombia().alias("fecha_carga"),
    )
    return validos, rechazados


def ajustar_a_tabla(spark, df, tabla):
    esquema = spark.table(tabla).schema
    return df.select(*[F.col(f.name).cast(f.dataType).alias(f.name) for f in esquema.fields])


def main():
    import boto3
    from awsglue.context import GlueContext
    from awsglue.utils import getResolvedOptions
    from pyspark import SparkConf, StorageLevel
    from pyspark.context import SparkContext

    args = getResolvedOptions(sys.argv, ["JOB_NAME"])
    conf = (SparkConf()
            .set("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
            .set(f"spark.sql.catalog.{CAT}", "org.apache.iceberg.spark.SparkCatalog")
            .set(f"spark.sql.catalog.{CAT}.catalog-impl", "org.apache.iceberg.aws.glue.GlueCatalog")
            .set(f"spark.sql.catalog.{CAT}.io-impl", "org.apache.iceberg.aws.s3.S3FileIO")
            .set(f"spark.sql.catalog.{CAT}.warehouse", f"s3://{BUCKET}/silver/")
            .set("spark.sql.legacy.timeParserPolicy", "CORRECTED")
            .set("spark.sql.session.timeZone", "UTC"))
    sc = SparkContext.getOrCreate(conf=conf)
    spark = GlueContext(sc).spark_session

    inicio = datetime.now(timezone.utc)
    id_corrida = "plata-proponentes-" + inicio.strftime("%Y%m%d-%H%M%S")
    sal = boto3.client("ssm").get_parameter(Name="/secop/hash-salt", WithDecryption=True)["Parameter"]["Value"]
    print(f"== {id_corrida}")
    leidas = n_val = n_rech = snap = ultima_ingesta = None
    por_motivo, cuadre = {}, False

    try:
        hist = spark.table("secop_bronze.raw_proponentes_hist")
        ing = L.leer_ingesta(spark, BUCKET, "proponentes-procesos")
        b = bronce_unificado(hist, ing).persist(StorageLevel.MEMORY_AND_DISK)
        leidas = b.count()
        ultima_ingesta = b.agg(F.max("_fecha_ingesta")).collect()[0][0]
        print(f"Leídas: {leidas:,} (última partición de ingesta: {ultima_ingesta})")

        validos, rechazados = construir(b, spark.table(TABLA_PROC), spark.table(TABLA_PROC_RECH), sal, id_corrida)
        validos = ajustar_a_tabla(spark, validos, TABLA).persist(StorageLevel.MEMORY_AND_DISK)
        rechazados = ajustar_a_tabla(spark, rechazados, TABLA_RECH).persist(StorageLevel.MEMORY_AND_DISK)

        n_val = validos.count()
        por_motivo = {r["motivo"]: r["count"] for r in rechazados.groupBy("motivo").count().collect()}
        n_rech = sum(por_motivo.values())
        cuadre = leidas == n_val + n_rech
        print(f"Válidas: {n_val:,} | Rechazadas: {n_rech:,} | Cuadre: {cuadre}")
        for m, n in sorted(por_motivo.items()):
            print(f"   {m}: {n:,}")
        if not cuadre:
            raise RuntimeError(f"El cuadre no cierra: {leidas} != {n_val} + {n_rech}")

        validos.writeTo(TABLA).overwrite(F.lit(True))
        rechazados.writeTo(TABLA_RECH).overwrite(F.lit(True))
        snap = spark.sql(f"SELECT snapshot_id FROM {TABLA}.snapshots ORDER BY committed_at DESC LIMIT 1").collect()[0][0]
        estado, error = "exito", None
    except Exception as e:
        estado, error = "fallo", str(e)[:1000]

    fila = spark.createDataFrame([(
        id_corrida, args["JOB_NAME"], "secop_silver.proponentes",
        inicio.replace(tzinfo=None), datetime.now(timezone.utc).replace(tzinfo=None),
        estado, leidas, n_val, n_rech, por_motivo, cuadre,
        datetime.strptime(ultima_ingesta, "%Y-%m-%d").date() if ultima_ingesta else None,
        snap, error)],
        "id_corrida string, job string, tabla string, inicio timestamp, fin timestamp, estado string, "
        "filas_leidas long, filas_validas long, filas_rechazadas long, rechazos_por_motivo map<string,long>, "
        "cuadre_ok boolean, ultima_fecha_ingesta date, snapshot_id long, mensaje_error string")
    ajustar_a_tabla(spark, fila, TABLA_CONTROL).writeTo(TABLA_CONTROL).append()
    print(f"== Registrado en control_corridas: {estado}")
    if estado != "exito":
        raise RuntimeError(error)


if __name__ == "__main__":
    main()
