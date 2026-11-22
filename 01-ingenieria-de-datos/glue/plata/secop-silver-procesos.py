"""
Fase E · Paso E3 · Job de plata: procesos

Construye secop_silver.procesos y secop_silver.procesos_rechazados a partir de bronce.

Flujo (un solo camino para las dos fuentes, para que nunca haya diferencias entre ellas):
  1. Lee el histórico (Parquet, secop_bronze.raw_procesos_hist) y la ingesta diaria (JSON en S3).
  2. Las UNE en un solo DataFrame con las mismas columnas de bronce.
  3. Aplica las mismas funciones de limpieza (limpieza_secop) y las reglas en orden:
       R1 fecha_publicacion_invalida · R2 no_publicado · R3 fuera_de_alcance · R4 version_anterior
       R5 fase_de_otro_proceso: en un portafolio con un proceso adjudicado (adjudicado='Si' o
          Seleccionado), los demás procesos no cancelados son fases de la misma compra
          (casi todos quedan en 'Evaluación' y no tienen proponentes). Una fila por compra real.
  4. Escribe válidos y rechazados (reemplaza el contenido: la carga es reproducible).
  5. Verifica el cuadre (leídas = válidas + rechazadas) y lo registra en secop_control.control_corridas.

El ganador y el estado definitivos se completan en el paso E6 (necesitan proponentes y contratos).
En este paso: ganador_codigo y ganador_proveedor_key salen del propio proceso, ganador_fuente
queda nulo y el estado es preliminar.

Parámetros del job:
  --datalake-formats  iceberg
  --extra-py-files    s3://proyecto-integrador-bucket-01/scripts/limpieza_secop.py
"""
import sys
from datetime import datetime, timezone

from pyspark.sql import Window
from pyspark.sql import functions as F

import limpieza_secop as L

BUCKET = "proyecto-integrador-bucket-01"
CAT = "glue_catalog"
TABLA = f"{CAT}.secop_silver.procesos"
TABLA_RECH = f"{CAT}.secop_silver.procesos_rechazados"
TABLA_CONTROL = f"{CAT}.secop_control.control_corridas"

# Alcance: lista explícita de modalidades (Q13, Q15, Q17 del informe)
MODALIDADES = [
    "Mínima cuantía",
    "Selección Abreviada de Menor Cuantía",
    "Selección abreviada subasta inversa",
    "Seleccion Abreviada Menor Cuantia Sin Manifestacion Interes",
    "Contratación régimen especial (con ofertas)",
    "Concurso de méritos abierto",
    "Concurso de méritos con precalificación",
    "Licitación pública",
    "Licitación pública Obra Publica",
    "Licitación Pública Acuerdo Marco de Precios",
]
NO_PUBLICADO = ["Borrador", "Aprobado", "En aprobación"]
CANCELADO = ["Cancelado", "Suspendido"]
DIAS_VIGENCIA_ABIERTO = 60

# Columnas de bronce que no van dentro de registro_original de los rechazados
COLS_TECNICAS = ["fuente", "sys_updated_at_txt", "_fecha_ingesta"]


# ----------------------------------------------------------------------------- 1 y 2. Bronce unificado
def bronce_unificado(hist, ing):
    """Histórico + ingesta con las mismas columnas de bronce (todo texto)."""
    h = (hist.withColumn("fuente", F.lit("historico"))
             .withColumn("sys_updated_at_txt", F.lit(None).cast("string"))
             .withColumn("_fecha_ingesta", F.lit(None).cast("string")))
    i = (ing.withColumnRenamed(":updated_at", "sys_updated_at_txt")
            .withColumnRenamed("fecha", "_fecha_ingesta")
            .drop(":id", ":created_at")
            .withColumn("fuente", F.lit("ingesta")))
    return h.unionByName(i, allowMissingColumns=True)


