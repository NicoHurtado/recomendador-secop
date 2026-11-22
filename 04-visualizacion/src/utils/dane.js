// Tabla de equivalencias nombre de departamento (como lo escribe SECOP) → código DANE (DIVIPOLA).
// La API devuelve nombres; el GeoJSON del mapa usa códigos. Bogotá y San Andrés se escriben distinto en SECOP.
import { normalizar } from './formato.js'

export const DEPARTAMENTOS = [
  { codigo: '05', nombre: 'Antioquia' }, { codigo: '08', nombre: 'Atlántico' }, { codigo: '11', nombre: 'Bogotá D.C.' },
  { codigo: '13', nombre: 'Bolívar' }, { codigo: '15', nombre: 'Boyacá' }, { codigo: '17', nombre: 'Caldas' },
  { codigo: '18', nombre: 'Caquetá' }, { codigo: '19', nombre: 'Cauca' }, { codigo: '20', nombre: 'Cesar' },
  { codigo: '23', nombre: 'Córdoba' }, { codigo: '25', nombre: 'Cundinamarca' }, { codigo: '27', nombre: 'Chocó' },
  { codigo: '41', nombre: 'Huila' }, { codigo: '44', nombre: 'La Guajira' }, { codigo: '47', nombre: 'Magdalena' },
  { codigo: '50', nombre: 'Meta' }, { codigo: '52', nombre: 'Nariño' }, { codigo: '54', nombre: 'Norte de Santander' },
  { codigo: '63', nombre: 'Quindío' }, { codigo: '66', nombre: 'Risaralda' }, { codigo: '68', nombre: 'Santander' },
  { codigo: '70', nombre: 'Sucre' }, { codigo: '73', nombre: 'Tolima' }, { codigo: '76', nombre: 'Valle del Cauca' },
  { codigo: '81', nombre: 'Arauca' }, { codigo: '85', nombre: 'Casanare' }, { codigo: '86', nombre: 'Putumayo' },
  { codigo: '88', nombre: 'San Andrés y Providencia' }, { codigo: '91', nombre: 'Amazonas' }, { codigo: '94', nombre: 'Guainía' },
  { codigo: '95', nombre: 'Guaviare' }, { codigo: '97', nombre: 'Vaupés' }, { codigo: '99', nombre: 'Vichada' },
]

/** Nombre que espera la API en /procesos/abiertos?departamento= (como lo escribe SECOP). */
const NOMBRE_SECOP = { '11': 'Distrito Capital de Bogotá', '88': 'San Andrés, Providencia y Santa Catalina' }

const ALIAS = {
  'distrito capital de bogota': '11', 'bogota': '11', 'bogota d c': '11', 'bogota dc': '11', 'santafe de bogota d c': '11',
  'santa fe de bogota': '11', 'bogota distrito capital': '11', 'distrito capital': '11',
  'san andres providencia y santa catalina': '88', 'archipielago de san andres providencia y santa catalina': '88',
  'san andres': '88', 'san andres y providencia': '88', 'archipielago de san andres': '88',
  'guajira': '44', 'valle': '76', 'norte santander': '54',
}

const POR_NORMAL = new Map()
for (const d of DEPARTAMENTOS) POR_NORMAL.set(normalizar(d.nombre), d.codigo)
for (const [k, v] of Object.entries(ALIAS)) POR_NORMAL.set(k, v)
const POR_CODIGO = new Map(DEPARTAMENTOS.map((d) => [d.codigo, d]))

export function codigoDepartamento(nombre) {
  if (nombre === null || nombre === undefined) return null
  const s = String(nombre).trim()
  if (/^\d{1,2}$/.test(s)) return s.padStart(2, '0')
  return POR_NORMAL.get(normalizar(s)) ?? null
}

export function nombreDepartamento(codigo) {
  return POR_CODIGO.get(String(codigo ?? '').padStart(2, '0'))?.nombre ?? null
}

/** Nombre de un departamento listo para mostrar, venga como venga. */
export function departamentoLegible(valor) {
  const c = codigoDepartamento(valor)
  return c ? nombreDepartamento(c) : null
}

export function nombreSecop(codigo) {
  return NOMBRE_SECOP[codigo] ?? nombreDepartamento(codigo)
}

export const DEPARTAMENTOS_ORDENADOS = [...DEPARTAMENTOS].sort((a, b) => a.nombre.localeCompare(b.nombre, 'es'))
