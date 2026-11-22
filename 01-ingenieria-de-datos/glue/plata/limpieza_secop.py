"""
Funciones de limpieza comunes para la capa plata de SECOP II (fase E, paso E2).

Todas devuelven expresiones de columna de Spark (pyspark.sql.Column), sin UDF de Python:
Spark las ejecuta de forma nativa y en paralelo sobre millones de filas.

Cada función indica el hallazgo que resuelve (ver el informe de calidad y reglas de plata).
Uso en el job de Glue:
    import limpieza_secop as L
    df.withColumn("precio_base", L.dinero("precio_base"))

Requisito de la sesión de Spark (lo fija el job):
    spark.sql.legacy.timeParserPolicy = CORRECTED   -> una fecha mal escrita da nulo, no error
"""
from pyspark.sql import Column
from pyspark.sql import functions as F

# Textos de relleno que SECOP usa en lugar de un nulo (H06)
CENTINELAS = ["", "no definido", "no definida", "no aplica", "no adjudicado", "sin descripcion",
              "sin descripción", "n/a", "na", "null", "none", "-", "no provisto", "no provista"]

# Pesos del dígito de verificación de la DIAN (módulo 11), del dígito de la derecha a la izquierda
_PESOS_DV = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]

_CON_TILDE = "áéíóúüñÁÉÍÓÚÜÑàèìòùÀÈÌÒÙ"
_SIN_TILDE = "aeiouunAEIOUUNaeiouAEIOU"


def _c(col) -> Column:
    return F.col(col) if isinstance(col, str) else col


def _let(valor: Column, fn) -> Column:
    """
    Calcula 'valor' una sola vez y lo usa dentro de fn, como una variable.
    Sin esto, cada vez que una expresión reutiliza un resultado intermedio, Spark copia toda la
    expresión, y el código generado puede superar el límite de 64 KB de Java ('Code grows beyond 64 KB').
    """
    return F.element_at(F.transform(F.array(valor), fn), 1)


# ----------------------------------------------------------------------------- texto
def centinela_a_nulo(col) -> Column:
    """H06. Recorta espacios y convierte vacíos y textos de relleno en nulo."""
    c = F.trim(_c(col))
    return F.when(F.lower(c).isin(CENTINELAS), F.lit(None)).otherwise(c)


def texto_limpio(col) -> Column:
    """Descripción normalizada: minúsculas, sin tildes, solo letras, números y espacios simples."""
    c = F.translate(F.lower(centinela_a_nulo(col)), _CON_TILDE.lower(), _SIN_TILDE.lower())
    c = F.regexp_replace(c, r"[^a-z0-9 ]", " ")
    c = F.trim(F.regexp_replace(c, r"\s+", " "))
    return F.when(c == "", F.lit(None)).otherwise(c)


def booleano_si_no(col) -> Column:
    """'Si'/'Sí'/'No' a booleano; cualquier otro valor a nulo."""
    c = F.translate(F.lower(F.trim(_c(col))), "í", "i")
    return F.when(c == "si", True).when(c == "no", False).otherwise(F.lit(None).cast("boolean"))


def booleano(col) -> Column:
    """'Si'/'Sí'/'true'/'1' a true y 'No'/'false'/'0' a false; cualquier otro valor a nulo."""
    c = F.translate(F.lower(F.trim(_c(col))), "í", "i")
    return (F.when(c.isin("si", "true", "1", "verdadero", "yes"), True)
             .when(c.isin("no", "false", "0", "falso"), False)
             .otherwise(F.lit(None).cast("boolean")))


def entero(col) -> Column:
    """Texto a entero. Lo que no sea un número entero queda nulo."""
    c = F.trim(_c(col))
    return F.when(c.rlike(r"^-?[0-9]+(\.0+)?$"), F.regexp_extract(c, r"^(-?[0-9]+)", 1).cast("int"))