# ----------------------------------------------------------------------------- 3. Limpieza y reglas
def construir(b, sal: str, id_corrida: str):
    """Devuelve (validos, rechazados) a partir del bronce unificado."""
    columnas_bronce = [c for c in b.columns if c not in COLS_TECNICAS]

    t = (b
         .withColumn("id_proceso", L.centinela_a_nulo("id_del_proceso"))
         .withColumn("fecha_publicacion", L.fecha("fecha_de_publicacion_del"))
         .withColumn("_fecha_ultima", L.fecha("fecha_de_ultima_publicaci"))
         .withColumn("estado_origen", L.centinela_a_nulo("estado_del_procedimiento"))
         .withColumn("adjudicado_origen", L.centinela_a_nulo("adjudicado"))
         .withColumn("apertura_origen", L.centinela_a_nulo("estado_de_apertura_del_proceso"))
         .withColumn("modalidad", L.centinela_a_nulo("modalidad_de_contratacion"))
         .withColumn("sys_updated_at", L.utc_a_colombia("sys_updated_at_txt"))
         .withColumn("_fecha_adj", L.fecha("fecha_adjudicacion"))
         .withColumn("valor_adjudicacion", L.dinero("valor_total_adjudicacion")))

    # R1 a R3: la primera regla que falla define el motivo
    t = (t.withColumn("regla",
                      F.when(F.col("id_proceso").isNull() | F.col("fecha_publicacion").isNull(), "R1")
                       .when(F.col("estado_origen").isin(NO_PUBLICADO), "R2")
                       .when(~F.coalesce(F.col("modalidad").isin(MODALIDADES), F.lit(False)), "R3"))
          .withColumn("motivo",
                      F.when(F.col("regla") == "R1", "fecha_publicacion_invalida")
                       .when(F.col("regla") == "R2", "no_publicado")
                       .when(F.col("regla") == "R3", "fuera_de_alcance"))
          .withColumn("detalle",
                      F.when(F.col("regla") == "R1",
                             F.when(F.col("id_proceso").isNull(), F.lit("id_del_proceso nulo"))
                              .otherwise(F.concat(F.lit("fecha recibida: "),
                                                  F.coalesce(F.col("fecha_de_publicacion_del"), F.lit("nula")))))
                       .when(F.col("regla") == "R2", F.concat(F.lit("estado: "), F.col("estado_origen")))
                       .when(F.col("regla") == "R3", F.concat(F.lit("modalidad: "),
                                                             F.coalesce(F.col("modalidad"), F.lit("nula"))))))

    # R4: una fila por proceso. Gana la ingesta; luego la versión más reciente.
    orden = Window.partitionBy("id_proceso").orderBy(
        F.when(F.col("fuente") == "ingesta", 0).otherwise(1),
        F.col("sys_updated_at").desc_nulls_last(),
        F.col("_fecha_ultima").desc_nulls_last(),
        F.col("adjudicado_origen").desc_nulls_last(),   # 'Si' antes que 'No'
        F.col("_fecha_adj").desc_nulls_last(),
        F.col("valor_adjudicacion").desc_nulls_last(),
        F.col("id_del_portafolio").asc_nulls_last(),     # desempate determinístico
    )
    pasan = t.filter(F.col("regla").isNull()).withColumn("_n", F.row_number().over(orden))
    unicos = pasan.filter(F.col("_n") == 1)

    # R5: en un portafolio con un proceso adjudicado, los demás (no cancelados) son fases de la misma compra
    es_adj_origen = (F.col("adjudicado_origen") == "Si") | (F.col("estado_origen") == "Seleccionado")
    por_portafolio = Window.partitionBy("id_del_portafolio")
    unicos = (unicos.withColumn("_adj_origen", F.coalesce(es_adj_origen, F.lit(False)))
                    .withColumn("_portafolio_adj",
                                F.when(F.col("id_del_portafolio").isNotNull(),
                                       F.max(F.col("_adj_origen").cast("int")).over(por_portafolio))
                                 .otherwise(F.lit(0))))
    es_fase = ((F.col("_portafolio_adj") == 1) & ~F.col("_adj_origen")
               & ~F.coalesce(F.col("estado_origen").isin(CANCELADO), F.lit(False)))
    validos_raw = unicos.filter(~es_fase).drop("_adj_origen", "_portafolio_adj")
    fases = (unicos.filter(es_fase).drop("_adj_origen", "_portafolio_adj")
             .withColumn("regla", F.lit("R5")).withColumn("motivo", F.lit("fase_de_otro_proceso"))
             .withColumn("detalle", F.concat(F.lit("portafolio "), F.col("id_del_portafolio"),
                                             F.lit(" ya tiene un proceso adjudicado; estado: "),
                                             F.coalesce(F.col("estado_origen"), F.lit("nulo")))))
    version_anterior = (pasan.filter(F.col("_n") > 1)
                        .withColumn("regla", F.lit("R4"))
                        .withColumn("motivo", F.lit("version_anterior"))
                        .withColumn("detalle", F.concat(F.lit("versión reemplazada, fuente "), F.col("fuente"))))

    # ----- Rechazados
    json_bronce = L.registro_json(b.select(*columnas_bronce), sal,
                                  columnas_hash=["nit_del_proveedor_adjudicado"],
                                  columnas_excluir=["nombre_del_proveedor"])
    rech_base = (t.filter(F.col("regla").isNotNull())
                 .unionByName(version_anterior.drop("_n"))
                 .unionByName(fases.drop("_n")))
    rechazados = rech_base.select(
        "id_proceso", "regla", "motivo", "detalle",
        F.when(F.col("motivo") == "fuera_de_alcance", F.lit(None).cast("string"))
         .otherwise(json_bronce).alias("registro_original"),
        "fuente", "sys_updated_at",
        F.lit(id_corrida).alias("id_corrida"),
        L.ahora_colombia().alias("fecha_carga"),
    )

    # ----- Válidos: columnas de plata
    v = validos_raw
    estado = (F.when(F.col("estado_origen").isin(CANCELADO), "cancelado")
               .when((F.col("adjudicado_origen") == "Si") | (F.col("estado_origen") == "Seleccionado"), "adjudicado")
               .when((F.col("apertura_origen") == "Abierto")
                     & (F.col("fecha_publicacion") >= F.date_sub(F.current_date(), DIAS_VIGENCIA_ABIERTO)),
                     "abierto")
               .otherwise("cerrado_sin_adjudicar"))
    v = v.withColumn("estado", estado)
    respaldo = (F.col("estado") == "adjudicado") & F.col("_fecha_adj").isNull()
    unspsc = L.unspsc("codigo_principal_de_categoria")

    # Corrección 2.6 · limpiezas del EDA
    # Texto: nombre del procedimiento + descripción (si el nombre no repite la descripción)
    desc = L.centinela_a_nulo("descripci_n_del_procedimiento")
    if "nombre_del_procedimiento" in v.columns:
        nombre = L.centinela_a_nulo("nombre_del_procedimiento")
        texto = (F.when(nombre.isNull() | (F.lower(nombre) == F.lower(desc)), desc)
                  .when(desc.isNull(), nombre)
                  .otherwise(F.concat_ws(" ", nombre, desc)))
    else:
        texto = desc
    # Duración: 0 días o más de 30 años no es real
    dur = L.duracion_dias("duracion", "unidad_de_duracion")
    # Fecha límite de ofertas: antes de publicar o más de un año después no es real
    limite = L.fecha("fecha_de_recepcion_de")
    limite_ok = F.when((limite >= F.col("fecha_publicacion"))
                       & (limite <= F.date_add(F.col("fecha_publicacion"), 365)), limite)
    v = (v.withColumn("_texto", texto)
          .withColumn("_dur", F.when((dur >= 1) & (dur <= 10950), dur))
          .withColumn("_limite", limite_ok)
          .withColumn("_precio", L.dinero("precio_base")))

    validos = v.select(
        "id_proceso",
        L.centinela_a_nulo("id_del_portafolio").alias("id_portafolio"),
        L.centinela_a_nulo("referencia_del_proceso").alias("referencia_proceso"),
        L.nit_normalizado("nit_entidad").alias("nit_entidad"),
        L.centinela_a_nulo("entidad").alias("nombre_entidad"),
        L.centinela_a_nulo("departamento_entidad").alias("departamento_entidad"),
        L.centinela_a_nulo("ciudad_entidad").alias("ciudad_entidad"),
        L.centinela_a_nulo("ordenentidad").alias("orden_entidad"),
        "modalidad",
        L.centinela_a_nulo("tipo_de_contrato").alias("tipo_contrato"),
        L.centinela_a_nulo("descripci_n_del_procedimiento").alias("descripcion"),
        L.texto_limpio("_texto").alias("descripcion_limpia"),
        L.centinela_a_nulo("urlproceso").alias("url_proceso"),
        F.col("_precio").alias("precio_base"),
        F.coalesce(F.col("_precio") > 100_000_000_000, F.lit(False)).alias("precio_atipico"),
        F.col("_dur").alias("duracion_dias"),
        unspsc.alias("unspsc"),
        L.unspsc_nivel(unspsc, 2).alias("unspsc_segmento"),
        L.unspsc_nivel(unspsc, 4).alias("unspsc_familia"),
        L.unspsc_nivel(unspsc, 6).alias("unspsc_clase"),
        L.entero("numero_de_lotes").alias("numero_lotes"),
        "fecha_publicacion",
        F.col("_limite").alias("fecha_limite_ofertas"),
        F.datediff("_limite", "fecha_publicacion").alias("dias_para_ofertar"),
        F.when(respaldo, F.col("fecha_publicacion")).otherwise(F.col("_fecha_adj")).alias("fecha_adjudicacion"),
        respaldo.alias("fecha_adjudicacion_es_respaldo"),
        "estado", "estado_origen", "adjudicado_origen", "apertura_origen",
        L.codigo_proveedor("codigoproveedor").alias("ganador_codigo"),
        L.proveedor_key(L.nit_confiable("nit_del_proveedor_adjudicado"), sal).alias("ganador_proveedor_key"),
        F.lit(None).cast("string").alias("ganador_fuente"),
        "valor_adjudicacion",
        F.coalesce(F.col("valor_adjudicacion") > 1.1 * F.col("_precio"), F.lit(False)).alias("valor_atipico"),
        F.lit(None).cast("string").alias("sector_entidad"),   # lo llena E6 desde contratos
        F.lit(None).cast("int").alias("n_proponentes"),       # lo llena E6
        F.lit(None).cast("int").alias("n_ganadores"),         # lo llena E6
        L.entero("respuestas_al_procedimiento").alias("respuestas_al_procedimiento"),
        L.entero("proveedores_unicos_con").alias("proveedores_unicos"),
        L.entero("visualizaciones_del").alias("visualizaciones"),
        "fuente", "sys_updated_at",
        L.ahora_colombia().alias("fecha_carga"),
    )

    # Departamento de la entidad: si falta, el más frecuente de la misma entidad (una alcaldía no se muda)
    moda = (validos.filter(F.col("nit_entidad").isNotNull() & F.col("departamento_entidad").isNotNull())
            .groupBy("nit_entidad", "departamento_entidad").count()
            .withColumn("_r", F.row_number().over(
                Window.partitionBy("nit_entidad").orderBy(F.desc("count"), "departamento_entidad")))
            .filter("_r = 1")
            .select("nit_entidad", F.col("departamento_entidad").alias("_depto_moda")))
    validos = (validos.join(moda, "nit_entidad", "left")
               .withColumn("departamento_entidad", F.coalesce("departamento_entidad", "_depto_moda"))
               .drop("_depto_moda"))

    # Ciudad de la entidad: si falta, la de sus otros procesos, solo si la entidad tiene una única
    # ciudad (las que tienen varias sedes no se adivinan). Corrección de David, 6-nov.
    ciudad_unica = (validos.filter(F.col("nit_entidad").isNotNull() & F.col("ciudad_entidad").isNotNull())
                    .groupBy("nit_entidad")
                    .agg(F.countDistinct("ciudad_entidad").alias("_n_ciudades"),
                         F.first("ciudad_entidad").alias("_ciudad_unica"))
                    .filter("_n_ciudades = 1").select("nit_entidad", "_ciudad_unica"))
    validos = (validos.join(ciudad_unica, "nit_entidad", "left")
               .withColumn("ciudad_entidad", F.coalesce("ciudad_entidad", "_ciudad_unica"))
               .drop("_ciudad_unica"))
    return validos, rechazados


