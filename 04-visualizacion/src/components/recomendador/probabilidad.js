// Textos compartidos de la tarjeta y del panel de detalle del recomendador.
import { numero } from '../../utils/formato.js'

/** "Suelen presentarse ~3 empresas" (oferentes_esperados es un promedio: se redondea). */
export function competencia(oferentes) {
  if (oferentes === null || oferentes === undefined) return ''
  const n = Math.max(1, Math.round(oferentes))
  return n === 1 ? 'Suele presentarse ~1 empresa' : `Suelen presentarse ~${numero(n)} empresas`
}

/** "Lote 1", si la API algún día manda el número de lote (hoy no lo trae). */
export const lote = (p) => (p?.lote !== null && p?.lote !== undefined && p?.lote !== '' ? `Lote ${p.lote}` : null)
