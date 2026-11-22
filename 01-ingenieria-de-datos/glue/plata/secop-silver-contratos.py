"""
Fase E · Paso E5 · Job de plata: contratos

Construye secop_silver.contratos y secop_silver.contratos_rechazados.

Flujo (un solo camino para histórico e ingesta, igual que procesos y proponentes):
  1. Lee el histórico (secop_bronze.raw_contratos_hist) y la ingesta (JSON en S3) y los une.
  2. Reglas en orden:
       R1 llave_incompleta   sin id_contrato o sin proceso_de_compra
       R2 version_anterior   una fila por id_contrato: gana la ingesta y luego la más reciente
  3. Los contratos cuyo portafolio no está en secop_silver.procesos NO se rechazan:
     se marcan con con_proceso = false (H04b). Cuentan para el perfil del proveedor.
  4. Identidad del proveedor, consistente con proponentes:
       a) si su código de SECOP ya tiene llave en secop_silver.proponentes, se usa esa llave;
       b) si no, hash del documento normalizado;
       c) si no hay documento, hash del código.
  5. No pasan a plata los datos personales (H12): representantes, supervisores, ordenadores,
     cuentas bancarias, género. Tampoco van dentro del JSON de los rechazados.

Requiere secop_silver.procesos (E3) y secop_silver.proponentes (E4).
Parámetros del job:  --datalake-formats iceberg  ·  Python library path: limpieza_secop.py
"""
import sys
from datetime import datetime, timezone

from pyspark.sql import Window
from pyspark.sql import functions as F

import limpieza_secop as L

BUCKET = "proyecto-integrador-bucket-01"
CAT = "glue_catalog"
TABLA = f"{CAT}.secop_silver.contratos"
TABLA_RECH = f"{CAT}.secop_silver.contratos_rechazados"
TABLA_PROC = f"{CAT}.secop_silver.procesos"
TABLA_PROP = f"{CAT}.secop_silver.proponentes"
TABLA_CONTROL = f"{CAT}.secop_control.control_corridas"
COLS_TECNICAS = ["fuente", "sys_updated_at_txt", "_fecha_ingesta"]

# H12: datos personales que no pasan a plata, ni siquiera dentro del JSON de rechazados
COLS_PERSONALES = [
    "proveedor_adjudicado",
    "nombre_representante_legal", "nacionalidad_representante_legal", "domicilio_representante_legal",
    "tipo_de_identificaci_n_representante_legal", "identificaci_n_representante_legal",
    "g_nero_representante_legal",
    "nombre_del_banco", "tipo_de_cuenta", "n_mero_de_cuenta",
    "nombre_ordenador_del_gasto", "tipo_de_documento_ordenador_del_gasto",
    "n_mero_de_documento_ordenador_del_gasto",
    "nombre_supervisor", "tipo_de_documento_supervisor", "n_mero_de_documento_supervisor",
    "nombre_ordenador_de_pago", "tipo_de_documento_ordenador_de_pago", "n_mero_de_documento_ordenador_de_pago",
]
PLURAL = r"CONSORCIO|UNI[OÓ]N TEMPORAL|^U\.? ?T\.? "


def bronce_unificado(hist, ing):
    h = (hist.withColumn("fuente", F.lit("historico"))
             .withColumn("sys_updated_at_txt", F.lit(None).cast("string"))
             .withColumn("_fecha_ingesta", F.lit(None).cast("string")))
    i = (ing.withColumnRenamed(":updated_at", "sys_updated_at_txt")
            .withColumnRenamed("fecha", "_fecha_ingesta")
            .drop(":id", ":created_at")
            .withColumn("fuente", F.lit("ingesta")))
    return h.unionByName(i, allowMissingColumns=True)


def _rango_duracion(d):
    """Corrección 2.6: 0 días o más de 30 años (10.950 días) no es una duración real: nulo."""
    return F.when((d >= 1) & (d <= 10950), d)


