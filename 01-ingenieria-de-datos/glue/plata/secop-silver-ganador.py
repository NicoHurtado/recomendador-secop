"""
Fase E · Paso E6 · Job de plata: ganador y estado final de los procesos

Completa secop_silver.procesos con la resolución del ganador. Se corre después de E3, E4 y E5,
porque necesita las tres tablas de plata:

  1. codigo    el código de proveedor del proceso está entre los proponentes del mismo proceso
  2. nit       el NIT del adjudicado (con hash) es la llave de un proponente del mismo proceso
  3. contrato  el proveedor del contrato cuyo proceso_de_compra es el id_portafolio del proceso.
               Solo se asigna si ese proveedor fue proponente del proceso, o si el proceso es el más
               reciente de su portafolio (un contrato nunca resuelve varios procesos).
               Si hay varios contratos (lotes), gana uno que esté entre los proponentes, luego el de
               mayor valor
  Si ninguna vía funciona: ganador_fuente y ganador_proveedor_key quedan nulos.

Estado final: un proceso no cancelado con ganador resuelto pasa a 'adjudicado'
(estado_origen y adjudicado_origen conservan los valores originales). Si no tenía fecha de
adjudicación, se usa la primera fecha de firma de sus contratos, o la de publicación,
marcada como respaldo.

Además (correcciones de David, 3-nov-2026):
  proponentes.es_ganador   ganador principal o firmante de un contrato del mismo portafolio (lotes)
  procesos.n_ganadores, procesos.n_proponentes, procesos.sector_entidad
E6 reescribe procesos y proponentes y deja una fila en control_corridas por cada tabla, con su
snapshot_id: para entrenar, los dos snapshots se toman de las filas de este job.

Es un paso de enriquecimiento, no de limpieza: no rechaza filas.
Orden obligatorio del pipeline: E3 procesos -> E4 proponentes -> E5 contratos -> E6 ganador.
Si procesos ya fue enriquecido, el job se detiene: hay que correr primero E3.
Parámetros del job:  --datalake-formats iceberg  ·  Python library path: limpieza_secop.py
"""
import sys
from datetime import datetime, timezone

from pyspark.sql import Window
from pyspark.sql import functions as F

import limpieza_secop as L

BUCKET = "proyecto-integrador-bucket-01"
CAT = "glue_catalog"
TABLA = f"{CAT}.secop_silver.procesos"
TABLA_PROP = f"{CAT}.secop_silver.proponentes"
TABLA_CONTR = f"{CAT}.secop_silver.contratos"
TABLA_CONTROL = f"{CAT}.secop_control.control_corridas"


