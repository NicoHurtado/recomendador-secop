"""
Corrección 2.4 · Job de plata: proveedores registrados

Construye secop_silver.proveedores y secop_silver.proveedores_rechazados a partir del dataset
"SECOP II - Proveedores Registrados" (qmzu-gj57). Una fila por proveedor_key.

Flujo (un solo camino para histórico e ingesta, igual que los demás jobs de plata):
  1. Lee el histórico (secop_bronze.raw_proveedores_hist) y, si existe, la ingesta (JSON en S3).
  2. Identidad del proveedor, la misma de proponentes y contratos (corrección 2.1):
       a) si su código ya tiene llave en secop_silver.proponentes, se usa esa llave;
       b) si es consorcio (es_grupo o nombre), si el NIT es de relleno o si es un NIT compartido,
          por código;
       c) si no, por NIT.
  3. Reglas en orden:
       R1 llave_incompleta     sin código y sin NIT confiable
       R2 version_anterior     una fila por código de SECOP: gana la ingesta y luego la más reciente
       R3 cuenta_consolidada   una fila por proveedor_key: varias cuentas de la misma empresa se
                               consolidan (fecha de registro: la más antigua; el resto: la cuenta
                               activa más reciente)
  4. tipo_proveedor, en orden:
       consorcio        es_grupo = true o nombre de consorcio o unión temporal
       entidad_publica  es_entidad = true o su NIT es nit_entidad de algún proceso
       persona_natural  tipo_empresa de persona natural, o documento que no es NIT de empresa
       empresa          el resto
     es_usuario_objetivo = empresa o persona_natural, y cuenta activa.
  5. No pasan a plata datos de contacto ni del representante legal: el job solo lee las columnas
     que necesita, y el JSON de los rechazados también se arma solo con ellas (NIT con hash).

Orden del pipeline: E3 procesos -> E4 proponentes -> PROVEEDORES -> E5 contratos -> E6 ganador.
Parámetros del job:  --datalake-formats iceberg  ·  Python library path: limpieza_secop.py
"""
import sys
from datetime import datetime, timezone

from pyspark.sql import Window
from pyspark.sql import functions as F

import limpieza_secop as L

BUCKET = "proyecto-integrador-bucket-01"
CAT = "glue_catalog"
CARPETA = "proveedores-registrados"
TABLA = f"{CAT}.secop_silver.proveedores"
TABLA_RECH = f"{CAT}.secop_silver.proveedores_rechazados"
TABLA_PROC = f"{CAT}.secop_silver.procesos"
TABLA_PROP = f"{CAT}.secop_silver.proponentes"
TABLA_CONTROL = f"{CAT}.secop_control.control_corridas"

# Únicas columnas de bronce que se leen (lista blanca: nada de contacto ni representante legal)
COLUMNAS = ["codigo", "nit", "nombre", "espyme", "tipo_empresa", "departamento", "municipio",
            "codigo_categoria_principal", "fecha_creacion", "es_grupo", "es_entidad", "esta_activa", "pais"]
COLS_TECNICAS = ["fuente", "sys_updated_at_txt", "_fecha_ingesta"]


def seleccionar(df):
    """Las columnas de la lista blanca; las que falten se agregan como nulas."""
    return df.select(*[F.col(f"`{c}`") if c in df.columns else F.lit(None).cast("string").alias(c)
                       for c in COLUMNAS + [c for c in COLS_TECNICAS if c in df.columns]])


def bronce_unificado(hist, ing=None):
    h = (seleccionar(hist).withColumn("fuente", F.lit("historico"))
         .withColumn("sys_updated_at_txt", F.lit(None).cast("string"))
         .withColumn("_fecha_ingesta", F.lit(None).cast("string")))
    if ing is None:
        return h
    i = (ing.withColumnRenamed(":updated_at", "sys_updated_at_txt")
            .withColumnRenamed("fecha", "_fecha_ingesta")
            .withColumn("fuente", F.lit("ingesta")))
    return h.unionByName(seleccionar(i), allowMissingColumns=True)


