# Fase 2 · Modelo de machine learning

Recomendador de procesos de contratación en tres etapas: un retrieval que deja 150 candidatos por empresa, dos modelos que los puntúan (interés y probabilidad de ganar) y reglas que arman dos listas de 10 procesos.

## Contenido

```
02-modelo-ml/
├── artefactos/v1/                  Modelo congelado que corre en producción
│   ├── config.json                 Fechas del split, K, filtros de la lista 2 e hiperparámetros
│   ├── manifest.sha256             Checksums de los artefactos
│   ├── modelos/g1_pgana.txt        G1 · LightGBM binario (P(gana))
│   ├── modelos/ranking_v2_final.txt Ranking v2 · LightGBM LambdaRank
│   ├── retrieval/M1_final_unico.txt Retrieval M1 · LightGBM
│   ├── historia/manifest_historia.sha256  Checksums de la historia congelada al 27 oct 2026
│   └── metricas/                   Tablas finales de la prueba (xlsx y parquet)
└── resultados/
    ├── resultados_finales.xlsx     Lista 1 y lista 2 por mes, P(gana) por segmento y calibración por deciles
    ├── R0_resumen_rondas.csv       Filas y tasas de cada ronda de validación de G1
    ├── R1_resumen_particiones.csv  Ventanas de entrenamiento y validación de cada ronda
    ├── rondas.json                 Definición de las rondas
    └── curva_aprendizaje.png       Recall@150 del retrieval según los meses de entrenamiento
```

El código del modelo está en [`../03-mlops/ml/`](../03-mlops/ml/): la lógica de los notebooks de ciencia de datos pasada a funciones con una interfaz fija, sin rutas fijas y con una prueba de paridad que exige el mismo resultado que el notebook.

| Módulo | Qué hace |
|---|---|
| [`limpieza.py`](../03-mlops/ml/limpieza.py) | Plata → tablas limpias del modelo |
| [`pit.py`](../03-mlops/ml/pit.py) | Utilidades point-in-time: solo eventos estrictamente anteriores a la fecha de corte |
| [`retrieval.py`](../03-mlops/ml/retrieval.py) | Retrieval M1: de todos los procesos abiertos a 150 candidatos por empresa |
| [`features.py`](../03-mlops/ml/features.py) | Las 103 features del constructor más las 3 de participación |
| [`ranking.py`](../03-mlops/ml/ranking.py) | G1 → `p_gana` y ranking v2 → `s_v2` |
| [`listas.py`](../03-mlops/ml/listas.py) | Lista 1 (`historial`) y lista 2 (`oportunidad`) |
| [`evaluacion.py`](../03-mlops/ml/evaluacion.py) | Métricas de las dos listas para un mes cerrado |
| [`unspsc.py`](../03-mlops/ml/unspsc.py) | Inferencia de la familia UNSPSC desde la descripción |
| [`config.py`](../03-mlops/ml/config.py) | Constantes del modelo congelado y verificación contra `config.json` |

## Formulación

- **Unidad:** una pareja empresa × proceso abierto. Cada día hay ~2.500 procesos abiertos y ~97 millones de parejas.
- **Dos preguntas, dos modelos.** Qué procesos disputaría la empresa (interés) no es lo mismo que si ganaría al presentarse. El ranking aprende de todos los candidatos; G1 solo de participaciones reales. Separarlas ataca el sesgo de selección: la probabilidad mostrada es "si te presentas".
- **Point-in-time.** Cada feature usa solo información anterior a la fecha de corte, y una victoria cuenta desde su fecha de adjudicación. Las variables que solo se conocen al cierre (número de oferentes, ganador, valor adjudicado) nunca son features.
- **Split temporal, nunca aleatorio.** Entrenamiento con el pasado, validación en periodos siguientes y una única prueba con jul 2025 – jul 2026.

```
Procesos abiertos (~2.500)  ×  empresas
        │
        ▼
1. Retrieval M1 ───────────► 150 candidatos por empresa
        │
        ▼
2. Ranking v2 (interés) ───► lista 1: top 10                         "Recomendados según tu historial"
   G1 (P(gana))  ──────────► lista 2: puestos 11–150 con filtros,     "Oportunidades que normalmente no verías"
                              ordenados por P(gana), hasta 10
```

