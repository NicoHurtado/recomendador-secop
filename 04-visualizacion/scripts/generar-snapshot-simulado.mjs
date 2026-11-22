// Genera public/data/estadisticas-simulado.json: agregados SIMULADOS con la forma exacta del snapshot
// que exporta scripts/exportar_snapshot_oro.py desde la capa oro. Sirve para diseñar y probar el dashboard
// mientras /estadisticas de la API está vacío. Es determinista (misma semilla → mismo archivo).
//
// Calibrado con cifras REALES del informe "Capa oro SECOP II" (17-nov-2026):
//  - 625.625 procesos competitivos en total; ~3 % sin departamento.
//  - Oferente único en mínima cuantía: 27 % (2020) → 44 % (2026); régimen especial ≈ 68 %.
//  - Categoría UNSPSC: sin categoría 8,5 % en mar-2026, 13,7 % (7-sep), 61,6 % (14-sep), 96,8 % (21-sep), >99 % desde 28-sep.
//  - Desempeño de las recomendaciones 11–17 nov (lista 1): valores reales del informe.
// Todo lo demás (reparto por departamento, categoría, entidades, valores) es inventado y se rotula como simulado en la web.
import { writeFileSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const raiz = join(dirname(fileURLToPath(import.meta.url)), '..')
const salida = join(raiz, 'public', 'data', 'estadisticas-simulado.json')

// PRNG determinista
function mulberry32(a) {
  return () => { a |= 0; a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296 }
}
const rnd = mulberry32(20261118)
const normal = () => { let u = 0, v = 0; while (!u) u = rnd(); while (!v) v = rnd(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v) }
const lognormal = (s) => Math.exp(normal() * s - (s * s) / 2)
const clamp = (x, a, b) => Math.max(a, Math.min(b, x))

const ANIOS = [2020, 2021, 2022, 2023, 2024, 2025, 2026]
const TOTAL = 625625
const PESO_ANIO = { 2020: 0.86, 2021: 0.95, 2022: 1.0, 2023: 1.06, 2024: 1.05, 2025: 1.1, 2026: 0.94 } // 2026 va hasta el 17 nov

// Departamentos: código DANE, peso en volumen, sesgo de oferente único (pp), factor de valor
const DEP = [
  ['11', 16, -4, 1.7], ['05', 12, -2, 1.2], ['76', 7, 0, 1.1], ['25', 7, 1, 0.9], ['68', 5, 1, 1.0], ['08', 4, 3, 1.1],
  ['13', 4, 5, 1.1], ['15', 3.5, 2, 0.8], ['52', 3, 6, 0.8], ['73', 3, 3, 0.8], ['19', 3, 7, 0.8], ['23', 2.5, 8, 0.9],
  ['41', 2.5, 4, 0.8], ['50', 2.5, 5, 0.9], ['54', 2.5, 6, 0.9], ['47', 2, 9, 0.9], ['20', 2, 7, 0.9], ['17', 2, 1, 0.8],
  ['66', 2, 0, 0.8], ['70', 1.5, 10, 0.8], ['44', 1.5, 12, 1.0], ['63', 1.2, 0, 0.7], ['85', 1.2, 6, 1.0], ['27', 1, 14, 0.9],
  ['18', 0.8, 10, 0.8], ['86', 0.8, 11, 0.8], ['81', 0.7, 9, 0.9], ['88', 0.4, 8, 0.9], ['91', 0.3, 16, 0.8], ['95', 0.3, 13, 0.7],
  ['99', 0.2, 15, 0.8], ['94', 0.2, 17, 0.7], ['97', 0.2, 18, 0.7],
]
const SD_PESO = 3.0 // "Sin departamento" ≈ 3 %

// Segmentos: código, peso, sesgo oferente único (pp), factor de valor
const SEG = [
  ['72', 14, -2, 2.2], ['80', 12, 4, 0.9], ['43', 6, 2, 1.1], ['85', 6, 6, 1.0], ['42', 6, -3, 0.8], ['51', 5, -4, 0.9],
  ['50', 5, 3, 0.7], ['44', 4, -6, 0.3], ['30', 4, -3, 1.3], ['78', 4, 5, 1.0], ['81', 5, 1, 1.8], ['25', 3, -1, 1.2],
  ['90', 3, 6, 0.6], ['86', 3, 8, 0.8], ['39', 2.5, -2, 0.8], ['47', 3, -5, 0.3], ['56', 2.5, -4, 0.5], ['76', 2, 4, 1.0],
  ['15', 2, 2, 1.3], ['92', 2, 3, 1.4], ['82', 2, 5, 0.5], ['46', 1.5, 0, 0.9], ['77', 1.5, 5, 1.1], ['53', 1.5, -3, 0.4],
  ['49', 1.5, -1, 0.4], ['41', 1.5, 0, 0.7], ['93', 1.2, 9, 0.6], ['84', 1, 10, 1.5], ['55', 1, 2, 0.3], ['60', 1, 0, 0.4],
]

// Grupos de modalidad: código, peso, oferente único 2020 y 2026, valor medio (COP), tasa pyme base
const MOD = [
  ['minima_cuantia', 52, 0.245, 0.415, 14e6, 0.74],
  ['seleccion_abreviada', 20, 0.33, 0.43, 320e6, 0.58],
  ['licitacion_publica', 8, 0.24, 0.31, 2.6e9, 0.42],
  ['concurso_meritos', 5, 0.29, 0.37, 650e6, 0.55],
  ['regimen_especial', 9, 0.67, 0.69, 420e6, 0.6],
  ['contratacion_directa', 4, 0.72, 0.76, 210e6, 0.57],
  ['enajenacion', 2, 0.18, 0.22, 95e6, 0.5],
]

const DEPS = [...DEP.map((d) => d[0]), 'SD']
const SEGS = [...SEG.map((s) => s[0]), '00']
const MODS = MOD.map((m) => m[0])

const pesoDep = [...DEP.map((d) => d[1]), SD_PESO]
const sumDep = pesoDep.reduce((a, b) => a + b, 0)
const sumMod = MOD.reduce((a, m) => a + m[1], 0)
const sumAnio = ANIOS.reduce((a, y) => a + PESO_ANIO[y], 0)

// Afinidad segmento × modalidad (las obras van por licitación; la papelería por mínima cuantía)
function afinidad(seg, mod) {
  if (mod === 'licitacion_publica') return ['72', '30', '81', '22'].includes(seg) ? 4 : 0.35
  if (mod === 'concurso_meritos') return ['81', '80', '72'].includes(seg) ? 5 : 0.15
  if (mod === 'enajenacion') return ['25', '95', '84'].includes(seg) ? 6 : 0.2
  if (mod === 'minima_cuantia') return ['44', '47', '56', '50', '53', '49', '55', '60', '39', '42', '80'].includes(seg) ? 1.4 : 0.85
  if (mod === 'regimen_especial') return ['85', '42', '51', '86', '90'].includes(seg) ? 2.2 : 0.7
  return 1
}

// Fracción "sin categoría" por año (2026 sube por el cambio de la fuente desde mediados de septiembre)
const SIN_CAT = { 2020: 0.035, 2021: 0.035, 2022: 0.04, 2023: 0.04, 2024: 0.045, 2025: 0.06, 2026: 0.27 }
const TASA_ADJ = { 2020: 0.84, 2021: 0.84, 2022: 0.83, 2023: 0.83, 2024: 0.82, 2025: 0.8, 2026: 0.62 }
// Estacionalidad mensual (ene bajo; picos feb-mar y oct-nov; dic bajo)
const ESTACION = [0.55, 1.15, 1.2, 1.05, 1.05, 1.0, 0.95, 1.05, 1.05, 1.1, 1.05, 0.8]
const MESES_2026 = 11 // hasta noviembre (parcial)

const anual = []
for (const y of ANIOS) {
  const totalY = (TOTAL * PESO_ANIO[y]) / sumAnio
  const t = (y - 2020) / 6
  for (let di = 0; di < DEPS.length; di++) {
    const depInfo = DEP[di] ?? ['SD', SD_PESO, 2, 0.9]
    for (let mi = 0; mi < MOD.length; mi++) {
      const [mod, wMod, u0, u1, valorMedio, pymeBase] = MOD[mi]
      const baseDM = totalY * (pesoDep[di] / sumDep) * (wMod / sumMod) * lognormal(0.18)
      // reparto por segmento, con "sin categoría"
      const pesos = SEG.map((s) => s[1] * afinidad(s[0], mod) * lognormal(0.45))
      const sp = pesos.reduce((a, b) => a + b, 0)
      for (let si = 0; si < SEGS.length; si++) {
        const esSin = SEGS[si] === '00'
        const frac = esSin ? SIN_CAT[y] : (1 - SIN_CAT[y]) * (pesos[si] / sp)
        const x = baseDM * frac; const procesos = x < 6 ? Math.floor(x / 3 + rnd()) * 3 : Math.round(x) // redondeo estocástico: celdas pequeñas dispersas, como en el dato real
        if (procesos <= 0) continue
        const segInfo = SEG[si] ?? ['00', 0, 0, 1]
        const adjudicados = Math.round(procesos * clamp(TASA_ADJ[y] + normal() * 0.02, 0.4, 0.95))
        const con_of = Math.round(adjudicados * 0.97)
        const tasaUnico = clamp(u0 + (u1 - u0) * t + (depInfo[2] + segInfo[2]) / 100 * (mod === 'regimen_especial' || mod === 'contratacion_directa' ? 0.4 : 1) + normal() * 0.025, 0.03, 0.96)
        const unico = Math.round(con_of * tasaUnico)
        const oferProm = 1 + (1 - tasaUnico) * (2.2 + rnd() * 2.6)
        const suma_of = Math.round(con_of * oferProm)
        const valor = Math.round(adjudicados * valorMedio * depInfo[3] * segInfo[3] * (1 + 0.04 * (y - 2020)) * lognormal(0.35))
        const tasaPyme = clamp(pymeBase + 0.008 * (y - 2020) + normal() * 0.04, 0.1, 0.95)
        const adj_pyme = Math.round(adjudicados * tasaPyme)
        const valor_pyme = Math.round(valor * clamp(tasaPyme * (0.55 + rnd() * 0.12), 0.05, 0.95))
        anual.push([y, di, si, mi, procesos, adjudicados, Math.round(valor / 1e6), con_of, unico, suma_of, adj_pyme, Math.round(valor_pyme / 1e6)])
      }
    }
  }
}

// ---- Mensual (mes × depto × modalidad) y mensual por segmento, repartiendo los totales anuales ----
function pesosMes(y, seg) {
  const n = y === 2026 ? MESES_2026 : 12
  const w = []
  for (let m = 0; m < n; m++) {
    let x = ESTACION[m] * lognormal(0.08)
    if (y === 2026 && m === 10) x *= 0.55 // noviembre parcial
    if (y === 2026 && seg !== undefined) {
      // En 2026 los procesos sin categoría se concentran desde mediados de septiembre
      if (seg === '00') x *= m < 8 ? 0.09 : m === 8 ? 0.6 : 1.0
      else x *= m < 8 ? 1.0 : m === 8 ? 0.45 : 0.004
    }
    w.push(x)
  }
  const s = w.reduce((a, b) => a + b, 0)
  return w.map((x) => x / s)
}
function repartir(total, pesos) {
  const crudo = pesos.map((p) => total * p)
  const ent = crudo.map(Math.floor)
  let resto = total - ent.reduce((a, b) => a + b, 0)
  const orden = crudo.map((c, i) => [c - ent[i], i]).sort((a, b) => b[0] - a[0])
  for (let k = 0; k < orden.length && resto > 0; k++, resto--) ent[orden[k][1]]++
  return ent
}
const mm = (y, m) => `${y}-${String(m + 1).padStart(2, '0')}`

const accDM = new Map()
const accS = new Map()
for (const r of anual) {
  const [y, di, si, mi] = r
  const k1 = `${y}|${di}|${mi}`; const k2 = `${y}|${si}`
  for (const [mapa, k] of [[accDM, k1], [accS, k2]]) {
    const a = mapa.get(k) ?? [0, 0, 0, 0, 0]
    a[0] += r[4]; a[1] += r[5]; a[2] += r[6]; a[3] += r[7]; a[4] += r[8]
    mapa.set(k, a)
  }
}
const mensual = []
for (const [k, a] of accDM) {
  const [y, di, mi] = k.split('|').map(Number)
  const w = pesosMes(y)
  const cols = a.map((v, j) => (j === 2 ? w.map((p) => Math.round(v * p)) : repartir(v, w)))
  for (let m = 0; m < w.length; m++) if (cols[0][m] > 0) mensual.push([mm(y, m), di, mi, cols[0][m], cols[1][m], cols[2][m], cols[3][m], Math.min(cols[4][m], cols[3][m])])
}
const mensualSeg = []
for (const [k, a] of accS) {
  const [y, si] = k.split('|').map(Number)
  const w = pesosMes(y, SEGS[si])
  const cols = a.map((v, j) => (j === 2 ? w.map((p) => Math.round(v * p)) : repartir(v, w)))
  for (let m = 0; m < w.length; m++) if (cols[0][m] > 0) mensualSeg.push([mm(y, m), si, cols[0][m], cols[1][m], cols[2][m], cols[3][m], Math.min(cols[4][m], cols[3][m])])
}
mensual.sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : a[1] - b[1] || a[2] - b[2]))
mensualSeg.sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : a[1] - b[1]))

