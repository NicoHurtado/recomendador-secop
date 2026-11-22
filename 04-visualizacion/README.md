# Fase 4 · Visualización y página web

Página publicada: **https://main.d360gidrarcxt9.amplifyapp.com**

SPA estática (Vue 3 + Vite) con dos partes, cada una para un usuario distinto. Toma la capa oro de ingeniería de datos y la API de recomendaciones de MLOps y las convierte en respuestas a preguntas de negocio.

| Ruta | Usuario | Qué obtiene |
|---|---|---|
| `/` · Dashboard | Dirección de SECOP II / Colombia Compra Eficiente | En una pantalla: dónde, en qué modalidades y en qué entidades se está perdiendo la competencia, frente a 2020 |
| `/recomendador` | Empresas con historial y empresas nuevas | Procesos abiertos donde tienen más opción de ganar, con la probabilidad de ganar si se presentan |
| `/recomendador/{proveedor_key}` | Empresa con historial | Sus dos listas del día y el detalle de cada proceso |

## De dónde salen los datos

```
capa oro (secop_gold) ── exportar_snapshot_oro.py ──► public/data/estadisticas-oro.json ──► Dashboard
                                                       (agregados, 1,9 MB, viaja en la página)

RDS (serving) ── API FastAPI en Lambda ── Amplify /api/* (proxy) ─────────────────────────► Recomendador
```

- **Dashboard:** snapshot de agregados de la capa oro (534.735 procesos publicados entre el 1 ene 2020 y el 17 nov 2026), exportado de Athena con [`scripts/exportar_snapshot_oro.py`](scripts/exportar_snapshot_oro.py). Solo trae sumas y conteos; los porcentajes se calculan en el navegador como razón de sumas, así se pueden reagrupar con cualquier filtro sin sesgo. El motor es [`src/api/estadisticasLocal.js`](src/api/estadisticasLocal.js).
- **Recomendador:** API en vivo. Todas las llamadas pasan por un único módulo, [`src/api/api.js`](src/api/api.js).

| Endpoint | Para qué |
|---|---|
| `GET /metadata` | Fecha de los datos del recomendador |
| `GET /empresas?q=` | Autocompletado del buscador de empresas |
| `GET /empresas/{proveedor_key}/recomendaciones` | Las dos listas de una empresa con historial |
| `GET /procesos/abiertos?departamento=&familia=` | Procesos abiertos para una empresa nueva |
| `GET /procesos/{id_proceso}` | Modalidad del proceso al abrir su detalle |
| `GET /health` | Estado del servicio |

## Dashboard

Diseñado con el método *Dashboards para responder preguntas de negocio*: entrevista de descubrimiento → pregunta principal → preguntas secundarias, cada una con la gráfica que mejor la responde.

**Pregunta principal:** ¿Qué % de los procesos competitivos se adjudica con un solo oferente, por departamento, modalidad y categoría, en 2025 frente a 2020, para decidir dónde intervenir primero?

**Respuesta en la vista por defecto:** en 2025, 45,3 % de los procesos competitivos se adjudicó con un solo oferente, +17,6 pp frente a 2020 (27,7 %). La competencia es más débil en Arauca (79,8 %) y en régimen especial (68,0 %).

**KPI** (valor del año, cambio frente a 2020 con ▲▼ y línea de tendencia desde 2020)

| KPI | Fórmula | Mejor si | 2025 | Frente a 2020 |
|---|---|---|---:|---|
| Procesos con un solo oferente | Σ adjudicados con una oferta ÷ Σ adjudicados | Baja | 45,3 % | ▲ +17,6 pp |
| Oferentes por proceso | Σ ofertas ÷ Σ adjudicados | Sube | 3,7 | ▼ −1,4 |
| Procesos competitivos | Σ publicados en modalidades con competencia | Volumen | 98.191 | ▲ +123 % |
| Valor adjudicado | Σ valor sin atípicos, pesos corrientes | Volumen | $51,8 billones | ▲ +221 % |
| Valor ganado por pymes | Σ valor a pymes ÷ Σ valor | Sube | 31,1 % | ▲ +7,3 pp |