def familia_declarada(col):
    """Familia UNSPSC (4 dígitos) de la categoría principal: acepta 'V1.80111600', '80111600' o '8011'."""
    d = F.regexp_extract(F.trim(F.col(col)), r"^(?:V1\.)?([0-9]{4})", 1)
    return F.when(d != "", d)


def construir(b, proponentes, nits_entidad, compartidos, sal: str, id_corrida: str):
    """
    b             bronce unificado de proveedores (solo columnas de la lista blanca)
    proponentes   secop_silver.proponentes (codigo_proveedor, proveedor_key)
    nits_entidad  NIT de entidades compradoras (columna nit), desde secop_silver.procesos
    compartidos   NIT compartidos (columna nit), de L.nits_compartidos sobre el bronce de proponentes
    Devuelve (validos, rechazados).
    """
    columnas_json = COLUMNAS + ["fuente"]
    t = (b.withColumn("codigo_proveedor", L.codigo_proveedor("codigo"))
          .withColumn("_es_grupo", L.booleano("es_grupo"))
          .withColumn("_es_entidad", L.booleano("es_entidad"))
          .withColumn("_activa", L.booleano("esta_activa"))
          .withColumn("_consorcio", F.coalesce(F.col("_es_grupo"), F.lit(False)) | L.es_consorcio("nombre"))
          .withColumn("_nit", L.nit_confiable("nit"))
          .withColumn("_fecha_registro", L.fecha("fecha_creacion"))
          .withColumn("sys_updated_at", L.utc_a_colombia("sys_updated_at_txt")))

    # Identidad (corrección 2.1): NIT compartido o de consorcio no identifica a nadie
    t = (t.join(F.broadcast(compartidos.withColumnRenamed("nit", "_nit").withColumn("_compartido", F.lit(True))),
                "_nit", "left")
          .withColumn("_nit_llave", F.when(F.col("_compartido").isNull() & ~F.col("_consorcio"), F.col("_nit"))))
    llave_prop = (proponentes.filter(F.col("codigo_proveedor").isNotNull())
                  .groupBy("codigo_proveedor").agg(F.first("proveedor_key").alias("_key_prop")))
    t = (t.join(llave_prop, "codigo_proveedor", "left")
          .withColumn("proveedor_key", F.coalesce(
              F.col("_key_prop"),
              L.proveedor_key("_nit_llave", sal),
              F.when(F.col("codigo_proveedor").isNotNull(),
                     F.sha2(F.concat(F.lit(sal), F.lit("codigo:"), F.col("codigo_proveedor")), 256)))))

    # R1
    t = (t.withColumn("regla", F.when(F.col("proveedor_key").isNull(), "R1"))
          .withColumn("motivo", F.when(F.col("regla") == "R1", "llave_incompleta"))
          .withColumn("detalle", F.when(F.col("regla") == "R1", F.lit("sin código y sin NIT confiable"))))

    # R2: una fila por código
    por_codigo = Window.partitionBy("codigo_proveedor").orderBy(
        F.when(F.col("fuente") == "ingesta", 0).otherwise(1),
        F.col("sys_updated_at").desc_nulls_last(),
        F.col("_fecha_registro").desc_nulls_last())
    pasan = (t.filter(F.col("regla").isNull())
              .withColumn("_n", F.when(F.col("codigo_proveedor").isNull(), 1)
                                 .otherwise(F.row_number().over(por_codigo))))
    r2 = (pasan.filter("_n > 1").withColumn("regla", F.lit("R2")).withColumn("motivo", F.lit("version_anterior"))
          .withColumn("detalle", F.concat(F.lit("versión reemplazada, fuente "), F.col("fuente"))).drop("_n"))
    pasan = pasan.filter("_n = 1").drop("_n")

    # R3: una fila por proveedor_key (varias cuentas de la misma empresa)
    por_llave = Window.partitionBy("proveedor_key")
    orden_llave = por_llave.orderBy(
        F.coalesce(F.col("_activa"), F.lit(True)).desc(),
        F.when(F.col("fuente") == "ingesta", 0).otherwise(1),
        F.col("_fecha_registro").desc_nulls_last(),
        F.col("codigo_proveedor").asc_nulls_last())
    pasan = (pasan.withColumn("_fecha_registro_min", F.min("_fecha_registro").over(por_llave))
                  .withColumn("_cuentas", F.count("*").over(por_llave))
                  .withColumn("_n", F.row_number().over(orden_llave)))
    r3 = (pasan.filter("_n > 1").withColumn("regla", F.lit("R3")).withColumn("motivo", F.lit("cuenta_consolidada"))
          .withColumn("detalle", F.lit("otra cuenta de SECOP con la misma llave"))
          .drop("_n", "_fecha_registro_min", "_cuentas"))
    v = pasan.filter("_n = 1")

    # Rechazados: JSON solo con las columnas de la lista blanca y el NIT con hash
    json_bronce = L.registro_json(b.select(*columnas_json), sal, columnas_hash=["nit"], columnas_excluir=["nombre"])
    rech = t.filter(F.col("regla").isNotNull()).unionByName(r2).unionByName(r3)
    rechazados = rech.select(
        "codigo_proveedor", "proveedor_key", "regla", "motivo", "detalle",
        json_bronce.alias("registro_original"),
        "fuente", "sys_updated_at",
        F.lit(id_corrida).alias("id_corrida"),
        L.ahora_colombia().alias("fecha_carga"),
    )

    # tipo_proveedor
    v = v.join(F.broadcast(nits_entidad.withColumnRenamed("nit", "_nit").withColumn("_nit_es_entidad", F.lit(True))),
               "_nit", "left")
    juridica = (F.when(F.col("_consorcio"), F.lit(True))
                 .when(F.col("_nit_llave").isNotNull(), L.es_persona_juridica("_nit_llave")))
    natural = (F.lower(F.coalesce(F.col("tipo_empresa"), F.lit(""))).rlike("natural")
               | (juridica == False))  # noqa: E712
    tipo = (F.when(F.col("_consorcio"), F.lit("consorcio"))
             .when(F.coalesce(F.col("_es_entidad"), F.lit(False)) | F.col("_nit_es_entidad").isNotNull(),
                   F.lit("entidad_publica"))
             .when(natural, F.lit("persona_natural"))
             .otherwise(F.lit("empresa")))
    v = v.withColumn("tipo_proveedor", tipo).withColumn("_juridica", juridica)

    # Ubicación (corrección de David, 6-nov): "No Provisto" es relleno (centinela) y los proveedores
    # del exterior no tienen departamento ni municipio colombiano. Sin país: se conserva lo que traiga.
    # El registro trae el país como código ISO de dos letras ("CO", "US", "ES"...).
    pais = F.lower(F.trim(L.centinela_a_nulo("pais")))
    _en_colombia = pais.isNull() | pais.isin("co", "col", "colombia")
    validos = v.select(
        "proveedor_key", "codigo_proveedor", "tipo_proveedor",
        F.col("_juridica").alias("es_persona_juridica"),
        F.when(F.col("_juridica") == True, L.centinela_a_nulo("nombre")).alias("nombre_proveedor"),  # noqa: E712
        L.booleano("espyme").alias("es_pyme"),
        L.centinela_a_nulo("tipo_empresa").alias("tipo_empresa"),
        F.when(_en_colombia, L.centinela_a_nulo("departamento")).alias("departamento"),
        F.when(_en_colombia, L.centinela_a_nulo("municipio")).alias("municipio"),
        familia_declarada("codigo_categoria_principal").alias("unspsc_familia_declarada"),
        F.col("_fecha_registro_min").alias("fecha_registro"),
        F.col("_activa").alias("esta_activa"),
        (F.col("tipo_proveedor").isin("empresa", "persona_natural")
         & F.coalesce(F.col("_activa"), F.lit(True))).alias("es_usuario_objetivo"),
        F.col("_cuentas").cast("int").alias("cuentas_secop"),
        "fuente", "sys_updated_at",
        L.ahora_colombia().alias("fecha_carga"),
    )
    return validos, rechazados


