# Recomendador SECOP II

Sistema que cada mañana le entrega a cada empresa los procesos abiertos de SECOP II donde tiene más opción de ganar, y un dashboard para que la dirección de SECOP vea dónde se está perdiendo la competencia en la contratación pública.

| | |
|---|---|
| **Página publicada** | https://main.d360gidrarcxt9.amplifyapp.com |
| **API** | https://i5rev77icbkeissqixiw6h5soi0npkxh.lambda-url.us-east-1.on.aws/docs |
| **Fuente de datos** | SECOP II, Colombia Compra Eficiente ([datos.gov.co](https://www.datos.gov.co), API Socrata, licencia CC BY-SA 4.0) |
| **Institución** | Universidad EAFIT · Ciencia de Datos · Equipo 8 (ContrataMatch) |

## Equipo

| Integrante |
|---|
| Juan Diego Acuña
| David Lopera
| Jacobo Restrepo
| Nicolás Hurtado
| José Alejandro Duque 

## Problema

El Estado colombiano publica en SECOP II cerca de 2.500 procesos abiertos cada día. Una empresa, sobre todo una pyme, no puede revisarlos a mano, y la competencia se está perdiendo: los procesos adjudicados con un solo oferente pasaron de **27,7 % en 2020 a 45,3 % en 2025** (47,2 % en 2026, hasta el 17 de noviembre).

**Decisión que apoya el sistema:** ¿a qué procesos debe presentarse la empresa?

## Solución

Cada mañana, para cada empresa con historial en SECOP II, el sistema publica dos listas de 10 procesos abiertos:

| Lista | Qué contiene | Cómo se ordena |
|---|---|---|
| **Lista 1 · Recomendados según tu historial** | Procesos parecidos a los que la empresa disputa | Ranking v2 (LightGBM LambdaRank) |
| **Lista 2 · Oportunidades que normalmente no verías** | Procesos de entidades nuevas para la empresa, con poca competencia esperada | P(gana) de G1 con filtros de competencia y precio |

Cada proceso lleva la **probabilidad de ganar si se presenta** (calibrada) y los oferentes esperados; la API entrega además los motivos de cada recomendación. Las empresas nuevas describen lo que venden y reciben los procesos abiertos que coinciden con su descripción.

## Arquitectura

```mermaid
flowchart LR
    S["datos.gov.co<br/>API Socrata<br/>4 datasets"] --> B["BRONCE<br/>S3 · JSON y Parquet<br/>tal como llega"]
    B --> P["PLATA<br/>Iceberg · 4 tablas<br/>+ 4 de rechazados"]
    P --> O["ORO<br/>Iceberg · estrella<br/>+ agregados"]
    P --> J["Job nocturno<br/>retrieval → ranking → listas<br/>ECS Fargate"]
    M["MLflow<br/>4 modelos @production"] --> J
    J --> R[("RDS PostgreSQL<br/>esquema serving")]
    J --> O
    R --> A["API FastAPI<br/>AWS Lambda"]
    A --> W["Página web<br/>Vue 3 · AWS Amplify"]
    O --> W
```

| Capa | Tecnología |
|---|---|
| Fuente | API Socrata de datos.gov.co (SECOP II) |
| Almacenamiento | Amazon S3 (bronce, plata y oro), Apache Iceberg, Glue Data Catalog |
| Procesamiento | AWS Glue 5.0 (PySpark) |
| Consulta analítica | Amazon Athena |
| Orquestación | AWS Step Functions + EventBridge Scheduler |
| Modelos | LightGBM, scikit-learn (TF-IDF, SVD, SGD) |
| Registro de modelos | MLflow 3 (EC2 + RDS + S3) |
| Job nocturno | Docker en ECS Fargate |
| Base de serving | Amazon RDS PostgreSQL 16 |
| API | FastAPI en AWS Lambda (Function URL) |
| CI/CD | GitHub Actions + Amazon ECR (OIDC, sin llaves) |
| Monitoreo | CloudWatch, SNS y Evidently (drift) |
| Web | Vue 3 + Vite, Pinia, Tailwind CSS 4, Apache ECharts 6 |
| Hosting web | AWS Amplify Hosting |

### Flujo de cada mañana

```
07:30 (Bogotá) EventBridge Scheduler → Step Functions secop-nocturno
  0. Ingesta de los últimos 45 días de las 4 tablas, en paralelo (ECS Fargate)      ≈ 7 min
  1. Plata: procesos → proponentes → proveedores → contratos → ganador (Glue)        ≈ 26 min
  2. score.py: retrieval → features → ranking → listas → motivos (ECS Fargate)      ≈ 25 min
  3. Publicación atómica en RDS (todo o nada) y copia en oro (secop_gold.recomendaciones)
  4. Métricas de volumen, reporte de drift y alarmas por correo (CloudWatch + SNS)
```

Costo medido: **≈ USD 1,6 por noche**. Si un paso obligatorio falla, no se publica y la web sigue con la versión anterior.

## Estructura del repositorio

```
recomendador-secop/
├── 01-ingenieria-de-datos/   Ingesta, jobs de Glue (bronce, plata, oro), DDL y esquemas
├── 02-modelo-ml/             Diseño, validación y resultados de los modelos; artefactos v1
├── 03-mlops/                 Paquete ml/, job nocturno, API, MLflow, orquestación, monitoreo, CI/CD
├── 04-visualizacion/         Página web: dashboard y recomendador (Vue 3)
└── .github/workflows/        Verificación continua de MLOps y de la web
```

## Fases

### Fase 1 · Ingeniería de datos

Lago medallón en S3 con tablas Iceberg, procesado con Glue.

- **Bronce:** la carga histórica (CSV de datos.gov.co, 9,4 millones de procesos) se convierte a Parquet con nombres técnicos; la ingesta incremental guarda NDJSON en gzip por fecha. Nunca se modifica.
- **Plata:** cinco jobs limpian, deduplican y unen las cuatro tablas. Cada fila descartada queda en una tabla de rechazados con su motivo, y cada corrida cuadra: leídas = válidas + rechazadas. Los NIT se guardan con hash y no pasan datos de personas naturales.
- **Oro:** modelo estrella (3 hechos, 6 dimensiones, 24 relaciones validadas) y 4 tablas agregadas para el dashboard y para medir las recomendaciones en producción.

| Tabla de plata | Filas (17 nov 2026) |
|---|---:|
| procesos | 625.625 |
| proponentes | 1.979.268 |
| contratos | 5.709.481 |
| proveedores | 1.607.715 |

Detalle: [`01-ingenieria-de-datos/README.md`](01-ingenieria-de-datos/README.md)

### Fase 2 · Modelo de machine learning

Recomendador en tres etapas, de ~97 millones de parejas empresa–proceso a 20 recomendaciones por empresa.

1. **Retrieval (M1, LightGBM):** reglas de afinidad (entidad, modalidad, categoría), similitud de texto TF-IDF y vecinos para empresas nuevas; el modelo deja 150 candidatos por empresa.
2. **Ranking v2 (LightGBM LambdaRank):** ordena los 150 candidatos por interés (0 = no se presentó, 1 = se presentó, 2 = ganó). Arma la lista 1.
3. **G1 (LightGBM binario):** probabilidad calibrada de ganar si la empresa se presenta. Se muestra en las dos listas y elige la lista 2.

Validación siempre temporal: entrenamiento con el pasado, validación por rondas y una prueba única con datos que el modelo nunca vio (jul 2025 – jul 2026). Un cuarto modelo (`secop-unspsc`, TF-IDF + SGD) infiere la categoría de los procesos que SECOP publica sin ella.

Detalle: [`02-modelo-ml/README.md`](02-modelo-ml/README.md)

### Fase 3 · MLOps

- Paquete `ml/` con una prueba de paridad: producción reproduce el notebook (diferencia máxima 0,0006).
- Job nocturno `score.py` por lotes, determinista e idempotente, con verificación de frescura antes de publicar.
- Publicación atómica por versiones en PostgreSQL (se guardan las últimas 7).
- MLflow con los 4 modelos en `@production` y compuerta de promoción que exige mejorar sin empeorar en pymes.
- API FastAPI en Lambda que responde en ~100 ms, sin datos de personas naturales.
- CI/CD con GitHub Actions: lint, pruebas, paridad, build de imágenes, despliegue en ECR y Lambda.
- Monitoreo: alarmas por correo, métricas de volumen y reporte diario de drift con Evidently.
- Plan B local con `docker-compose`.

Detalle: [`03-mlops/README.md`](03-mlops/README.md) y [`03-mlops/OPERACION.md`](03-mlops/OPERACION.md)

### Fase 4 · Visualización y página web

Una SPA con dos partes, cada una para un usuario:

| Ruta | Usuario | Qué responde |
|---|---|---|
| `/` · Dashboard | Dirección de SECOP II | ¿Qué % de los procesos competitivos se adjudica con un solo oferente, por departamento, modalidad y categoría, en 2025 frente a 2020, para decidir dónde intervenir primero? |
| `/recomendador` | Empresas | ¿En qué procesos abiertos tengo más opción de ganar? |

El dashboard usa la capa oro (534.735 procesos, 2020 – 17 nov 2026): 5 KPI con referencia frente a 2020, 5 gráficas que responden una pregunta cada una, filtros cruzados, detalle por entidad y filtros en la URL. El recomendador consulta la API en vivo.

Detalle: [`04-visualizacion/README.md`](04-visualizacion/README.md)

## Resultados

**Prueba temporal** (jul 2025 – jul 2026, datos que el modelo nunca vio):

| Etapa | Métrica | Resultado | Referencia |
|---|---|---:|---:|
| Retrieval M1 | Recall@150 | 78,9 % | — |
| Lista 1 (ranking v2) | NDCG@10 | 0,462 | 0,362 (retrieval solo) |
| Lista 1 (ranking v2) | Recall@10 | 0,566 | 0,455 |
| Lista 1 (ranking v2) | Precision@10 | 0,110 | 0,086 |
| G1 · P(gana) | Log loss / ECE / AUC | 0,379 / 0,004 / 0,877 | — |
| Lista 2 | Oportunidades plausibles | 67,7 % | 62,2 % (azar con filtros) |

**Producción** (noviembre de 2026):

| Medida | Valor |
|---|---|
| Mañanas sin fallas (13–21 nov) | 9 de 9 |
| Empresas con listas cada día | ~37.400 |
| Ofertas reales de cada día que ya estaban en la lista 1 (11–17 nov) | 53–69 % |
| Respuesta de la API | ~100 ms |
| Costo por noche | ≈ USD 1,6 |

**Limitaciones:** el modelo no conoce el precio que va a ofertar la empresa; en empresas sin historial el Recall@150 baja a 43,3 %; en la lista 2 la probabilidad es algo optimista (promete 38 %, se gana 30 %).

## Reproducir

### Requisitos

| Herramienta | Versión | Para qué |
|---|---|---|
| Python + [uv](https://docs.astral.sh/uv/) | 3.11 | API, job nocturno y pruebas |
| Node.js | 22 o superior | Página web |
| Docker | — | Pruebas con PostgreSQL, imágenes y plan B (opcional en local) |
| AWS CLI | v2 | Solo para el pipeline en la nube |

```bash
git clone https://github.com/NicoHurtado/recomendador-secop.git
cd recomendador-secop
```

### 1. API y página web en local (sin AWS)

API con datos simulados (mismo contrato que la API real):

```bash
cd 03-mlops
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/uvicorn api.main:app --port 8000
```

La documentación de la API queda en http://localhost:8000/docs.

En otra terminal, la página web contra esa API:

```bash
cd 04-visualizacion
npm ci
VITE_API_URL=http://localhost:8000 npm run dev
```

Abrir http://localhost:5173. El dashboard usa los agregados de la capa oro incluidos en `04-visualizacion/public/data/estadisticas-oro.json`.

Sin ninguna API, con respuestas guardadas de la API real:

```bash
cd 04-visualizacion
npm run dev:mock
```

### 2. Pruebas

MLOps (lint, formato y pruebas; las de PostgreSQL corren si `TEST_DATABASE_URL` está definida):

```bash
cd 03-mlops
uv pip install --python .venv/bin/python -r requirements-ml.txt
.venv/bin/ruff check . && .venv/bin/ruff format --check .
docker run -d --name secop-pg-prueba -e POSTGRES_PASSWORD=prueba -e POSTGRES_DB=secop -p 55432:5432 postgres:16
TEST_DATABASE_URL=postgresql://postgres:prueba@localhost:55432/secop .venv/bin/python -m pytest -q
```

Página web (ESLint, 24 pruebas de Vitest y build de producción):

```bash
cd 04-visualizacion
npm run lint && npm test && npm run build
```

Las dos verificaciones corren en cada push y pull request con [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

### 3. Pipeline completo en AWS

Los scripts usan el bucket `proyecto-integrador-bucket-01` y la región `us-east-1`; en otra cuenta se cambia la constante `BUCKET` de cada script. Cada paso remite al README de su fase, donde están los comandos completos.

| # | Paso | Dónde |
|---|---|---|
| 1 | Bucket S3, workgroup de Athena, rol de Glue y parámetros de SSM `/secop/app-token` (token de datos.gov.co) y `/secop/hash-salt` (sal del hash de NIT) | [Fase 1 · Preparar la cuenta](01-ingenieria-de-datos/README.md#1-preparar-la-cuenta) |
| 2 | Bases del catálogo, esquemas de columnas y carga histórica en bronce | [Fase 1 · Bronce](01-ingenieria-de-datos/README.md#2-bronce) |
| 3 | Tablas y jobs de plata, en orden | [Fase 1 · Plata](01-ingenieria-de-datos/README.md#3-plata) |
| 4 | Job de oro | [Fase 1 · Oro](01-ingenieria-de-datos/README.md#4-oro) |
| 5 | Artefactos del modelo en `s3://…/modelos/v1/` | [Fase 2 · Artefactos](02-modelo-ml/README.md#artefactos-v1) |
| 6 | RDS, MLflow y registro de los 4 modelos | [Fase 3 · MLflow](03-mlops/README.md#mlflow) |
| 7 | Esquema `serving` en RDS e imágenes `secop-api` y `secop-jobs` en ECR | [Fase 3 · Serving](03-mlops/README.md#base-de-serving-y-publicación-atómica) |
| 8 | Lambda de la API | [Fase 3 · API](03-mlops/README.md#api-publicada) |
| 9 | Step Functions `secop-nocturno` y su programación diaria | [Fase 3 · Job nocturno](03-mlops/README.md#job-nocturno) |
| 10 | Publicación de la web en Amplify | [Fase 4 · Publicar](04-visualizacion/README.md#publicar) |

## Fuente y privacidad

Datos abiertos de SECOP II publicados por Colombia Compra Eficiente en datos.gov.co bajo licencia CC BY-SA 4.0. Los NIT se guardan con hash, no se publican datos de personas naturales y la página no guarda lo que escribe el usuario. Proyecto académico, sin relación oficial con Colombia Compra Eficiente.