def construir(b, procesos_validos, proponentes, sal: str, id_corrida: str, compartidos=None, proveedores=None):
    """
    b               bronce unificado de contratos
    procesos_validos secop_silver.procesos (id_portafolio)
    proponentes     secop_silver.proponentes (codigo_proveedor, proveedor_key)
    Devuelve (validos, rechazados).
    """
    columnas_bronce = [c for c in b.columns if c not in COLS_TECNICAS]

    t = (b.withColumn("id_contrato_l", L.centinela_a_nulo("id_contrato"))
          .withColumn("id_portafolio", L.centinela_a_nulo("proceso_de_compra"))
          .withColumn("codigo_proveedor_l", L.codigo_proveedor("codigo_proveedor"))
          .withColumn("_consorcio", L.es_consorcio("proveedor_adjudicado"))
          .withColumn("_doc", L.nit_confiable("documento_proveedor"))
          .withColumn("sys_updated_at", L.utc_a_colombia("sys_updated_at_txt"))
          .withColumn("_ultima_act", L.fecha_hora("ultima_actualizacion"))
          .withColumn("fecha_firma", L.fecha_hora("fecha_de_firma")))

    # Corrección 2.1: mismo criterio de identidad que proponentes (consorcio o NIT compartido -> código)
    if compartidos is not None:
        t = (t.join(F.broadcast(compartidos.withColumnRenamed("nit", "_doc").withColumn("_compartido", F.lit(True))),
                    "_doc", "left"))
    else:
        t = t.withColumn("_compartido", F.lit(None).cast("boolean"))
    t = t.withColumn("_doc", F.when(F.col("_compartido").isNull() & ~F.col("_consorcio"), F.col("_doc")))

    # R1
    t = (t.withColumn("regla", F.when(F.col("id_contrato_l").isNull() | F.col("id_portafolio").isNull(), "R1"))
          .withColumn("motivo", F.when(F.col("regla") == "R1", "llave_incompleta"))
          .withColumn("detalle", F.when(F.col("regla") == "R1",
                                        F.when(F.col("id_contrato_l").isNull(), F.lit("id_contrato nulo"))
                                         .otherwise(F.lit("proceso_de_compra nulo")))))

    # R2: una fila por contrato
    orden = Window.partitionBy("id_contrato_l").orderBy(
        F.when(F.col("fuente") == "ingesta", 0).otherwise(1),
        F.col("sys_updated_at").desc_nulls_last(),
        F.col("_ultima_act").desc_nulls_last(),
        F.col("fecha_firma").desc_nulls_last(),
        F.col("id_portafolio").asc_nulls_last(),
    )
    pasan = t.filter(F.col("regla").isNull()).withColumn("_n", F.row_number().over(orden))
    v = pasan.filter("_n = 1")
    anteriores = (pasan.filter("_n > 1")
                  .withColumn("regla", F.lit("R2")).withColumn("motivo", F.lit("version_anterior"))
                  .withColumn("detalle", F.concat(F.lit("versión reemplazada, fuente "), F.col("fuente"))))

    json_bronce = L.registro_json(b.select(*columnas_bronce), sal,
                                  columnas_hash=["documento_proveedor"], columnas_excluir=COLS_PERSONALES)
    rech = t.filter(F.col("regla").isNotNull()).unionByName(anteriores.drop("_n"))
    rechazados = rech.select(
        F.col("id_contrato_l").alias("id_contrato"), "id_portafolio", "regla", "motivo", "detalle",
        json_bronce.alias("registro_original"),
        "fuente", "sys_updated_at",
        F.lit(id_corrida).alias("id_corrida"),
        L.ahora_colombia().alias("fecha_carga"),
    )

    # Identidad del proveedor, consistente con proponentes
    llave_por_codigo = (proponentes.filter(F.col("codigo_proveedor").isNotNull())
                        .groupBy("codigo_proveedor").agg(F.first("proveedor_key").alias("_key_proponentes"))
                        .withColumnRenamed("codigo_proveedor", "codigo_proveedor_l"))
    portafolios = (procesos_validos.select("id_portafolio").where(F.col("id_portafolio").isNotNull())
                   .distinct().withColumn("_con_proceso", F.lit(True)))
    v = (v.join(llave_por_codigo, "codigo_proveedor_l", "left")
          .join(portafolios, "id_portafolio", "left"))
    proveedor_key = F.coalesce(
        F.col("_key_proponentes"),
        L.proveedor_key("_doc", sal),
        F.when(F.col("codigo_proveedor_l").isNotNull(),
               F.sha2(F.concat(F.lit(sal), F.lit("codigo:"), F.col("codigo_proveedor_l")), 256)))

    tipo_doc = L.centinela_a_nulo("tipodocproveedor")
    juridica = (F.when(F.col("_consorcio"), F.lit(True))
                 .when(F.lower(tipo_doc).rlike("c[eé]dula|pasaporte|tarjeta"), F.lit(False))
                 .when(F.col("_doc").isNotNull(), L.es_persona_juridica("_doc")))
    unspsc = L.unspsc("codigo_de_categoria_principal")

    # tipo_proveedor (2.4): el del registro; si el proveedor no está, uno provisional
    entidades = (procesos_validos.select(F.col("nit_entidad").alias("_doc")).filter(F.col("_doc").isNotNull())
                 .distinct().withColumn("_doc_es_entidad", F.lit(True)))
    v = v.join(F.broadcast(entidades), "_doc", "left").withColumn("proveedor_key", proveedor_key)
    if proveedores is not None:
        v = v.join(proveedores.select("proveedor_key", F.col("tipo_proveedor").alias("_tipo_registro")),
                   "proveedor_key", "left")
    else:
        v = v.withColumn("_tipo_registro", F.lit(None).cast("string"))
    tipo = F.coalesce(F.col("_tipo_registro"),
                      F.when(F.col("_consorcio"), F.lit("consorcio"))
                       .when(F.col("_doc_es_entidad").isNotNull(), F.lit("entidad_publica"))
                       .when(juridica == False, F.lit("persona_natural")),  # noqa: E712
                      F.lit("no_registrado"))

    validos = v.select(
        F.col("id_contrato_l").alias("id_contrato"),
        "id_portafolio",
        F.coalesce(F.col("_con_proceso"), F.lit(False)).alias("con_proceso"),
        L.nit_normalizado("nit_entidad").alias("nit_entidad"),
        L.centinela_a_nulo("nombre_entidad").alias("nombre_entidad"),
        L.centinela_a_nulo("departamento").alias("departamento"),
        L.centinela_a_nulo("ciudad").alias("ciudad"),
        L.centinela_a_nulo("sector").alias("sector"),
        L.centinela_a_nulo("orden").alias("orden"),
        "proveedor_key",
        tipo.alias("tipo_proveedor"),
        F.col("codigo_proveedor_l").alias("codigo_proveedor"),
        tipo_doc.alias("tipo_documento_proveedor"),
        juridica.alias("es_persona_juridica"),
        F.when(juridica == True, L.centinela_a_nulo("proveedor_adjudicado")).alias("nombre_proveedor"),  # noqa: E712
        L.booleano_si_no("es_pyme").alias("es_pyme"),
        L.centinela_a_nulo("modalidad_de_contratacion").alias("modalidad"),
        L.centinela_a_nulo("tipo_de_contrato").alias("tipo_contrato"),
        L.centinela_a_nulo("estado_contrato").alias("estado_contrato"),
        unspsc.alias("unspsc"),
        L.unspsc_nivel(unspsc, 2).alias("unspsc_segmento"),
        L.unspsc_nivel(unspsc, 4).alias("unspsc_familia"),
        L.unspsc_nivel(unspsc, 6).alias("unspsc_clase"),
        L.dinero("valor_del_contrato").alias("valor_contrato"),
        "fecha_firma",
        L.fecha("fecha_de_inicio_del_contrato").alias("fecha_inicio"),
        L.fecha("fecha_de_fin_del_contrato").alias("fecha_fin"),
        _rango_duracion(L.duracion_dias_texto("duraci_n_del_contrato")).alias("duracion_dias"),
        F.coalesce(F.lower(F.col("estado_contrato")).rlike("cedid|cesi[oó]n"), F.lit(False)).alias("es_cedido"),
        "fuente", "sys_updated_at",
        L.ahora_colombia().alias("fecha_carga"),
    )
    return validos, rechazados