// ---- Entidades simuladas (nombres genéricos a propósito: no se atribuyen cifras inventadas a entidades reales) ----
const TIPOS = ['Alcaldía', 'Gobernación', 'Hospital (ESE)', 'Secretaría de Educación', 'Empresa de servicios públicos', 'Universidad pública', 'Instituto de infraestructura', 'Ministerio', 'Agencia nacional', 'Fuerza pública']
const entidades = []
for (let i = 1; i <= 90; i++) {
  const di = Math.min(Math.floor(Math.pow(rnd(), 1.6) * DEP.length), DEP.length - 1)
  const tipo = TIPOS[Math.floor(rnd() * TIPOS.length)]
  const nacional = ['Ministerio', 'Agencia nacional', 'Fuerza pública'].includes(tipo)
  const d = nacional ? 0 : di // las nacionales quedan en Bogotá
  const nombre = `${tipo} · ejemplo ${String(i).padStart(2, '0')}`
  const escala = Math.pow(1 / i, 0.85) * 4.2e12 * lognormal(0.3)
  const sesgo = (nacional ? -0.08 : 0) + (DEP[d][2] / 100) + normal() * 0.08
  for (const y of ANIOS) {
    const f = PESO_ANIO[y] * lognormal(0.2)
    const procesos = Math.max(5, Math.round((escala / 9e9) * f * (0.6 + rnd())))
    const con_of = Math.round(procesos * 0.8)
    const unico = Math.round(con_of * clamp(0.38 + sesgo + 0.02 * (y - 2020) + normal() * 0.04, 0.05, 0.95))
    const contratos = Math.round(procesos * (1.1 + rnd()))
    const proveedores = Math.round(contratos * clamp(0.45 + normal() * 0.12, 0.08, 0.95))
    const hhi = clamp(0.04 + Math.abs(normal()) * 0.09 + (unico / Math.max(con_of, 1)) * 0.1, 0.01, 0.92)
    const cuota = clamp(Math.sqrt(hhi) * (0.9 + rnd() * 0.3), 0.03, 0.97)
    entidades.push([`SIM-${String(i).padStart(3, '0')}`, nombre, DEPS.indexOf(DEP[d][0]), y, procesos, con_of, unico, contratos, Math.round(escala * f / 7 / 1e6), proveedores, Number(hhi.toFixed(4)), Number(cuota.toFixed(4)), Math.round(rnd() * 2)])
  }
}

