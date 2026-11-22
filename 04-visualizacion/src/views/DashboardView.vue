<script setup>
// Dashboard para la dirección de SECOP II, siguiendo el manual «Dashboards para responder preguntas de negocio».
// Pregunta principal (métrica · segmento · periodo · referencia · acción), visible arriba:
//   ¿Qué % de los procesos competitivos se adjudica con un solo oferente, por departamento, modalidad y categoría,
//   en el año elegido frente a 2020, para decidir dónde intervenir primero?
//   KPI → respuesta corta, cada uno frente a 2020 (▲▼ + color + texto)
//   P1  → ¿es una tendencia o un mal año?                     (línea; clic en una tarjeta KPI cambia el indicador)
//   P2  → ¿qué departamentos / categorías tienen menos competencia? (barras ordenadas + promedio + umbral)
//   P3  → ¿en qué modalidades empeoró desde 2020?               (mancuerna 2020 → año elegido)
//   P4  → ¿las entidades que más contratan tienen competencia? (barras ordenadas de las 15 con más valor)
//   P5  → ¿las Pymes ganan en proporción al valor?              (composición 100 %)
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import * as api from '../api/api.js'
import { useRecurso } from '../composables/useRecurso.js'
import { useFiltros } from '../composables/useFiltros.js'
import { useMetadata } from '../stores/metadata.js'
import Kpi from '../components/dashboard/Kpi.vue'
import Panel from '../components/dashboard/Panel.vue'
import Lineas from '../components/graficas/Lineas.vue'
import BarrasOrdenadas from '../components/graficas/BarrasOrdenadas.vue'
import Mancuerna from '../components/graficas/Mancuerna.vue'
import Composicion from '../components/graficas/Composicion.vue'
import DetalleEntidad from '../components/dashboard/DetalleEntidad.vue'
import Ayuda from '../components/ui/Ayuda.vue'
import { GLOSARIO } from '../utils/glosario.js'
import { pesos, pesosCorto, pesosEje, pct, numero, mesCorto, fecha, tituloEntidad, nombreCorto } from '../utils/formato.js'
import { DEPARTAMENTOS_ORDENADOS, nombreDepartamento } from '../utils/dane.js'
import { MODALIDADES, nombreModalidad } from '../utils/modalidades.js'
import { SEGMENTOS_ORDENADOS, nombreSegmento } from '../utils/unspsc.js'

const meta = useMetadata()
const { filtros, poner, alternar, limpiar } = useFiltros()
const MIN = 30          // departamentos, categorías y modalidades con menos procesos adjudicados no se grafican
const MIN_ENTIDAD = 10  // en el top 15 de entidades basta con 10 procesos adjudicados
const UMBRAL = 0.1      // alerta: 10 puntos porcentuales o más sobre el promedio
const ANIO_BASE = 2020
// Sep, oct y dic de 2022: el oferente único cae a 3–15 % en todas las modalidades a la vez (lo normal es 30–40 %)
// sin que cambie el número de procesos. Es un dato atípico de la fuente; se omite de la serie mensual (ver ficha técnica).
const MESES_ATIPICOS = new Set(['2022-09', '2022-10', '2022-12'])

const dimensiones = () => ({ departamento: filtros.value.departamento, modalidad: filtros.value.modalidad, segmento: filtros.value.segmento })
const anual = useRecurso((f, s) => api.estadistica('pymes-por-anio', f, {}, { signal: s }), dimensiones)
// Una sola fecha de corte en todo el tablero: la de los datos que se están mostrando.
const fechaCorte = computed(() => anual.datos.value?.fecha_datos ?? meta.datos?.fecha_datos ?? null)
const corte = computed(() => (fechaCorte.value ? fecha(fechaCorte.value) : '…'))
// La barra superior muestra esta misma fecha mientras el dashboard está abierto.
watch(fechaCorte, (f) => { meta.fechaPagina = f }, { immediate: true })
onBeforeUnmount(() => { meta.fechaPagina = null })
const corteCorto = computed(() => corte.value.replace(/\s\d{4}$/, ''))
const anioDatos = computed(() => (fechaCorte.value ? Number(String(fechaCorte.value).slice(0, 4)) : new Date().getFullYear()))
const filas = computed(() => anual.datos.value?.datos ?? [])
const anios = computed(() => filas.value.map((d) => Number(d.etiqueta)))
const anio = computed(() => Number(filtros.value.anio) || anioDatos.value - 1)
const parcial = computed(() => anio.value === anioDatos.value)
const anioTxt = (y) => (Number(y) === anioDatos.value ? `${y}*` : String(y))
const periodo = computed(() => (parcial.value ? `${anio.value} (hasta ${corteCorto.value})` : String(anio.value)))
const fila = (y) => filas.value.find((d) => Number(d.etiqueta) === y)?.valores ?? null
const A = computed(() => fila(anio.value))
const R = computed(() => fila(ANIO_BASE))
const esBase = computed(() => anio.value === ANIO_BASE)