def resolver(procesos, proponentes, contratos):
    """Devuelve procesos con estado, ganador_* y fecha de adjudicación finales (mismas columnas)."""
    prop = proponentes.select("id_proceso", "codigo_proveedor", "proveedor_key").dropna(subset=["proveedor_key"])

    # Vía 1: código del proceso entre los proponentes del mismo proceso
    via_codigo = (prop.filter(F.col("codigo_proveedor").isNotNull())
                  .groupBy("id_proceso", F.col("codigo_proveedor").alias("ganador_codigo"))
                  .agg(F.first("proveedor_key").alias("_k_codigo")))

    # Vía 2: llave del NIT adjudicado entre las llaves de los proponentes del mismo proceso
    via_nit = (prop.select("id_proceso", F.col("proveedor_key").alias("ganador_proveedor_key"),
                           F.col("codigo_proveedor").alias("_c_nit"))
               .groupBy("id_proceso", "ganador_proveedor_key").agg(F.first("_c_nit").alias("_c_nit"))
               .withColumn("_k_nit", F.col("ganador_proveedor_key")))

    # Vía 3: contrato del portafolio. Preferir proveedor que esté entre los proponentes del proceso.
    c = (contratos.filter(F.col("id_portafolio").isNotNull() & F.col("proveedor_key").isNotNull())
         .select("id_portafolio", "id_contrato", "proveedor_key", "codigo_proveedor", "valor_contrato", "fecha_firma"))
    # Un portafolio puede tener varios procesos. El contrato se asigna al proceso donde su proveedor
    # fue proponente, o si no, solo al proceso más reciente del portafolio (nunca a todos).
    reciente = Window.partitionBy("id_portafolio").orderBy(
        F.col("fecha_publicacion").desc_nulls_last(), F.col("id_proceso").desc())
    p_port = (procesos.select("id_proceso", "id_portafolio", "fecha_publicacion")
              .filter(F.col("id_portafolio").isNotNull())
              .withColumn("_mas_reciente", F.row_number().over(reciente) == 1)
              .drop("fecha_publicacion"))
    cand = (c.join(p_port, "id_portafolio")
             .join(prop.select("id_proceso", "proveedor_key").distinct().withColumn("_es_prop", F.lit(True)),
                   ["id_proceso", "proveedor_key"], "left")
             .filter(F.col("_es_prop").isNotNull() | F.col("_mas_reciente")))
    orden = Window.partitionBy("id_proceso").orderBy(
        F.coalesce(F.col("_es_prop"), F.lit(False)).desc(),
        F.col("valor_contrato").desc_nulls_last(),
        F.col("id_contrato"))
    primera_firma = cand.groupBy("id_proceso").agg(F.min("fecha_firma").alias("_primera_firma"))
    via_contrato = (cand.withColumn("_n", F.row_number().over(orden)).filter("_n = 1")
                    .select("id_proceso", F.col("proveedor_key").alias("_k_contrato"),
                            F.col("codigo_proveedor").alias("_c_contrato"))
                    .join(primera_firma, "id_proceso"))

    t = (procesos
         .join(via_codigo, ["id_proceso", "ganador_codigo"], "left")
         .join(via_nit, ["id_proceso", "ganador_proveedor_key"], "left")
         .join(via_contrato, "id_proceso", "left"))

    fuente = (F.when(F.col("_k_codigo").isNotNull(), "codigo")
               .when(F.col("_k_nit").isNotNull(), "nit")
               .when(F.col("_k_contrato").isNotNull(), "contrato"))
    t = (t.withColumn("_fuente", fuente)
          .withColumn("_key", F.coalesce("_k_codigo", "_k_nit", "_k_contrato"))
          .withColumn("_cod", F.when(F.col("_fuente") == "codigo", F.col("ganador_codigo"))
                               .when(F.col("_fuente") == "nit", F.coalesce("_c_nit", "ganador_codigo"))
                               .when(F.col("_fuente") == "contrato", F.col("_c_contrato"))
                               .otherwise(F.col("ganador_codigo"))))

    promovido = (F.col("estado") != "adjudicado") & (F.col("estado") != "cancelado") & F.col("_fuente").isNotNull()
    estado_final = F.when(promovido, F.lit("adjudicado")).otherwise(F.col("estado"))
    sin_fecha = promovido & F.col("fecha_adjudicacion").isNull()

    return (t.withColumn("fecha_adjudicacion_es_respaldo",
                         F.when(sin_fecha, F.lit(True)).otherwise(F.col("fecha_adjudicacion_es_respaldo")))
             .withColumn("fecha_adjudicacion",
                         F.when(sin_fecha, F.coalesce(F.to_date("_primera_firma"), F.col("fecha_publicacion")))
                          .otherwise(F.col("fecha_adjudicacion")))
             .withColumn("_promovido", promovido)
             .withColumn("estado", estado_final)
             .withColumn("ganador_fuente", F.col("_fuente"))
             .withColumn("ganador_proveedor_key", F.col("_key"))
             .withColumn("ganador_codigo", F.col("_cod")))