# ----------------------------------------------------------------------------- fechas (H07)
def fecha(col) -> Column:
    """
    Texto a date. Acepta los formatos de las dos fuentes:
      histórico CSV      MM/DD/YYYY  o  MM/DD/YYYY hh:mm:ss AM
      ingesta (API)      YYYY-MM-DDThh:mm:ss.sss
    Si ningún formato aplica, nulo.
    """
    c = F.trim(_c(col))
    return F.coalesce(
        F.to_date(c, "MM/dd/yyyy"),
        F.to_date(c, "MM/dd/yyyy hh:mm:ss a"),
        F.to_date(F.substring(c, 1, 10), "yyyy-MM-dd"),
    )


def fecha_hora(col) -> Column:
    """
    Texto a timestamp SIN zona horaria (timestamp_ntz): guarda la hora tal como está escrita,
    que en SECOP es hora de Colombia. Las columnas timestamp de las tablas Iceberg creadas en
    Athena son sin zona, así que este es el tipo que corresponde.
    Formatos: MM/DD/YYYY hh:mm:ss AM, YYYY-MM-DDThh:mm:ss(.sss), MM/DD/YYYY, YYYY-MM-DD.
    """
    c = F.trim(_c(col))
    return F.coalesce(
        F.to_timestamp_ntz(c, F.lit("MM/dd/yyyy hh:mm:ss a")),
        F.to_timestamp_ntz(F.substring(c, 1, 19), F.lit("yyyy-MM-dd'T'HH:mm:ss")),
        F.to_timestamp_ntz(c, F.lit("MM/dd/yyyy")),
        F.to_timestamp_ntz(F.substring(c, 1, 10), F.lit("yyyy-MM-dd")),
    )


def utc_a_colombia(col) -> Column:
    """
    Marca de tiempo de sistema de Socrata (:updated_at, en UTC, con 'Z') a hora de Colombia
    sin zona. Ejemplo: '2026-10-30T13:50:54.960Z' a 2026-10-30 08:50:54.960.
    """
    c = F.regexp_replace(F.trim(_c(col)), "Z$", "")
    utc = F.to_timestamp(c, "yyyy-MM-dd'T'HH:mm:ss.SSS")
    utc = F.coalesce(utc, F.to_timestamp(F.substring(c, 1, 19), "yyyy-MM-dd'T'HH:mm:ss"))
    return F.from_utc_timestamp(utc, "America/Bogota").cast("timestamp_ntz")


def ahora_colombia() -> Column:
    """Momento actual en hora de Colombia, sin zona (para fecha_carga)."""
    return F.from_utc_timestamp(F.current_timestamp(), "America/Bogota").cast("timestamp_ntz")


# ----------------------------------------------------------------------------- dinero (H09)
def dinero(col) -> Column:
    """
    Texto a decimal(18,2). Dos formatos:
      histórico CSV   $4.800.000 o $4.800.000,50  (punto de miles, coma decimal)
      ingesta (API)   4800000 o 4800000.50        (punto decimal)
    Valores en cero, negativos o no numéricos: nulo.
    """
    def convertir(s):
        csv = F.regexp_replace(F.regexp_replace(F.regexp_replace(s, r"\$", ""), r"\.", ""), ",", ".")
        return (F.when(s.rlike(r"^-?\$"), csv.cast("decimal(18,2)"))
                 .when(s.rlike(r"^-?[0-9]+(\.[0-9]+)?$"), s.cast("decimal(18,2)")))

    v = _let(F.regexp_replace(F.trim(_c(col)), r"\s", ""), convertir)
    return _let(v, lambda x: F.when(x > 0, x))


# ----------------------------------------------------------------------------- UNSPSC (H10)
def unspsc(col) -> Column:
    """'V1.80111701' u '80111701' a '80111701'; cualquier otra cosa a nulo."""
    v = F.regexp_extract(F.trim(_c(col)), r"^(?:V1\.)?([0-9]{8})$", 1)
    return F.when(v != "", v)


def unspsc_nivel(col_unspsc, digitos: int) -> Column:
    """Segmento (2), familia (4) o clase (6) a partir del UNSPSC ya limpio."""
    return F.substring(_c(col_unspsc), 1, digitos)