const porMes = useRecurso((f, s) => api.estadistica('por-mes', f, {}, { signal: s }), dimensiones)
const porDep = useRecurso((f, s) => api.estadistica('por-departamento', f, {}, { signal: s }), () => ({ anio: anio.value, modalidad: filtros.value.modalidad, segmento: filtros.value.segmento }))
const porCat = useRecurso((f, s) => api.estadistica('por-categoria', f, {}, { signal: s }), () => ({ anio: anio.value, departamento: filtros.value.departamento, modalidad: filtros.value.modalidad }))
const porMod = useRecurso((f, s) => api.estadistica('por-modalidad', f, {}, { signal: s }), () => ({ departamento: filtros.value.departamento, segmento: filtros.value.segmento }))
const porEnt = useRecurso((f, s) => api.estadistica('top-entidades', f, { limite: 15 }, { signal: s }), () => ({ anio: anio.value, departamento: filtros.value.departamento }))

const menos = '−'
const signo = (d) => (d > 0 ? '+' : d < 0 ? menos : '±')
const flecha = (d, tol = 1e-9) => (d > tol ? '▲' : d < -tol ? '▼' : '=')
const ppTxt = (d) => `${signo(d)}${numero(Math.abs(d * 100), 1)} pp`
const alcance = computed(() => [
  filtros.value.departamento ? nombreDepartamento(filtros.value.departamento) : 'Todo el país',
  filtros.value.modalidad ? nombreModalidad(filtros.value.modalidad) : 'todas las modalidades competitivas',
  ...(filtros.value.segmento ? [nombreSegmento(filtros.value.segmento)] : []),
].join(' · '))

// ---------------- KPI (ficha técnica al pie) ----------------
// mejor: 'baja' | 'sube' | null (volumen: sin dirección buena). tipo: cómo se compara con 2020.
const FICHAS = [
  { id: 'unico', campo: 'pct_oferente_unico', nombre: 'Procesos con un solo oferente', ayuda: GLOSARIO.oferenteUnico, mejor: 'baja', tipo: 'pp', fmt: (v) => pct(v, 1),
    formula: 'Σ procesos adjudicados con una sola oferta ÷ Σ procesos adjudicados' },
  { id: 'oferentes', campo: 'oferentes_promedio', nombre: 'Oferentes por proceso', ayuda: GLOSARIO.oferentesPorProceso, mejor: 'sube', tipo: 'abs', fmt: (v) => numero(v, 1),
    formula: 'Σ ofertas recibidas ÷ Σ procesos adjudicados' },
  { id: 'procesos', campo: 'procesos', nombre: 'Procesos competitivos', ayuda: GLOSARIO.procesosCompetitivos, mejor: null, tipo: 'rel', fmt: (v) => numero(v),
    formula: 'Σ procesos publicados en modalidades con competencia' },
  { id: 'valor', campo: 'valor_adjudicado', nombre: 'Valor adjudicado', ayuda: GLOSARIO.valorAdjudicado, mejor: null, tipo: 'rel', fmt: pesosCorto, corrientes: true,
    formula: 'Σ valor adjudicado, sin procesos con valor atípico (pesos corrientes)' },
  { id: 'pymes', campo: 'pct_valor_pyme', nombre: 'Valor ganado por Pymes', ayuda: GLOSARIO.valorPymes, mejor: 'sube', tipo: 'pp', fmt: (v) => pct(v, 1),
    formula: 'Σ valor adjudicado a Pymes ÷ Σ valor adjudicado' },
]
const vale = (v) => v !== null && v !== undefined
function cambioKpi(k) {
  const a = A.value?.[k.campo], r = R.value?.[k.campo]
  if (!vale(a) || !vale(r)) return null
  if (esBase.value) return { flecha: '', texto: 'Año de referencia', estado: 'neutro' }
  if (k.tipo === 'rel' && parcial.value) return { flecha: '', texto: `Año incompleto: no se compara con ${ANIO_BASE}`, estado: 'neutro' }
  const d = a - r
  const f = flecha(d, k.tipo === 'abs' ? 0.05 : k.tipo === 'pp' ? 0.0005 : 0)
  const estado = f === '=' || !k.mejor ? 'neutro' : (k.mejor === 'baja') === (d < 0) ? 'bueno' : 'malo'
  const dif = k.tipo === 'pp' ? ppTxt(d) : k.tipo === 'abs' ? `${signo(d)}${numero(Math.abs(d), 1)}` : `${signo(d)}${numero(Math.abs(d / r) * 100)} %`
  return { flecha: f, texto: `${dif} frente a ${ANIO_BASE}${k.corrientes ? ' (pesos corrientes)' : ''}`, estado }
}
const serieHasta = (campo) => filas.value.filter((d) => Number(d.etiqueta) <= anio.value).map((d) => d.valores[campo])
const kpis = computed(() => FICHAS.map((k) => ({ ...k, valor: vale(A.value?.[k.campo]) ? k.fmt(A.value[k.campo]) : '—', cambio: cambioKpi(k), tendencia: serieHasta(k.campo) })))

