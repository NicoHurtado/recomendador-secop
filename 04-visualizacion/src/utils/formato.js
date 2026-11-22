// Formatos en español de Colombia: pesos, porcentajes, fechas y textos de SECOP.
const NBSP = '\u00a0'
const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
const MESES_LARGOS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
const VACIOS = new Set(['', '<na>', 'na', 'n/a', 'nan', 'none', 'null', 'undefined', 'no definido', 'no aplica'])

/** La API a veces devuelve textos como "<NA>" en vez de null. Esto los convierte en null. */
export function limpiar(v) {
  if (v === null || v === undefined) return null
  if (typeof v === 'number') return Number.isFinite(v) ? v : null
  const s = String(v).trim()
  return VACIOS.has(s.toLowerCase()) ? null : s
}

export function normalizar(s) {
  return String(s ?? '')
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .toLowerCase().replace(/[^a-z0-9ñ ]+/g, ' ').replace(/\s+/g, ' ').trim()
}

const nf = (min, max) => new Intl.NumberFormat('es-CO', { minimumFractionDigits: min, maximumFractionDigits: max })
const NF0 = nf(0, 0)
const NF1 = nf(0, 1)

export function numero(v, decimales = 0) {
  v = limpiar(v)
  if (v === null) return '—'
  return decimales === 0 ? NF0.format(v) : nf(0, decimales).format(v)
}

/** Número compacto para ejes y tarjetas: 12.900 → "12,9 mil"; 1.250.000 → "1,3 M". */
export function numeroCompacto(v) {
  v = limpiar(v)
  if (v === null) return '—'
  const a = Math.abs(v)
  if (a >= 1e6) return `${NF1.format(v / 1e6)}${NBSP}M`
  if (a >= 1e4) return `${NF1.format(v / 1e3)}${NBSP}mil`
  return NF0.format(v)
}

/** "$171,8 millones", "$25,9 mil millones", "$1,2 billones" (billón colombiano = 10¹²). */
export function pesos(v, { nulo = 'Valor no publicado' } = {}) {
  v = limpiar(v)
  if (v === null) return nulo
  const a = Math.abs(v)
  const conUnidad = (n, sing, plur) => { const t = NF1.format(n); return `$${t}${NBSP}${t === '1' ? sing : plur}` }
  if (a >= 1e12) return conUnidad(v / 1e12, 'billón', 'billones')
  if (a >= 1e9) return `$${NF1.format(v / 1e9)}${NBSP}mil millones`
  if (a >= 1e6) return conUnidad(v / 1e6, 'millón', 'millones')
  return `$${NF0.format(v)}`
}

/** Para tarjetas KPI: "$51,8 billones", "$592,8 mil M", "$35 M". */
export function pesosCorto(v) {
  v = limpiar(v)
  if (v === null) return '—'
  const a = Math.abs(v)
  if (a >= 1e12) return pesos(v)
  if (a >= 1e9) return `$${NF1.format(v / 1e9)}${NBSP}mil${NBSP}M`
  if (a >= 1e6) return `$${NF1.format(v / 1e6)}${NBSP}M`
  return `$${NF0.format(v)}`
}

/** Para ejes: "$1,2 B", "$350 mil M", "$80 M". Etiquetas cortas y legibles. */
export function pesosEje(v) {
  const a = Math.abs(v)
  if (a >= 1e12) return `$${NF1.format(v / 1e12)}${NBSP}bill.`
  if (a >= 1e9) return `$${NF1.format(v / 1e9)}${NBSP}mil${NBSP}M`
  if (a >= 1e6) return `$${NF0.format(v / 1e6)}${NBSP}M`
  return `$${NF0.format(v)}`
}

/** "$35.000.000" */
export function pesosCompleto(v) {
  v = limpiar(v)
  if (v === null) return 'Valor no publicado'
  return `$${NF0.format(Math.round(v))}`
}

/** Porcentaje desde una fracción 0–1: 0.0882 → "9 %". */
export function pct(fraccion, decimales = 0) {
  fraccion = limpiar(fraccion)
  if (fraccion === null) return '—'
  const v = fraccion * 100
  const txt = decimales === 0 ? NF0.format(Math.round(v)) : nf(decimales, decimales).format(v)
  return `${txt}${NBSP}%`
}

/** Probabilidad para la tarjeta: nunca "0 %" si es positiva; "<1 %". */
export function probabilidad(p) {
  p = limpiar(p)
  if (p === null) return '—'
  if (p > 0 && p < 0.005) return `<1${NBSP}%`
  return pct(p)
}

function partesFecha(s) {
  s = limpiar(s)
  if (!s) return null
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s)
  if (!m) return null
  return { y: +m[1], m: +m[2], d: +m[3] }
}

/** "2026-11-17" → "17 nov 2026" (sin desfase de zona horaria). */
export function fecha(s) {
  const p = partesFecha(s)
  if (!p) return '—'
  return `${p.d} ${MESES[p.m - 1]} ${p.y}`
}