# ----------------------------------------------------------------------------- duración (H18)
_DIAS_POR_UNIDAD = [("dia", 1.0), ("semana", 7.0), ("mes", 30.0), ("ano", 365.0), ("hora", 1.0 / 24)]


def _factor(unidad) -> Column:
    u = F.translate(F.lower(F.trim(unidad)), "íñ", "in")
    expr = None
    for clave, factor in _DIAS_POR_UNIDAD:
        cond = u.startswith(clave)
        expr = F.when(cond, F.lit(factor)) if expr is None else expr.when(cond, F.lit(factor))
    return expr


def duracion_dias(col_numero, col_unidad) -> Column:
    """Procesos: número + unidad (día(s), mes(es), año(s)...) a días, redondeando hacia arriba."""
    n = F.regexp_replace(F.trim(_c(col_numero)), ",", ".").cast("double")
    d = F.ceil(n * _factor(_c(col_unidad)))
    return F.when(d > 0, d.cast("int"))


def duracion_dias_texto(col) -> Column:
    """Contratos: '306 Dia(s)' a 306."""
    c = F.trim(_c(col))
    return duracion_dias(F.regexp_extract(c, r"^([0-9]+(?:[.,][0-9]+)?)", 1),
                         F.regexp_extract(c, r"^[0-9.,]+\s*(.*)$", 1))


# ----------------------------------------------------------------------------- NIT e identidad (H05, H13)
def _dv_de_9_digitos(d9: Column) -> Column:
    """Dígito de verificación DIAN de un número de 9 dígitos (texto)."""
    def calcular(n):
        suma = None
        for i in range(9):  # i = posición desde la derecha
            termino = F.substring(n, 9 - i, 1).cast("int") * F.lit(_PESOS_DV[i])
            suma = termino if suma is None else suma + termino
        return _let(suma % 11, lambda r: F.when(r <= 1, r).otherwise(F.lit(11) - r))

    return _let(d9, calcular)


def nit_normalizado(col) -> Column:
    """
    NIT o documento a solo dígitos, sin DV y sin ceros a la izquierda.
      1. Si viene con guion ('900123456-1'), se descarta lo que sigue al guion.
      2. Si tiene 10 dígitos, empieza por 8 o 9 (rango de NIT de empresas) y el último dígito
         es el DV DIAN de los 9 primeros, se quita ese último dígito.
         Las cédulas de 10 dígitos empiezan por 1, así que nunca se recortan.
      3. Se quitan ceros a la izquierda. Vacíos y centinelas: nulo.
    """
    def digitos(c):
        base = F.when(c.rlike(r"^[0-9.,\s]+-\s*[0-9]\s*$"), F.regexp_extract(c, r"^([^-]+)-", 1)).otherwise(c)
        return F.regexp_replace(base, r"[^0-9]", "")

    def sin_dv(d):
        d9 = F.substring(d, 1, 9)
        pegado = (F.length(d) == 10) & d.rlike(r"^[89]") & (_dv_de_9_digitos(d9) == F.substring(d, 10, 1).cast("int"))
        return F.regexp_replace(F.when(pegado, d9).otherwise(d), r"^0+", "")

    r = _let(_let(centinela_a_nulo(col), digitos), sin_dv)
    return _let(r, lambda x: F.when(x != "", x))


def es_persona_juridica(col_nit_normalizado) -> Column:
    """NIT de empresa: 9 dígitos que empiezan por 8 o 9. Nulo si no hay NIT."""
    n = _c(col_nit_normalizado)
    return F.when(n.isNotNull(), n.rlike(r"^[89][0-9]{8}$"))


def proveedor_key(col_nit_normalizado, sal: str) -> Column:
    """H13. SHA-256 en hexadecimal de sal + NIT normalizado. Nulo si no hay NIT."""
    n = _c(col_nit_normalizado)
    return F.when(n.isNotNull(), F.sha2(F.concat(F.lit(sal), n), 256))


