"""
Capa oro · Modelo estrella de SECOP II (job de Glue: secop-gold-estrella)

Lee las 4 tablas de plata (en su último snapshot) y reconstruye completo, en cada corrida:

  Dimensiones                         Hechos
  -----------                         ------
  dim_fecha        (un día)           fact_procesos        (un proceso)
  dim_entidad      (una entidad)      fact_participaciones (un proveedor en un proceso)
  dim_proveedor    (un proveedor)     fact_contratos       (un contrato)
  dim_geografia    (depto + ciudad)
  dim_categoria    (UNSPSC a nivel clase)
  dim_modalidad    (modalidad + tipo de contrato)

  Tablas del dashboard (salen de la estrella, en la misma corrida)
  ----------------------------------------------------------------
  mercado_mensual            mes × departamento × grupo de modalidad × segmento
  competencia_entidad        entidad × año: oferentes, oferente único, concentración (HHI)
  calidad_fuente             semana: volumen y completitud de lo publicado
  desempeno_recomendaciones  día de corte × lista: resultado real de lo recomendado

Reglas de diseño
  * Llaves: entidad = nit_entidad, proveedor = proveedor_key (ya son llaves estables de plata);
    geografía, categoría y modalidad = xxhash64 de sus atributos; fecha = AAAAMMDD (int).
  * Ningún hecho tiene llaves nulas: lo que falta apunta a un miembro "Sin dato"
    (llave 'sin_dato' en texto, -1 en fecha, o el hash de los atributos en 'Sin dato').
  * Banderas de los hechos como 0/1 (int) para poder sumarlas en los tableros.
  * Personas naturales: nunca se guarda su nombre.
  * Antes de escribir se valida: llaves únicas, integridad referencial, que los hechos tengan
    las mismas filas que plata y que los valores sumen igual. Si algo falla, no se escribe nada.

Parámetros del job: --datalake-formats iceberg ; library path con limpieza_secop.py no es necesario.
"""
import sys
from datetime import datetime, timezone

from pyspark.sql import Window
from pyspark.sql import functions as F

CAT = "glue_catalog"
BUCKET = "proyecto-integrador-bucket-01"
DB = f"{CAT}.secop_gold"
TABLA_CONTROL = f"{CAT}.secop_control.control_corridas"
PLATA = ["procesos", "proponentes", "contratos", "proveedores"]
RUTA_RECOMENDACIONES = f"s3://{BUCKET}/gold/recomendaciones/"   # copia diaria de MLOps (Parquet)
DASHBOARD = ["mercado_mensual", "competencia_entidad", "calidad_fuente", "desempeno_recomendaciones"]

SIN = "Sin dato"          # etiqueta del miembro desconocido en atributos de texto
SIN_KEY = "sin_dato"      # llave del miembro desconocido en entidad y proveedor
FECHA_MIN, FECHA_MAX = "2000-01-01", "2060-12-31"
UMBRAL_VALOR_ATIPICO = 1e11   # 100 mil millones: misma regla que precio_atipico de procesos en plata
UMBRAL_RELATIVO_MIN = 1e10    # regla relativa: más de 10 mil millones…
VECES_MEDIANA = 1000          # …y más de 1.000 veces la mediana de la entidad en ese año

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

# Partición de cada tabla de oro (None = sin partición)
PARTICION = {
    "fact_procesos": "fecha_publicacion",
    "fact_participaciones": "fecha_publicacion",
    "fact_contratos": "fecha_firma",
}


# ----------------------------------------------------------------------------- utilidades
def _norm(c):
    """Texto comparable: minúsculas, sin tildes ni signos. Sirve para unir nombres de lugares."""
    c = F.lower(F.translate(c, "ÁÉÍÓÚÜáéíóúüÑñ", "AEIOUUaeiouuNn"))
    c = F.trim(F.regexp_replace(c, r"[^a-z0-9]+", " "))
    return F.when(c == "", None).otherwise(c)


def _txt(c):
    return F.coalesce(c, F.lit(SIN))


def _fecha_key(c):
    """AAAAMMDD; -1 si la fecha es nula o está fuera del calendario."""
    return (F.when(c.between(F.lit(FECHA_MIN).cast("date"), F.lit(FECHA_MAX).cast("date")),
                   F.date_format(c, "yyyyMMdd").cast("int"))
             .otherwise(F.lit(-1)))


def _geo_key(depto_norm, ciudad_norm):
    return F.xxhash64(F.coalesce(depto_norm, F.lit(SIN_KEY)), F.coalesce(ciudad_norm, F.lit(SIN_KEY)))


def _cat_key(seg, fam, clase):
    return F.xxhash64(_txt(seg), _txt(fam), _txt(clase))


def _mod_key(modalidad, tipo):
    return F.xxhash64(_txt(modalidad), _txt(tipo))


def _ultimo(valor, fecha):
    """Agregado: el valor no nulo más reciente (desempate determinista por el propio valor)."""
    return F.max(F.when(valor.isNotNull(),
                        F.struct(F.coalesce(fecha, F.lit("1900-01-01").cast("date")).alias("f"),
                                 valor.alias("v")))).getField("v")


def _int(c):
    return F.when(c, 1).when(~c, 0)


# ----------------------------------------------------------------------------- dimensiones
def dim_fecha(spark):
    d = spark.sql(f"SELECT explode(sequence(to_date('{FECHA_MIN}'), to_date('{FECHA_MAX}'), "
                  f"interval 1 day)) AS fecha")
    meses = F.array(*[F.lit(m) for m in MESES])
    dias = F.array(*[F.lit(x) for x in DIAS])
    dow = (F.dayofweek("fecha") + 5) % 7 + 1          # 1 = lunes … 7 = domingo
    d = d.select(
        F.date_format("fecha", "yyyyMMdd").cast("int").alias("fecha_key"),
        "fecha",
        F.year("fecha").alias("anio"),
        F.when(F.month("fecha") <= 6, 1).otherwise(2).alias("semestre"),
        F.quarter("fecha").alias("trimestre"),
        F.month("fecha").alias("mes"),
        meses[F.month("fecha") - 1].alias("nombre_mes"),
        F.date_format("fecha", "yyyy-MM").alias("anio_mes"),
        F.weekofyear("fecha").alias("semana_iso"),
        F.dayofmonth("fecha").alias("dia_mes"),
        dow.alias("dia_semana"),
        dias[dow - 1].alias("nombre_dia"),
        (dow >= 6).alias("es_fin_de_semana"),
    )
    nulos = {"nombre_mes": F.lit(SIN), "anio_mes": F.lit(SIN), "nombre_dia": F.lit(SIN), "fecha_key": F.lit(-1)}
    desconocido = spark.range(1).select(*[nulos.get(f.name, F.lit(None)).cast(f.dataType).alias(f.name)
                                          for f in d.schema.fields])
    return d.unionByName(desconocido)


