# Fase 1 · Ingeniería de datos

Trae los datos abiertos de SECOP II, los limpia y los organiza en un lago medallón (bronce, plata y oro) sobre Amazon S3 con tablas Apache Iceberg, procesadas con AWS Glue y consultables con Amazon Athena.

## Fuentes

| Dataset (datos.gov.co) | Id Socrata | Carpeta en bronce | Una fila es |
|---|---|---|---|
| SECOP II · Procesos de Contratación | `p6dx-8zbt` | `procesos-contratacion` | un lote de un proceso |
| Proponentes por Proceso SECOP II | `hgi6-6wh3` | `proponentes-procesos` | una oferta de un proveedor |
| SECOP II · Contratos Electrónicos | `jbjy-vk9h` | `contratos-electronicos` | un contrato |
| SECOP II · Proveedores Registrados | `qmzu-gj57` | `proveedores-registrados` | una cuenta de proveedor |

Llaves que unen las cuatro tablas: `id_proceso` (proceso) y `proveedor_key` (hash SHA-256 del NIT normalizado o del código de proveedor).

**Hallazgos del EDA que definieron la limpieza:** una fila de procesos es un lote y no un proceso; el 50 % de las filas de proponentes está duplicado; en ~45 % de los procesos el NIT del ganador está vacío; el 57 % de los códigos de proveedor son consorcios; contratos trae datos personales.

## Contenido

```
01-ingenieria-de-datos/
├── ingesta/
│   └── lambda_function.py              Ingesta Socrata → bronce (ventanas por fecha, paginación keyset, verificación de conteos)
├── glue/
│   ├── bronce/
│   │   └── secop-bronze-historico-parquet.py   CSV histórico → Parquet con nombres técnicos
│   ├── plata/
│   │   ├── limpieza_secop.py           Funciones de limpieza comunes (Spark nativo, sin UDF)
│   │   ├── secop-silver-procesos.py    E3 · procesos
│   │   ├── secop-silver-proponentes.py E4 · proponentes
│   │   ├── secop-silver-proveedores.py proveedores registrados
│   │   ├── secop-silver-contratos.py   E5 · contratos
│   │   └── secop-silver-ganador.py     E6 · ganador y estado final
│   └── oro/
│       └── secop-gold-estrella.py      Modelo estrella + tablas del dashboard
├── sql/
│   ├── 00_bases.sql                    Bases del catálogo
│   ├── 01_bronce_ingesta.sql           Tablas de la ingesta incremental (NDJSON gzip, proyección por fecha)
│   ├── 02_plata.sql                    8 tablas Iceberg de plata (válidos y rechazados)
│   └── 03_control.sql                  secop_control.control_corridas
└── control/esquemas/                   Nombre visible → nombre técnico de cada columna, por dataset
```

## Arquitectura

```
datos.gov.co ──► BRONCE (S3)                 ──► PLATA (Iceberg)              ──► ORO (Iceberg)
                 carga-historica/  CSV            4 tablas + 4 de rechazados        6 dimensiones + 3 hechos
                 historico-parquet/ Parquet       llaves únicas                     4 tablas del dashboard
                 ingesta/fecha=…/  NDJSON gzip    cuadre por corrida                validación antes de escribir
                                    │                     │                                 │
                                    └──── secop_control.control_corridas (una fila por tabla y corrida) ┘
```

| Capa | Base del catálogo | Qué garantiza |
|---|---|---|
| Bronce | `secop_bronze` | Lo que llega, sin modificar. Se puede reprocesar sin volver a descargar |
| Plata | `secop_silver` | Tipos correctos, una fila por llave, sin personas naturales identificables, cada rechazo con su motivo |
| Oro | `secop_gold` | Modelo estrella sin llaves nulas y agregados listos para la web |
| Control | `secop_control` | Trazabilidad de cada corrida: filas leídas, válidas y rechazadas, `cuadre_ok` y `snapshot_id` |

## Bronce

- **Carga histórica:** los cuatro datasets exportados en CSV desde datos.gov.co se guardan en `bronze/<carpeta>/carga-historica/`. El job `secop-bronze-historico-parquet` los lee como texto, renombra las columnas visibles a los nombres técnicos de la API (con `control/esquemas/<carpeta>.json`), separa las filas corruptas y escribe Parquet en `bronze/<carpeta>/historico-parquet/`, registrado como `secop_bronze.raw_<tabla>_hist`. Resultado en procesos: 9.384.949 filas leídas, 0 corruptas, 59 columnas.
- **Ingesta incremental:** NDJSON en gzip con todas las columnas, en `bronze/<carpeta>/ingesta/fecha=<AAAA-MM-DD>/`. Se pide por una fecha de negocio de cada tabla (no por `:updated_at`, que datos.gov.co reescribe en lote sobre millones de filas), con paginación keyset y nombres de archivo deterministas: un reintento sobrescribe, no duplica. Cada mañana la corre el paso 0 del flujo nocturno ([`03-mlops/jobs/ingesta_recientes.py`](../03-mlops/jobs/ingesta_recientes.py)) sobre los últimos 45 días de las cuatro tablas. [`ingesta/lambda_function.py`](ingesta/lambda_function.py) implementa la misma ingesta por ventanas con verificación de conteos contra la fuente.