def codigo_proveedor(col) -> Column:
    """Código interno de proveedor de SECOP: solo dígitos ('700.006.091' a '700006091')."""
    d = F.regexp_replace(centinela_a_nulo(col), r"[^0-9]", "")
    return F.when(d != "", d)


# ----------------------------------------------------------------------------- identidad del proveedor (corrección 2.1)
MAX_CODIGOS_POR_NIT = 5
_RE_CONSORCIO = r"CONSORCIO|UNI[OÓ]N\s+TEMPORAL|^U\.?\s?T\.?\s|^CS\s|^UT\s"
_SUFIJOS = r"\b(s a s|sas|s a|sa|ltda|limitada|e u|eu|bic|e s p|esp|y cia|cia|s en c)\b"


def es_consorcio(col_nombre) -> Column:
    """Nombre de consorcio o unión temporal (CONSORCIO, UNIÓN TEMPORAL, U.T., prefijos CS y UT)."""
    return F.upper(F.trim(F.coalesce(_c(col_nombre), F.lit("")))).rlike(_RE_CONSORCIO)


def nit_confiable(col) -> Column:
    """NIT normalizado con 6 dígitos o más. Los NIT de relleno ('0', '1', '12345') quedan nulos."""
    return _let(nit_normalizado(col), lambda n: F.when(F.length(n) >= 6, n))


def nombre_base(col) -> Column:
    """Nombre comparable: sin tildes, signos, espacios ni sufijos societarios (S.A.S., LTDA...)."""
    c = F.regexp_replace(texto_limpio(col), _SUFIJOS, " ")
    c = F.regexp_replace(c, r"\s+", "")
    return F.when(c != "", c)


def nits_compartidos(proponentes_bronce, max_codigos: int = MAX_CODIGOS_POR_NIT):
    """
    Corrección 2.1. NIT que no identifican a una sola empresa: los usan más de max_codigos
    códigos de SECOP distintos y no tienen exactamente un nombre (varios nombres = NIT prestado;
    ningún nombre = NIT de relleno). Una empresa real con varias cuentas y un solo nombre no entra.
    Las filas de consorcios no cuentan: esas siempre se identifican por código.
    Recibe el bronce de proponentes (columnas nit_proveedor, codigo_proveedor, proveedor) y
    devuelve un DataFrame con la columna nit.
    """
    p = (proponentes_bronce
         .select(nit_confiable("nit_proveedor").alias("nit"),
                 codigo_proveedor("codigo_proveedor").alias("codigo"),
                 nombre_base("proveedor").alias("nombre"),
                 es_consorcio("proveedor").alias("consorcio"))
         .filter(F.col("nit").isNotNull() & F.col("codigo").isNotNull() & ~F.col("consorcio")))
    return (p.groupBy("nit")
             .agg(F.countDistinct("codigo").alias("codigos"), F.countDistinct("nombre").alias("nombres"))
             .filter((F.col("codigos") > max_codigos) & (F.col("nombres") != 1))
             .select("nit"))


# ----------------------------------------------------------------------------- lectura de bronce
def a_texto(df):
    """
    Deja todas las columnas como texto, igual que el histórico (esquema al leer).
    La API de Socrata entrega algunos campos como objetos JSON. Por ejemplo, las URL llegan como
    {"url": "https://..."}, mientras que en el CSV histórico son un texto simple. Para que las dos
    fuentes sean idénticas:
      - un objeto con un único campo 'url' se convierte en ese texto (igual al CSV);
      - cualquier otro objeto o lista se convierte en su texto JSON.
    """
    from pyspark.sql.types import StringType, StructType

    columnas = []
    for campo in df.schema.fields:
        c = F.col(f"`{campo.name}`")
        if isinstance(campo.dataType, StringType):
            columnas.append(c.alias(campo.name))
        elif isinstance(campo.dataType, StructType) and [f.name for f in campo.dataType.fields] == ["url"]:
            columnas.append(c.getField("url").cast("string").alias(campo.name))
        elif isinstance(campo.dataType, StructType) or campo.dataType.typeName() in ("array", "map"):
            columnas.append(F.to_json(c).alias(campo.name))
        else:
            columnas.append(c.cast("string").alias(campo.name))
    return df.select(*columnas)


