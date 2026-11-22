// Definiciones que aparecen al pasar el mouse. Cortas, en lenguaje sencillo y con la misma redacción en toda la web.
export const GLOSARIO = {
  // Indicadores
  oferenteUnico: 'Porcentaje de procesos adjudicados en los que se presentó una sola empresa. Sin competencia, la entidad no puede comparar precios. Mejor si baja (▼ en verde).',
  oferentesPorProceso: 'Número promedio de empresas que presentaron oferta en cada proceso adjudicado. Más oferentes significa más competencia. Mejor si sube.',
  procesosCompetitivos: 'Cantidad de procesos publicados en SECOP II en modalidades donde varias empresas pueden competir por el contrato. Es contexto de volumen: no tiene una dirección buena o mala.',
  valorAdjudicado: 'Suma del dinero por el que se adjudicaron los procesos, en pesos de cada año (sin ajustar por inflación). No incluye procesos con valores atípicos (errores evidentes de registro). Es contexto de volumen.',
  valorPymes: 'Parte del valor adjudicado que ganaron pequeñas y medianas empresas. Muestra si las Pymes acceden a contratos grandes o solo a los pequeños. Mejor si sube.',
  pp: 'pp = puntos porcentuales: la diferencia directa entre dos porcentajes. Pasar de 40 % a 45 % es +5 pp.',
  // Filtros
  anio: 'Año en que se publicó el proceso en SECOP II. El año en curso (marcado con *) está incompleto: llega hasta la fecha de corte de los datos.',
  categoria: 'Segmento del código UNSPSC, el catálogo con el que SECOP clasifica lo que se compra (por ejemplo, Salud o Construcción y mantenimiento). Desde mediados de septiembre de 2026 casi todos los procesos se publican sin categoría.',
  modalidad: 'Forma legal de escoger al contratista. Mínima cuantía: compras pequeñas. Selección abreviada: bienes y servicios comunes. Licitación pública: contratos grandes. Concurso de méritos: consultorías. Régimen especial: entidades con reglas propias, como hospitales y universidades.',
  // Gráficas
  graficaTendencia: 'Cada mes, qué porcentaje de los procesos adjudicados tuvo una sola oferta. La línea gris es el dato mensual, que varía mucho; la azul es el promedio de los últimos 12 meses y muestra la tendencia. La línea punteada es el nivel de 2020 y la franja gris marca el año elegido. Haz clic en otra tarjeta de arriba para ver ese indicador.',
  graficaDepartamentos: 'Porcentaje de procesos con un solo oferente en cada departamento (o categoría) durante el año elegido. La línea punteada es el promedio. En rojo, los que están 10 puntos porcentuales o más por encima: allí la competencia es más débil. Haz clic en una barra para filtrar todo el tablero.',
  graficaModalidades: 'Compara cada modalidad entre 2020 (punto gris) y el año elegido (punto oscuro). El número de la derecha es el cambio en puntos porcentuales: ▲ en rojo significa que la competencia empeoró. Haz clic en una modalidad para filtrar el tablero.',
  graficaEntidades: 'Las 15 entidades públicas que más dinero adjudicaron en el año, ordenadas por su porcentaje de procesos con un solo oferente. Junto a cada barra va ese porcentaje y el valor adjudicado. La línea punteada es el promedio; en rojo, las que están 10 puntos porcentuales o más por encima: mucho dinero con poca competencia. Haz clic en una barra para ver la historia de la entidad.',
  graficaPymes: 'Qué parte de los procesos y qué parte del valor ganaron las Pymes en el año elegido. La línea punteada marca 2020. Si su parte del valor es mucho menor que su parte de los procesos, las Pymes están ganando contratos pequeños.',
  // Recomendador
  probabilidad: 'Estimación del modelo de qué tan probable es ganar si tu empresa presenta oferta, según su historial en SECOP II. No conoce el precio que vas a ofertar. Es normal que sea baja: varias empresas compiten por cada proceso. Un 9 % con ~10 competidores es un buen número.',
  historial: 'Procesos abiertos parecidos a los que tu empresa suele disputar. Ordenadas por qué tan probable es que te interese el proceso, no por la probabilidad de ganar: por eso un 14 % puede ir antes que un 30 %.',
  oportunidad: 'Procesos de entidades o tipos de contrato que tu empresa normalmente no miraría y que suelen tener pocos competidores. Ordenadas por probabilidad de ganar. Es una estimación con menos historial: en la prueba, esta lista prometía 38 % y se ganó 30 %.',
  cierranSemana: 'Procesos recomendados cuya fecha límite para presentar oferta es en los próximos 7 días.',
  yaTrabajaste: 'Procesos recomendados de entidades con las que tu empresa ya ha trabajado en SECOP II.',
  fechaRecomendaciones: 'Los procesos abiertos se actualizan cada mañana. Lo que el modelo sabe de tu empresa (dónde ha participado y qué ha ganado) es del 27 de octubre de 2026: una participación posterior todavía no cambia estas recomendaciones.',
  coincidencia: 'Las palabras de tu descripción que también aparecen en el objeto del proceso. Sin historial en SECOP no hay probabilidad; se ordena por coincidencia.',
}
