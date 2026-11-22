"""
Ingesta de SECOP II (datos.gov.co / Socrata) hacia la capa bronce en S3, orquestada por
Step Functions (maquina_ingesta.asl.json). Equipo 8 · Ingeniería de datos.

Una sola Lambda con varias acciones; Step Functions le pasa {"accion": ..., "datos": {...}}:

  preparar   completa la entrada de la ejecución (modo, datasets, corte, ejecutar_plata)
  planear    parte un dataset en VENTANAS por fecha de negocio y cuenta cuántas filas espera
               modo diario   -> 1 ventana: fecha_diario >= corte - dias_diario
               modo completo -> 1 ventana por mes de fecha_completo (+ 'sin-fecha' si hay nulos)
  descargar  baja UNA ventana paginando por :id (keyset). Antes del tope de 15 min devuelve
             {"terminado": false, "cursor": ...} y Step Functions la vuelve a llamar.
  verificar  compara filas escritas contra las esperadas, por ventana; deja un reporte en S3
  cerrar     falla la ejecución si algún dataset no cuadra (así no corre plata con datos a medias)

Por qué NO se usa :updated_at: datos.gov.co re-sella ese campo en casi todo el dataset en
lote (H25: 220.000 procesos con el mismo :updated_at al milisegundo). No indica qué cambió.

Rutas en S3 (nombres deterministas: un reintento sobrescribe, no duplica):
  diario    bronze/<carpeta>/ingesta/fecha=<corte>/part-diario-NNNNN.json.gz
  completo  bronze/<carpeta>/completa/corte=<corte>/part-<AAAA-MM>-NNNNN.json.gz
  reportes  control/ingesta/<modo>/corte=<corte>/<carpeta>.json

Uso local (desde tu PC, con credenciales de AWS para leer el app token de SSM):
  python ingesta_secop.py columnas <carpeta>              -> columnas de fecha del dataset
  python ingesta_secop.py planear <carpeta> diario|completo -> ventanas y conteos, sin escribir
  python ingesta_secop.py ddl                              -> CREATE TABLE de bronce (ingesta y completa)

Solo librería estándar + boto3 (ya viene en Lambda).
"""
import gzip
import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

import boto3

BUCKET = os.environ.get("BUCKET", "proyecto-integrador-bucket-01")
REGION = os.environ.get("AWS_REGION", "us-east-1")
BASE_URL = "https://www.datos.gov.co"
# 10.000 filas por página: los contratos traen muchas columnas de texto largo y
# 50.000 filas superaban 1 GB de memoria en Lambda (Runtime.OutOfMemory).
PAGE_SIZE = 10_000
SSM_TOKEN = "/secop/app-token"
MARGEN_S = 60            # segundos de reserva antes del tope de la Lambda
TOLERANCIA = 0.001       # faltante admitido por ventana: 0,1 % (o 10 filas, lo que sea mayor)
INICIO_INGESTA = "2026-10-27"
BOGOTA = timezone(timedelta(hours=-5))

# carpeta en bronze/ -> configuración del dataset.
#   fecha_completo: columna para partir la recarga completa por mes (debe estar casi siempre llena)
#   fecha_diario:   columna para la ventana diaria (lo nuevo o lo que cambió hace poco)
#   dias_diario:    cuántos días hacia atrás cubre la ventana diaria
# 'planear' valida que cada columna exista y sea de tipo fecha; si no, falla y lista las
# columnas de fecha disponibles. Las marcadas POR CONFIRMAR se revisan con:
#   python ingesta_secop.py columnas <carpeta>
DATASETS = {
    "procesos-contratacion": {
        "id": "p6dx-8zbt", "tabla": "raw_procesos",
        "fecha_completo": "fecha_de_publicacion_del",
        "fecha_diario": "fecha_de_publicacion_del",
        "dias_diario": 45,
    },
    "proponentes-procesos": {
        "id": "hgi6-6wh3", "tabla": "raw_proponentes",
        "fecha_completo": "fecha_publicaci_n",       # POR CONFIRMAR
        "fecha_diario": "fecha_publicaci_n",         # POR CONFIRMAR
        "dias_diario": 45,
    },
    "contratos-electronicos": {
        "id": "jbjy-vk9h", "tabla": "raw_contratos",
        "fecha_completo": "fecha_de_firma",          # POR CONFIRMAR
        "fecha_diario": "ultima_actualizacion",      # POR CONFIRMAR
        "dias_diario": 7,
    },
}