## Etapa 1 · Retrieval

Tres fuentes de candidatos que entiende cualquiera, y un LightGBM que deja los 150 mejores:

1. **¿Dónde ya compite?** Procesos de las entidades, modalidades y categorías donde la empresa ya se presentó.
2. **¿De qué se trata?** Similitud TF-IDF entre el texto del proceso y los procesos anteriores de la empresa.
3. **¿Empresa nueva?** El historial de sus 20 empresas más parecidas (temas 0,5 · tamaño 0,2 · tipo 0,15 · departamento 0,1 · pyme 0,05).

**Modelos evaluados** (validación ene–jun 2025, Recall@150):

| Opción | Cómo funciona | Total | Con historial | Nuevas |
|---|---|---:|---:|---:|
| M0 · solo reglas | Afinidad + texto, sin modelo | 73,1 % | 77,6 % | 29,8 % |
| **M1 · LightGBM (elegido)** | Todos los positivos + 100 negativos al azar por empresa | **80,5 %** | **84,1 %** | **46,6 %** |
| M2 · LightGBM | 50 negativos difíciles + 50 al azar | 74,2 % | 78,4 % | 34,3 % |
| M3 · dos LightGBM | Como M2, un modelo para empresas normales y otro para nuevas | 74,4 % | 78,4 % | 36,1 % |

M1 se entrenó con jul–dic 2024 (7,7 millones de filas, 1,5 % positivos). Los negativos difíciles empeoraron el resultado.

## Etapa 2 · Ranking v2 (lista 1)

- **Fila:** empresa × proceso candidato, agrupada por empresa y mes. **Etiqueta:** 0 = no se presentó, 1 = se presentó, 2 = ganó.
- **Modelo:** LightGBM LambdaRank (NDCG@10), 31 hojas, mínimo 500 por hoja, 269 árboles.
- **Datos:** entrenamiento jul 2024 – jun 2025 (11,9 millones de filas, 79 mil grupos empresa-mes); validación mes a mes ene–jun 2025; prueba jul 2025 – jul 2026.
- **Variables:** las 103 de G1 más 3 del retrieval. Las que más pesan: interés según el retrieval (47,2 %), posición en el retrieval (11,5 %), categoría UNSPSC (9,6 %), días desde la última participación (5,4 %), relación previa con la entidad (3,1 %), mismo municipio y departamento (2,5 % y 2,1 %).

**Formas de ordenar la lista 1** (validación ene–jun 2025):

| Cómo se ordena | NDCG@10 | Precision@10 | HitRate@10 | Recall ganadas@10 | Hit@10 ganador |
|---|---:|---:|---:|---:|---:|
| Solo P(gana) · G1 | 0,166 | 0,044 | 0,333 | 0,392 | 0,576 |
| Solo P(gana) · stacking de 5 modelos | 0,175 | 0,045 | 0,343 | 0,408 | 0,572 |
| Interés × P(gana) · G1 | 0,315 | 0,077 | 0,545 | 0,553 | 0,749 |
| Interés × P(gana) · stacking | 0,318 | 0,078 | 0,544 | 0,556 | 0,746 |
| Solo interés del retrieval (línea base) | 0,386 | 0,092 | 0,604 | 0,544 | 0,752 |
| Híbrida (interés × P solo en empresas nuevas) | 0,387 | 0,093 | 0,606 | 0,547 | 0,756 |
| Ranking v2 sin variables de participación | 0,474 | 0,115 | 0,696 | 0,652 | 0,818 |
| Ranking v2 con fuga de información (descartado) | 0,501 | 0,116 | 0,724 | 0,652 | 0,759 |
| **Ranking v2 corregido (elegido)** | **0,483** | **0,115** | **0,705** | **0,652** | **0,797** |

Ordenar por probabilidad de ganar empeora el orden (0,386 → 0,166): interés y probabilidad son preguntas distintas. La fuga se encontró, se corrigió y la mejora se mantuvo.

## Etapa 3 · G1 (probabilidad de ganar)