def _lugares(procesos, contratos, proveedores):
    """Todas las parejas (departamento, ciudad) en su forma original, con la fuente que las trae."""
    return (procesos.select(F.col("departamento_entidad").alias("d"), F.col("ciudad_entidad").alias("c"))
            .unionByName(contratos.select(F.col("departamento").alias("d"), F.col("ciudad").alias("c")))
            .unionByName(proveedores.select(F.col("departamento").alias("d"), F.col("municipio").alias("c"))))


def dim_geografia(procesos, contratos, proveedores):
    """Un registro por (departamento, ciudad) normalizados. La etiqueta es la escritura más frecuente."""
    l = (_lugares(procesos, contratos, proveedores)
         .withColumn("dn", _norm(F.col("d"))).withColumn("cn", _norm(F.col("c"))))

    def etiqueta(orig, norm):
        conteo = l.filter(F.col(orig).isNotNull()).groupBy(norm, orig).count()
        w = Window.partitionBy(norm).orderBy(F.desc("count"), F.asc(orig))
        return (conteo.withColumn("_r", F.row_number().over(w)).filter("_r = 1")
                .select(norm, F.trim(F.col(orig)).alias(orig + "_lbl")))

    nulo = F.lit(None).cast("string")
    combos = l.select("dn", "cn").unionByName(
        l.sparkSession.range(1).select(nulo.alias("dn"), nulo.alias("cn"))).distinct()
    return (combos
            .join(etiqueta("d", "dn"), "dn", "left")
            .join(etiqueta("c", "cn"), "cn", "left")
            .select(_geo_key(F.col("dn"), F.col("cn")).alias("geografia_key"),
                    _txt(F.col("d_lbl")).alias("departamento"),
                    _txt(F.col("c_lbl")).alias("ciudad"),
                    F.col("dn").alias("departamento_norm"),
                    F.col("cn").alias("ciudad_norm"),
                    F.lit(None).cast("string").alias("codigo_divipola"))   # se llena con DIVIPOLA
            .dropDuplicates(["geografia_key"]))


def dim_categoria(procesos, contratos):
    cols = ["unspsc_segmento", "unspsc_familia", "unspsc_clase"]
    nulos = procesos.sparkSession.range(1).select(*[F.lit(None).cast("string").alias(x) for x in cols])
    c = procesos.select(*cols).unionByName(contratos.select(*cols)).unionByName(nulos).distinct()
    nivel = (F.when(F.col("unspsc_clase").isNotNull(), "clase")
              .when(F.col("unspsc_familia").isNotNull(), "familia")
              .when(F.col("unspsc_segmento").isNotNull(), "segmento")
              .otherwise("sin_dato"))
    return (c.select(_cat_key(*[F.col(x) for x in cols]).alias("categoria_key"),
                     _txt(F.col("unspsc_segmento")).alias("segmento_codigo"),
                     _txt(F.col("unspsc_familia")).alias("familia_codigo"),
                     _txt(F.col("unspsc_clase")).alias("clase_codigo"),
                     nivel.alias("nivel_detalle"),
                     F.lit(None).cast("string").alias("segmento_nombre"),   # catálogo UNSPSC pendiente
                     F.lit(None).cast("string").alias("familia_nombre"),
                     F.lit(None).cast("string").alias("clase_nombre"))
            .dropDuplicates(["categoria_key"]))


GRUPOS_MODALIDAD = [   # (patrón sobre el nombre normalizado, grupo, es competitiva)
    ("^licitacion", "Licitación pública", True),
    ("^seleccion abreviada", "Selección abreviada", True),
    ("^concurso de meritos", "Concurso de méritos", True),
    ("minima cuantia", "Mínima cuantía", True),
    ("^contratacion directa", "Contratación directa", False),
    ("regimen especial", "Régimen especial", False),
    ("^enajenacion", "Enajenación de bienes", True),
]


def _grupo_modalidad(col):
    n = _norm(col)
    g = F.lit(SIN)
    comp = F.lit(None).cast("boolean")
    for patron, grupo, competitiva in reversed(GRUPOS_MODALIDAD):
        g = F.when(n.rlike(patron), F.lit(grupo)).otherwise(g)
        comp = F.when(n.rlike(patron), F.lit(competitiva)).otherwise(comp)
    # Directa y régimen especial "con ofertas" sí reciben ofertas de varios proponentes
    comp = F.when(n.rlike("con ofertas"), F.lit(True)).otherwise(comp)
    return g, comp


def dim_modalidad(procesos, contratos):
    nulos = procesos.sparkSession.range(1).select(F.lit(None).cast("string").alias("modalidad"),
                                                  F.lit(None).cast("string").alias("tipo_contrato"))
    c = (procesos.select("modalidad", "tipo_contrato")
         .unionByName(contratos.select("modalidad", "tipo_contrato")).unionByName(nulos).distinct())
    grupo, competitiva = _grupo_modalidad(F.col("modalidad"))
    return (c.select(_mod_key(F.col("modalidad"), F.col("tipo_contrato")).alias("modalidad_key"),
                     _txt(F.col("modalidad")).alias("modalidad"),
                     grupo.alias("modalidad_grupo"),
                     competitiva.alias("es_competitiva"),
                     _txt(F.col("tipo_contrato")).alias("tipo_contrato"))
            .dropDuplicates(["modalidad_key"]))