/** "2026-03" → "mar 2026" */
export function mesCorto(s) {
  const m = /^(\d{4})-(\d{2})/.exec(String(s))
  return m ? `${MESES[+m[2] - 1]} ${m[1]}` : String(s)
}
export function mesLargo(s) {
  const m = /^(\d{4})-(\d{2})/.exec(String(s))
  return m ? `${MESES_LARGOS[+m[2] - 1]} de ${m[1]}` : String(s)
}

/** Fecha de hoy en Bogotá como "AAAA-MM-DD". */
export function hoyBogota(ahora = new Date()) {
  const f = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Bogota', year: 'numeric', month: '2-digit', day: '2-digit' })
  return f.format(ahora)
}

/** ISO en UTC → "18 nov 2026, 8:21 a. m." en hora de Colombia. */
export function fechaHoraBogota(iso) {
  iso = limpiar(iso)
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const dia = fecha(hoyBogota(d))
  const hora = new Intl.DateTimeFormat('es-CO', { timeZone: 'America/Bogota', hour: 'numeric', minute: '2-digit', hour12: true }).format(d)
  return `${dia}, ${hora}`
}

export function diasEntre(desde, hasta) {
  const a = partesFecha(desde)
  const b = partesFecha(hasta)
  if (!a || !b) return null
  return Math.round((Date.UTC(b.y, b.m - 1, b.d) - Date.UTC(a.y, a.m - 1, a.d)) / 86400000)
}

/** Texto de cierre de un proceso: "Cierra en 4 días (17 nov)"; el año solo si no es el actual. Urgente si quedan menos de 5 días. */
export function cierre(fechaLimite, hoy = hoyBogota()) {
  const dias = diasEntre(hoy, fechaLimite)
  if (dias === null) return { dias: null, texto: 'Fecha de cierre no publicada', urgente: false, cerrado: false }
  const f = String(fechaLimite).slice(0, 4) === String(hoy).slice(0, 4) ? fecha(fechaLimite).replace(/\s\d{4}$/, '') : fecha(fechaLimite)
  if (dias < 0) return { dias, texto: `Cerrado (${f})`, urgente: false, cerrado: true }
  if (dias === 0) return { dias, texto: `Cierra hoy (${f})`, urgente: true, cerrado: false }
  if (dias === 1) return { dias, texto: `Cierra mañana (${f})`, urgente: true, cerrado: false }
  return { dias, texto: `Cierra en ${dias} días (${f})`, urgente: dias < 5, cerrado: false }
}

const MINUSCULAS = new Set(['de', 'del', 'la', 'las', 'los', 'el', 'y', 'e', 'en', 'a', 'al', 'para', 'por', 'con', 'o', 'u'])
const SIGLAS = new Set(['ese', 'e.s.e', 'e.s.e.', 'sena', 'icbf', 'dane', 'invias', 'uae', 'ips', 'eps', 'esp', 'e.s.p', 'e.s.p.', 'sas', 's.a.s', 's.a.s.', 's.a', 's.a.', 'd.c', 'd.c.', 'dc', 'ltda', 'ltda.', 'ani', 'dian', 'car', 'cra', 'emcali', 'epm', 'ii', 'iii', 'iv', 'vi', 'vii', 'viii', 'ix', 'xi', 'xii', 'unad', 'unal', 'tic', 'ue', 'ut', 'mintic', 'fonade', 'enterritorio', 'idu', 'ica', 'igac', 'ungrd', 'inpec', 'uspec', 'fiduprevisora', 'colpensiones'])

// SECOP publica muchos nombres en mayúsculas sin tildes. Palabras frecuentes en nombres de entidades.
const TILDES = Object.fromEntries(['Alcaldía', 'Gobernación', 'Secretaría', 'Educación', 'Nación', 'Nacional', 'Pública', 'Público', 'Públicos', 'Públicas',
  'Policía', 'Fiscalía', 'Contraloría', 'Personería', 'Procuraduría', 'Registraduría', 'Defensoría', 'Jurisdicción', 'Información', 'Tecnología',
  'Tecnológico', 'Tecnológica', 'Innovación', 'Investigación', 'Corporación', 'Autónoma', 'Región', 'Dirección', 'Administración', 'Gestión',
  'Atención', 'Protección', 'Planeación', 'Participación', 'Integración', 'Recreación', 'Población', 'Rehabilitación', 'Energía', 'Pacífico',
  'Económico', 'Económica', 'Técnica', 'Técnico', 'Vías', 'Ejército', 'Aeronáutica', 'Crédito', 'Hábitat', 'Turístico', 'Histórico', 'Bogotá',
  'Medellín', 'Bolívar', 'Córdoba', 'Boyacá', 'Caquetá', 'Chocó', 'Quindío', 'Vaupés', 'Guainía', 'Atlántico', 'Cúcuta', 'Ibagué', 'Popayán',
  'Montería', 'Fusagasugá', 'Zipaquirá', 'Itagüí', 'Tuluá', 'Policlínica', 'Clínica', 'Médico', 'Ingeniería', 'Ingenierías',
  'Compañía', 'Logística', 'Tecnologías', 'Asociación', 'Fundación', 'Consultoría', 'Consultorías', 'Interventoría', 'Asesoría', 'Electrónica',
  'Eléctrica', 'Eléctricas', 'Eléctricos', 'Óptica', 'Química', 'Biomédica', 'Biomédicos', 'Topografía', 'Arquitectónica', 'Comunicación', 'Unión', 'Inversión', 'Inversiones']
  .map((w) => [w.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase(), w.toLowerCase()]))