// ---------------- P1 · Tendencia (cambia con la tarjeta KPI elegida) ----------------
// El mes en curso está incompleto: se excluye para no distorsionar la tendencia.
const mesParcial = computed(() => String(fechaCorte.value ?? '').slice(0, 7))
const meses = computed(() => (porMes.datos.value?.datos ?? []).filter((d) => d.etiqueta !== mesParcial.value))
const mesX = computed(() => meses.value.map((d) => d.etiqueta))
// La serie mensual trae procesos, valor y oferente único; oferentes por proceso y % de valor Pyme solo existen por año.
const GRAFICA = {
  unico: { pregunta: '¿El oferente único es una tendencia o un mal año?', detalle: '% de procesos adjudicados con un solo oferente, por mes de publicación', ayuda: GLOSARIO.graficaTendencia,
    mensual: (v, mes) => (MESES_ATIPICOS.has(mes) ? null : v.pct_oferente_unico), suma: (v, mes) => (MESES_ATIPICOS.has(mes) ? [0, 0] : [v.procesos_unico_oferente, v.procesos_con_oferentes]),
    eje: (v) => pct(v), min: 0, max: 0.8, intervalo: 0.2 },
  oferentes: { pregunta: '¿Cuántas empresas compiten por cada proceso?', detalle: 'Promedio de empresas que presentaron oferta en cada proceso adjudicado, por año', ayuda: GLOSARIO.oferentesPorProceso,
    eje: (v) => numero(v, 1), min: 0 },
  procesos: { pregunta: '¿Cuántos procesos competitivos se publican?', detalle: 'Procesos publicados en modalidades con competencia, por mes de publicación', ayuda: GLOSARIO.procesosCompetitivos,
    mensual: (v) => v.procesos, eje: (v) => numero(v), min: 0 },
  valor: { pregunta: '¿Cuánto dinero se adjudica?', detalle: 'Por mes de publicación. Pesos corrientes, sin ajustar por inflación: el crecimiento frente a 2020 está sobrestimado', ayuda: GLOSARIO.valorAdjudicado,
    mensual: (v) => v.valor_adjudicado, eje: pesosEje, etiqueta: pesosEje, min: 0,
    nota: { mes: '2025-12', texto: 'Dic 2025: licitaciones públicas\nde entidades con sede en Bogotá' } },
  pymes: { pregunta: '¿Qué parte del dinero ganan las Pymes?', detalle: '% del valor adjudicado que ganaron pequeñas y medianas empresas, por año', ayuda: GLOSARIO.valorPymes,
    eje: (v) => pct(v), min: 0, max: 1, intervalo: 0.25 },
}
const indicadorId = ref('unico')
const ficha = computed(() => FICHAS.find((k) => k.id === indicadorId.value))
const ind = computed(() => ({ ...ficha.value, ...GRAFICA[indicadorId.value] }))
const movil = (arr, i) => arr.map((_, j) => {
  if (j < 11) return null
  if (i.suma) {
    let u = 0, c = 0
    for (let k = j - 11; k <= j; k++) { const [a, b] = i.suma(arr[k].valores, arr[k].etiqueta); u += a; c += b }
    return c ? u / c : null
  }
  let t = 0
  for (let k = j - 11; k <= j; k++) t += i.mensual(arr[k].valores, arr[k].etiqueta) ?? 0
  return t / 12
})
const banda = computed(() => {
  const m = mesX.value.filter((x) => x.startsWith(String(anio.value)))
  return m.length ? { desde: m[0], hasta: m.at(-1), etiqueta: anioTxt(anio.value) } : null
})
const mm = computed(() => (ind.value.mensual ? movil(meses.value, ind.value) : []))
const tendencia = computed(() => {
  const i = ind.value
  if (!i.mensual) {
    const f = filas.value.filter((d) => vale(d.valores[i.campo]))
    const x = f.map((d) => d.etiqueta), datos = f.map((d) => d.valores[i.campo])
    const base = R.value?.[i.campo]
    const idxParcial = x.findIndex((y) => Number(y) === anioDatos.value)
    return { x, etiquetaX: anioTxt, vacio: !x.length, banda: null, anotaciones: [],
      series: [{ id: 'a', nombre: 'Anual', datos, color: 's1', simbolos: true, huecos: idxParcial >= 0 ? [idxParcial] : [], etiquetaFinal: datos.length ? i.fmt(datos.at(-1)) : null }],
      referencia: vale(base) ? { valor: base, etiqueta: `Nivel de ${ANIO_BASE}: ${i.fmt(base)}` } : null }
  }
  const mensual = meses.value.map((d) => i.mensual(d.valores, d.etiqueta))
  let base = null
  if (i.id === 'unico') base = R.value?.pct_oferente_unico ?? null
  else { const m20 = meses.value.filter((d) => d.etiqueta.startsWith(String(ANIO_BASE))); base = m20.length ? m20.reduce((s, d) => s + i.mensual(d.valores, d.etiqueta), 0) / m20.length : null }
  const anotaciones = []
  if (i.id === 'unico' && mesX.value.includes('2022-10')) anotaciones.push({ x: '2022-10', y: 0.1, texto: 'Sep, oct y dic 2022 omitidos:\ndato atípico en la fuente', posicion: 'bottom' })
  if (i.nota) {
    const k = mesX.value.indexOf(i.nota.mes)
    const orden = [...mensual].filter(vale).sort((a, b) => a - b)
    if (k >= 0 && mensual[k] >= 2 * orden[Math.floor(orden.length / 2)]) anotaciones.push({ x: i.nota.mes, y: mensual[k], texto: i.nota.texto, posicion: 'left', desplazar: [-2, 30] })
  }
  return { x: mesX.value, etiquetaX: mesCorto, vacio: !meses.value.length, banda: banda.value, anotaciones,
    series: [{ id: 'm', nombre: 'Mensual', datos: mensual, color: 'deemph' }, { id: 'mm', nombre: 'Promedio móvil de 12 meses', datos: mm.value, color: 's1', etiquetaFinal: mm.value.length && vale(mm.value.at(-1)) ? (i.etiqueta ?? i.fmt)(mm.value.at(-1)) : null }],
    referencia: vale(base) ? { valor: base, etiqueta: `${i.id === 'unico' ? 'Nivel' : 'Promedio mensual'} de ${ANIO_BASE}: ${i.fmt(base)}` } : null }
})
const respuestaP1 = computed(() => {
  const i = ind.value, a = A.value?.[i.campo], r = R.value?.[i.campo]
  if (!vale(a) || !vale(r)) return ''
  const ultimoMM = mm.value.length && vale(mm.value.at(-1)) ? `; el promedio de los últimos 12 meses va en ${i.fmt(mm.value.at(-1))} (a ${mesCorto(mesX.value.at(-1))})` : ''
  if (esBase.value) return `${ANIO_BASE} es el año de referencia: ${i.fmt(r)}${ultimoMM}.`
  if (!i.mejor && parcial.value) return `${anio.value} va hasta el ${corteCorto.value} (${i.fmt(a)}), así que no se compara con el año completo de ${ANIO_BASE}${ultimoMM}.`
  const verbo = Math.abs(a - r) < (i.tipo === 'pp' ? 0.005 : Math.abs(r) * 0.02) ? 'se mantuvo' : a > r ? 'subió' : 'bajó'
  return `${verbo === 'se mantuvo' ? 'Se mantuvo' : verbo === 'subió' ? 'Subió' : 'Bajó'} de ${i.fmt(r)} en ${ANIO_BASE} a ${i.fmt(a)} en ${anioTxt(anio.value)}${ultimoMM}.`
})