def dim_entidad(procesos, contratos):
    """Atributos tipo 1 (el valor más reciente conocido), de procesos y contratos."""
    p = procesos.select(F.col("nit_entidad"), F.col("nombre_entidad"), F.col("orden_entidad").alias("orden"),
                        F.col("sector_entidad").alias("sector"), F.col("departamento_entidad").alias("d"),
                        F.col("ciudad_entidad").alias("c"), F.col("fecha_publicacion").alias("f"))
    c = contratos.select("nit_entidad", "nombre_entidad", "orden", "sector",
                         F.col("departamento").alias("d"), F.col("ciudad").alias("c"),
                         F.to_date("fecha_firma").alias("f"))
    u = p.unionByName(c).filter(F.col("nit_entidad").isNotNull())
    # El lugar se toma como pareja (para que depto y ciudad sean coherentes)
    lugar = F.when(F.col("d").isNotNull(), F.struct(F.col("d").alias("d"), F.col("c").alias("c")))
    e = (u.groupBy("nit_entidad")
          .agg(_ultimo(F.col("nombre_entidad"), F.col("f")).alias("nombre_entidad"),
               _ultimo(F.col("orden"), F.col("f")).alias("orden_entidad"),
               _ultimo(F.col("sector"), F.col("f")).alias("sector_entidad"),
               _ultimo(lugar, F.col("f")).alias("_lugar")))
    e = e.select(
        F.col("nit_entidad").alias("entidad_key"),
        "nit_entidad",
        _txt(F.col("nombre_entidad")).alias("nombre_entidad"),
        _txt(F.col("orden_entidad")).alias("orden_entidad"),
        _txt(F.col("sector_entidad")).alias("sector_entidad"),
        _geo_key(_norm(F.col("_lugar.d")), _norm(F.col("_lugar.c"))).alias("geografia_key"))
    spark = procesos.sparkSession
    desconocido = spark.createDataFrame([(SIN_KEY, None, SIN, SIN, SIN)],
                                        "entidad_key string, nit_entidad string, nombre_entidad string, "
                                        "orden_entidad string, sector_entidad string") \
        .withColumn("geografia_key", _geo_key(F.lit(None).cast("string"), F.lit(None).cast("string")))
    return e.unionByName(desconocido)


def dim_proveedor(proponentes, contratos, proveedores, procesos):
    """Registro de proveedores primero; para llaves que no están en el registro, lo más reciente
    visto en participaciones o contratos. Nunca guarda el nombre de una persona natural."""
    vistos = (proponentes.select("proveedor_key", "tipo_proveedor", "es_persona_juridica", "nombre_proveedor",
                                 F.lit(None).cast("boolean").alias("es_pyme"),
                                 F.col("fecha_publicacion").alias("f"))
              .unionByName(contratos.select("proveedor_key", "tipo_proveedor", "es_persona_juridica",
                                            "nombre_proveedor", "es_pyme", F.to_date("fecha_firma").alias("f")))
              .unionByName(procesos.filter(F.col("ganador_proveedor_key").isNotNull())
                           .select(F.col("ganador_proveedor_key").alias("proveedor_key"),
                                   F.lit(None).cast("string").alias("tipo_proveedor"),
                                   F.lit(None).cast("boolean").alias("es_persona_juridica"),
                                   F.lit(None).cast("string").alias("nombre_proveedor"),
                                   F.lit(None).cast("boolean").alias("es_pyme"),
                                   F.col("fecha_publicacion").alias("f")))
              .filter(F.col("proveedor_key").isNotNull())
              .groupBy("proveedor_key")
              .agg(_ultimo(F.col("tipo_proveedor"), F.col("f")).alias("v_tipo"),
                   _ultimo(F.col("es_persona_juridica"), F.col("f")).alias("v_pj"),
                   _ultimo(F.col("nombre_proveedor"), F.col("f")).alias("v_nombre"),
                   _ultimo(F.col("es_pyme"), F.col("f")).alias("v_pyme")))

    reg = proveedores.select(
        "proveedor_key", F.col("tipo_proveedor").alias("r_tipo"), F.col("es_persona_juridica").alias("r_pj"),
        F.col("nombre_proveedor").alias("r_nombre"), F.col("es_pyme").alias("r_pyme"), "tipo_empresa",
        "departamento", "municipio", "unspsc_familia_declarada", "fecha_registro", "esta_activa",
        "es_usuario_objetivo", F.lit(True).alias("en_registro"))

    p = vistos.join(reg, "proveedor_key", "full")
    tipo = F.coalesce(F.col("r_tipo"), F.col("v_tipo"))
    pj = F.coalesce(F.col("r_pj"), F.col("v_pj"))
    es_natural = (tipo == "persona_natural") | (pj == F.lit(False))
    nombre = F.when(es_natural, F.lit(None)).otherwise(F.coalesce(F.col("r_nombre"), F.col("v_nombre")))
    p = p.select(
        "proveedor_key",
        _txt(tipo).alias("tipo_proveedor"),
        pj.alias("es_persona_juridica"),
        F.when(es_natural, F.lit("Persona natural")).otherwise(_txt(nombre)).alias("nombre_proveedor"),
        F.coalesce(F.col("r_pyme"), F.col("v_pyme")).alias("es_pyme"),
        _txt(F.col("tipo_empresa")).alias("tipo_empresa"),
        _geo_key(_norm(F.col("departamento")), _norm(F.col("municipio"))).alias("geografia_key"),
        _txt(F.col("unspsc_familia_declarada")).alias("unspsc_familia_declarada"),
        "fecha_registro",
        "esta_activa",
        "es_usuario_objetivo",
        F.coalesce(F.col("en_registro"), F.lit(False)).alias("en_registro"))
    spark = proponentes.sparkSession
    desconocido = (spark.createDataFrame(
        [(SIN_KEY, SIN, None, SIN, None, SIN, SIN, None, None, None, False)],
        "proveedor_key string, tipo_proveedor string, es_persona_juridica boolean, nombre_proveedor string, "
        "es_pyme boolean, tipo_empresa string, unspsc_familia_declarada string, fecha_registro date, "
        "esta_activa boolean, es_usuario_objetivo boolean, en_registro boolean")
        .withColumn("geografia_key", _geo_key(F.lit(None).cast("string"), F.lit(None).cast("string"))))
    return p.unionByName(desconocido)


