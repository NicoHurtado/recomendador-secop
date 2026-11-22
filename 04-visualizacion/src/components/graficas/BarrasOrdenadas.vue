<script setup>
// Barras horizontales ordenadas. Gris = contexto; color de alerta solo para las que cruzan el umbral.
// Umbral/referencia como línea punteada. Valor escrito al final de cada barra. Clic = filtro (profundizar).
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'
import { VChart } from '../../charts/echarts.js'
import { base, ejeCategorias, ejeValores, filaTooltip, tituloTooltip } from '../../charts/tema.js'
import { useTemaGrafica } from '../../composables/useTemaGrafica.js'

const props = defineProps({
  items: { type: Array, default: () => [] }, // [{ codigo, etiqueta, nombre?, valor, resaltar, etiquetaValor?, detalle: [[e, v]] }]
  formato: { type: Function, required: true },
  formatoEje: { type: Function, default: null },
  nombreX: { type: String, default: '' },
  seleccionado: { type: String, default: null },
  referencia: { type: Object, default: null }, // { valor, etiqueta }
  colorResaltado: { type: String, default: 'alerta' },
  max: { type: Number, default: null },
  intervalo: { type: Number, default: null },
  alturaBarra: { type: Number, default: 26 },
  descripcion: { type: String, default: '' },
  clicable: { type: Boolean, default: true },
  derecha: { type: Number, default: 56 }, // espacio para la etiqueta al final de la barra
  anchoEtiqueta: { type: Number, default: 0.3 }, // fracción del ancho para los nombres
})
const emit = defineEmits(['elegir'])
const t = useTemaGrafica()
const caja = ref(null)
const ancho = ref(600)
let ro = null
onMounted(() => { ro = new ResizeObserver(() => { if (caja.value?.clientWidth) ancho.value = caja.value.clientWidth }); if (caja.value) ro.observe(caja.value) })
onBeforeUnmount(() => ro?.disconnect())
const alto = computed(() => Math.max(140, props.items.length * props.alturaBarra + (props.referencia ? 58 : 40)))

const option = computed(() => {
  const c = t.value
  return {
    ...base(c),
    grid: { left: 4, right: props.derecha, top: props.referencia ? 26 : 8, bottom: props.nombreX ? 30 : 8, containLabel: true },
    tooltip: {
      ...base(c).tooltip, trigger: 'item',
      formatter: (p) => {
        const it = props.items[p.dataIndex]
        return tituloTooltip(it.nombre ?? it.etiqueta) + (it.detalle ?? [['', props.formato(it.valor)]]).map(([e, v]) => filaTooltip(null, e, v)).join('')
      },
    },
    xAxis: ejeValores(c, { max: props.max ?? undefined, interval: props.intervalo ?? undefined, splitNumber: 4,
      name: props.nombreX, nameLocation: 'middle', nameGap: 22, axisLabel: { color: c.axisLabel, fontSize: 11, formatter: props.formatoEje ?? props.formato } }),
    yAxis: ejeCategorias(c, { data: props.items.map((i) => i.etiqueta), inverse: true,
      axisLabel: { color: c.ink1, fontSize: 12, width: Math.round(Math.max(90, Math.min(220, ancho.value * props.anchoEtiqueta))), overflow: 'truncate' } }),
    series: [{
      type: 'bar', barMaxWidth: 16, barCategoryGap: '30%', cursor: props.clicable ? 'pointer' : 'default',
      data: props.items.map((it) => ({
        value: it.valor,
        itemStyle: {
          color: it.resaltar ? c[props.colorResaltado] : c.deemph,
          borderRadius: [0, 3, 3, 0],
          opacity: props.seleccionado && it.codigo !== props.seleccionado ? 0.35 : 1,
        },
      })),
      label: { show: true, position: 'right', distance: 6, color: c.ink1, fontSize: 12, formatter: (p) => { const it = props.items[p.dataIndex]; return it.etiquetaValor ?? props.formato(it.valor) } },
      emphasis: { itemStyle: { borderColor: c.ink1, borderWidth: 1 } },
      markLine: props.referencia ? {
        symbol: 'none', silent: true, lineStyle: { color: c.ref, width: 1, type: [4, 4] },
        label: { formatter: props.referencia.etiqueta, position: 'start', color: c.ink2, fontSize: 11, distance: 4 },
        data: [{ xAxis: props.referencia.valor }],
      } : undefined,
    }],
  }
})
function clic(p) { if (props.clicable && p?.dataIndex !== undefined) emit('elegir', props.items[p.dataIndex].codigo) }
</script>

<template>
  <figure ref="caja" class="m-0" role="img" :aria-label="descripcion">
    <VChart :style="{ height: `${alto}px` }" class="w-full" :option="option" autoresize @click="clic" />
  </figure>
</template>
