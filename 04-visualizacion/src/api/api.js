// ÚNICO módulo que habla con la API. Ningún componente arma URLs por su cuenta.
// Cambiar de API real a local (plan B) o a datos de prueba es cambiar VITE_API_URL.
import { getJSON as getJSONBase, ApiError, MENSAJES } from './http.js'
import { limpiar } from '../utils/formato.js'
import { FILTROS } from './indicadores.js'

// La API atiende máximo 5 peticiones a la vez (responde 429 si se pasa). El dashboard pide ~8 indicadores
// por cambio de filtro, así que aquí se limitan a 4 simultáneas y las demás esperan turno.
const MAX_SIMULTANEAS = 4
let enCurso = 0
const cola = []
function getJSON(u, opts) {
  return new Promise((resolve, reject) => {
    const correr = () => {
      enCurso++
      getJSONBase(u, opts).then(resolve, reject).finally(() => { enCurso--; cola.shift()?.() })
    }
    enCurso < MAX_SIMULTANEAS ? correr() : cola.push(correr)
  })
}

const BASE = String(import.meta.env.VITE_API_URL ?? '').trim().replace(/\/+$/, '')
const MODO_ESTADISTICAS = String(import.meta.env.VITE_ESTADISTICAS || 'auto') // auto | api | local
export const SIN_RED = BASE === '' // sin URL: todo sale de los fixtures (npm run dev:mock)

const url = (ruta, params) => {
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(params ?? {})) if (v !== undefined && v !== null && v !== '') qs.set(k, v)
  const q = qs.toString()
  return `${BASE}${ruta}${q ? `?${q}` : ''}`
}

let mockPromise = null
const mock = () => (mockPromise ??= import('./mock.js'))

// ---------- Limpieza de respuestas (la API puede traer "<NA>" en vez de null) ----------
function limpiarProceso(p) {
  return {
    ...p,
    entidad: limpiar(p.entidad),
    objeto: limpiar(p.objeto),
    categoria: limpiar(p.categoria),
    unspsc_familia: limpiar(p.unspsc_familia),
    departamento: limpiar(p.departamento),
    municipio: limpiar(p.municipio),
    modalidad: limpiar(p.modalidad),
    precio_base: limpiar(p.precio_base),
    fecha_limite_ofertas: limpiar(p.fecha_limite_ofertas),
    fecha_publicacion: limpiar(p.fecha_publicacion),
    probabilidad: limpiar(p.probabilidad),
    oferentes_esperados: limpiar(p.oferentes_esperados),
    // "Por qué se recomienda": hasta 3 de 5 textos fijos, en orden de prioridad (guía de la API, sección 4). Se muestran tal cual.
    motivos: (Array.isArray(p.motivos) ? p.motivos : []).map(limpiar).filter(Boolean),
    url_proceso: limpiar(p.url_proceso),
  }
}

function limpiarEmpresa(e) {
  return { ...e, nombre: limpiar(e.nombre) ?? 'Empresa sin nombre publicado', departamento: limpiar(e.departamento) }
}

// ---------- Endpoints ----------
export async function salud(opts) {
  if (SIN_RED) return { estado: 'ok', fuente_datos: 'fixtures', base_datos: 'ok' }
  return getJSON(url('/health'), opts)
}

export async function metadata(opts) {
  if (SIN_RED) return (await mock()).metadata()
  return getJSON(url('/metadata'), opts)
}

/** Autocompletado: la API exige ≥ 2 caracteres; la web lo activa desde el 3.º */
export async function buscarEmpresas(q, opts) {
  const texto = String(q ?? '').trim()
  if (texto.length < 2) return []
  const lista = SIN_RED ? await (await mock()).buscarEmpresas(texto) : await getJSON(url('/empresas', { q: texto }), opts)
  return lista.map(limpiarEmpresa)
}

/**
 * Huella de un proceso para detectar republicaciones: SECOP a veces tiene dos avisos abiertos (dos id_proceso)
 * con la misma entidad, objeto y precio (p. ej. IDUVI, CO1.REQ.11310897 y CO1.REQ.11367571, publicados el 3 y el
 * 12 nov; o Gachancipá, con el cierre movido del 19 al 20 nov). No son lotes: el precio es el mismo y completo.
 * Se muestra solo el primero que llega (el de mejor puesto en la lista).
 */
const huella = (p) => [p.entidad, p.objeto, p.precio_base].map((v) => String(v ?? '').toLowerCase().replace(/\s+/g, ' ').trim()).join('|')