# ----------------------------------------------------------------------------- hechos
def fact_procesos(procesos):
    p = procesos
    return p.select(
        "id_proceso", "id_portafolio",
        F.coalesce("nit_entidad", F.lit(SIN_KEY)).alias("entidad_key"),
        _geo_key(_norm(F.col("departamento_entidad")), _norm(F.col("ciudad_entidad"))).alias("geografia_key"),
        _cat_key(F.col("unspsc_segmento"), F.col("unspsc_familia"), F.col("unspsc_clase")).alias("categoria_key"),
        _mod_key(F.col("modalidad"), F.col("tipo_contrato")).alias("modalidad_key"),
        _fecha_key(F.col("fecha_publicacion")).alias("fecha_publicacion_key"),
        _fecha_key(F.col("fecha_limite_ofertas")).alias("fecha_limite_ofertas_key"),
        _fecha_key(F.col("fecha_adjudicacion")).alias("fecha_adjudicacion_key"),
        F.coalesce("ganador_proveedor_key", F.lit(SIN_KEY)).alias("ganador_proveedor_key"),
        "estado",
        F.when(F.col("estado") == "abierto", 1).otherwise(0).alias("es_abierto"),
        F.when(F.col("estado") == "adjudicado", 1).otherwise(0).alias("es_adjudicado"),
        F.when(F.col("estado") == "cancelado", 1).otherwise(0).alias("es_cancelado"),
        F.when(F.col("n_proponentes") == 1, 1).otherwise(0).alias("es_unico_oferente"),
        "n_proponentes", "n_ganadores",
        "precio_base", "valor_adjudicacion",
        "duracion_dias", "dias_para_ofertar", "numero_lotes",
        F.coalesce(_int(F.col("precio_atipico")), F.lit(0)).alias("precio_atipico"),
        F.coalesce(_int(F.col("valor_atipico")), F.lit(0)).alias("valor_atipico"),
        F.when(F.col("unspsc_familia").isNull(), 1).otherwise(0).alias("sin_categoria"),
        "url_proceso",
        "fecha_publicacion")


def fact_participaciones(proponentes, f_procesos):
    llaves = f_procesos.select("id_proceso", "entidad_key", "geografia_key", "categoria_key",
                               "modalidad_key", "fecha_publicacion_key",
                               F.col("precio_base").alias("precio_base_proceso"),
                               F.col("n_proponentes").alias("n_proponentes_proceso"))
    p = proponentes.select("id_proceso", "proveedor_key", "es_ganador", "fecha_publicacion")
    return (p.join(llaves, "id_proceso", "left")
             .select("id_proceso",
                     F.coalesce("proveedor_key", F.lit(SIN_KEY)).alias("proveedor_key"),
                     F.coalesce("entidad_key", F.lit(SIN_KEY)).alias("entidad_key"),
                     F.coalesce("geografia_key", _geo_key(F.lit(None).cast("string"),
                                                          F.lit(None).cast("string"))).alias("geografia_key"),
                     F.coalesce("categoria_key", _cat_key(F.lit(None), F.lit(None), F.lit(None))).alias("categoria_key"),
                     F.coalesce("modalidad_key", _mod_key(F.lit(None), F.lit(None))).alias("modalidad_key"),
                     F.coalesce("fecha_publicacion_key", _fecha_key(F.col("fecha_publicacion"))).alias("fecha_publicacion_key"),
                     F.coalesce(_int(F.col("es_ganador")), F.lit(0)).alias("es_ganador"),
                     "precio_base_proceso", "n_proponentes_proceso",
                     "fecha_publicacion"))


def fact_contratos(contratos):
    c = contratos.withColumn("_firma", F.to_date("fecha_firma"))
    # Mediana del valor de los contratos de la entidad en el año de firma
    w = Window.partitionBy("nit_entidad", F.year("_firma"))
    c = c.withColumn("_mediana", F.percentile_approx(
        F.when(F.col("valor_contrato") > 0, F.col("valor_contrato")).cast("double"), 0.5).over(w))
    absoluto = F.col("valor_contrato") > UMBRAL_VALOR_ATIPICO
    relativo = ((F.col("valor_contrato") > UMBRAL_RELATIVO_MIN)
                & (F.col("valor_contrato") > F.col("_mediana") * VECES_MEDIANA))
    c = c.withColumn("_motivo", F.when(absoluto, "absoluto").when(relativo, "relativo"))
    return c.select(
        "id_contrato", "id_portafolio",
        F.coalesce("nit_entidad", F.lit(SIN_KEY)).alias("entidad_key"),
        F.coalesce("proveedor_key", F.lit(SIN_KEY)).alias("proveedor_key"),
        _geo_key(_norm(F.col("departamento")), _norm(F.col("ciudad"))).alias("geografia_key"),
        _cat_key(F.col("unspsc_segmento"), F.col("unspsc_familia"), F.col("unspsc_clase")).alias("categoria_key"),
        _mod_key(F.col("modalidad"), F.col("tipo_contrato")).alias("modalidad_key"),
        _fecha_key(F.col("_firma")).alias("fecha_firma_key"),
        _fecha_key(F.col("fecha_inicio")).alias("fecha_inicio_key"),
        _fecha_key(F.col("fecha_fin")).alias("fecha_fin_key"),
        _txt(F.col("estado_contrato")).alias("estado_contrato"),
        "valor_contrato", "duracion_dias",
        F.when(F.col("_motivo").isNotNull(), 1).otherwise(0).alias("valor_atipico"),
        F.col("_motivo").alias("motivo_atipico"),
        F.coalesce(_int(F.col("es_cedido")), F.lit(0)).alias("es_cedido"),
        F.coalesce(_int(F.col("con_proceso")), F.lit(0)).alias("con_proceso"),
        F.col("es_pyme").alias("es_pyme_al_firmar"),
        F.col("_firma").alias("fecha_firma"))