## Plata

Un solo camino para el histórico y la ingesta: los dos se unen antes de limpiar, así nunca hay diferencias entre fuentes. Cada job reemplaza el contenido de su tabla (la carga es reproducible), verifica `leídas = válidas + rechazadas` y registra la corrida en `control_corridas`.

| Orden | Job | Tabla | Reglas de rechazo, en orden | Qué más hace |
|---|---|---|---|---|
| 1 | `secop-silver-procesos` (E3) | `procesos` | fecha de publicación inválida · no publicado · fuera de alcance (modalidades sin competencia) · versión anterior · fase de otro proceso (una fila por compra real) | Fechas en hora de Colombia, NIT sin DV, precio ≤ 0 a nulo, duración en días, UNSPSC en segmento, familia y clase, estado unificado (abierto, adjudicado, cancelado, cerrado sin adjudicar), bandera de precio atípico |
| 2 | `secop-silver-proponentes` (E4) | `proponentes` | llave incompleta · proceso fuera de alcance o inexistente · duplicado (gana la ingesta y luego la más reciente) | `proveedor_key` con hash; consorcios, NIT de relleno y NIT compartidos se identifican por código de SECOP |
| 3 | `secop-silver-proveedores` | `proveedores` | llave incompleta · versión anterior · cuenta consolidada (una fila por `proveedor_key`) | `tipo_proveedor` (consorcio, entidad pública, persona natural, empresa), pyme y `es_usuario_objetivo`; no pasan datos de contacto ni del representante legal |
| 4 | `secop-silver-contratos` (E5) | `contratos` | llave incompleta · versión anterior | Contratos sin proceso en plata se conservan con `con_proceso = false`; no pasan representantes, supervisores, cuentas bancarias ni género |
| 5 | `secop-silver-ganador` (E6) | `procesos`, `proponentes` | — (enriquece, no rechaza) | Resuelve el ganador por código, por NIT o por contrato; estado final; `es_ganador`, `n_proponentes`, `n_ganadores` y `sector_entidad` |

Las funciones de [`limpieza_secop.py`](glue/plata/limpieza_secop.py) devuelven expresiones de columna de Spark, sin UDF de Python, y cada una documenta el hallazgo que resuelve.

| Tabla de plata | Filas (17 nov 2026) |
|---|---:|
| procesos | 625.625 |
| proponentes | 1.979.268 |
| contratos | 5.709.481 |
| proveedores | 1.607.715 |

## Oro

Un solo job, `secop-gold-estrella`, reconstruye completas 13 tablas desde el último snapshot de plata. Cada tabla guarda en sus propiedades el `id_corrida` y los `snapshot_id` de plata con que se armó.

**Modelo estrella**

| Tabla | Una fila por | Llave |
|---|---|---|
| `dim_fecha` | día (2000–2060) | `fecha_key` AAAAMMDD |
| `dim_entidad` | entidad compradora | NIT |
| `dim_proveedor` | proveedor | `proveedor_key` |
| `dim_geografia` | departamento + ciudad | xxhash64 |
| `dim_categoria` | clase UNSPSC | xxhash64 |
| `dim_modalidad` | modalidad + tipo de contrato (7 grupos, `es_competitiva`) | xxhash64 |
| `fact_procesos` | proceso (625.625) | `id_proceso` |
| `fact_participaciones` | proveedor en un proceso (1.979.268) | `id_proceso` + `proveedor_key` |
| `fact_contratos` | contrato (5.709.481) | `id_contrato` |

**Tablas del dashboard** (sumas y conteos, nunca promedios, para que la web pueda reagrupar sin sesgo)

| Tabla | Una fila por | Filas |
|---|---|---:|
| `mercado_mensual` | mes × departamento × grupo de modalidad × segmento | 164.668 |
| `competencia_entidad` | entidad × año (incluye HHI y cuota del proveedor principal) | 20.770 |
| `calidad_fuente` | semana de publicación | 586 |
| `desempeno_recomendaciones` | día de corte × lista: resultado real de lo recomendado | 14 |

**Reglas y validaciones**

- Sin llaves nulas: lo que falta apunta a un miembro "Sin dato", así un `INNER JOIN` en Athena nunca pierde filas.
- Contratos con valor atípico (absoluto: más de 100 mil millones; relativo: más de 10 mil millones y más de 1.000 veces la mediana de la entidad en el año) se conservan con su motivo, pero no entran a los indicadores.
- Antes de escribir se validan: llaves únicas, las 24 relaciones de integridad referencial, que cada hecho tenga las filas de su tabla de plata, que los valores sumen igual que en plata, que los agregados cuadren con `fact_procesos` y que no haya tasas imposibles. Si algo falla, no se escribe ninguna tabla.