// ---- Calidad de la fuente por semana (lunes) ----
const calidad = []
const REALES = { '2026-09-07': [1798, 0.137], '2026-09-14': [1818, 0.616], '2026-09-21': [1823, 0.968] }
for (let d = new Date(Date.UTC(2020, 0, 6)); d <= new Date(Date.UTC(2026, 10, 16)); d.setUTCDate(d.getUTCDate() + 7)) {
  const s = d.toISOString().slice(0, 10)
  const y = d.getUTCFullYear()
  let procesos = Math.round((TOTAL * PESO_ANIO[y]) / sumAnio / 52 * ESTACION[d.getUTCMonth()] * lognormal(0.12))
  let sinCat
  if (REALES[s]) { procesos = REALES[s][0]; sinCat = REALES[s][1] }
  else if (s >= '2026-09-28') { procesos = Math.round(1951 + rnd() * (3339 - 1951)); sinCat = 0.992 + rnd() * 0.007 }
  else if (y === 2026) sinCat = clamp(0.07 + (d.getUTCMonth() / 8) * 0.05 + normal() * 0.01, 0.04, 0.2)
  else sinCat = clamp(SIN_CAT[y] + normal() * 0.008, 0.01, 0.1)
  calidad.push([s, procesos, Math.round(procesos * sinCat), Math.round(procesos * clamp(0.03 + normal() * 0.006, 0.005, 0.08)), Math.round(procesos * clamp(0.02 + normal() * 0.005, 0.002, 0.06)), Math.round(procesos * 0.001)])
}