# ----------------------------------------------------------------------------- armado y validación
def construir(spark, procesos, proponentes, contratos, proveedores):
    fp = fact_procesos(procesos)
    return {
        "dim_fecha": dim_fecha(spark),
        "dim_geografia": dim_geografia(procesos, contratos, proveedores),
        "dim_categoria": dim_categoria(procesos, contratos),
        "dim_modalidad": dim_modalidad(procesos, contratos),
        "dim_entidad": dim_entidad(procesos, contratos),
        "dim_proveedor": dim_proveedor(proponentes, contratos, proveedores, procesos),
        "fact_procesos": fp,
        "fact_participaciones": fact_participaciones(proponentes, fp),
        "fact_contratos": fact_contratos(contratos),
    }

# ----------------------------------------------------------------------------- tablas del dashboard
# Guardan sumas y conteos (no promedios) para que la web pueda volver a agregar sin error:
#   oferentes promedio = suma_oferentes / procesos_con_oferentes
#   % oferente único   = procesos_unico_oferente / procesos_con_oferentes
def _procesos_enriquecidos(t):
    return (t["fact_procesos"]
            .join(t["dim_fecha"].select(F.col("fecha_key").alias("fecha_publicacion_key"), "anio", "mes",
                                        "anio_mes", "semana_iso", "fecha"), "fecha_publicacion_key")
            .join(t["dim_geografia"].select("geografia_key", "departamento"), "geografia_key")
            .join(t["dim_modalidad"].select("modalidad_key", "modalidad_grupo", "es_competitiva"), "modalidad_key")
            .join(t["dim_categoria"].select("categoria_key", "segmento_codigo"), "categoria_key"))


def _metricas_procesos():
    adj = F.col("es_adjudicado") == 1
    con_of = adj & F.col("n_proponentes").isNotNull()
    return [
        F.count("*").alias("procesos_publicados"),
        F.sum("es_adjudicado").alias("procesos_adjudicados"),
        F.sum("es_cancelado").alias("procesos_cancelados"),
        F.sum(F.when(F.col("precio_atipico") == 0, F.col("precio_base"))).alias("valor_ofertado"),
        F.sum(F.when(adj & (F.col("valor_atipico") == 0), F.col("valor_adjudicacion"))).alias("valor_adjudicado"),
        F.sum(F.when(con_of, 1).otherwise(0)).alias("procesos_con_oferentes"),
        F.sum(F.when(con_of, F.col("n_proponentes"))).alias("suma_oferentes"),
        F.sum(F.when(con_of & (F.col("n_proponentes") == 1), 1).otherwise(0)).alias("procesos_unico_oferente"),
    ]


def mercado_mensual(t):
    """Mes × departamento × grupo de modalidad × segmento UNSPSC (según la fecha de publicación)."""
    p = _procesos_enriquecidos(t).filter(F.col("fecha_publicacion_key") != -1)
    return (p.groupBy("anio_mes", "anio", "mes", "departamento", "modalidad_grupo", "es_competitiva",
                      "segmento_codigo")
             .agg(*_metricas_procesos()))


def competencia_entidad(t):
    """Entidad × año: competencia en sus procesos y concentración de su contratación (HHI).
    contratos, valor y HHI excluyen contratos con valor atípico (absoluto: > 100 mil millones; relativo:
    > 10 mil millones y > 1.000 veces la mediana de la entidad ese año), que se cuentan aparte."""
    p = (_procesos_enriquecidos(t).filter(F.col("anio").isNotNull())
         .groupBy("entidad_key", "anio").agg(*_metricas_procesos()))

    todos = (t["fact_contratos"]
             .join(t["dim_fecha"].select(F.col("fecha_key").alias("fecha_firma_key"), "anio"), "fecha_firma_key")
             .filter(F.col("anio").isNotNull() & (F.col("valor_contrato") > 0)))
    atip = (todos.filter("valor_atipico = 1").groupBy("entidad_key", "anio")
                 .agg(F.count("*").alias("contratos_valor_atipico")))
    c = todos.filter("valor_atipico = 0")
    por_prov = (c.filter(F.col("proveedor_key") != SIN_KEY)
                 .groupBy("entidad_key", "anio", "proveedor_key").agg(F.sum("valor_contrato").alias("v")))
    w = Window.partitionBy("entidad_key", "anio")
    conc = (por_prov.withColumn("cuota", F.col("v") / F.sum("v").over(w))
                    .groupBy("entidad_key", "anio")
                    .agg(F.countDistinct("proveedor_key").alias("proveedores_distintos"),
                         F.sum(F.col("cuota") * F.col("cuota")).cast("double").alias("hhi_valor"),
                         F.max("cuota").cast("double").alias("cuota_proveedor_principal")))
    ctot = c.groupBy("entidad_key", "anio").agg(F.count("*").alias("contratos"),
                                                F.sum("valor_contrato").alias("valor_contratos"))

    e = t["dim_entidad"].join(t["dim_geografia"].select("geografia_key", "departamento"), "geografia_key", "left")
    ctot = ctot.join(atip, ["entidad_key", "anio"], "full")
    r = (p.join(ctot, ["entidad_key", "anio"], "full").join(conc, ["entidad_key", "anio"], "left")
          .join(e.select("entidad_key", "nombre_entidad", "orden_entidad", "sector_entidad", "departamento"),
                "entidad_key", "left"))
    ceros = ["procesos_publicados", "procesos_adjudicados", "procesos_cancelados", "procesos_con_oferentes",
             "procesos_unico_oferente", "contratos", "contratos_valor_atipico"]
    return r.fillna(0, subset=ceros).select(
        "entidad_key", "nombre_entidad", "orden_entidad", "sector_entidad", "departamento", "anio",
        *ceros[:3], "valor_ofertado", "valor_adjudicado", "procesos_con_oferentes", "suma_oferentes",
        "procesos_unico_oferente", "contratos", "valor_contratos", "contratos_valor_atipico",
        "proveedores_distintos", "hhi_valor",
        "cuota_proveedor_principal")


