// API simulada para trabajar sin red (npm run dev:mock). Usa respuestas reales guardadas de la API
// el 18 nov 2026, con exactamente el mismo formato. Solo se carga cuando VITE_API_URL está vacío.
import metadataFx from './fixtures/metadata.json'
import empresasA from './fixtures/empresas-construcciones.json'
import empresasB from './fixtures/empresas-suministros.json'
import recos from './fixtures/recomendaciones.json'
import abiertos from './fixtures/procesos-abiertos.json'
import { normalizar } from '../utils/formato.js'
import { ApiError, MENSAJES } from './http.js'

const espera = (ms) => new Promise((r) => setTimeout(r, ms))
const EMPRESAS = [...empresasA, ...empresasB]

export async function metadata() {
  await espera(250)
  return structuredClone(metadataFx)
}

export async function buscarEmpresas(q) {
  await espera(200)
  const n = normalizar(q)
  return EMPRESAS.filter((e) => normalizar(e.nombre).includes(n)).slice(0, 20)
}

export async function recomendaciones(key) {
  await espera(400)
  const r = recos[key]
  if (r) return structuredClone(r)
  // Igual que la API real: una empresa sin listas (o una llave que no existe) responde 200 con listas vacías.
  return {
    proveedor_key: key, fecha_corte: metadataFx.fecha_datos, tiene_historial: false, version_modelos: metadataFx.version_modelos,
    listas: {
      historial: { titulo: 'Recomendados según tu historial', procesos: [] },
      oportunidad: { titulo: 'Oportunidades que normalmente no verías', procesos: [] },
    },
  }
}

export async function proceso(id) {
  await espera(200)
  const p = abiertos.find((x) => x.id_proceso === id)
  if (!p) throw new ApiError('no_encontrado', MENSAJES.no_encontrado, 404)
  return structuredClone(p)
}

export async function procesosAbiertos({ departamento, limite = 50 }) {
  await espera(300)
  const n = departamento ? normalizar(departamento) : null
  return abiertos.filter((p) => !n || normalizar(p.departamento) === n).slice(0, limite)
}
