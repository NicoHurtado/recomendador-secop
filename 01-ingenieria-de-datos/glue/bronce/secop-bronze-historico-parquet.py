"""
Job de Glue (Spark): bronce histórico CSV -> bronce histórico Parquet.

Qué hace, para cada dataset:
  1. Lee el CSV exportado de bronze/<carpeta>/carga-historica/ (todo como texto).
  2. Renombra las columnas visibles ("ID del Proceso") a los nombres técnicos de la API
     ("id_del_proceso"), usando control/esquemas/<carpeta>.json, para que el histórico
     y la ingesta diaria (JSON) hablen el mismo idioma.
  3. Separa las filas que Spark no pudo interpretar (_corrupt_record).
  4. Escribe las filas buenas en Parquet en bronze/<carpeta>/historico-parquet/ y registra
     la tabla secop_bronze.raw_<tabla>_hist en el Glue Data Catalog (Athena la ve sola).
  5. Escribe las corruptas en bronze/<carpeta>/historico-corruptas/ para auditarlas.
  6. Deja un resumen (filas leídas, buenas, corruptas) en control/historico/.

No limpia ni tipa nada: sigue siendo bronce (esquema al leer, todo string).
Solo cambia el formato físico (CSV -> Parquet) y los nombres de las columnas.
El CSV original no se toca.
"""
import json
import re
import sys
import time
import unicodedata

import boto3
from awsglue.context import GlueContext
from awsglue.utils import getResolvedOptions
from pyspark import StorageLevel
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.types import StringType, StructField, StructType

args = getResolvedOptions(sys.argv, ["JOB_NAME"])
sc = SparkContext.getOrCreate()
glue = GlueContext(sc)
spark = glue.spark_session

BUCKET = "proyecto-integrador-bucket-01"
# carpeta en bronze/ -> tabla de bronce histórica en Athena
DATASETS = {
    "proponentes-procesos": "raw_proponentes_hist",
    "contratos-electronicos": "raw_contratos_hist",
    "procesos-contratacion": "raw_procesos_hist",
    "proveedores-registrados": "raw_proveedores_hist",
}
# Parámetro opcional --datasets (carpetas separadas por coma) para recargar solo algunas.
# Sin el parámetro, procesa todos.
if "--datasets" in sys.argv:
    elegidos = [d.strip() for d in getResolvedOptions(sys.argv, ["datasets"])["datasets"].split(",")]
    desconocidos = [d for d in elegidos if d not in DATASETS]
    if desconocidos:
        raise ValueError(f"--datasets no reconocidos: {desconocidos}. Válidos: {list(DATASETS)}")
    DATASETS = {d: DATASETS[d] for d in elegidos}
print(f"== Datasets a procesar: {list(DATASETS)}")
OPC = {"header": True, "multiLine": True, "quote": '"', "escape": '"', "encoding": "UTF-8"}
PARTICIONES = 64  # reparte el archivo leído por una sola tarea entre todos los workers

s3 = boto3.client("s3")


def limpio(nombre):
    """'Fecha de Publicación del Proceso' -> 'fecha_de_publicacion_del_proceso'."""
    n = unicodedata.normalize("NFKD", nombre.lstrip("﻿"))
    n = "".join(ch for ch in n if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]+", "_", n).strip("_")


def nombres_tecnicos(carpeta, encabezados):
    cuerpo = s3.get_object(Bucket=BUCKET, Key=f"control/esquemas/{carpeta}.json")["Body"].read()
    columnas = json.loads(cuerpo)
    por_nombre = {c["name"]: c["fieldName"] for c in columnas}
    por_limpio = {limpio(c["name"]): c["fieldName"] for c in columnas}

    nuevos, sin_mapeo, usados = [], [], set()
    for h in encabezados:
        h2 = h.lstrip("﻿")  # el primer encabezado puede traer BOM
        n = por_nombre.get(h2) or por_limpio.get(limpio(h2))
        if n is None:
            sin_mapeo.append(h2)
            n = limpio(h2) or "columna"
        base, i = n, 2
        while n in usados:  # evita nombres repetidos
            n, i = f"{base}_{i}", i + 1
        usados.add(n)
        nuevos.append(n)
    return nuevos, sin_mapeo


resumen_general = {}
for carpeta, tabla in DATASETS.items():
    t0 = time.time()
    ruta = f"s3://{BUCKET}/bronze/{carpeta}/carga-historica/"
    print(f"== {carpeta}: leyendo {ruta}")

    encabezados = spark.read.options(**OPC).csv(ruta).columns
    esquema = StructType([StructField(c, StringType()) for c in encabezados]
                         + [StructField("_corrupt_record", StringType())])
    df = (spark.read.options(**OPC)
          .option("mode", "PERMISSIVE")
          .option("columnNameOfCorruptRecord", "_corrupt_record")
          .schema(esquema)
          .csv(ruta)
          .repartition(PARTICIONES)
          .persist(StorageLevel.MEMORY_AND_DISK))

    nuevos, sin_mapeo = nombres_tecnicos(carpeta, encabezados)
    df = df.toDF(*nuevos, "_corrupt_record")

    buenas = df.filter(F.col("_corrupt_record").isNull()).drop("_corrupt_record")
    malas = df.filter(F.col("_corrupt_record").isNotNull()).select("_corrupt_record")

    total = df.count()
    n_malas = malas.count()

    (buenas.write.mode("overwrite").format("parquet")
     .option("compression", "snappy")
     .option("path", f"s3://{BUCKET}/bronze/{carpeta}/historico-parquet/")
     .saveAsTable(f"secop_bronze.{tabla}"))

    if n_malas:
        (malas.coalesce(1).write.mode("overwrite")
         .json(f"s3://{BUCKET}/bronze/{carpeta}/historico-corruptas/"))

    resumen = {
        "carpeta": carpeta,
        "tabla": f"secop_bronze.{tabla}",
        "filas_leidas": total,
        "filas_buenas": total - n_malas,
        "filas_corruptas": n_malas,
        "columnas": len(nuevos),
        "columnas_sin_mapeo": sin_mapeo,
        "segundos": round(time.time() - t0),
    }
    resumen_general[carpeta] = resumen
    s3.put_object(Bucket=BUCKET, Key=f"control/historico/resumen_{carpeta}.json",
                  Body=json.dumps(resumen, ensure_ascii=False, indent=2).encode("utf-8"))
    print(json.dumps(resumen, ensure_ascii=False))
    df.unpersist()

print("RESUMEN:", json.dumps(resumen_general, ensure_ascii=False))