def calidad_fuente(t):
    """Semana de publicación: volumen y completitud de lo que llega de SECOP."""
    p = _procesos_enriquecidos(t).filter(F.col("fecha").isNotNull())
    semana = F.date_sub(F.col("fecha"), ((F.dayofweek("fecha") + 5) % 7))   # lunes de esa semana
    return (p.withColumn("semana_inicio", semana)
             .groupBy("semana_inicio")
             .agg(F.count("*").alias("procesos_publicados"),
                  F.sum("sin_categoria").alias("procesos_sin_categoria"),
                  F.sum(F.when(F.col("departamento") == SIN, 1).otherwise(0)).alias("procesos_sin_departamento"),
                  F.sum(F.when(F.col("precio_base").isNull(), 1).otherwise(0)).alias("procesos_sin_precio"),
                  F.sum("precio_atipico").alias("procesos_precio_atipico"),
                  F.sum("es_abierto").alias("procesos_abiertos_hoy"))
             .withColumn("pct_sin_categoria",
                         F.round(F.col("procesos_sin_categoria") / F.col("procesos_publicados"), 4))
             .withColumn("anio", F.year("semana_inicio"))
             .withColumn("semana_iso", F.weekofyear("semana_inicio")))


def desempeno_recomendaciones(t, recomendaciones):
    """Día de corte × lista: resultado real de lo recomendado, cada tasa sobre la base donde ya se conoce.
      * se_presento se mide solo en procesos que ya tienen proponentes publicados en plata
        (antes de eso no se sabe quién ofertó);
      * gano se mide solo en procesos adjudicados;
      * ganes_esperados = suma de P(gana) donde la empresa se presentó y el proceso ya se adjudicó;
        compararlo con gano mide la calibración del G1 en producción;
      * cobertura = de las participaciones reales (empresas puntuadas ese día que ofertaron en procesos
        recomendados ese día y con proponentes), qué fracción estaba recomendada en esta lista;
      * precision_empresas_activas = se_presento sobre las recomendaciones a empresas que ofertaron en
        alguno de esos procesos (comparable con la evaluación de ML, que mide sobre empresas activas)."""
    r = recomendaciones.withColumn("fecha_corte", F.to_date(F.col("fecha_corte").cast("string")))
    ultima = r.groupBy("fecha_corte").agg(F.max("version_id").alias("version_id"))   # una versión por día
    r = r.join(ultima, ["fecha_corte", "version_id"])
    estado = t["fact_procesos"].select("id_proceso", "estado")
    con_prop = t["fact_participaciones"].select("id_proceso").distinct().withColumn("tiene_proponentes", F.lit(1))
    part = t["fact_participaciones"].select("id_proceso", "proveedor_key", F.lit(1).alias("se_presento"),
                                            F.col("es_ganador").alias("gano"))
    x = (r.join(estado, "id_proceso", "left")
          .join(con_prop, "id_proceso", "left")
          .join(part, ["id_proceso", "proveedor_key"], "left")
          .withColumn("tiene_proponentes", F.coalesce("tiene_proponentes", F.lit(0)))
          .withColumn("adjudicado", F.when(F.col("estado") == "adjudicado", 1).otherwise(0))
          .withColumn("se_presento", F.coalesce("se_presento", F.lit(0)))
          .withColumn("gano", F.coalesce("gano", F.lit(0))))
    conp = F.col("tiene_proponentes") == 1
    adj = F.col("adjudicado") == 1
    pres = F.col("se_presento") == 1

    # Base comparable con la evaluación de ML: participaciones reales del día, es decir, empresas
    # puntuadas ese día que ofertaron en procesos (recomendados a alguien ese día) que ya tienen proponentes.
    emp_dia = r.select("fecha_corte", "proveedor_key").distinct()
    proc_dia = x.filter(conp).select("fecha_corte", "id_proceso").distinct()
    reales = (proc_dia.join(t["fact_participaciones"].select("id_proceso", "proveedor_key"), "id_proceso")
                      .join(emp_dia, ["fecha_corte", "proveedor_key"]))
    n_reales = reales.groupBy("fecha_corte").agg(F.count("*").alias("participaciones_reales"))
    activas = reales.select("fecha_corte", "proveedor_key").distinct().withColumn("_activa", F.lit(1))
    x = x.join(activas, ["fecha_corte", "proveedor_key"], "left")
    act = F.col("_activa") == 1

    return (x.groupBy("fecha_corte", "lista")
             .agg(F.countDistinct("proveedor_key").alias("empresas"),
                  F.count("*").alias("recomendaciones"),
                  F.sum(F.when(F.col("estado") == "abierto", 1).otherwise(0)).alias("recomendaciones_abiertas"),
                  F.sum("tiene_proponentes").alias("recomendaciones_con_proponentes"),
                  F.sum(F.when(conp & pres, 1).otherwise(0)).alias("se_presento"),
                  F.sum("adjudicado").alias("recomendaciones_adjudicadas"),
                  F.sum(F.when(adj & pres, 1).otherwise(0)).alias("se_presento_adjudicadas"),
                  F.sum(F.when(adj & pres, F.col("gano")).otherwise(0)).alias("gano"),
                  F.sum(F.when(adj & pres, F.col("probabilidad"))).cast("double").alias("ganes_esperados"),
                  F.sum(F.when(conp & act, 1).otherwise(0)).alias("recomendaciones_empresas_activas"),
                  F.avg("probabilidad").cast("double").alias("probabilidad_media"))
             .join(n_reales, "fecha_corte", "left")
             .fillna(0, subset=["participaciones_reales"])
             .withColumn("cobertura",
                         F.round(F.when(F.col("participaciones_reales") > 0,
                                        F.col("se_presento") / F.col("participaciones_reales")), 4))
             .withColumn("precision_empresas_activas",
                         F.round(F.when(F.col("recomendaciones_empresas_activas") > 0,
                                        F.col("se_presento") / F.col("recomendaciones_empresas_activas")), 4))
             .withColumn("tasa_presentacion",
                         F.round(F.when(F.col("recomendaciones_con_proponentes") > 0,
                                        F.col("se_presento") / F.col("recomendaciones_con_proponentes")), 4))
             .withColumn("tasa_gano",
                         F.round(F.when(F.col("se_presento_adjudicadas") > 0,
                                        F.col("gano") / F.col("se_presento_adjudicadas")), 4))
             .withColumn("dias_desde_corte", F.datediff(F.current_date(), F.col("fecha_corte"))))


