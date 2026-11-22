#!/usr/bin/env python3
"""
Exporta los agregados del dashboard desde la capa oro (Athena) a public/data/estadisticas-oro.json,
con la misma forma que estadisticas-simulado.json. Cuando ese archivo existe, la web lo usa en lugar
de los datos simulados (mientras la API no publique /estadisticas).

El JSON tiene el mismo formato que GET /estadisticas/snapshot del contrato del dashboard.

Uso (con credenciales de la cuenta del proyecto, perfil "secop" o las del entorno):
    pip install boto3
    python3 scripts/exportar_snapshot_oro.py --perfil secop
    python3 scripts/exportar_snapshot_oro.py --solo-esquema   # muestra las columnas reales de cada tabla

IMPORTANTE: los nombres de columna de las consultas siguen el documento "Capa oro SECOP II"
(17-nov-2026). Antes de la primera corrida, compárenlos con estrella_oro_secop.sql (consultas D01–D05)
o con --solo-esquema y ajusten solo el bloque CONSULTAS. Si una columna no existe, Athena falla
con un mensaje claro y el script no escribe nada.
"""
import argparse
import datetime as dt
import json
import sys
import time
import unicodedata
from pathlib import Path

BASE = "secop_gold"
WORKGROUP = "proyecto-integrador-workgroup"
REGION = "us-east-1"
SALIDA = Path(__file__).resolve().parent.parent / "public" / "data" / "estadisticas-oro.json"

# ---------------------------------------------------------------------------------------------
# CONSULTAS: cada una devuelve exactamente las columnas que espera el snapshot (en ese orden).
# Ajustar aquí los nombres reales de las columnas de oro si difieren.
# ---------------------------------------------------------------------------------------------
# Ventana del dashboard: desde 2020, como el informe de oro. Antes hay muy pocos procesos, y 2018 trae un
# valor adjudicado imposible (~2.000 billones) que la regla de atípicos de oro no marca.
DESDE = 2020