// ---------------- P2 · Departamentos o categorías ----------------
const vistaP2 = ref('departamento') // departamento | categoria
const promedio = (rows) => {
  const u = rows.reduce((s, d) => s + d.valores.procesos_unico_oferente, 0)
  const c = rows.reduce((s, d) => s + d.valores.procesos_con_oferentes, 0)
  return c ? u / c : null
}
const fuenteP2 = computed(() => (vistaP2.value === 'departamento' ? porDep : porCat))
const p2 = computed(() => {
  const esDep = vistaP2.value === 'departamento'
  const rows = fuenteP2.value.datos.value?.datos ?? []
  const prom = promedio(rows)
  const items = rows
    .filter((d) => d.codigo && d.codigo !== '00' && d.valores.procesos_con_oferentes >= MIN)
    .map((d) => ({ codigo: d.codigo, etiqueta: esDep ? d.etiqueta : nombreSegmento(d.codigo), nombre: esDep ? d.etiqueta : nombreSegmento(d.codigo, true), valor: d.valores.pct_oferente_unico,
      resaltar: prom !== null && d.valores.pct_oferente_unico >= prom + UMBRAL,
      detalle: [['Con un solo oferente', pct(d.valores.pct_oferente_unico, 1)], ['Frente al promedio', ppTxt(d.valores.pct_oferente_unico - (prom ?? 0))], ['Procesos adjudicados', numero(d.valores.procesos_con_oferentes)], ['Valor adjudicado', pesos(d.valores.valor_adjudicado)]] }))
    .sort((a, b) => b.valor - a.valor)
  const etiquetaProm = esDep ? 'promedio nacional' : 'promedio'
  const k = items.filter((i) => i.resaltar).length
  const plural = esDep ? 'departamentos' : 'categorías'
  const masAlto = esDep ? 'el más alto es' : 'la más alta es'
  const respuesta = items.length && prom !== null ? `${k} de ${items.length} ${plural} ${k === 1 ? 'está' : 'están'} 10 pp o más sobre el ${etiquetaProm} (${pct(prom, 1)}); ${masAlto} ${items[0].etiqueta} (${pct(items[0].valor, 1)}).` : ''
  return { items, prom, etiquetaProm, respuesta, esDep }
})