def construir_dashboard(t, recomendaciones=None):
    d = {"mercado_mensual": mercado_mensual(t),
         "competencia_entidad": competencia_entidad(t),
         "calidad_fuente": calidad_fuente(t)}
    if recomendaciones is not None:
        d["desempeno_recomendaciones"] = desempeno_recomendaciones(t, recomendaciones)
    return d


def validar_dashboard(d, t):
    """Lo que suman las tablas del dashboard tiene que dar lo mismo que los hechos."""
    fallas, filas = [], {k: v.count() for k, v in d.items()}
    n_proc = t["fact_procesos"].filter("fecha_publicacion_key != -1").count()
    for k in ["mercado_mensual", "calidad_fuente"]:
        s = d[k].agg(F.sum("procesos_publicados")).collect()[0][0] or 0
        if s != n_proc:
            fallas.append(f"{k}: suma {s} procesos, fact_procesos tiene {n_proc}")
    s = d["competencia_entidad"].agg(F.sum("procesos_publicados")).collect()[0][0] or 0
    if s != n_proc:
        fallas.append(f"competencia_entidad: suma {s} procesos, fact_procesos tiene {n_proc}")
    dup = filas["competencia_entidad"] - d["competencia_entidad"].select("entidad_key", "anio").distinct().count()
    if dup:
        fallas.append(f"competencia_entidad: {dup} filas duplicadas por entidad y año")
    if "desempeno_recomendaciones" in d:
        malo = d["desempeno_recomendaciones"].filter(
            "se_presento > recomendaciones_con_proponentes OR gano > se_presento_adjudicadas "
            "OR se_presento_adjudicadas > se_presento OR se_presento > participaciones_reales "
            "OR se_presento > recomendaciones_empresas_activas").count()
        if malo:
            fallas.append(f"desempeno_recomendaciones: {malo} filas con conteos imposibles")
    if fallas:
        raise RuntimeError("Validación del dashboard falló:\n  - " + "\n  - ".join(fallas))
    return filas


LLAVES = {
    "dim_fecha": ["fecha_key"],
    "dim_geografia": ["geografia_key"],
    "dim_categoria": ["categoria_key"],
    "dim_modalidad": ["modalidad_key"],
    "dim_entidad": ["entidad_key"],
    "dim_proveedor": ["proveedor_key"],
    "fact_procesos": ["id_proceso"],
    "fact_participaciones": ["id_proceso", "proveedor_key"],
    "fact_contratos": ["id_contrato"],
}

# (hecho, columna) -> (dimensión, llave)
RELACIONES = [
    ("fact_procesos", "entidad_key", "dim_entidad", "entidad_key"),
    ("fact_procesos", "geografia_key", "dim_geografia", "geografia_key"),
    ("fact_procesos", "categoria_key", "dim_categoria", "categoria_key"),
    ("fact_procesos", "modalidad_key", "dim_modalidad", "modalidad_key"),
    ("fact_procesos", "fecha_publicacion_key", "dim_fecha", "fecha_key"),
    ("fact_procesos", "fecha_limite_ofertas_key", "dim_fecha", "fecha_key"),
    ("fact_procesos", "fecha_adjudicacion_key", "dim_fecha", "fecha_key"),
    ("fact_procesos", "ganador_proveedor_key", "dim_proveedor", "proveedor_key"),
    ("fact_participaciones", "proveedor_key", "dim_proveedor", "proveedor_key"),
    ("fact_participaciones", "entidad_key", "dim_entidad", "entidad_key"),
    ("fact_participaciones", "geografia_key", "dim_geografia", "geografia_key"),
    ("fact_participaciones", "categoria_key", "dim_categoria", "categoria_key"),
    ("fact_participaciones", "modalidad_key", "dim_modalidad", "modalidad_key"),
    ("fact_participaciones", "fecha_publicacion_key", "dim_fecha", "fecha_key"),
    ("fact_contratos", "entidad_key", "dim_entidad", "entidad_key"),
    ("fact_contratos", "proveedor_key", "dim_proveedor", "proveedor_key"),
    ("fact_contratos", "geografia_key", "dim_geografia", "geografia_key"),
    ("fact_contratos", "categoria_key", "dim_categoria", "categoria_key"),
    ("fact_contratos", "modalidad_key", "dim_modalidad", "modalidad_key"),
    ("fact_contratos", "fecha_firma_key", "dim_fecha", "fecha_key"),
    ("fact_contratos", "fecha_inicio_key", "dim_fecha", "fecha_key"),
    ("fact_contratos", "fecha_fin_key", "dim_fecha", "fecha_key"),
    ("dim_entidad", "geografia_key", "dim_geografia", "geografia_key"),
    ("dim_proveedor", "geografia_key", "dim_geografia", "geografia_key"),
]