def ajustar_a_tabla(spark, df, tabla):
    esquema = spark.table(tabla).schema
    faltan = [f.name for f in esquema.fields if f.name not in df.columns]
    sobran = [c for c in df.columns if c not in esquema.fieldNames()]
    if faltan or sobran:
        raise ValueError(f"{tabla}: la tabla y el job no coinciden. Faltan en el job: {faltan}. "
                         f"Faltan en la tabla: {sobran}")
    return df.select(*[F.col(f.name).cast(f.dataType).alias(f.name) for f in esquema.fields])


def main():
    import boto3
    from awsglue.context import GlueContext
    from awsglue.utils import getResolvedOptions
    from pyspark import SparkConf, StorageLevel
    from pyspark.context import SparkContext
    from pyspark.sql.utils import AnalysisException

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
    id_corrida = "plata-proveedores-" + inicio.strftime("%Y%m%d-%H%M%S")
    sal = boto3.client("ssm").get_parameter(Name="/secop/hash-salt", WithDecryption=True)["Parameter"]["Value"]
    print(f"== {id_corrida}")
    leidas = n_val = n_rech = snap = ultima_ingesta = None
    por_motivo, cuadre = {}, False

    try:
        hist = spark.table("secop_bronze.raw_proveedores_hist")
        faltantes = [c for c in COLUMNAS if c not in hist.columns]
        print(f"Columnas de la lista blanca que no vienen en bronce (quedan nulas): {faltantes}")
        try:
            ing = L.leer_ingesta(spark, BUCKET, CARPETA)
        except AnalysisException:
            ing = None
            print("Sin ingesta diaria para proveedores: solo histórico")
        b = bronce_unificado(hist, ing).persist(StorageLevel.MEMORY_AND_DISK)
        leidas = b.count()
        if "_fecha_ingesta" in b.columns:
            ultima_ingesta = b.agg(F.max("_fecha_ingesta")).collect()[0][0]
        print(f"Leídas: {leidas:,}")

        prop_bronce = (spark.table("secop_bronze.raw_proponentes_hist")
                       .unionByName(L.leer_ingesta(spark, BUCKET, "proponentes-procesos"), allowMissingColumns=True))
        compartidos = L.nits_compartidos(prop_bronce).cache()
        nits_entidad = (spark.table(TABLA_PROC).select(F.col("nit_entidad").alias("nit"))
                        .filter(F.col("nit").isNotNull()).distinct().cache())
        print(f"NIT compartidos: {compartidos.count():,} · NIT de entidades compradoras: {nits_entidad.count():,}")

        validos, rechazados = construir(b, spark.table(TABLA_PROP), nits_entidad, compartidos, sal, id_corrida)
        validos = ajustar_a_tabla(spark, validos, TABLA).persist(StorageLevel.MEMORY_AND_DISK)
        rechazados = ajustar_a_tabla(spark, rechazados, TABLA_RECH).persist(StorageLevel.MEMORY_AND_DISK)

        n_val = validos.count()
        por_motivo = {r["motivo"]: r["count"] for r in rechazados.groupBy("motivo").count().collect()}
        n_rech = sum(por_motivo.values())
        cuadre = leidas == n_val + n_rech
        print(f"Válidas: {n_val:,} | Rechazadas: {n_rech:,} | Cuadre: {cuadre}")
        for m, n in sorted(por_motivo.items()):
            print(f"   {m}: {n:,}")
        print("Tipos:", {r["tipo_proveedor"]: r["count"] for r in validos.groupBy("tipo_proveedor").count().collect()})
        if not cuadre:
            raise RuntimeError(f"El cuadre no cierra: {leidas} != {n_val} + {n_rech}")

        validos.writeTo(TABLA).overwrite(F.lit(True))
        rechazados.writeTo(TABLA_RECH).overwrite(F.lit(True))
        snap = spark.sql(f"SELECT snapshot_id FROM {TABLA}.snapshots ORDER BY committed_at DESC LIMIT 1").collect()[0][0]
        estado, error = "exito", None
    except Exception as e:
        estado, error = "fallo", str(e)[:1000]

    fila = spark.createDataFrame([(
        id_corrida, args["JOB_NAME"], "secop_silver.proveedores",
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