s3 = boto3.client("s3", region_name=REGION)
ssm = boto3.client("ssm", region_name=REGION)
_token = None


# ---------------------------------------------------------------- utilidades
def token():
    global _token
    if _token is None:
        try:
            _token = ssm.get_parameter(Name=SSM_TOKEN, WithDecryption=True)["Parameter"]["Value"]
        except ssm.exceptions.ParameterNotFound:
            _token = ""
    return _token or None


def http_get_json(url, retries=4):
    headers = {"Accept": "application/json"}
    if token():
        headers["X-App-Token"] = token()
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=180) as resp:
                return json.loads(resp.read())
        except Exception as exc:  # timeouts o 5xx de Socrata: reintento con espera exponencial
            if attempt == retries - 1:
                raise
            wait = 2 ** attempt * 5
            print(f"  error ({exc}); reintento en {wait}s")
            time.sleep(wait)


def soql(dataset_id, params):
    return http_get_json(f"{BASE_URL}/resource/{dataset_id}.json?" + urllib.parse.urlencode(params))


def contar(dataset_id, where=None):
    params = {"$select": "count(*) AS n"}
    if where:
        params["$where"] = where
    return int(soql(dataset_id, params)[0]["n"])


def columnas_fecha(dataset_id):
    meta = http_get_json(f"{BASE_URL}/api/views/{dataset_id}.json")
    return [c["fieldName"] for c in meta["columns"] if c.get("dataTypeName") == "calendar_date"]


def validar_columna(carpeta, columna):
    disponibles = columnas_fecha(DATASETS[carpeta]["id"])
    if columna not in disponibles:
        raise ValueError(f"{carpeta}: la columna '{columna}' no existe o no es de fecha. "
                         f"Columnas de fecha disponibles: {disponibles}")


def prefijo(carpeta, modo, corte, ventana_id):
    if modo == "diario":
        return f"bronze/{carpeta}/ingesta/fecha={corte}/part-{ventana_id}-"
    return f"bronze/{carpeta}/completa/corte={corte}/part-{ventana_id}-"


def borrar_prefijo(prefix):
    """Borra lo que haya quedado de una corrida anterior de la misma ventana (reintento o re-ejecución)."""
    borrados = 0
    for pagina in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=prefix):
        objetos = [{"Key": o["Key"]} for o in pagina.get("Contents", [])]
        if objetos:
            s3.delete_objects(Bucket=BUCKET, Delete={"Objects": objetos})
            borrados += len(objetos)
    return borrados


def mes_siguiente(anio, mes):
    return (anio + 1, 1) if mes == 12 else (anio, mes + 1)


# ---------------------------------------------------------------- acciones
def preparar(datos):
    modo = datos.get("modo", "diario")
    if modo not in ("diario", "completo"):
        raise ValueError(f"modo debe ser 'diario' o 'completo', no '{modo}'")
    datasets = datos.get("datasets") or list(DATASETS)
    desconocidos = [d for d in datasets if d not in DATASETS]
    if desconocidos:
        raise ValueError(f"datasets desconocidos: {desconocidos}. Válidos: {list(DATASETS)}")
    return {
        "modo": modo,
        "datasets": datasets,
        "corte": datos.get("corte") or datetime.now(BOGOTA).strftime("%Y-%m-%d"),
        "ejecutar_plata": bool(datos.get("ejecutar_plata", False)),
    }


def planear(datos):
    carpeta, modo, corte = datos["dataset"], datos["modo"], datos["corte"]
    cfg = DATASETS[carpeta]
    ds = cfg["id"]

    if modo == "diario":
        col = cfg["fecha_diario"]
        validar_columna(carpeta, col)
        desde = (date.fromisoformat(corte) - timedelta(days=cfg["dias_diario"])).isoformat()
        where = f"{col} >= '{desde}T00:00:00'"
        ventanas = [{"id": "diario", "where": where, "esperado": contar(ds, where)}]
    else:
        col = cfg["fecha_completo"]
        validar_columna(carpeta, col)
        filas = soql(ds, {"$select": f"date_trunc_ym({col}) AS mes, count(*) AS n",
                          "$group": "mes", "$order": "mes", "$limit": 50000})
        ventanas = []
        for r in filas:
            n = int(r["n"])
            if r.get("mes") is None:
                ventanas.append({"id": "sin-fecha", "where": f"{col} IS NULL", "esperado": n})
                continue
            anio, mes = int(r["mes"][:4]), int(r["mes"][5:7])
            a2, m2 = mes_siguiente(anio, mes)
            ventanas.append({
                "id": f"{anio:04d}-{mes:02d}",
                "where": f"{col} >= '{anio:04d}-{mes:02d}-01T00:00:00' AND {col} < '{a2:04d}-{m2:02d}-01T00:00:00'",
                "esperado": n,
            })

    total = contar(ds)
    esperado = sum(v["esperado"] for v in ventanas)
    print(f"{carpeta} [{modo}]: {len(ventanas)} ventanas, {esperado} filas esperadas "
          f"(total del dataset en la API: {total})")
    return {"dataset": carpeta, "modo": modo, "corte": corte, "total_api": total, "ventanas": ventanas}


