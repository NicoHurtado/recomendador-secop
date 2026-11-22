// Ordena procesos abiertos por coincidencia de palabras con lo que describe la empresa.
// Es una ayuda de búsqueda sobre unos cientos de procesos ya filtrados, NO el modelo de recomendación.
import { normalizar } from './formato.js'

const VACIAS = new Set(('de la el los las y en para por con del al a un una unos unas su sus que se o e lo como mas otros otras ' +
  'servicio servicios prestacion prestamos contratar contratacion suministro suministros adquisicion compra proceso municipio departamento ' +
  'entidad empresa empresas vendemos ofrecemos somos hacemos nuestra nuestro nuestros todo tipo general generales cumplimiento objeto marco ' +
  'elementos productos equipos insumos').split(' '))

function raiz(w) {
  return w.replace(/(aciones|iciones|amientos|imientos|mente|ciones|cion|es|s)$/u, '') || w
}

/** Palabras clave de un texto: [{ r: raíz para comparar, w: palabra original para mostrar }]. */
export function palabrasClave(texto) {
  const vistas = new Map()
  for (const w of normalizar(texto).split(' ')) {
    if (w.length <= 3 || VACIAS.has(w)) continue
    const r = raiz(w)
    if (!vistas.has(r)) vistas.set(r, w)
  }
  return [...vistas].map(([r, w]) => ({ r, w }))
}

function raices(texto) {
  return new Set(normalizar(texto).split(' ').map(raiz))
}

export function puntuar(proceso, claves) {
  if (!claves.length) return 0
  const t = raices(proceso.objeto)
  let n = 0
  for (const c of claves) if (t.has(c.r)) n++
  return n / Math.sqrt(claves.length)
}

/** Palabras de la descripción (tal como las escribió la empresa) que aparecen en el objeto del proceso. */
export function coincidencias(proceso, claves, max = 3) {
  const t = raices(proceso.objeto)
  return claves.filter((c) => t.has(c.r)).slice(0, max).map((c) => c.w)
}