def ajustar_a_tabla(spark, df, tabla):
    esquema = spark.table(tabla).schema
    faltan_en_df = [f.name for f in esquema.fields if f.name not in df.columns]
    sobran_en_df = [c for c in df.columns if c not in esquema.fieldNames()]
    if faltan_en_df:
        raise ValueError(f"{tabla}: la tabla tiene columnas que el job no produce: {faltan_en_df}")
    if sobran_en_df:
        raise ValueError(f"{tabla}: el job produce columnas que la tabla no tiene: {sobran_en_df}. "
                         f"Agréguelas con ALTER TABLE ... ADD COLUMNS en Athena.")
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
    id_corrida = "plata-contratos-" + inicio.strftime("%Y%m%d-%H%M%S")
    sal = boto3.client("ssm").get_parameter(Name="/secop/hash-salt", WithDecryption=True)["Parameter"]["Value"]
    print(f"== {id_corrida}")
    leidas = n_val = n_rech = snap = ultima_ingesta = None
    por_motivo, cuadre = {}, False

    try:
        hist = spark.table("secop_bronze.raw_contratos_hist")
        ing = L.leer_ingesta(spark, BUCKET, "contratos-electronicos")
        b = bronce_unificado(hist, ing).persist(StorageLevel.MEMORY_AND_DISK)
        leidas = b.count()
        ultima_ingesta = b.agg(F.max("_fecha_ingesta")).collect()[0][0]
        print(f"Leídas: {leidas:,} (última partición de ingesta: {ultima_ingesta})")

        prop_bronce = (spark.table("secop_bronze.raw_proponentes_hist")
                       .unionByName(L.leer_ingesta(spark, BUCKET, "proponentes-procesos"), allowMissingColumns=True))
        compartidos = L.nits_compartidos(prop_bronce).cache()
        print(f"NIT compartidos (identidad por código): {compartidos.count():,}")
        validos, rechazados = construir(b, spark.table(TABLA_PROC), spark.table(TABLA_PROP), sal, id_corrida,
                                        compartidos, spark.table(f"{CAT}.secop_silver.proveedores"))
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
        id_corrida, args["JOB_NAME"], "secop_silver.contratos",
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