// ---------------- P3 · Modalidades ----------------
const modFilas = computed(() => porMod.datos.value?.datos ?? [])
const mancuerna = computed(() => {
  const val = (cod, y) => { const r = modFilas.value.find((d) => d.codigo === cod && d.anio === y); return r && r.valores.procesos_con_oferentes >= MIN ? r : null }
  const cods = [...new Set(modFilas.value.map((d) => d.codigo))]
  const rows = cods.map((cod) => { const a = val(cod, ANIO_BASE), b = val(cod, anio.value); return a && b ? { codigo: cod, etiqueta: nombreModalidad(cod), a: a.valores.pct_oferente_unico, b: b.valores.pct_oferente_unico, detalle: [['Procesos adjudicados ' + anio.value, numero(b.valores.procesos_con_oferentes)]] } : null }).filter(Boolean)
    .sort((x, y) => y.b - x.b)
  const ta = R.value?.pct_oferente_unico, tb = A.value?.pct_oferente_unico
  if (!filtros.value.modalidad && vale(ta) && vale(tb)) rows.unshift({ codigo: null, etiqueta: 'Todas las modalidades', a: ta, b: tb, total: true })
  return rows
})
const respuestaP3 = computed(() => {
  const r = mancuerna.value.filter((x) => !x.total)
  if (!r.length) return ''
  if (esBase.value) return `Elige otro año para comparar con ${ANIO_BASE}.`
  const suben = r.filter((x) => x.b > x.a).length
  const max = [...r].sort((x, y) => (y.b - y.a) - (x.b - x.a))[0]
  return `Desde ${ANIO_BASE} el oferente único subió en ${suben} de ${r.length} modalidades; el mayor cambio está en ${max.etiqueta.toLowerCase()} (${ppTxt(max.b - max.a)}, hasta ${pct(max.b, 1)}).`
})

// ---------------- P4 · Entidades que más contratan ----------------
const p4 = computed(() => {
  const prom = A.value?.pct_oferente_unico ?? null
  const items = (porEnt.datos.value?.datos ?? [])
    .filter((d) => d.valores.procesos_con_oferentes >= MIN_ENTIDAD && vale(d.valores.pct_oferente_unico))
    .map((d) => ({ codigo: d.codigo, etiqueta: nombreCorto(d.etiqueta), nombre: tituloEntidad(d.etiqueta), valor: d.valores.pct_oferente_unico, monto: d.valores.valor_adjudicado,
      etiquetaValor: `${pct(d.valores.pct_oferente_unico)} · ${pesosEje(d.valores.valor_adjudicado)}`,
      resaltar: prom !== null && d.valores.pct_oferente_unico >= prom + UMBRAL,
      detalle: [['Valor adjudicado', pesos(d.valores.valor_adjudicado)], ['Con un solo oferente', pct(d.valores.pct_oferente_unico, 1)], ['Frente al promedio', ppTxt(d.valores.pct_oferente_unico - (prom ?? 0))], ['Procesos adjudicados', numero(d.valores.procesos_con_oferentes)], ['Departamento', nombreDepartamento(d.valores.departamento) ?? '—']] }))
    .sort((a, b) => b.valor - a.valor)
  const alertas = items.filter((i) => i.resaltar)
  let respuesta = ''
  if (items.length && prom !== null) {
    const monto = pesos(alertas.reduce((s, i) => s + i.monto, 0))
    const n = items.length, k = alertas.length
    respuesta = k === 0
      ? `Ninguna de las ${n} entidades que más contratan está 10 pp sobre el promedio (${pct(prom, 1)}); la más alta es ${items[0].etiqueta} (${pct(items[0].valor, 1)}).`
      : k === 1
        ? `De las ${n} entidades que más contratan, solo ${items[0].etiqueta} está 10 pp o más sobre el promedio (${pct(items[0].valor, 1)} frente a ${pct(prom, 1)}); adjudicó ${monto}.`
        : `${k} de las ${n} entidades que más contratan están 10 pp o más sobre el promedio (${pct(prom, 1)}); juntas adjudicaron ${monto}. La más alta es ${items[0].etiqueta} (${pct(items[0].valor, 1)}).`
  }
  return { items, prom, respuesta }
})
const entidad = ref(null)
const abrirEntidad = (codigo) => { const it = p4.value.items.find((i) => i.codigo === codigo); if (it) entidad.value = { codigo, etiqueta: it.nombre } }

// ---------------- P5 · Pymes ----------------
const pymes = computed(() => {
  const a = A.value, r = R.value
  if (!a || !vale(a.pct_procesos_pyme)) return null
  return [
    { nombre: 'Procesos ganados', parte: a.pct_procesos_pyme, referencia: esBase.value ? null : r?.pct_procesos_pyme ?? null },
    { nombre: 'Valor adjudicado', parte: a.pct_valor_pyme, referencia: esBase.value ? null : r?.pct_valor_pyme ?? null },
  ]
})
const respuestaP5 = computed(() => (pymes.value ? `Las Pymes ganan ${Math.round(pymes.value[0].parte * 100)} de cada 100 procesos, pero reciben ${Math.round(pymes.value[1].parte * 100)} de cada 100 pesos.` : ''))

