<script setup>
// Mancuerna (antes → después) por categoría: punto gris = año base, punto de color = año elegido,
// unidos por un trazo. El punto del año elegido va en tinta oscura: el azul queda solo para la tendencia del indicador.
// El color del punto final indica la dirección (alerta si empeora). Etiqueta directa con el cambio.
import { computed } from 'vue'
import { VChart } from '../../charts/echarts.js'
import { base, ejeCategorias, ejeValores, filaTooltip, tituloTooltip } from '../../charts/tema.js'
import { useTemaGrafica } from '../../composables/useTemaGrafica.js'

const props = defineProps({
  filas: { type: Array, required: true }, // [{ codigo, etiqueta, a, b, detalle }]  a = base, b = actual
  nombreA: { type: String, required: true },
  nombreB: { type: String, required: true },
  formato: { type: Function, required: true },
  formatoCambio: { type: Function, required: true },
  peorSiSube: { type: Boolean, default: true },
  nombreX: { type: String, default: '' },
  max: { type: Number, default: 1 },
  seleccionado: { type: String, default: null },
  descripcion: { type: String, default: '' },
})
const emit = defineEmits(['elegir'])
const t = useTemaGrafica()
const alto = computed(() => props.filas.length * 36 + 72)

const option = computed(() => {
  const c = t.value
  const nombres = props.filas.map((f) => f.etiqueta)
  const peor = (f) => (props.peorSiSube ? f.b > f.a : f.b < f.a)
  const op = (f) => (props.seleccionado && f.codigo !== props.seleccionado ? 0.35 : 1)
  return {
    ...base(c),
    grid: { left: 4, right: 104, top: 30, bottom: props.nombreX ? 30 : 8, containLabel: true },
    legend: { top: 0, left: 0, itemWidth: 10, itemHeight: 10, itemGap: 16, textStyle: { color: c.ink2, fontSize: 12 }, selectedMode: false,
      data: [{ name: props.nombreA, icon: 'circle', itemStyle: { color: c.deemph } }, { name: props.nombreB, icon: 'circle', itemStyle: { color: c.ink1 } }] },
    tooltip: {
      ...base(c).tooltip, trigger: 'item',
      formatter: (p) => {
        const f = props.filas[p.dataIndex]
        if (!f) return ''
        return tituloTooltip(f.etiqueta) + filaTooltip(c.deemph, props.nombreA, props.formato(f.a)) + filaTooltip(c.ink1, props.nombreB, props.formato(f.b)) +
          filaTooltip(null, 'Cambio', props.formatoCambio(f.b - f.a)) + (f.detalle ?? []).map(([e, v]) => filaTooltip(null, e, v)).join('')
      },
    },
    xAxis: ejeValores(c, { min: 0, max: props.max, interval: 0.2, name: props.nombreX, nameLocation: 'middle', nameGap: 22, axisLabel: { color: c.axisLabel, fontSize: 11, formatter: props.formato } }),
    yAxis: ejeCategorias(c, { data: nombres, inverse: true, axisLine: { show: false },
      axisLabel: { color: c.ink1, fontSize: 12, width: 160, overflow: 'truncate', formatter: (v) => (props.filas.find((f) => f.etiqueta === v)?.total ? `{t|${v}}` : v), rich: { t: { fontWeight: 600, color: c.ink1, fontSize: 12 } } } }),
    series: [
      { type: 'bar', stack: 'm', silent: true, barWidth: 3, itemStyle: { color: 'transparent' }, data: props.filas.map((f) => Math.min(f.a, f.b)), tooltip: { show: false } },
      { type: 'bar', stack: 'm', barWidth: 3, cursor: 'pointer', data: props.filas.map((f) => ({ value: Math.abs(f.b - f.a), itemStyle: { color: c.axis, opacity: op(f) } })) },
      { name: props.nombreA, type: 'scatter', symbolSize: 11, z: 3, cursor: 'pointer', data: props.filas.map((f) => ({ value: [f.a, f.etiqueta], itemStyle: { color: c.deemph, opacity: op(f), borderColor: c.surface1, borderWidth: 2 } })) },
      { name: props.nombreB, type: 'scatter', symbolSize: 13, z: 4, cursor: 'pointer',
        data: props.filas.map((f) => ({ value: [f.b, f.etiqueta], itemStyle: { color: c.ink1, opacity: op(f), borderColor: c.surface1, borderWidth: 2 } })),
        label: { show: true, position: 'right', distance: 0, formatter: (p) => { const f = props.filas[p.dataIndex]; const d = f.b - f.a; return `{v|${props.formato(f.b)}}  {${peor(f) ? 'm' : 'b'}|${d > 0 ? '▲' : d < 0 ? '▼' : '='} ${props.formatoCambio(d)}}` },
          rich: { v: { color: c.ink1, fontSize: 12, fontWeight: 600 }, m: { color: c.alertaInk, fontSize: 11, fontWeight: 600 }, b: { color: c.ink2, fontSize: 11, fontWeight: 600 } }, offset: [10, 0] },
      },
    ],
  }
})
function clic(p) { const f = props.filas[p?.dataIndex]; if (f?.codigo) emit('elegir', f.codigo) }
</script>

<template>
  <figure class="m-0" role="img" :aria-label="descripcion">
    <VChart :style="{ height: `${alto}px` }" class="w-full" :option="option" autoresize @click="clic" />
  </figure>
</template>