def validar(t, fuentes):
    """Devuelve {tabla: filas}. Lanza error con la lista completa de fallas si algo no cuadra."""
    fallas, filas = [], {k: v.count() for k, v in t.items()}

    for tabla, llave in LLAVES.items():
        nulas = t[tabla].filter(" OR ".join(f"{c} IS NULL" for c in llave)).count()
        dup = filas[tabla] - t[tabla].select(*llave).distinct().count()
        if nulas or dup:
            fallas.append(f"{tabla}: llave {llave} con {nulas} nulas y {dup} duplicadas")

    for hecho, col, dim, llave in RELACIONES:
        huerf = (t[hecho].select(F.col(col).alias("_k")).filter(F.col("_k").isNotNull()).distinct()
                 .join(t[dim].select(F.col(llave).alias("_k")), "_k", "left_anti").count())
        nulas = t[hecho].filter(F.col(col).isNull()).count()
        if huerf or nulas:
            fallas.append(f"{hecho}.{col} -> {dim}: {huerf} llaves sin dimensión, {nulas} nulas")

    # Los hechos tienen exactamente las filas de plata
    for hecho, fuente in [("fact_procesos", "procesos"), ("fact_participaciones", "proponentes"),
                          ("fact_contratos", "contratos")]:
        n = fuentes[fuente].count()
        if filas[hecho] != n:
            fallas.append(f"{hecho}: {filas[hecho]} filas, plata {fuente} tiene {n}")

    # Los valores suman igual que en plata
    for hecho, col, fuente in [("fact_procesos", "precio_base", "procesos"),
                               ("fact_procesos", "valor_adjudicacion", "procesos"),
                               ("fact_contratos", "valor_contrato", "contratos")]:
        a = t[hecho].agg(F.sum(col)).collect()[0][0]
        b = fuentes[fuente].agg(F.sum(col)).collect()[0][0]
        if a != b:
            fallas.append(f"{hecho}.{col}: suma {a} distinta de plata {b}")

    # Cada proceso adjudicado con participaciones tiene al menos un ganador marcado
    gan = t["fact_participaciones"].groupBy("id_proceso").agg(F.max("es_ganador").alias("g"))
    sin_gan = (t["fact_procesos"].filter("es_adjudicado = 1").select("id_proceso")
               .join(gan, "id_proceso").filter("g = 0").count())
    print(f"   Procesos adjudicados con participaciones pero sin ganador marcado: {sin_gan:,} (informativo)")

    if fallas:
        raise RuntimeError("Validación del modelo estrella falló:\n  - " + "\n  - ".join(fallas))
    return filas


# ----------------------------------------------------------------------------- job
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
            .set(f"spark.sql.catalog.{CAT}.warehouse", f"s3://{BUCKET}/gold/")
            .set("spark.sql.legacy.timeParserPolicy", "CORRECTED")
            .set("spark.sql.session.timeZone", "UTC"))
    sc = SparkContext.getOrCreate(conf=conf)
    spark = GlueContext(sc).spark_session

    inicio = datetime.now(timezone.utc)
    id_corrida = "oro-estrella-" + inicio.strftime("%Y%m%d-%H%M%S")
    print(f"== {id_corrida}")
    filas, snaps_oro, error = {}, {}, None

    try:
        fuentes, snaps = {}, {}
        for t in PLATA:
            nombre = f"{CAT}.secop_silver.{t}"
            snaps[t] = spark.sql(f"SELECT snapshot_id FROM {nombre}.snapshots "
                                 f"ORDER BY committed_at DESC LIMIT 1").collect()[0][0]
            fuentes[t] = spark.read.option("snapshot-id", snaps[t]).table(nombre)
        print("Snapshots de plata:", snaps)

        tablas = construir(spark, fuentes["procesos"], fuentes["proponentes"],
                           fuentes["contratos"], fuentes["proveedores"])
        tablas = {k: v.persist(StorageLevel.MEMORY_AND_DISK) for k, v in tablas.items()}

        filas = validar(tablas, fuentes)

        # Tablas del dashboard (las recomendaciones de MLOps son opcionales: si no existen, se omite)
        try:
            recs = spark.read.parquet(RUTA_RECOMENDACIONES)
            print(f"Recomendaciones leídas: {recs.count():,} filas")
        except Exception as e:
            recs = None
            print(f"AVISO: sin recomendaciones, se omite desempeno_recomendaciones ({str(e)[:200]})")
        dash = construir_dashboard(tablas, recs)
        dash = {k: v.persist(StorageLevel.MEMORY_AND_DISK) for k, v in dash.items()}
        filas.update(validar_dashboard(dash, tablas))
        tablas.update(dash)

        for k, n in filas.items():
            print(f"   {k:<26} {n:>12,}")
        print("Validaciones OK")

        # Se escribe solo si todo validó. Dimensiones primero, hechos después.
        for nombre_t, df in tablas.items():
            destino = f"{DB}.{nombre_t}"
            w = (df.writeTo(destino).using("iceberg")
                   .tableProperty("location", f"s3://{BUCKET}/gold/{nombre_t}/")
                   .tableProperty("format-version", "2")
                   .tableProperty("secop.id_corrida", id_corrida))
            for t, s in snaps.items():
                w = w.tableProperty(f"secop.snapshot_{t}", str(s))
            if PARTICION.get(nombre_t):
                w = w.partitionedBy(F.years(PARTICION[nombre_t]))
            w.createOrReplace()
            snaps_oro[nombre_t] = spark.sql(f"SELECT snapshot_id FROM {destino}.snapshots "
                                            f"ORDER BY committed_at DESC LIMIT 1").collect()[0][0]
            print(f"   escrita {destino}")
        estado = "exito"
    except Exception as e:
        estado, error = "fallo", str(e)[:1000]
        print(error)

    fin = datetime.now(timezone.utc)
    registros = []
    for nombre_t in list(LLAVES) + [k for k in DASHBOARD if k in filas or not filas]:
        n = filas.get(nombre_t)
        registros.append((
            id_corrida, args["JOB_NAME"], f"secop_gold.{nombre_t}",
            inicio.replace(tzinfo=None), fin.replace(tzinfo=None), estado,
            n, n, 0 if n is not None else None, {}, estado == "exito", None,
            snaps_oro.get(nombre_t), error))
    fila = spark.createDataFrame(
        registros,
        "id_corrida string, job string, tabla string, inicio timestamp, fin timestamp, estado string, "
        "filas_leidas long, filas_validas long, filas_rechazadas long, rechazos_por_motivo map<string,long>, "
        "cuadre_ok boolean, ultima_fecha_ingesta date, snapshot_id long, mensaje_error string")
    esquema = spark.table(TABLA_CONTROL).schema
    fila.select(*[F.col(f.name).cast(f.dataType) for f in esquema.fields]).writeTo(TABLA_CONTROL).append()
    print(f"== Registrado en control_corridas: {estado} ({len(registros)} tablas)")
    if estado != "exito":
        raise RuntimeError(error)


if __name__ == "__main__":
    main()