- **Fila:** una participación real. **Etiqueta:** 1 = ganó, 0 = perdió. Solo entran procesos ya adjudicados en la fecha de corte.
- **Modelo:** LightGBM binario, 60 hojas, mínimo 1.297 por hoja, tasa de aprendizaje 0,054, 700 árboles (hiperparámetros en [`config.json`](artefactos/v1/config.json)).
- **Validación cruzada temporal con ventana creciente:**

| Ronda | Entrenamiento | Validación | Filas de entrenamiento | Filas de validación |
|---|---|---|---:|---:|
| 1 | ene 2022 – dic 2023 | ene – jun 2024 | 401.726 | 115.077 |
| 2 | ene 2022 – jun 2024 | jul – dic 2024 | 502.292 | 142.367 |
| 3 | ene 2022 – dic 2024 | ene – jun 2025 | 658.968 | 128.571 |
| Prueba | ene 2022 – jun 2025 | jul 2025 – jul 2026 | 769.515 | 314.090 |

- **Variables:** 70 point-in-time salidas del EDA más 33 de rivales, entidad y grafo (log loss 0,3771 → 0,3758); 4 se corrigieron por fuga. Las que más pesan: tasa de victoria en sus 50 procesos más parecidos (29,7 %), en sus 5 más parecidos (15,3 %), categoría UNSPSC (9,3 %), tasa de victoria con la entidad (7,4 %), departamento de la entidad (2,2 %) y competencia esperada en la entidad y modalidad (1,9 %).

**Candidatos** (ronda 3, ene–jun 2025; 12 de 23 evaluados, incluidos 6 ensambles):

| Modelo | Familia | Log loss ↓ | ECE ↓ | AUC ↑ | AUC por proceso ↑ | Hit@1 ↑ |
|---|---|---:|---:|---:|---:|---:|
| **G1 · LightGBM + features nuevas (elegido)** | árboles | **0,3758** | **0,0065** | 0,871 | 0,695 | 0,502 |
| Stacking (8 modelos) | ensamble | 0,3769 | 0,0247 | 0,872 | 0,697 | 0,506 |
| LightGBM 70 features | árboles | 0,3771 | 0,0066 | 0,870 | 0,695 | 0,502 |
| Promedio G1 + CatBoost + logística | ensamble | 0,3775 | 0,0131 | 0,871 | 0,695 | 0,504 |
| Calibración Platt | ensamble | 0,3780 | 0,0228 | 0,871 | 0,695 | 0,502 |
| CatBoost | árboles | 0,3787 | 0,0100 | 0,869 | 0,695 | 0,504 |
| Wide & Deep | deep learning | 0,3887 | 0,0089 | 0,861 | 0,688 | 0,495 |
| Logística | lineal | 0,3923 | 0,0141 | 0,859 | 0,684 | 0,490 |
| Two-Tower | deep learning | 0,4089 | 0,0104 | 0,846 | 0,661 | 0,459 |
| Vecinos (entidades y familias) | colaborativo | 0,4171 | 0,0432 | 0,844 | 0,669 | 0,471 |
| Procesos parecidos por texto | contenido | 0,4337 | 0,0376 | 0,826 | 0,660 | 0,460 |
| Azar informado (1 / oferentes) | línea base | 0,5242 | 0,0300 | 0,714 | 0,500 | 0,301 |

El stacking casi empata en log loss pero calibra unas cuatro veces peor; como el usuario ve el porcentaje, se eligió G1.

## Lista 2 · Oportunidades

De los puestos 11–150 del ranking v2, los procesos que pasan tres filtros, ordenados por P(gana) de G1, hasta 10:

- entidad nueva para la empresa;
- como máximo 3 oferentes esperados;
- precio dentro del rango que la empresa suele ganar (|log| ≤ 1,4).

Una oportunidad es **plausible** si la empresa no la disputó, se adjudicó y tuvo 1 o 2 oferentes.

## Resultados en la prueba (jul 2025 – jul 2026)

**Lista 1**

| Métrica | Ranking v2 | Retrieval M1 solo | Mejora |
|---|---:|---:|---:|
| NDCG@10 | 0,462 | 0,362 | +28 % |
| Recall@10 | 0,566 | 0,455 | +24 % |
| Precision@10 | 0,110 | 0,086 | +27 % |
| HitRate@10 | 0,693 | 0,582 | +19 % |
| Recall ganadas@10 | 0,626 | 0,516 | +21 % |
| NDCG@10 empresas sin historial | 0,145 | 0,044 | ×3,3 |
| ROC-AUC por empresa | 0,917 | 0,850 | — |