def completar(procesos_r, proponentes, contratos, proveedores=None):
    """
    Correcciones 2.2, 2.3 y 2.6 (sector). Recibe procesos ya resueltos y devuelve (procesos, proponentes):
      proponentes.es_ganador   adjudicado: true si es el ganador principal o si firmó un contrato del
                               mismo portafolio (lotes); false si no. Nulo si el proceso no está adjudicado.
      procesos.n_ganadores     proponentes con es_ganador = true (solo adjudicados)
      procesos.n_proponentes   participaciones del proceso (0 si no tiene)
      procesos.sector_entidad  sector más frecuente de la entidad en contratos
    """
    con_contrato = (contratos.filter(F.col("id_portafolio").isNotNull() & F.col("proveedor_key").isNotNull())
                    .select("id_portafolio", "proveedor_key").distinct()
                    .withColumn("_tiene_contrato", F.lit(True)))
    info = procesos_r.select("id_proceso", "id_portafolio", "estado",
                             F.col("ganador_proveedor_key").alias("_gk"))
    gana = (F.coalesce(F.col("proveedor_key") == F.col("_gk"), F.lit(False))
            | F.col("_tiene_contrato").isNotNull())
    prop = (proponentes.drop("es_ganador")
            .join(info, "id_proceso", "left")
            .join(con_contrato, ["id_portafolio", "proveedor_key"], "left")
            .withColumn("es_ganador", F.when(F.col("estado") == "adjudicado", gana))
            .drop("id_portafolio", "estado", "_gk", "_tiene_contrato"))
    # tipo_proveedor (2.4): el del registro; si no está, el provisional de E4; si no, no_registrado
    if proveedores is not None:
        prop = (prop.join(proveedores.select("proveedor_key", F.col("tipo_proveedor").alias("_tipo_registro")),
                          "proveedor_key", "left")
                    .withColumn("tipo_proveedor", F.coalesce("_tipo_registro", "tipo_proveedor", F.lit("no_registrado")))
                    .drop("_tipo_registro"))

    conteos = prop.groupBy("id_proceso").agg(
        F.count("*").alias("_n_prop"),
        F.sum(F.when(F.col("es_ganador"), 1).otherwise(0)).alias("_n_gan"))
    sector_limpio = F.when(~F.lower(F.col("sector")).rlike(r"^no (aplica|pertenece|definido)"), F.col("sector"))
    sector = (contratos.filter(F.col("nit_entidad").isNotNull())
              .withColumn("_sector", sector_limpio).filter(F.col("_sector").isNotNull())
              .groupBy("nit_entidad", "_sector").count()
              .withColumn("_r", F.row_number().over(
                  Window.partitionBy("nit_entidad").orderBy(F.desc("count"), "_sector")))
              .filter("_r = 1").select("nit_entidad", F.col("_sector").alias("_sector_moda")))
    proc = (procesos_r.join(conteos, "id_proceso", "left")
            .join(F.broadcast(sector), "nit_entidad", "left")
            .withColumn("n_proponentes", F.coalesce("_n_prop", F.lit(0)).cast("int"))
            .withColumn("n_ganadores", F.when(F.col("estado") == "adjudicado",
                                              F.coalesce("_n_gan", F.lit(0))).cast("int"))
            .withColumn("sector_entidad", F.col("_sector_moda"))
            .drop("_n_prop", "_n_gan", "_sector_moda"))
    return proc, prop


def ajustar_a_tabla(spark, df, tabla):
    esquema = spark.table(tabla).schema
    faltan = [f.name for f in esquema.fields if f.name not in df.columns]
    if faltan:
        raise ValueError(f"{tabla}: faltan columnas en el resultado: {faltan}")
    return df.select(*[F.col(f.name).cast(f.dataType).alias(f.name) for f in esquema.fields])