def leer_ingesta(spark, bucket: str, carpeta: str, columnas=None):
    """
    Lee la ingesta diaria (JSON) directamente desde S3, no desde la tabla de Athena:
    las tablas raw_* usan partition projection, que solo entiende Athena; desde Spark
    aparecen vacías. La carpeta fecha=AAAA-MM-DD se convierte en la columna 'fecha'.
    Todo se lee como texto (esquema al leer). Si se piden columnas que no vienen en el
    JSON (Socrata omite los campos nulos), se agregan como nulas.
    """
    base = f"s3://{bucket}/bronze/{carpeta}/ingesta/"
    df = (spark.read.option("primitivesAsString", "true").option("basePath", base)
          .json(base + "fecha=*/"))
    df = a_texto(df)
    if columnas:
        df = df.select(*[F.col(f"`{c}`") if c in df.columns else F.lit(None).cast("string").alias(c)
                         for c in columnas])
    return df


# ----------------------------------------------------------------------------- rechazados
def registro_json(df, sal: str, columnas_hash=(), columnas_excluir=()) -> Column:
    """
    Fila original de bronce como JSON para las tablas de rechazados, sin datos personales:
    columnas_hash se reemplazan por el hash de su valor normalizado y columnas_excluir no se incluyen.
    """
    campos = []
    for nombre in df.columns:
        if nombre in columnas_excluir:
            continue
        if nombre in columnas_hash:
            campos.append(proveedor_key(nit_normalizado(nombre), sal).alias(nombre))
        else:
            campos.append(F.col(nombre))
    return F.to_json(F.struct(*campos))