CONSULTAS = {
    # Cifras oficiales de oro: mercado_mensual (mes × depto × grupo de modalidad × segmento), agregadas a año.
    # procesos_con_oferentes es la base del % de oferente único, igual que en el informe de oro.
    "anual": f"""
        SELECT anio, departamento, segmento_codigo AS segmento, modalidad_grupo AS modalidad,
               SUM(procesos_publicados)     AS procesos,
               SUM(procesos_adjudicados)    AS adjudicados,
               SUM(valor_adjudicado)        AS valor,
               SUM(procesos_con_oferentes)  AS con_of,
               SUM(procesos_unico_oferente) AS unico,
               SUM(suma_oferentes)          AS suma_of
        FROM {BASE}.mercado_mensual
        WHERE anio >= {DESDE}
        GROUP BY 1, 2, 3, 4
    """,
    # Pymes: no está en mercado_mensual; sale de la estrella. Conteo sobre todos los adjudicados (igual base que
    # procesos_adjudicados) y valor sin los procesos con valor atípico (igual regla que valor_adjudicado).
    "pymes": f"""
        SELECT year(f.fecha_publicacion) AS anio, g.departamento AS departamento, c.segmento_codigo AS segmento,
               mo.modalidad_grupo AS modalidad,
               SUM(CASE WHEN p.es_pyme THEN 1 ELSE 0 END) AS adj_pyme,
               SUM(CASE WHEN p.es_pyme AND f.valor_atipico = 0 THEN f.valor_adjudicacion ELSE 0 END) AS valor_pyme
        FROM {BASE}.fact_procesos f
        JOIN {BASE}.dim_proveedor p  ON p.proveedor_key  = f.ganador_proveedor_key
        JOIN {BASE}.dim_geografia g  ON g.geografia_key  = f.geografia_key
        JOIN {BASE}.dim_categoria c  ON c.categoria_key  = f.categoria_key
        JOIN {BASE}.dim_modalidad mo ON mo.modalidad_key = f.modalidad_key
        WHERE f.es_adjudicado = 1 AND year(f.fecha_publicacion) >= {DESDE}
        GROUP BY 1, 2, 3, 4
    """,
    "mensual": f"""
        SELECT anio_mes AS mes, departamento, modalidad_grupo AS modalidad,
               SUM(procesos_publicados) AS procesos, SUM(procesos_adjudicados) AS adjudicados, SUM(valor_adjudicado) AS valor,
               SUM(procesos_con_oferentes) AS con_of, SUM(procesos_unico_oferente) AS unico
        FROM {BASE}.mercado_mensual WHERE anio >= {DESDE} GROUP BY 1, 2, 3
    """,
    "mensual_segmento": f"""
        SELECT anio_mes AS mes, segmento_codigo AS segmento,
               SUM(procesos_publicados) AS procesos, SUM(procesos_adjudicados) AS adjudicados, SUM(valor_adjudicado) AS valor,
               SUM(procesos_con_oferentes) AS con_of, SUM(procesos_unico_oferente) AS unico
        FROM {BASE}.mercado_mensual WHERE anio >= {DESDE} GROUP BY 1, 2
    """,
    # Valor = adjudicado en procesos competitivos (misma medida y regla de atípicos que el resto del tablero).
    # No se usa valor_contratos: suma todos los contratos (incluida contratación directa) y deja pasar valores
    # erróneos de 50–99 mil millones que no alcanzan las reglas de atípicos (p. ej. 11,8 billones en una regional).
    # El HHI y la cuota del proveedor principal sí son sobre los contratos de la entidad.
    # dim_entidad usa el NIT como llave y guarda el nombre MÁS RECIENTE. En SECOP varias dependencias comparten NIT
    # (todas las de Bogotá D.C., las regionales del SENA o del ICBF), así que ese nombre puede ser el de una sola
    # dependencia. Aquí se usa el nombre más frecuente del NIT en plata y se cuentan las dependencias que lo comparten.
    "entidades": f"""
        WITH nombres AS (
            SELECT f.entidad_key, s.nombre_entidad,
                   regexp_replace(lower(translate(s.nombre_entidad, 'ÁÉÍÓÚÜÑáéíóúüñ', 'AEIOUUNaeiouun')), '[^a-z0-9]', '') AS norm,
                   COUNT(*) AS n
            FROM {BASE}.fact_procesos f JOIN secop_silver.procesos s ON s.id_proceso = f.id_proceso
            WHERE year(f.fecha_publicacion) >= {DESDE}
            GROUP BY 1, 2, 3),
        por_nit AS (SELECT entidad_key, max_by(nombre_entidad, n) AS nombre, COUNT(DISTINCT norm) AS dependencias FROM nombres GROUP BY 1)
        SELECT e.entidad_key AS key, COALESCE(pn.nombre, e.nombre_entidad) AS nombre, e.departamento, e.anio,
               e.procesos_publicados AS procesos, e.procesos_con_oferentes AS con_of, e.procesos_unico_oferente AS unico,
               e.contratos, e.valor_adjudicado AS valor, e.proveedores_distintos AS proveedores,
               e.hhi_valor AS hhi, e.cuota_proveedor_principal AS cuota_principal, e.contratos_valor_atipico AS atipicos,
               COALESCE(pn.dependencias, 1) AS dependencias
        FROM {BASE}.competencia_entidad e LEFT JOIN por_nit pn ON pn.entidad_key = e.entidad_key
        WHERE e.anio >= {DESDE} AND e.entidad_key IN (
            SELECT entidad_key FROM {BASE}.competencia_entidad WHERE anio >= {DESDE}
            GROUP BY 1 ORDER BY SUM(valor_adjudicado) DESC LIMIT 400)
    """,
    "calidad": f"""
        SELECT CAST(semana_inicio AS VARCHAR) AS semana, procesos_publicados AS procesos, procesos_sin_categoria AS sin_categoria,
               procesos_sin_departamento AS sin_departamento, procesos_sin_precio AS sin_precio, procesos_precio_atipico AS precio_atipico
        FROM {BASE}.calidad_fuente WHERE semana_inicio >= DATE '{DESDE}-01-01' ORDER BY 1
    """,
    "desempeno": f"""
        SELECT CAST(fecha_corte AS VARCHAR) AS fecha_corte, lista, participaciones_reales AS ofertas_reales,
               cobertura, precision_empresas_activas AS precision_activas, gano, ganes_esperados
        FROM {BASE}.desempeno_recomendaciones ORDER BY 1, 2
    """,
}
TABLAS_ESQUEMA = ["mercado_mensual", "competencia_entidad", "calidad_fuente", "desempeno_recomendaciones",
                  "fact_procesos", "dim_proveedor", "dim_geografia", "dim_categoria", "dim_modalidad", "dim_entidad"]