// ---- Desempeño real de las recomendaciones (informe de oro, lista 1) ----
const desempeno = [
  ['2026-11-11', 'historial', 68, 0.618, 0.494], ['2026-11-12', 'historial', 1271, 0.585, 0.193],
  ['2026-11-13', 'historial', 146, 0.644, 0.357], ['2026-11-14', 'historial', 206, 0.563, 0.327],
  ['2026-11-15', 'historial', 206, 0.568, 0.326], ['2026-11-16', 'historial', 243, 0.531, 0.37],
  ['2026-11-17', 'historial', 65, 0.692, 0.682],
]

const snapshot = {
  version: 1,
  fuente: 'simulado',
  descripcion: 'Agregados SIMULADOS con la forma de la capa oro, para diseñar el dashboard mientras /estadisticas está vacío. No son datos de SECOP.',
  generado: new Date().toISOString(),
  fecha_datos: '2026-11-17',
  escala_valor: 1e6, // los montos van en millones de pesos para aligerar el archivo
  anios: ANIOS,
  departamentos: DEPS,
  segmentos: SEGS,
  modalidades: MODS,
  anual: { cols: ['anio', 'd', 's', 'm', 'procesos', 'adjudicados', 'valor', 'con_of', 'unico', 'suma_of', 'adj_pyme', 'valor_pyme'], filas: anual },
  mensual: { cols: ['mes', 'd', 'm', 'procesos', 'adjudicados', 'valor', 'con_of', 'unico'], filas: mensual },
  mensual_segmento: { cols: ['mes', 's', 'procesos', 'adjudicados', 'valor', 'con_of', 'unico'], filas: mensualSeg },
  entidades: { cols: ['key', 'nombre', 'd', 'anio', 'procesos', 'con_of', 'unico', 'contratos', 'valor', 'proveedores', 'hhi', 'cuota_principal', 'atipicos'], filas: entidades },
  calidad: { cols: ['semana', 'procesos', 'sin_categoria', 'sin_departamento', 'sin_precio', 'precio_atipico'], filas: calidad },
  desempeno: { cols: ['fecha_corte', 'lista', 'ofertas_reales', 'cobertura', 'precision_activas'], filas: desempeno, nota: 'Valores reales de la lista 1 (historial) según el informe de la capa oro del 17 nov 2026. La lista 2 tiene cobertura cercana a 0 por diseño.' },
}

mkdirSync(dirname(salida), { recursive: true })
writeFileSync(salida, JSON.stringify(snapshot))
const tot = anual.reduce((a, r) => a + r[4], 0)
console.log(`Escrito ${salida}`)
console.log(`  anual: ${anual.length} filas · mensual: ${mensual.length} · mensual_segmento: ${mensualSeg.length} · entidades: ${entidades.length} · semanas: ${calidad.length}`)
console.log(`  procesos totales: ${tot.toLocaleString('es-CO')}`)