def descargar(datos, context=None):
    """
    Baja una ventana por páginas ordenadas por :id. Paginación por llave (keyset): cada página
    pide las filas con :id mayor al último recibido. :id no cambia cuando el portal re-sella
    :updated_at, así que el orden es estable mientras se descarga.
    """
    carpeta, modo, corte, ventana = datos["dataset"], datos["modo"], datos["corte"], datos["ventana"]
    ds = DATASETS[carpeta]["id"]
    cursor = datos.get("cursor")
    filas = datos.get("filas", 0)
    prefix = prefijo(carpeta, modo, corte, ventana["id"])

    if not cursor:
        borrados = borrar_prefijo(prefix)
        if borrados:
            print(f"  {prefix}*: {borrados} archivos de una corrida anterior borrados")
        ultimo_id, pagina = None, 0
    else:
        ultimo_id, pagina = cursor["id"], cursor["pagina"]

    restante = context.get_remaining_time_in_millis() / 1000 if context else 900
    deadline = time.time() + restante - MARGEN_S
    t_max = 0.0

    def salida(terminado):
        return {"dataset": carpeta, "modo": modo, "corte": corte, "ventana": ventana,
                "cursor": {"id": ultimo_id, "pagina": pagina}, "filas": filas, "terminado": terminado}

    while True:
        where = f"({ventana['where']})"
        if ultimo_id is not None:
            where += f" AND :id > '{ultimo_id}'"
        t0 = time.time()
        rows = soql(ds, {"$select": ":*, *", "$where": where, "$order": ":id", "$limit": PAGE_SIZE})
        if not rows:
            return salida(True)

        # Comprime fila por fila: evita armar en memoria un string gigante con toda la página
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
            for r in rows:
                gz.write((json.dumps(r, ensure_ascii=False) + "\n").encode("utf-8"))
        key = f"{prefix}{pagina:05d}.json.gz"
        s3.put_object(Bucket=BUCKET, Key=key, Body=buf.getvalue())

        n = len(rows)
        filas += n
        ultimo_id = rows[-1][":id"]
        pagina += 1
        dt = time.time() - t0
        t_max = max(t_max, dt)
        print(f"  {carpeta}/{ventana['id']}: página {pagina - 1} -> {n} filas "
              f"(acumulado {filas}) [{dt:.0f} s]")
        del rows, buf

        if n < PAGE_SIZE:
            return salida(True)
        # ¿Cabe otra página tan lenta como la más lenta vista? Si no, se sale y Step Functions sigue.
        if time.time() + t_max * 1.5 > deadline:
            return salida(False)


def verificar(datos):
    carpeta, modo, corte = datos["dataset"], datos["modo"], datos["corte"]
    escritas = {r["ventana"]["id"]: r["filas"] for r in datos["resultados"]}
    detalle, faltantes = [], []
    for v in datos["ventanas"]:
        esc = escritas.get(v["id"], 0)
        falta = v["esperado"] - esc
        fila = {"ventana": v["id"], "esperado": v["esperado"], "escrito": esc}
        detalle.append(fila)
        if falta > max(10, TOLERANCIA * v["esperado"]):
            faltantes.append(fila)

    esperado = sum(v["esperado"] for v in datos["ventanas"])
    escrito = sum(escritas.values())
    resultado = {
        "dataset": carpeta, "modo": modo, "corte": corte, "ok": not faltantes,
        "esperado": esperado, "escrito": escrito, "total_api": datos.get("total_api"),
        "ventanas": len(datos["ventanas"]), "ventanas_con_faltantes": len(faltantes),
    }
    key = f"control/ingesta/{modo}/corte={corte}/{carpeta}.json"
    s3.put_object(Bucket=BUCKET, Key=key, ContentType="application/json",
                  Body=json.dumps({**resultado, "faltantes": faltantes, "detalle": detalle},
                                  ensure_ascii=False, indent=1).encode("utf-8"))
    resultado["reporte"] = f"s3://{BUCKET}/{key}"
    resultado["primeros_faltantes"] = faltantes[:10]   # lo demás está en el reporte
    print(json.dumps(resultado, ensure_ascii=False))
    return resultado


