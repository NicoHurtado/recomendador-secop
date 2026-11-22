// Contrato v2 de /estadisticas: indicadores del dashboard y sus dimensiones.
// Todos los porcentajes viajan como fracción 0–1. Los montos, en pesos corrientes (COP).
export const INDICADORES = {
  resumen: { descripcion: 'Los cuatro números de cabecera', unidad: 'mixta' },
  'por-departamento': { descripcion: 'Procesos, valor adjudicado y oferente único por departamento (código DANE)', unidad: 'mixta' },
  'por-categoria': { descripcion: 'Lo mismo por segmento UNSPSC', unidad: 'mixta' },
  'por-mes': { descripcion: 'Procesos publicados y valor adjudicado por mes de publicación', unidad: 'mixta' },
  'por-modalidad': { descripcion: 'Oferente único por grupo de modalidad y año', unidad: 'fraccion' },
  'pymes-por-anio': { descripcion: 'Participación de las Pymes en procesos ganados y en valor ganado, por año', unidad: 'fraccion' },
  'top-entidades': { descripcion: 'Las 15 entidades con más valor adjudicado en procesos competitivos, con su % de oferente único', unidad: 'COP' },
  'detalle-entidad': { descripcion: 'Serie anual de una entidad', unidad: 'mixta' },
  'calidad-fuente': { descripcion: 'Calidad de la fuente por semana de publicación', unidad: 'fraccion' },
  'desempeno-recomendaciones': { descripcion: 'Desempeño real de las recomendaciones por día de corte', unidad: 'fraccion' },
}

/** Filtros globales del dashboard (van en la URL y en la consulta a la API). */
export const FILTROS = ['anio', 'departamento', 'segmento', 'modalidad']
