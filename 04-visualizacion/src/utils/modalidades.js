// Los 7 grupos de modalidad de dim_modalidad (capa oro). La web filtra por el código del grupo.
import { normalizar } from './formato.js'

export const MODALIDADES = [
  { codigo: 'minima_cuantia', nombre: 'Mínima cuantía' },
  { codigo: 'seleccion_abreviada', nombre: 'Selección abreviada' },
  { codigo: 'licitacion_publica', nombre: 'Licitación pública' },
  { codigo: 'concurso_meritos', nombre: 'Concurso de méritos' },
  { codigo: 'regimen_especial', nombre: 'Régimen especial' },
  { codigo: 'contratacion_directa', nombre: 'Contratación directa (con ofertas)' },
  { codigo: 'enajenacion', nombre: 'Enajenación de bienes' },
]
const POR_CODIGO = new Map(MODALIDADES.map((m) => [m.codigo, m]))

export function nombreModalidad(codigo) {
  return POR_CODIGO.get(codigo)?.nombre ?? codigo
}

/** Modalidad oficial de SECOP (p. ej. "Selección Abreviada de Menor Cuantía") → grupo. */
export function grupoModalidad(texto) {
  const t = normalizar(texto)
  if (!t) return null
  if (t.includes('minima')) return 'minima_cuantia'
  if (t.includes('seleccion abreviada') || t.includes('subasta inversa') || t.includes('menor cuantia')) return 'seleccion_abreviada'
  if (t.includes('licitacion')) return 'licitacion_publica'
  if (t.includes('concurso')) return 'concurso_meritos'
  if (t.includes('regimen especial')) return 'regimen_especial'
  if (t.includes('directa')) return 'contratacion_directa'
  if (t.includes('enajenacion') || t.includes('subasta') || t.includes('sobre cerrado')) return 'enajenacion'
  return null
}