**Gráficas** (el título es la pregunta y debajo va la respuesta con cifras, recalculada con los filtros)

| # | Pregunta | Gráfica | Respuesta (2025) |
|---|---|---|---|
| P1 | ¿El oferente único es una tendencia o un mal año? | Línea mensual con promedio móvil de 12 meses; cambia de indicador con clic en un KPI | Tendencia: de 27,7 % en 2020 a 45,3 % en 2025; 48,5 % en los últimos 12 meses |
| P2 | ¿Dónde hay menos competencia? | Barras ordenadas por departamento o por categoría | 10 de 33 departamentos están 10 pp o más sobre el promedio; el más alto es Arauca (79,8 %) |
| P3 | ¿En qué modalidades empeoró desde 2020? | Mancuerna 2020 → año elegido | En las cinco; el mayor cambio es selección abreviada (+24,7 pp) |
| P4 | ¿Las entidades que más contratan tienen competencia? | Barras de las 15 entidades con más valor adjudicado | Solo la Gobernación del Cesar está 10 pp o más sobre el promedio (67,4 %) |
| P5 | ¿Las pymes ganan en proporción al valor? | Barras 100 % | No: ganan 79 de cada 100 procesos y reciben 31 de cada 100 pesos |

**Interacción:** filtros de año, departamento, modalidad y categoría; tarjetas KPI que cambian la tendencia; filtro cruzado con clic en P2 y P3; detalle de entidad desde P4 (serie anual de valor, procesos, oferente único, proveedores y HHI); tooltips; filtros en la URL para compartir una vista; ficha técnica desplegable con fórmulas y notas sobre los datos.

**Reglas con el dato:** porcentajes como razón de sumas; solo procesos competitivos; valor sin atípicos; barras desde cero; grupos con menos de 30 procesos adjudicados (10 en entidades) no se grafican; el mes en curso no entra en la tendencia; 2026 se marca como año parcial y no se compara con 2020.

**Notas sobre los datos** (en la ficha técnica del dashboard):

- Varias dependencias comparten NIT (Bogotá D.C. tiene 38): la entidad se muestra con el nombre más frecuente de su NIT y el aviso "NIT compartido por N dependencias".
- En sep, oct y dic de 2022 el oferente único cae a 3–15 % en todas las modalidades a la vez, sin cambio en el número de procesos: esos meses se omiten de la tendencia mensual y la gráfica lo anota.
- Desde el 21 sep 2026 más del 90 % de los procesos llega sin categoría UNSPSC.
- Los valores van en pesos corrientes.

**Color por función:** azul `#0f6cbd` protagonista, gris `#c8c8c8` contexto, punteado `#5d5d5d` referencia, rojo `#c4314b` alerta (siempre con ▲▼ o texto), verde `#107c10` mejora. Paleta revisada para protanopia y deuteranopia.

## Recomendador

La primera pantalla pregunta "¿Tu empresa ya ha participado en SECOP II?" y abre uno de dos caminos.

| | Empresa con historial | Empresa nueva |
|---|---|---|
| Cómo entra | Busca su nombre (autocompletado) o usa un ejemplo | Describe qué vende, elige departamentos y un valor máximo, o carga un ejemplo |
| Qué ve | Dos filas: "Recomendados según tu historial" y "Oportunidades que normalmente no verías" | Una lista ordenable por coincidencias, cierre más próximo o mayor valor |
| De dónde sale | Las listas que el modelo calculó esa noche | Procesos abiertos del departamento, ordenados por coincidencia de palabras con la descripción |
| Probabilidad de ganar | Sí, "de ganar si te presentas", en barra y número, junto a los oferentes esperados | No: el modelo necesita historial, y la página lo dice |

Cada tarjeta muestra entidad, objeto, precio base, lugar, cierre (en ámbar si faltan menos de 5 días), probabilidad y competencia esperada. Al abrirla, un panel lateral trae el objeto completo, la modalidad, el identificador y el enlace al proceso en SECOP II. Si la API envía el mismo proceso dos veces con distinto identificador, la página lo muestra una sola vez.

## Stack