# ---------------------------------------------------------------------------------------------
# Departamentos: oro guarda el nombre (DIVIPOLA en dim_geografia queda para después de la demo).
# Misma tabla de equivalencias que src/utils/dane.js.
# ---------------------------------------------------------------------------------------------
DEPTOS = {"antioquia": "05", "atlantico": "08", "bogota d c": "11", "bolivar": "13", "boyaca": "15", "caldas": "17", "caqueta": "18",
          "cauca": "19", "cesar": "20", "cordoba": "23", "cundinamarca": "25", "choco": "27", "huila": "41", "la guajira": "44",
          "magdalena": "47", "meta": "50", "narino": "52", "norte de santander": "54", "quindio": "63", "risaralda": "66",
          "santander": "68", "sucre": "70", "tolima": "73", "valle del cauca": "76", "arauca": "81", "casanare": "85", "putumayo": "86",
          "san andres y providencia": "88", "amazonas": "91", "guainia": "94", "guaviare": "95", "vaupes": "97", "vichada": "99",
          "distrito capital de bogota": "11", "bogota": "11", "bogota dc": "11", "santafe de bogota d c": "11", "distrito capital": "11",
          "san andres providencia y santa catalina": "88", "archipielago de san andres providencia y santa catalina": "88",
          "san andres": "88", "guajira": "44", "valle": "76"}
GRUPOS = {"licitacion publica": "licitacion_publica", "seleccion abreviada": "seleccion_abreviada", "concurso de meritos": "concurso_meritos",
          "minima cuantia": "minima_cuantia", "enajenacion de bienes": "enajenacion", "contratacion directa": "contratacion_directa",
          "regimen especial": "regimen_especial"}


def normalizar(s):
    s = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " ".join("".join(c if c.isalnum() else " " for c in s).split())


def depto(nombre):
    n = normalizar(nombre)
    if not n or n in ("sin dato", "sin_dato", "na"):
        return "SD"
    if n.isdigit():
        return n.zfill(2)
    return DEPTOS.get(n, "SD")


def grupo(nombre):
    n = normalizar(nombre).replace("con ofertas", "").strip()
    if n in GRUPOS.values():
        return n
    for k, v in GRUPOS.items():
        if n.startswith(k):
            return v
    raise ValueError(f"Grupo de modalidad desconocido: {nombre!r}. Agréguenlo a GRUPOS.")


def segmento(v):
    s = str(v or "").strip()
    return s.zfill(2)[:2] if s.isdigit() and s not in ("0", "00") else "00"


def num(v):
    if v in (None, ""):
        return None
    f = float(v)
    return int(f) if f.is_integer() else f


