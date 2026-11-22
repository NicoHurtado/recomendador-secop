<script setup>
// Dispersión: valor adjudicado (X, escala logarítmica) frente a % de oferente único (Y).
// Referencias punteadas: mediana de valor y promedio de oferente único. El cuadrante
// "mucho valor y poca competencia" va en color de alerta; el resto en gris de contexto.
import { computed } from 'vue'
import { VChart } from '../../charts/echarts.js'
import { base, ejeValores, filaTooltip, tituloTooltip } from '../../charts/tema.js'
import { useTemaGrafica } from '../../composables/useTemaGrafica.js'

const props = defineProps({
  puntos: { type: Array, required: true }, // [{ id, nombre, x, y, alerta, detalle }]
  refX: { type: Number, default: null },
  refY: { type: Number, default: null },
  formatoX: { type: Function, required: true },
  formatoY: { type: Function, required: true },
  nombreX: { type: String, default: '' },
  nombreY: { type: String, default: '' },
  etiquetar: { type: Array, default: () => [] },
  alto: { type: Number, default: 380 },
  descripcion: { type: String, default: '' },
})
const emit = defineEmits(['elegir'])
const t = useTemaGrafica()

const option = computed(() => {
  const c = t.value
  const xs = props.puntos.map((p) => p.x).filter((v) => v > 0)
  const xMin = xs.length ? 10 ** Math.floor(Math.log10(Math.min(...xs))) : 1
  const xMax = xs.length ? 10 ** Math.ceil(Math.log10(Math.max(...xs))) : 10
  const corto = (s) => (s.length > 26 ? `${s.slice(0, 25)}…` : s)
  const serie = (alerta) => ({
    type: 'scatter', cursor: 'pointer', symbolSize: alerta ? 10 : 8, z: alerta ? 3 : 2,
    data: props.puntos.filter((p) => !!p.alerta === alerta).map((p) => ({
      value: [p.x, p.y], id: p.id, nombre: p.nombre,
      label: props.etiquetar.includes(p.id) ? { show: true, formatter: corto(p.nombre), position: 'right', color: c.ink1, fontSize: 11, distance: 5 } : undefined,
    })),
    itemStyle: { color: alerta ? c.alerta : c.deemph, opacity: alerta ? 0.9 : 0.75, borderColor: c.surface1, borderWidth: 1 },
    emphasis: { itemStyle: { borderColor: c.ink1, borderWidth: 2, opacity: 1 } },
    labelLayout: { hideOverlap: true },
  })
  const s0 = serie(false)
  s0.markLine = {
    symbol: 'none', silent: true, lineStyle: { color: c.ref, width: 1, type: [4, 4] }, label: { color: c.ink2, fontSize: 11 },
    data: [
      ...(props.refX ? [{ xAxis: props.refX, label: { formatter: `Mediana de valor ${props.formatoX(props.refX)}`, position: 'end' } }] : []),
      ...(props.refY !== null ? [{ yAxis: props.refY, label: { formatter: `Promedio ${props.formatoY(props.refY)}`, position: 'insideStartTop' } }] : []),
    ],
  }
  return {
    ...base(c),
    grid: { left: 8, right: 24, top: 24, bottom: 34, containLabel: true },
    tooltip: {
      ...base(c).tooltip, trigger: 'item',
      formatter: (p) => { const d = props.puntos.find((x) => x.id === p.data.id); return d ? tituloTooltip(d.nombre) + (d.detalle ?? []).map(([e, v]) => filaTooltip(null, e, v)).join('') : '' },
    },
    xAxis: ejeValores(c, { type: 'log', min: xMin, max: xMax, logBase: 10, name: props.nombreX, nameLocation: 'middle', nameGap: 24, axisLabel: { color: c.axisLabel, fontSize: 11, formatter: props.formatoX } }),
    yAxis: ejeValores(c, { min: 0, max: 1, interval: 0.25, name: props.nombreY, nameLocation: 'middle', nameGap: 40, axisLabel: { color: c.axisLabel, fontSize: 11, formatter: props.formatoY } }),
    series: [s0, serie(true)],
  }
})
function clic(p) { if (p?.data?.id) emit('elegir', { codigo: p.data.id, etiqueta: p.data.nombre }) }
</script>

<template>
  <figure class="m-0" role="img" :aria-label="descripcion">
    <VChart :style="{ height: `${alto}px` }" class="w-full" :option="option" autoresize @click="clic" />
  </figure>
</template>