// ---------------- Respuesta corta a la pregunta principal ----------------
const resumen = computed(() => {
  const a = A.value?.pct_oferente_unico, r = R.value?.pct_oferente_unico
  if (!vale(a)) return ''
  const comp = !esBase.value && vale(r) ? `, ${ppTxt(a - r)} frente a ${ANIO_BASE} (${pct(r, 1)})` : ''
  const frases = [`En ${periodo.value}, ${pct(a, 1)} de los procesos competitivos se adjudicó con un solo oferente${comp}.`]
  const dep = !filtros.value.departamento ? p2.value.esDep && p2.value.items[0] : null
  const mod = mancuerna.value.filter((x) => !x.total).sort((x, y) => y.b - x.b)[0]
  const donde = [dep ? `${dep.etiqueta} (${pct(dep.valor, 1)})` : null, mod && !filtros.value.modalidad ? `${mod.etiqueta.toLowerCase()} (${pct(mod.b, 1)})` : null].filter(Boolean)
  if (donde.length) frases.push(`La competencia es más débil en ${donde.join(' y en ')}.`)
  return frases.join(' ')
})

const notas = (r) => (r.datos.value?.notas ?? []).join(' ')
const cambiarAnio = (y) => poner({ anio: y === anioDatos.value - 1 ? null : y })
const hayFiltros = computed(() => !!(filtros.value.anio || filtros.value.departamento || filtros.value.modalidad || filtros.value.segmento))
const origen = computed(() => [anual, porMes, porDep].map((r) => r.datos.value?.origen).find(Boolean))
</script>