## Resultados

- Ingesta verificada contra la fuente: 100 % en las cuatro tablas (17 nov 2026).
- 0 participaciones perdidas por llave incompleta gracias a la identidad única de proveedor.
- 13 tablas de oro escritas con éxito en la corrida del 17 nov 2026; procesos sin entidad o sin fecha: 0 %.
- Hallazgo de la fuente: desde mediados de septiembre de 2026 más del 99 % de los procesos nuevos llega sin categoría UNSPSC.

## Reproducir

Variables usadas en los comandos:

```bash
export AWS_PROFILE=<perfil> AWS_REGION=us-east-1
BUCKET=proyecto-integrador-bucket-01
ROL=proyecto-integrador-glue-role
```

### 1. Preparar la cuenta

1. Bucket S3 `$BUCKET` y workgroup de Athena con resultados en `s3://$BUCKET/athena-results/`.
2. Rol de Glue `$ROL` con acceso de lectura y escritura al bucket, al Glue Data Catalog y a los dos parámetros de SSM.
3. Parámetros de SSM (SecureString):

```bash
aws ssm put-parameter --name /secop/app-token --type SecureString --value <app-token-de-datos.gov.co>
aws ssm put-parameter --name /secop/hash-salt --type SecureString --value <sal-aleatoria>
```

### 2. Bronce

```bash
# Bases y tabla de control (en Athena): sql/00_bases.sql y sql/03_control.sql

# Esquemas de columnas
aws s3 cp control/esquemas/ s3://$BUCKET/control/esquemas/ --recursive

# Carga histórica: exportar cada dataset en CSV desde datos.gov.co y subirlo a su carpeta
curl -L -o procesos.csv "https://www.datos.gov.co/api/views/p6dx-8zbt/rows.csv?accessType=DOWNLOAD"
aws s3 cp procesos.csv s3://$BUCKET/bronze/procesos-contratacion/carga-historica/
# igual con hgi6-6wh3 → proponentes-procesos, jbjy-vk9h → contratos-electronicos, qmzu-gj57 → proveedores-registrados

# Scripts de Glue
for f in glue/*/*.py; do aws s3 cp "$f" s3://$BUCKET/scripts/; done

# Job de bronce histórico (Glue 5.0, G.1X, 10 workers)
aws glue create-job --name secop-bronze-historico-parquet --role $ROL \
  --glue-version 5.0 --worker-type G.1X --number-of-workers 10 --timeout 180 \
  --command Name=glueetl,ScriptLocation=s3://$BUCKET/scripts/secop-bronze-historico-parquet.py,PythonVersion=3
aws glue start-job-run --job-name secop-bronze-historico-parquet
```

Después, en Athena: `sql/01_bronce_ingesta.sql`.

### 3. Plata

En Athena: `sql/02_plata.sql`. Luego se crean los cinco jobs y se corren **en este orden**, cada uno cuando el anterior termina:

```bash
ARGS='{"--datalake-formats":"iceberg","--extra-py-files":"s3://'$BUCKET'/scripts/limpieza_secop.py"}'
for par in procesos:10 proponentes:6 proveedores:4 contratos:10 ganador:10; do
  job=secop-silver-${par%%:*}
  aws glue create-job --name $job --role $ROL \
    --glue-version 5.0 --worker-type G.1X --number-of-workers ${par##*:} --timeout 60 \
    --command Name=glueetl,ScriptLocation=s3://$BUCKET/scripts/$job.py,PythonVersion=3 \
    --default-arguments "$ARGS"
done

aws glue start-job-run --job-name secop-silver-procesos
aws glue get-job-runs --job-name secop-silver-procesos --max-items 1 --query 'JobRuns[0].JobRunState'
# … proponentes → proveedores → contratos → ganador
```

Cada mañana los cinco jobs los encadena la Step Functions `secop-nocturno` ([`03-mlops/infra/stepfunctions/`](../03-mlops/infra/stepfunctions/)).

### 4. Oro

```bash
aws glue create-job --name secop-gold-estrella --role $ROL \
  --glue-version 5.0 --worker-type G.1X --number-of-workers 3 --timeout 60 \
  --command Name=glueetl,ScriptLocation=s3://$BUCKET/scripts/secop-gold-estrella.py,PythonVersion=3 \
  --default-arguments '{"--datalake-formats":"iceberg"}'
aws glue start-job-run --job-name secop-gold-estrella
```

Tarda de 5 a 10 minutos. Verificación en Athena (13 filas en `exito`):

```sql
SELECT tabla, estado, filas_validas, cuadre_ok
FROM secop_control.control_corridas
WHERE job = 'secop-gold-estrella'
ORDER BY inicio DESC, tabla
LIMIT 13;
```