class ConteoNoCuadra(Exception):
    pass


def cerrar(datos):
    malos = [v for v in datos["verificaciones"] if not v["ok"]]
    resumen = {v["dataset"]: {"ok": v["ok"], "esperado": v["esperado"], "escrito": v["escrito"]}
               for v in datos["verificaciones"]}
    print(json.dumps(resumen, ensure_ascii=False))
    if malos:
        raise ConteoNoCuadra("Faltan filas en: " + ", ".join(
            f"{v['dataset']} ({v['ventanas_con_faltantes']} ventanas, ver {v['reporte']})" for v in malos))
    return resumen


ACCIONES = {"preparar": preparar, "planear": planear, "verificar": verificar, "cerrar": cerrar}


def lambda_handler(event, context):
    accion = event.get("accion")
    datos = event.get("datos", {})
    if accion == "descargar":
        return descargar(datos, context)
    if accion in ACCIONES:
        return ACCIONES[accion](datos)
    raise ValueError(f"accion desconocida: {accion}. Esta Lambda se invoca desde Step Functions "
                     f"con {{'accion': ..., 'datos': ...}}")


# ---------------------------------------------------------------- DDL de bronce
def ddl(carpeta, capa):
    """CREATE TABLE a partir de los metadatos reales del dataset (todo como string).
    capa 'ingesta' -> tabla raw_<x> (partición fecha); 'completa' -> raw_<x>_completa (partición corte)."""
    cfg = DATASETS[carpeta]
    meta = http_get_json(f"{BASE_URL}/api/views/{cfg['id']}.json")
    cols = [c["fieldName"] for c in meta["columns"] if not c["fieldName"].startswith(":")]
    cols_sql = ",\n  ".join([f"`{c}` string" for c in cols] +
                            ["`sys_id` string", "`sys_created_at` string", "`sys_updated_at` string"])
    part = "fecha" if capa == "ingesta" else "corte"
    tabla = cfg["tabla"] if capa == "ingesta" else f"{cfg['tabla']}_completa"
    location = f"s3://{BUCKET}/bronze/{carpeta}/{capa}/"
    inicio = INICIO_INGESTA if capa == "ingesta" else "2026-11-01"
    return f"""CREATE EXTERNAL TABLE IF NOT EXISTS secop_bronze.{tabla} (
  {cols_sql}
)
PARTITIONED BY ({part} string)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
WITH SERDEPROPERTIES (
  'ignore.malformed.json' = 'true',
  'mapping.sys_id' = ':id',
  'mapping.sys_created_at' = ':created_at',
  'mapping.sys_updated_at' = ':updated_at'
)
LOCATION '{location}'
TBLPROPERTIES (
  'projection.enabled' = 'true',
  'projection.{part}.type' = 'date',
  'projection.{part}.format' = 'yyyy-MM-dd',
  'projection.{part}.range' = '{inicio},NOW',
  'projection.{part}.interval' = '1',
  'projection.{part}.interval.unit' = 'DAYS',
  'storage.location.template' = '{location}{part}=${{{part}}}/'
);"""


# ---------------------------------------------------------------- CLI local
if __name__ == "__main__":
    modo_cli = sys.argv[1] if len(sys.argv) > 1 else ""
    if modo_cli == "columnas":
        print(columnas_fecha(DATASETS[sys.argv[2]]["id"]))
    elif modo_cli == "planear":
        plan = planear({"dataset": sys.argv[2], "modo": sys.argv[3],
                        "corte": datetime.now(BOGOTA).strftime("%Y-%m-%d")})
        for v in plan["ventanas"]:
            print(f"  {v['id']:>10}  {v['esperado']:>10,}")
    elif modo_cli == "ddl":
        for c in DATASETS:
            for capa in ("ingesta", "completa"):
                print(f"-- {c} ({capa})\n{ddl(c, capa)}\n")
    else:
        print(__doc__)