<template>
  <div class="contenedor pt-4">
    <!-- Título + pregunta principal + filtros -->
    <div class="flex flex-wrap items-end justify-between gap-x-8 gap-y-4">
      <div class="min-w-0 max-w-[860px]">
        <h1 class="t-title">Competencia en la contratación pública</h1>
        <p class="mt-1 text-[15px] font-semibold leading-5 text-ink">¿Qué % de los procesos competitivos se adjudica con un solo oferente, por departamento, modalidad y categoría, en {{ anioTxt(anio) }} frente a {{ ANIO_BASE }}, para decidir dónde intervenir primero?</p>
        <p class="mt-1 text-[13px] text-ink-2">Para la dirección de SECOP II · se actualiza a diario · {{ alcance }}</p>
      </div>
      <div class="flex min-w-0 max-w-full flex-wrap items-end gap-3" role="group" aria-label="Filtros">
        <div class="min-w-0 max-w-full">
          <span class="rotulo"><Ayuda :texto="GLOSARIO.anio">Año</Ayuda></span>
          <div class="segmentos" role="group" aria-label="Año">
            <button v-for="y in anios" :key="y" type="button" class="tabular" :aria-pressed="y === anio" :title="y === anioDatos ? `Año incompleto: hasta el ${corte}` : undefined" @click="cambiarAnio(y)">{{ anioTxt(y) }}</button>
          </div>
        </div>
        <div class="w-44">
          <label class="rotulo" for="f-dep">Departamento</label>
          <select id="f-dep" class="campo" :value="filtros.departamento ?? ''" @change="poner({ departamento: $event.target.value || null })">
            <option value="">Todo el país</option>
            <option v-for="d in DEPARTAMENTOS_ORDENADOS" :key="d.codigo" :value="d.codigo">{{ d.nombre }}</option>
          </select>
        </div>
        <div class="w-48">
          <span class="rotulo"><label for="f-mod">Modalidad</label> <Ayuda :texto="GLOSARIO.modalidad" titulo="Modalidades de contratación">¿cuáles?</Ayuda></span>
          <select id="f-mod" class="campo" :value="filtros.modalidad ?? ''" @change="poner({ modalidad: $event.target.value || null })">
            <option value="">Todas las competitivas</option>
            <option v-for="m in MODALIDADES.filter((x) => modFilas.some((r) => r.codigo === x.codigo))" :key="m.codigo" :value="m.codigo">{{ m.nombre }}</option>
          </select>
        </div>
        <div class="w-48">
          <span class="rotulo"><label for="f-cat">Categoría</label> <Ayuda :texto="GLOSARIO.categoria" titulo="Categoría (segmento UNSPSC)">¿qué es?</Ayuda></span>
          <select id="f-cat" class="campo" :value="filtros.segmento ?? ''" @change="poner({ segmento: $event.target.value || null })">
            <option value="">Todas las categorías</option>
            <option v-for="s in SEGMENTOS_ORDENADOS" :key="s.codigo" :value="s.codigo">{{ s.corto }}</option>
          </select>
        </div>
        <button type="button" class="btn" :disabled="!hayFiltros" @click="limpiar">Restablecer</button>
      </div>
    </div>

    <!-- Respuesta corta a la pregunta principal -->
    <p v-if="resumen" class="mt-3 max-w-[1100px] text-[14px] leading-5 text-ink"><strong class="font-semibold">Respuesta corta:</strong> {{ resumen }}</p>

    <!-- KPI: clic en una tarjeta = ese indicador en la tendencia (P1) -->
    <section class="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5" aria-label="Indicadores clave. Haz clic en uno para verlo en la tendencia.">
      <Kpi v-for="k in kpis" :key="k.id" :nombre="k.nombre" :periodo="periodo" :valor="k.valor" :cambio="k.cambio" :tendencia="k.tendencia" :ultimo-parcial="parcial"
        :desde="String(ANIO_BASE)" :hasta="anioTxt(anio)" :principal="k.id === indicadorId" :ayuda="k.ayuda" :cargando="anual.primeraCarga.value" @elegir="indicadorId = k.id" />
    </section>

    <!-- P1 · P2: qué pasó y dónde -->
    <div class="mt-3 grid gap-3 xl:grid-cols-12">
      <Panel class="xl:col-span-8" :titulo="`P1 · ${ind.pregunta}`" :detalle="`${ind.detalle}. Clic en una tarjeta de arriba para cambiar el indicador.`" :ayuda="ind.ayuda"
        :respuesta="respuestaP1" :nota="notas(porMes)" :primera-carga="porMes.primeraCarga.value" :cargando="porMes.cargando.value" :error="porMes.error.value" :vacio="tendencia.vacio" :alto="262" @reintentar="porMes.recargar()">
        <Lineas :key="indicadorId" :x="tendencia.x" :etiqueta-x="tendencia.etiquetaX" :alto="262" :min="ind.min" :max="ind.max ?? null" :intervalo="ind.intervalo ?? null" :formato="ind.fmt" :formato-eje="ind.eje"
          :series="tendencia.series" :referencia="tendencia.referencia" :banda="tendencia.banda" :anotaciones="tendencia.anotaciones" :descripcion="respuestaP1" />
      </Panel>

      <Panel class="xl:col-span-4" :titulo="p2.esDep ? 'P2 · ¿Dónde hay menos competencia?' : 'P2 · ¿En qué compras hay menos competencia?'"
        :detalle="`% con un solo oferente en ${periodo}. Rojo = 10 pp o más sobre el ${p2.etiquetaProm}. Clic para filtrar.`" :ayuda="GLOSARIO.graficaDepartamentos" :respuesta="p2.respuesta"
        :nota="p2.esDep ? '' : notas(porCat)" :primera-carga="fuenteP2.primeraCarga.value" :cargando="fuenteP2.cargando.value" :error="fuenteP2.error.value" :vacio="!p2.items.length" :alto="300" @reintentar="fuenteP2.recargar()">
        <div class="segmentos mb-1" role="group" aria-label="Ver por">
          <button type="button" :aria-pressed="vistaP2 === 'departamento'" @click="vistaP2 = 'departamento'">Por departamento</button>
          <button type="button" :aria-pressed="vistaP2 === 'categoria'" @click="vistaP2 = 'categoria'">Por categoría</button>
        </div>
        <div class="max-h-[270px] overflow-y-auto pr-1">
          <BarrasOrdenadas :items="p2.items" :formato="(v) => pct(v)" :max="1" :intervalo="0.25" :altura-barra="20" :derecha="44" :ancho-etiqueta="0.42" :seleccionado="p2.esDep ? filtros.departamento : filtros.segmento"
            :referencia="p2.prom !== null ? { valor: p2.prom, etiqueta: `${p2.esDep ? 'Promedio nacional' : 'Promedio'} ${pct(p2.prom)}` } : null" :descripcion="p2.respuesta"
            @elegir="(c) => alternar(p2.esDep ? 'departamento' : 'segmento', c)" />
        </div>
      </Panel>
    </div>

    <!-- P3 · P4 · P5: por qué -->
    <div class="mt-3 grid gap-3 xl:grid-cols-12">
      <Panel class="xl:col-span-4" titulo="P3 · ¿En qué modalidades empeoró desde 2020?" :detalle="`% con un solo oferente: ${ANIO_BASE} frente a ${periodo}. Clic en una modalidad para filtrar.`" :ayuda="GLOSARIO.graficaModalidades"
        :respuesta="respuestaP3" :primera-carga="porMod.primeraCarga.value" :cargando="porMod.cargando.value" :error="porMod.error.value" :vacio="!mancuerna.length" :alto="300" @reintentar="porMod.recargar()">
        <Mancuerna :filas="mancuerna" :nombre-a="String(ANIO_BASE)" :nombre-b="anioTxt(anio)" :formato="(v) => pct(v)" :formato-cambio="ppTxt" :max="0.8" :seleccionado="filtros.modalidad" :descripcion="respuestaP3" @elegir="(c) => alternar('modalidad', c)" />
      </Panel>

      <Panel class="xl:col-span-4" titulo="P4 · ¿Las entidades que más contratan tienen competencia?" :detalle="`Las 15 entidades con más valor adjudicado en ${periodo}: % con un solo oferente · valor. Clic para ver la entidad.`" :ayuda="GLOSARIO.graficaEntidades"
        :respuesta="p4.respuesta" :nota="filtros.modalidad || filtros.segmento ? 'Esta vista no se filtra por modalidad ni por categoría.' : ''" :primera-carga="porEnt.primeraCarga.value" :cargando="porEnt.cargando.value" :error="porEnt.error.value" :vacio="!p4.items.length" :alto="300" @reintentar="porEnt.recargar()">
        <BarrasOrdenadas :items="p4.items" :formato="(v) => pct(v)" :max="1" :intervalo="0.5" :altura-barra="20" :derecha="104" :ancho-etiqueta="0.4"
          :referencia="p4.prom !== null ? { valor: p4.prom, etiqueta: `Promedio ${pct(p4.prom)}` } : null" :descripcion="p4.respuesta" @elegir="abrirEntidad" />
      </Panel>

      <Panel class="xl:col-span-4" titulo="P5 · ¿Las Pymes ganan en proporción al valor?" :detalle="`% de procesos y de valor ganados por Pymes en ${periodo}. Línea punteada: ${ANIO_BASE}.`" :ayuda="GLOSARIO.graficaPymes"
        :respuesta="respuestaP5" :primera-carga="anual.primeraCarga.value" :error="anual.error.value" :vacio="!pymes" :alto="160" @reintentar="anual.recargar()">
        <Composicion v-if="pymes" :barras="pymes" :etiqueta-referencia="esBase ? '' : String(ANIO_BASE)" :decimales="1" />
      </Panel>
    </div>

    <p class="mt-3 text-xs text-muted">
      Fuente: capa oro de SECOP II, procesos en modalidades con competencia, {{ ANIO_BASE }} al {{ corte }} · * {{ anioDatos }} es un año incompleto · valores en pesos corrientes, sin ajustar por inflación · pp = puntos porcentuales<template v-if="origen === 'simulado'"> · datos simulados</template>.
    </p>

    <details class="capa mt-3 px-4 py-3 text-[13px]">
      <summary class="cursor-pointer font-semibold text-ink">Ficha técnica de los indicadores y notas sobre los datos</summary>
      <div class="mt-3 overflow-x-auto">
        <table class="w-full min-w-[640px] border-collapse text-left">
          <thead class="text-xs text-muted">
            <tr><th class="border-b border-line py-1.5 pr-4 font-semibold">Indicador</th><th class="border-b border-line py-1.5 pr-4 font-semibold">Fórmula</th><th class="border-b border-line py-1.5 pr-4 font-semibold">Referencia</th><th class="border-b border-line py-1.5 font-semibold">Mejor si</th></tr>
          </thead>
          <tbody class="text-ink-2">
            <tr v-for="k in FICHAS" :key="k.id">
              <td class="border-b border-line py-1.5 pr-4 font-semibold text-ink">{{ k.nombre }}</td>
              <td class="border-b border-line py-1.5 pr-4">{{ k.formula }}</td>
              <td class="border-b border-line py-1.5 pr-4">{{ k.tipo === 'rel' ? `Año ${ANIO_BASE} (en la tendencia, su promedio mensual)` : `Nivel de ${ANIO_BASE}` }}</td>
              <td class="border-b border-line py-1.5">{{ k.mejor === 'baja' ? '▼ Baja' : k.mejor === 'sube' ? '▲ Sube' : 'Sin dirección (volumen)' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <ul class="mt-3 grid list-disc gap-1 pl-5 text-ink-2">
        <li>Los porcentajes son razones de sumas (nunca promedios de porcentajes). Departamentos, categorías y modalidades con menos de {{ MIN }} procesos adjudicados no se grafican; en las entidades el mínimo es {{ MIN_ENTIDAD }}.</li>
        <li><strong class="font-semibold text-ink">Régimen especial</strong> se incluye entre las modalidades competitivas porque sus procesos se publican como invitaciones en las que pueden ofertar varias empresas. Es la modalidad con más oferente único (de 53 % en 2020 a 68 % en 2025) y sube el promedio; para verla aparte, filtra por modalidad.</li>
        <li>Sep, oct y dic de 2022 se omiten de la tendencia mensual de oferente único: la fuente muestra una caída a 3–15 % en todas las modalidades a la vez, sin cambio en el número de procesos. Está en revisión con ingeniería de datos; el total anual de 2022 sí los incluye.</li>
        <li>El pico de valor de diciembre de 2025 es real: ese mes las entidades con sede en Bogotá adjudicaron $10,3 billones, $8,3 billones de ellos en licitaciones públicas.</li>
        <li>Los valores están en pesos corrientes: comparar {{ ANIO_BASE }} con años recientes sin ajustar por inflación exagera el crecimiento.</li>
        <li>Desde mediados de septiembre de 2026 SECOP publica casi todos los procesos sin categoría UNSPSC; para {{ anioDatos }} la vista por categoría está incompleta. El mes en curso no entra en la tendencia mensual.</li>
        <li>Las entidades se agrupan por NIT, como en SECOP. El valor excluye procesos con valor atípico según la regla de la capa oro.</li>
      </ul>
    </details>

    <DetalleEntidad :entidad="entidad" @cerrar="entidad = null" />
  </div>
</template>