def ajustar_a_tabla(spark, df, tabla):
    """Selecciona y convierte las columnas al esquema exacto de la tabla destino."""
    esquema = spark.table(tabla).schema
    return df.select(*[F.col(f.name).cast(f.dataType).alias(f.name) for f in esquema.fields])


# ----------------------------------------------------------------------------- 4 y 5. Glue
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
    id_corrida = "plata-procesos-" + inicio.strftime("%Y%m%d-%H%M%S")
    sal = boto3.client("ssm").get_parameter(Name="/secop/hash-salt", WithDecryption=True)["Parameter"]["Value"]
    print(f"== {id_corrida}")

    try:
        hist = spark.table("secop_bronze.raw_procesos_hist")
        ing = L.leer_ingesta(spark, BUCKET, "procesos-contratacion")
        b = bronce_unificado(hist, ing).persist(StorageLevel.MEMORY_AND_DISK)
        leidas = b.count()
        ultima_ingesta = b.agg(F.max("_fecha_ingesta")).collect()[0][0]
        print(f"Leídas: {leidas:,} (última partición de ingesta: {ultima_ingesta})")

        validos, rechazados = construir(b, sal, id_corrida)
        validos = ajustar_a_tabla(spark, validos, TABLA).persist(StorageLevel.MEMORY_AND_DISK)
        rechazados = ajustar_a_tabla(spark, rechazados, TABLA_RECH).persist(StorageLevel.MEMORY_AND_DISK)

        n_val = validos.count()
        por_motivo = {r["motivo"]: r["count"] for r in rechazados.groupBy("motivo").count().collect()}
        n_rech = sum(por_motivo.values())
        cuadre = leidas == n_val + n_rech
        print(f"Válidas: {n_val:,} | Rechazadas: {n_rech:,} | Cuadre: {cuadre}")
        for m, n in sorted(por_motivo.items()):
            print(f"   {m}: {n:,}")
        print("Estados:", {r["estado"]: r["count"] for r in validos.groupBy("estado").count().collect()})
        if not cuadre:
            raise RuntimeError(f"El cuadre no cierra: {leidas} != {n_val} + {n_rech}")

        validos.writeTo(TABLA).overwrite(F.lit(True))
        rechazados.writeTo(TABLA_RECH).overwrite(F.lit(True))
        snap = spark.sql(f"SELECT snapshot_id FROM {TABLA}.snapshots "
                         f"ORDER BY committed_at DESC LIMIT 1").collect()[0][0]
        estado, error = "exito", None
    except Exception as e:
        n_val = n_rech = snap = None
        por_motivo, cuadre, ultima_ingesta = {}, False, None
        leidas = locals().get("leidas")
        estado, error = "fallo", str(e)[:1000]

    fila = spark.createDataFrame([(
        id_corrida, args["JOB_NAME"], "secop_silver.procesos",
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