# ---------------------------------------------------------------------------------------------
def athena(boto3_session, sql):
    cli = boto3_session.client("athena", region_name=REGION)
    q = cli.start_query_execution(QueryString=sql, WorkGroup=WORKGROUP)["QueryExecutionId"]
    while True:
        st = cli.get_query_execution(QueryExecutionId=q)["QueryExecution"]["Status"]
        if st["State"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(1.5)
    if st["State"] != "SUCCEEDED":
        raise RuntimeError(f"Athena {st['State']}: {st.get('StateChangeReason')}\n{sql}")
    filas, cab = [], None
    for pagina in cli.get_paginator("get_query_results").paginate(QueryExecutionId=q):
        for r in pagina["ResultSet"]["Rows"]:
            vals = [c.get("VarCharValue") for c in r["Data"]]
            if cab is None:
                cab = vals
            else:
                filas.append(dict(zip(cab, vals)))
    return filas


def mostrar_esquema(sesion):
    glue = sesion.client("glue", region_name=REGION)
    for t in TABLAS_ESQUEMA:
        try:
            cols = glue.get_table(DatabaseName=BASE, Name=t)["Table"]["StorageDescriptor"]["Columns"]
            print(f"\n{BASE}.{t}:\n  " + ", ".join(f"{c['Name']}:{c['Type']}" for c in cols))
        except Exception as e:  # noqa: BLE001
            print(f"\n{BASE}.{t}: no disponible ({e})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--perfil", default=None, help="Perfil de AWS (p. ej. secop)")
    ap.add_argument("--solo-esquema", action="store_true", help="Solo imprime las columnas reales de las tablas de oro")
    ap.add_argument("--salida", default=str(SALIDA))
    args = ap.parse_args()

    import boto3  # se importa aquí para que --help funcione sin boto3
    sesion = boto3.Session(profile_name=args.perfil) if args.perfil else boto3.Session()
    if args.solo_esquema:
        mostrar_esquema(sesion)
        return

    print("Consultando la capa oro en Athena…")
    r = {k: athena(sesion, sql) for k, sql in CONSULTAS.items()}

    deps, segs, mods = ["SD"], ["00"], []
    def idx(lista, v):
        if v not in lista:
            lista.append(v)
        return lista.index(v)

    pymes = {}
    for f in r["pymes"]:
        k = (int(f["anio"]), depto(f["departamento"]), segmento(f["segmento"]), grupo(f["modalidad"]))
        a = pymes.setdefault(k, [0, 0])
        a[0] += num(f["adj_pyme"]) or 0
        a[1] += num(f["valor_pyme"]) or 0

    anual = {}
    for f in r["anual"]:
        k = (int(f["anio"]), depto(f["departamento"]), segmento(f["segmento"]), grupo(f["modalidad"]))
        a = anual.setdefault(k, [0] * 6)
        for i, c in enumerate(["procesos", "adjudicados", "valor", "con_of", "unico", "suma_of"]):
            a[i] += num(f[c]) or 0
    filas_anual = []
    for (y, d, s, m), a in sorted(anual.items()):
        p = pymes.get((y, d, s, m), [0, 0])
        filas_anual.append([y, idx(deps, d), idx(segs, s), idx(mods, m), a[0], a[1], round(a[2] / 1e6), a[3], a[4], a[5], p[0], round(p[1] / 1e6)])

    mensual = {}
    for f in r["mensual"]:
        k = (str(f["mes"])[:7], depto(f["departamento"]), grupo(f["modalidad"]))
        a = mensual.setdefault(k, [0] * 5)
        for i, c in enumerate(["procesos", "adjudicados", "valor", "con_of", "unico"]):
            a[i] += num(f[c]) or 0
    filas_mensual = [[mes, idx(deps, d), idx(mods, m), a[0], a[1], round(a[2] / 1e6), a[3], a[4]] for (mes, d, m), a in sorted(mensual.items())]

    filas_mseg = [[str(f["mes"])[:7], idx(segs, segmento(f["segmento"])), num(f["procesos"]) or 0, num(f["adjudicados"]) or 0,
                   round((num(f["valor"]) or 0) / 1e6), num(f["con_of"]) or 0, num(f["unico"]) or 0] for f in r["mensual_segmento"]]

    filas_ent = [[f["key"], f["nombre"], idx(deps, depto(f["departamento"])), int(f["anio"]), num(f["procesos"]) or 0, num(f["con_of"]) or 0,
                  num(f["unico"]) or 0, num(f["contratos"]) or 0, round((num(f["valor"]) or 0) / 1e6), num(f["proveedores"]) or 0,
                  num(f["hhi"]), num(f["cuota_principal"]), num(f["atipicos"]) or 0, num(f["dependencias"]) or 1] for f in r["entidades"]]

    filas_cal = [[f["semana"][:10], num(f["procesos"]) or 0, num(f["sin_categoria"]) or 0, num(f["sin_departamento"]) or 0,
                  num(f["sin_precio"]) or 0, num(f["precio_atipico"]) or 0] for f in r["calidad"]]
    filas_des = [[f["fecha_corte"][:10], f["lista"], num(f["ofertas_reales"]), num(f["cobertura"]), num(f["precision_activas"]),
                  num(f["gano"]), num(f["ganes_esperados"])] for f in r["desempeno"]]

    total = sum(f[4] for f in filas_anual)
    if total == 0:
        sys.exit("La consulta anual no devolvió procesos: no se escribe nada.")

    snapshot = {
        "version": 1, "fuente": "capa_oro",
        "descripcion": "Agregados de la capa oro de SECOP II (secop_gold) exportados desde Athena.",
        "generado": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "fecha_datos": max((f[0] for f in filas_des), default=dt.date.today().isoformat()),
        "escala_valor": 1e6,
        "anios": sorted({f[0] for f in filas_anual}),
        "departamentos": deps, "segmentos": segs, "modalidades": mods,
        "anual": {"cols": ["anio", "d", "s", "m", "procesos", "adjudicados", "valor", "con_of", "unico", "suma_of", "adj_pyme", "valor_pyme"], "filas": filas_anual},
        "mensual": {"cols": ["mes", "d", "m", "procesos", "adjudicados", "valor", "con_of", "unico"], "filas": filas_mensual},
        "mensual_segmento": {"cols": ["mes", "s", "procesos", "adjudicados", "valor", "con_of", "unico"], "filas": filas_mseg},
        "entidades": {"cols": ["key", "nombre", "d", "anio", "procesos", "con_of", "unico", "contratos", "valor", "proveedores", "hhi", "cuota_principal", "atipicos", "dependencias"], "filas": filas_ent},
        "calidad": {"cols": ["semana", "procesos", "sin_categoria", "sin_departamento", "sin_precio", "precio_atipico"], "filas": filas_cal},
        "desempeno": {"cols": ["fecha_corte", "lista", "ofertas_reales", "cobertura", "precision_activas", "gano", "ganes_esperados"], "filas": filas_des,
                      "nota": "Desempeño real de las recomendaciones según secop_gold.desempeno_recomendaciones."},
    }
    Path(args.salida).parent.mkdir(parents=True, exist_ok=True)
    Path(args.salida).write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Escrito {args.salida}: {total:,} procesos, {len(filas_anual)} filas anuales, {len(filas_ent)} filas de entidades.")


if __name__ == "__main__":
    main()