export async function recomendaciones(proveedorKey, opts) {
  const r = SIN_RED
    ? await (await mock()).recomendaciones(proveedorKey)
    : await getJSON(url(`/empresas/${encodeURIComponent(proveedorKey)}/recomendaciones`), opts)
  const listas = {}
  const vistos = new Set()
  // historial primero: si un proceso está en las dos listas, se queda en la de historial
  const claves = Object.keys(r?.listas ?? {}).sort((a, b) => (a === 'historial' ? -1 : b === 'historial' ? 1 : 0))
  for (const clave of claves) {
    const l = r.listas[clave]
    const procesos = []
    let repetidos = 0
    for (const p of (l?.procesos ?? []).map(limpiarProceso)) {
      const h = huella(p)
      if (vistos.has(h)) { repetidos++; continue }
      vistos.add(h)
      procesos.push(p)
    }
    listas[clave] = { titulo: limpiar(l?.titulo) ?? '', procesos, repetidos }
  }
  return { ...r, listas }
}

export async function proceso(idProceso, opts) {
  const p = SIN_RED ? await (await mock()).proceso(idProceso) : await getJSON(url(`/procesos/${encodeURIComponent(idProceso)}`), opts)
  return limpiarProceso(p)
}

/** Procesos abiertos ordenados por cierre más cercano. departamento = nombre como lo escribe SECOP. */
export async function procesosAbiertos({ departamento, familia, limite = 50 } = {}, opts) {
  const lista = SIN_RED
    ? await (await mock()).procesosAbiertos({ departamento, limite })
    : await getJSON(url('/procesos/abiertos', { departamento, familia, limite }), opts)
  return lista.map(limpiarProceso)
}

// ---------- Estadísticas del dashboard ----------
// Modo auto, en este orden:
//  1. Si GET /estadisticas lista el indicador pedido, se consulta la API con filtros (contrato v2).
//  2. Si lista "snapshot", se descarga una vez GET /estadisticas/snapshot (agregados de oro del día)
//     y se filtra aquí sobre esos agregados pequeños (propuesta 7.2 de la guía de la API).
//  3. Si no, snapshot local: public/data/estadisticas-oro.json (exportado de Athena) o, en su defecto,
//     estadisticas-simulado.json (datos de ejemplo, rotulados como tales en la página).
let disponiblesEnApi = null
let motorLocal = null

async function indicadoresApi() {
  if (disponiblesEnApi) return disponiblesEnApi
  disponiblesEnApi = (async () => {
    if (SIN_RED || MODO_ESTADISTICAS === 'local') return new Set()
    try {
      const lista = await getJSON(url('/estadisticas'), { timeout: 15000 })
      return new Set((Array.isArray(lista) ? lista : []).map((x) => (typeof x === 'string' ? x : x?.indicador)).filter(Boolean))
    } catch {
      return new Set()
    }
  })()
  return disponiblesEnApi
}

async function cargarSnapshot() {
  const enApi = await indicadoresApi()
  if (enApi.has('snapshot')) {
    try {
      const s = await getJSON(url('/estadisticas/snapshot'), { timeout: 20000 })
      return { ...s, fuente: 'api' }
    } catch { /* si falla, se usan los archivos locales */ }
  }
  for (const archivo of ['estadisticas-oro.json', 'estadisticas-simulado.json']) {
    try {
      const res = await fetch(`${import.meta.env.BASE_URL}data/${archivo}`, { cache: 'no-cache' })
      if (res.ok) return await res.json()
    } catch { /* se intenta el siguiente */ }
  }
  throw new ApiError('servidor', MENSAJES.servidor)
}

async function motor() {
  if (!motorLocal) {
    motorLocal = Promise.all([cargarSnapshot(), import('./estadisticasLocal.js')]).then(([snap, m]) => ({ snap, motor: m.crearMotor(snap) }))
    motorLocal.catch(() => { motorLocal = null })
  }
  return motorLocal
}

/**
 * Devuelve { ...respuestaDelContrato, origen } con origen:
 *  'api' | 'capa_oro' (snapshot exportado de Athena) | 'simulado' (datos de ejemplo).
 */
export async function estadistica(indicador, filtros = {}, extra = {}, opts) {
  const params = Object.fromEntries(FILTROS.map((k) => [k, filtros[k]]))
  const enApi = await indicadoresApi()
  if (enApi.has(indicador) || (MODO_ESTADISTICAS === 'api' && !enApi.has('snapshot'))) {
    const r = await getJSON(url(`/estadisticas/${encodeURIComponent(indicador)}`, { ...params, ...extra }), opts)
    return { filtros_ignorados: [], notas: [], ...r, origen: 'api' }
  }
  const { snap, motor: m } = await motor()
  try {
    const origen = snap.fuente === 'api' ? 'api' : snap.fuente === 'capa_oro' ? 'capa_oro' : 'simulado'
    return { ...m.consultar(indicador, params, extra), origen, generado: snap.generado }
  } catch (e) {
    if (e.status === 404) throw new ApiError('no_encontrado', MENSAJES.no_encontrado, 404)
    throw new ApiError('servidor', MENSAJES.servidor)
  }
}

export const config = { base: BASE, sinRed: SIN_RED, modoEstadisticas: MODO_ESTADISTICAS }