Recall@150 del retrieval en la prueba: **78,9 %**.

**G1 · P(gana)**

| Métrica | Prueba | Validación ronda 3 |
|---|---:|---:|
| Log loss | 0,3794 | 0,3763 |
| ECE | 0,0041 | 0,0066 |
| AUC | 0,8773 | 0,8707 |
| AUC por proceso | 0,6861 | 0,6949 |
| Hit@1 (2 o más oferentes) | 0,4994 | 0,5024 |

Calibración por deciles en la prueba (lo que el modelo dice frente a lo que pasó):

| Decil | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| P(gana) media | 1,9 % | 3,9 % | 6,5 % | 10,0 % | 14,3 % | 20,2 % | 29,3 % | 44,7 % | 69,7 % | 93,0 % |
| Ganó de verdad | 1,6 % | 3,6 % | 6,3 % | 9,9 % | 14,4 % | 20,2 % | 28,4 % | 43,9 % | 70,6 % | 93,4 % |

Por segmento: en pymes, log loss 0,398 y ECE 0,004 (233.181 participaciones), igual de calibrado que el total.

**Lista 2**

| Medida | Lista 2 | Azar en 11–150 con filtros | Azar sin filtros |
|---|---:|---:|---:|
| Oportunidades plausibles | 67,7 % | 62,2 % | 42,9 % |
| Oferentes reales promedio | 1,66 | 2,03 | 4,95 |
| Plausibles con ganador parecido a la empresa | 23,0 % | 20,8 % | — |

## Familia UNSPSC inferida (`secop-unspsc`)

Desde septiembre de 2026 SECOP publica casi todos los procesos nuevos sin categoría UNSPSC, la variable categórica más pesada de G1 y una de las llaves del retrieval. Sin mitigar, el NDCG@10 de la lista 1 cae entre 6,9 % y 8,5 %.

- **Modelo:** TF-IDF de palabras y bigramas (150 mil términos) + `SGDClassifier(log_loss)`, entrenado con 570.667 procesos con categoría real (409 familias).
- **Uso:** solo llena la familia donde falta y la clase más probable pasa el umbral de 0,5. Es solo para el modelo: la web nunca la muestra como dato de SECOP.
- **Evaluación point-in-time (sep 2026):** cobertura 32,9 %; acierto de familia entre los cubiertos 79,2 %; de segmento 83,5 %.
- **Efecto:** recupera el 52–55 % de la pérdida de NDCG@10 de la lista 1 (mar 2026: 0,4760 → 0,4954; oct 2025: 0,3717 → 0,3896).

Entrenamiento y experimento: [`03-mlops/jobs/entrenar_unspsc.py`](../03-mlops/jobs/entrenar_unspsc.py) y [`03-mlops/tests/experimentos/`](../03-mlops/tests/experimentos/).

## Artefactos v1

Los artefactos de esta carpeta son los que registra MLflow y usa el job nocturno. En la nube viven en `s3://proyecto-integrador-bucket-01/modelos/v1/`, junto con la historia congelada al 27 oct 2026 (`historia/`, verificada con `manifest_historia.sha256`) y las listas de la prueba (`listas/`).

```bash
BUCKET=proyecto-integrador-bucket-01
aws s3 cp artefactos/v1/ s3://$BUCKET/modelos/v1/ --recursive
cd artefactos/v1 && shasum -a 256 -c manifest.sha256 --ignore-missing
```

El registro en MLflow (`secop-retrieval`, `secop-pgana`, `secop-ranking` con alias `production`) verifica estos checksums y comprueba que el modelo registrado predice igual que el original: [`03-mlops/jobs/registrar_v1.py`](../03-mlops/jobs/registrar_v1.py).

## Limitaciones

- No se conoce el precio que ofertará la empresa, probablemente la variable más importante para ganar.
- Empresas sin historial: Recall@150 de 43,3 % en la prueba.
- En la lista 2 la probabilidad es algo optimista: promete 38 % y se gana 30 %, porque son entidades nuevas para la empresa.
- La importancia de variables es la ganancia de LightGBM en el modelo final.