/** Entidades como vienen de SECOP ("ALCALDIA LOCAL DE TEUSAQUILLO(oficial)") → "Alcaldía Local de Teusaquillo". */
export function tituloEntidad(s) {
  s = limpiar(s)
  if (!s) return 'Entidad no publicada'
  s = s.replace(/\(\s*oficial\s*\)/gi, '').replace(/[\s/\\.,;:*+-]+$/, '').replace(/(\p{L}{3,})-(\p{L}{3,})/gu, '$1 - $2').replace(/\s+/g, ' ').trim()
  const palabras = s.split(' ')
  if (palabras.length === 1 && s.length <= 8 && s === s.toUpperCase()) return s
  return palabras.map((w, i) => {
    const l = w.toLowerCase()
    const nucleo = l.replace(/^[(]+/, '').replace(/[),;:.]+$/, '')
    if (SIGLAS.has(nucleo) && w === w.toUpperCase()) return w
    if (/\d/.test(w)) return w
    if (i > 0 && MINUSCULAS.has(l)) return l
    const conTilde = TILDES[nucleo] ? l.replace(nucleo, TILDES[nucleo]) : l
    return conTilde.replace(/(^|[-/(])(\p{L})/gu, (_, a, b) => a + b.toUpperCase())
  }).join(' ')
}

/**
 * Nombre corto para etiquetas de gráficas (el nombre completo va en el tooltip).
 * "Gobernación del Departamento del Cesar" → "Gobernación del Cesar";
 * "Distrito Especial Industrial y Portuario de Barranquilla" → "Distrito de Barranquilla".
 */
export function nombreCorto(s) {
  let t = tituloEntidad(s)
  t = t.replace(/\s+(S\.?A\.?S?\.?|E\.?S\.?P\.?|Ltda\.?)(?=\s|$)/g, '').trim()
  t = t.replace(/^RNEC$/, 'Registraduría (RNEC)')
  t = t.replace(/^Gobernación del Departamento (del?) /, 'Gobernación $1 ')
  t = t.replace(/^Departamento (del?) /, 'Gobernación $1 ')
  t = t.replace(/^Santiago de Cali Distrito Especial\s*-\s*/, 'Cali · ')
  t = t.replace(/^(Alcaldía del )?Distrito((?: Especial| Turístico| Cultural| Industrial| Portuario| Histórico| Biodiverso| Deportivo| y| de Ciencia,? Tecnología e Innovación)+) de /, 'Distrito de ')
  t = t.replace(/^Corporación Autónoma Regional (?:del? )?(.+?)(?:\s*-\s*\S+)?$/, 'CAR $1')
  t = t.replace(/Unidad Administrativa Especial/g, 'UAE')
  t = t.replace(/\s+Grupo de Apoyo Administrativo Mixto$/, '')
  const sigla = /^(.{30,}?)\s*-\s*(\p{L}{2,8})$/u.exec(t)
  if (sigla && t.length > 44) t = sigla[2].toUpperCase()
  return t
}

/**
 * Primera letra en mayúscula, el resto como viene pero sin gritar si casi todo está en mayúsculas.
 * `nombres` (municipio, departamento…) se vuelven a escribir con mayúscula inicial: "municipio de chía" → "municipio de Chía".
 */
const VARIANTES = { a: '[aáà]', e: '[eéè]', i: '[iíì]', o: '[oóò]', u: '[uúü]', n: '[nñ]' }
export function oracion(s, nombres = []) {
  s = limpiar(s)
  if (!s) return ''
  const letras = s.replace(/[^\p{L}]/gu, '')
  const mayus = letras.replace(/[^\p{Lu}]/gu, '').length
  let t = letras.length && mayus / letras.length > 0.7 ? s.toLowerCase() : s // "grita" si casi todo está en mayúsculas
  for (const n of nombres) {
    const limpio = limpiar(n)
    if (!limpio || limpio.length < 3) continue
    const propio = limpio.toLowerCase().replace(/(^|[\s-])(\p{L})/gu, (_, a, b) => a + b.toUpperCase()).replace(/\s(De|Del|La|Las|Los|El|Y)\s/g, (m) => m.toLowerCase())
    // insensible a tildes: "gachancipa" también se reconoce como "Gachancipá"
    const patron = normalizar(limpio).split(' ').map((w) => [...w].map((ch) => VARIANTES[ch] ?? ch.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('')).join('[\\s-]+')
    const re = new RegExp(`(^|[^\\p{L}])${patron}(?=[^\\p{L}]|$)`, 'giu')
    t = t.replace(re, (_, a) => a + propio)
  }
  return t.charAt(0).toUpperCase() + t.slice(1)
}