| Componente | Tecnología |
|---|---|
| Framework | Vue 3 + Vite 8 |
| Rutas y estado | Vue Router, Pinia |
| Gráficas | Apache ECharts 6 con vue-echarts, render SVG |
| Estilos | Tailwind CSS 4 + tokens propios (`main.css` para el dashboard, `sitio.css` para la barra, el pie y el recomendador) |
| Pruebas | Vitest (24 pruebas) y ESLint |
| Hosting | AWS Amplify Hosting, `us-east-1` |

Accesibilidad: descripción para lectores de pantalla en cada gráfica, navegación con teclado y foco visible, contraste AA, botones de al menos 44 px en pantallas táctiles. Responsive de 390 a 1920 px. Todo en español de Colombia.

## Estructura

```
src/
  api/          api.js (único punto de acceso), http.js, estadisticasLocal.js, indicadores.js, mock.js + fixtures/
  views/        DashboardView, RecomendadorView, NoEncontradaView
  components/   graficas/ (Lineas, BarrasOrdenadas, Mancuerna, Composicion, Sparkline), dashboard/ (Kpi, Panel,
                DetalleEntidad), recomendador/ (FilaProcesos, TarjetaProceso, PanelProceso), consulta/ (BuscadorEmpresas)
  composables/  useFiltros (filtros en la URL), useRecurso (carga con cancelación y reintento), useTemaGrafica
  utils/        formato es-CO, códigos DANE, modalidades, UNSPSC, relevancia (empresa nueva), glosario
  styles/       main.css, sitio.css
public/data/    estadisticas-oro.json (snapshot real) y estadisticas-simulado.json
public/geo/     departamentos de Colombia con código DANE
scripts/        exportar_snapshot_oro.py, publicar_amplify.sh, generar-snapshot-simulado.mjs, simplificar_geo.py
tests/          formato, DANE, motor del dashboard, API sin red
```

## Correr en local

```bash
npm ci
npm run dev          # http://localhost:5173 contra la API publicada
npm run dev:mock     # sin internet: respuestas guardadas de la API real y el snapshot local
VITE_API_URL=http://localhost:8000 npm run dev   # contra la API local de 03-mlops
```

| Variable | Valores | Para qué |
|---|---|---|
| `VITE_API_URL` | URL de la API, `/api` o vacío | Vacío = sin red (fixtures) |
| `VITE_ESTADISTICAS` | `auto`, `api`, `local` | De dónde salen los datos del dashboard |

## Pruebas

```bash
npm run lint && npm test && npm run build
```

| Archivo | Pruebas | Qué comprueba |
|---|---:|---|
| `tests/formato.test.js` | 8 | Pesos, porcentajes, puntos porcentuales y fechas en español de Colombia |
| `tests/motor.test.js` | 7 | Que el motor del dashboard sume, filtre e ignore filtros cruzados como el contrato `/estadisticas` |
| `tests/api-sin-red.test.js` | 5 | Que la página funcione sin red y que los procesos repetidos se muestren una sola vez |
| `tests/dane.test.js` | 4 | Que nombres y códigos DANE coincidan con los de la capa oro |

## Actualizar los datos del dashboard

Requiere acceso de lectura a Athena (`secop_gold`):

```bash
pip install boto3 "botocore[crt]"
python3 scripts/exportar_snapshot_oro.py --perfil <perfil>
```

Corre 7 consultas `SELECT` sobre las tablas de oro y reescribe `public/data/estadisticas-oro.json`.

## Publicar

App de Amplify `proyecto-integrador-secop`, rama `main`, con dos reglas de reescritura:

| Origen | Destino | Tipo |
|---|---|---|
| `/api/<*>` | `https://i5rev77icbkeissqixiw6h5soi0npkxh.lambda-url.us-east-1.on.aws/<*>` | 200 (proxy, sin CORS) |
| Toda ruta sin extensión de archivo | `/index.html` | 200 (rutas de la SPA) |

```bash
aws login --profile <perfil> --region us-east-1
AWS_PROFILE=<perfil> ./scripts/publicar_amplify.sh
```

El script corre lint, pruebas y build, sube `dist/` a Amplify y espera a que el despliegue termine. Con `.env.production`, la web llama a `/api` en su propio dominio.