def main():
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
    id_corrida = "plata-ganador-" + inicio.strftime("%Y%m%d-%H%M%S")
    print(f"== {id_corrida}")
    leidas = n_val = snap = snap_prop = n_prop_despues = None
    cuadre = False

    try:
        procesos = spark.table(TABLA)
        ya = procesos.filter(F.col("ganador_fuente").isNotNull()).limit(1).count()
        if ya:
            raise RuntimeError("secop_silver.procesos ya tiene ganador_fuente: corra primero "
                               "secop-silver-procesos (E3) y luego este job.")
        procesos = procesos.persist(StorageLevel.MEMORY_AND_DISK)
        leidas = procesos.count()
        antes = {r["estado"]: r["count"] for r in procesos.groupBy("estado").count().collect()}

        proponentes = spark.table(TABLA_PROP).persist(StorageLevel.MEMORY_AND_DISK)
        n_prop_antes = proponentes.count()
        contratos = spark.table(TABLA_CONTR)
        r0 = resolver(procesos, proponentes, contratos).persist(StorageLevel.MEMORY_AND_DISK)
        r, prop = completar(r0, proponentes, contratos, spark.table(f"{CAT}.secop_silver.proveedores"))
        r = r.persist(StorageLevel.MEMORY_AND_DISK)
        prop = prop.persist(StorageLevel.MEMORY_AND_DISK)
        n_prop_despues = prop.count()
        n_val = r.count()
        cuadre = leidas == n_val
        despues = {x["estado"]: x["count"] for x in r.groupBy("estado").count().collect()}
        fuentes = {str(x["ganador_fuente"]): x["count"] for x in
                   r.filter("estado = 'adjudicado'").groupBy("ganador_fuente").count().collect()}
        promovidos = r.filter("_promovido").count()
        print(f"Procesos: {leidas:,} -> {n_val:,} | Cuadre: {cuadre}")
        print(f"Estados antes:   {antes}")
        print(f"Estados después: {despues} (promovidos a adjudicado: {promovidos:,})")
        print(f"Adjudicados por ganador_fuente: {fuentes}")
        multi = r.filter("n_ganadores > 1").count()
        print(f"Proponentes: {n_prop_antes:,} -> {n_prop_despues:,} | procesos con varios ganadores: {multi:,}")
        if not cuadre:
            raise RuntimeError(f"El join duplicó o perdió procesos: {leidas} != {n_val}")
        if n_prop_antes != n_prop_despues:
            raise RuntimeError(f"El join duplicó o perdió proponentes: {n_prop_antes} != {n_prop_despues}")

        ajustar_a_tabla(spark, r, TABLA).writeTo(TABLA).overwrite(F.lit(True))
        ajustar_a_tabla(spark, prop, TABLA_PROP).writeTo(TABLA_PROP).overwrite(F.lit(True))
        snap = spark.sql(f"SELECT snapshot_id FROM {TABLA}.snapshots "
                         f"ORDER BY committed_at DESC LIMIT 1").collect()[0][0]
        snap_prop = spark.sql(f"SELECT snapshot_id FROM {TABLA_PROP}.snapshots "
                              f"ORDER BY committed_at DESC LIMIT 1").collect()[0][0]
        estado, error = "exito", None
    except Exception as e:
        estado, error = "fallo", str(e)[:1000]

    fin = datetime.now(timezone.utc).replace(tzinfo=None)
    fila = spark.createDataFrame([
        (id_corrida, args["JOB_NAME"], "secop_silver.procesos", inicio.replace(tzinfo=None), fin,
         estado, leidas, n_val, 0 if n_val is not None else None, {}, cuadre, None, snap, error),
        (id_corrida, args["JOB_NAME"], "secop_silver.proponentes", inicio.replace(tzinfo=None), fin,
         estado, n_prop_despues, n_prop_despues, 0 if n_prop_despues is not None else None, {}, cuadre, None,
         snap_prop, error)],
        "id_corrida string, job string, tabla string, inicio timestamp, fin timestamp, estado string, "
        "filas_leidas long, filas_validas long, filas_rechazadas long, rechazos_por_motivo map<string,long>, "
        "cuadre_ok boolean, ultima_fecha_ingesta date, snapshot_id long, mensaje_error string")
    ajustar_a_tabla(spark, fila, TABLA_CONTROL).writeTo(TABLA_CONTROL).append()
    print(f"== Registrado en control_corridas: {estado}")
    if estado != "exito":
        raise RuntimeError(error)


if __name__ == "__main__":
    main()