# ----------------------------------------------------------------------------- autoprueba
def autoprueba(spark) -> bool:
    """Casos de prueba de cada función. Imprime el resultado y devuelve True si todos pasan."""
    from datetime import date, datetime
    from decimal import Decimal

    casos = [
        # (función, entrada, esperado)
        ("centinela_a_nulo", "  No Definido ", None),
        ("centinela_a_nulo", "ACME S.A.S", "ACME S.A.S"),
        ("centinela_a_nulo", "   ", None),
        ("centinela_a_nulo", "No Provisto", None),
        ("texto_limpio", "Prestación de SERVICIOS, área (Medellín)", "prestacion de servicios area medellin"),
        ("booleano_si_no", "Sí", True),
        ("booleano_si_no", "No", False),
        ("booleano_si_no", "No Definido", None),
        ("entero", "12", 12),
        ("entero", "abc", None),
        ("fecha", "08/16/2026", date(2026, 8, 16)),
        ("fecha", "01/20/2018 12:48:11 AM", date(2018, 1, 20)),
        ("fecha", "2026-10-29T12:31:07.472", date(2026, 10, 29)),
        ("fecha", "13/45/2018", None),
        ("fecha", "No Definido", None),
        ("fecha_hora", "01/20/2018 12:48:11 PM", datetime(2018, 1, 20, 12, 48, 11)),
        ("fecha_hora", "2026-10-29T12:31:07.472", datetime(2026, 10, 29, 12, 31, 7)),
        ("utc_a_colombia", "2026-10-30T13:50:54.960Z", datetime(2026, 10, 30, 8, 50, 54, 960000)),
        ("dinero", "$4.800.000", Decimal("4800000.00")),
        ("dinero", "$4.800.000,50", Decimal("4800000.50")),
        ("dinero", "4800000.5", Decimal("4800000.50")),
        ("dinero", "$0", None),
        ("dinero", "-$1.000", None),
        ("dinero", "abc", None),
        ("unspsc", "V1.80111701", "80111701"),
        ("unspsc", "80111701", "80111701"),
        ("unspsc", "V1.123", None),
        ("unspsc", "No definido", None),
        ("nit_normalizado", "899,999,239", "899999239"),
        ("nit_normalizado", "900.123.456-7", "900123456"),
        ("nit_normalizado", "8001972684", "800197268"),      # DV 4 pegado y válido: se quita
        ("nit_normalizado", "8001972685", "8001972685"),     # último dígito no es el DV: se conserva
        ("nit_normalizado", "1026275627", "1026275627"),     # cédula de 10 dígitos: nunca se recorta
        ("nit_normalizado", "000900123456", "900123456"),
        ("nit_normalizado", "No Definido", None),
        ("codigo_proveedor", "700.006.091", "700006091"),
        ("codigo_proveedor", "No Definido", None),
        ("booleano", "true", True),
        ("booleano", "No", False),
        ("booleano", "No Definido", None),
        ("nit_confiable", "1", None),
        ("nit_confiable", "000000000", None),
        ("nit_confiable", "900.123.456-7", "900123456"),
        ("es_consorcio", "CONSORCIO VIAS 2024", True),
        ("es_consorcio", "Unión Temporal Salud", True),
        ("es_consorcio", "CS CALDAS JINT 5", True),
        ("es_consorcio", "UT ALIMENTOS", True),
        ("es_consorcio", "CSA LTDA", False),
        ("es_consorcio", "JPS INGENIERIA S.A.S.", False),
        ("nombre_base", "JPS Ingeniería S.A.S.", "jpsingenieria"),
        ("nombre_base", "JPS INGENIERIA SAS", "jpsingenieria"),
    ]
    fn = {
        "centinela_a_nulo": centinela_a_nulo, "texto_limpio": texto_limpio, "booleano_si_no": booleano_si_no,
        "entero": entero, "fecha": fecha, "fecha_hora": fecha_hora, "utc_a_colombia": utc_a_colombia, "dinero": dinero, "unspsc": unspsc,
        "nit_normalizado": nit_normalizado, "codigo_proveedor": codigo_proveedor,
        "nit_confiable": nit_confiable, "es_consorcio": es_consorcio, "nombre_base": nombre_base,
        "booleano": booleano,
    }
    df = spark.createDataFrame([(i, c[1]) for i, c in enumerate(casos)], "i int, x string")
    sel = [F.col("i")] + [fn[nombre](F.col("x")).alias(nombre) for nombre in fn]
    filas = {r["i"]: r for r in df.select(*sel).collect()}

    extra = spark.createDataFrame(
        [("3", "mes(es)", "306 Dia(s)", "900123456")], "n string, u string, t string, nit string"
    ).select(duracion_dias("n", "u").alias("dur"), duracion_dias_texto("t").alias("dur_txt"),
             es_persona_juridica("nit").alias("pj"), proveedor_key("nit", "sal").alias("key"),
             proveedor_key(F.lit(None).cast("string"), "sal").alias("key_nula")).collect()[0]

    errores = 0
    for i, (nombre, entrada, esperado) in enumerate(casos):
        obtenido = filas[i][nombre]
        ok = obtenido == esperado
        errores += not ok
        print(f"[{'OK' if ok else 'FALLA'}] {nombre}({entrada!r}) = {obtenido!r}" + ("" if ok else f"  esperado {esperado!r}"))
    for nombre, obtenido, esperado in [("duracion_dias('3','mes(es)')", extra["dur"], 90),
                                       ("duracion_dias_texto('306 Dia(s)')", extra["dur_txt"], 306),
                                       ("es_persona_juridica('900123456')", extra["pj"], True),
                                       ("proveedor_key longitud", len(extra["key"]), 64),
                                       ("proveedor_key(nulo)", extra["key_nula"], None)]:
        ok = obtenido == esperado
        errores += not ok
        print(f"[{'OK' if ok else 'FALLA'}] {nombre} = {obtenido!r}" + ("" if ok else f"  esperado {esperado!r}"))
    print(f"== {len(casos) + 5 - errores} de {len(casos) + 5} pruebas correctas")
    return errores == 0
