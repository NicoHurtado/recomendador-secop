<script setup>
// Línea(s) sobre un solo eje. Protagonista en color, contexto en gris, referencia en línea punteada.
// Etiqueta directa al final de la serie protagonista; tooltip con todas las series en el punto.
// Los puntos de un periodo incompleto (huecos) se dibujan vacíos; las anotaciones explican datos atípicos.
import { computed } from 'vue'
import { VChart } from '../../charts/echarts.js'
import { base, ejeCategorias, ejeValores, filaTooltip, tituloTooltip } from '../../charts/tema.js'
import { useTemaGrafica } from '../../composables/useTemaGrafica.js'

const props = defineProps({
  x: { type: Array, required: true },
  etiquetaX: { type: Function, default: (v) => v },
  series: { type: Array, required: true }, // [{ id, nombre, datos, color: 's1'|'deemph'|'alerta'|'s2', area?, etiquetaFinal?, simbolos?, huecos?: [índices] }]
  formato: { type: Function, required: true },
  formatoEje: { type: Function, default: null },
  nombreY: { type: String, default: '' },
  alto: { type: Number, default: 280 },
  min: { type: [Number, String], default: 0 },
  max: { type: [Number, String], default: null },
  intervalo: { type: Number, default: null },
  referencia: { type: Object, default: null }, // { valor, etiqueta }
  banda: { type: Object, default: null },      // { desde, hasta, etiqueta } resalta un tramo del eje X
  leyenda: { type: Boolean, default: null },
  anotaciones: { type: Array, default: () => [] }, // [{ x, y, texto, posicion?, desplazar?: [dx, dy] }] notas sobre puntos concretos
  descripcion: { type: String, default: '' },
})
const t = useTemaGrafica()

const option = computed(() => {
  const c = t.value
  const col = (s) => c[s.color ?? 's1'] ?? s.color
  const conLeyenda = props.leyenda ?? props.series.length > 1
  const conFinal = props.series.some((s) => s.etiquetaFinal)
  return {
    ...base(c),
    grid: { left: 8, right: conFinal ? 64 : 16, top: conLeyenda ? 40 : 28, bottom: 4, containLabel: true },
    legend: conLeyenda ? { top: 0, left: 0, icon: 'rect', itemWidth: 14, itemHeight: 3, itemGap: 16, textStyle: { color: c.ink2, fontSize: 12 }, selectedMode: false,
      data: [...props.series].sort((a, b) => (a.color === 'deemph') - (b.color === 'deemph')).map((s) => s.nombre) } : undefined,
    tooltip: {
      ...base(c).tooltip, trigger: 'axis', axisPointer: { type: 'line', lineStyle: { color: c.axis, width: 1 } },
      formatter: (ps) => {
        const i = ps[0]?.dataIndex ?? 0
        const filas = props.series.filter((s) => s.datos[i] !== null && s.datos[i] !== undefined)
          .sort((a, b) => (a.color === 'deemph') - (b.color === 'deemph'))
          .map((s) => filaTooltip(col(s), s.nombre, props.formato(s.datos[i])))
        if (props.referencia) filas.push(filaTooltip(c.ref, props.referencia.etiqueta, props.formato(props.referencia.valor)))
        return tituloTooltip(props.etiquetaX(props.x[i])) + filas.join('')
      },
    },
    xAxis: ejeCategorias(c, { data: props.x, boundaryGap: false, axisLabel: { color: c.axisLabel, fontSize: 12, formatter: (v) => props.etiquetaX(v), hideOverlap: true } }),
    yAxis: ejeValores(c, { min: props.min, max: props.max ?? undefined, interval: props.intervalo ?? undefined, splitNumber: 4,
      name: props.nombreY, nameLocation: 'end', nameGap: 12, nameTextStyle: { color: c.ink2, fontSize: 12, align: 'left', padding: [0, 0, 0, -36] },
      axisLabel: { color: c.axisLabel, fontSize: 12, formatter: props.formatoEje ?? props.formato } }),
    series: props.series.map((s, k) => {
      const ultimo = (() => { for (let j = s.datos.length - 1; j >= 0; j--) if (s.datos[j] !== null && s.datos[j] !== undefined) return j; return -1 })()
      const hueco = (j) => (s.huecos ?? []).includes(j)
      const vacio = { color: c.surface1, borderColor: col(s), borderWidth: 2 }
      const puntosFinal = s.etiquetaFinal && ultimo >= 0 ? [{ coord: [props.x[ultimo], s.datos[ultimo]], itemStyle: hueco(ultimo) ? vacio : undefined }] : []
      const notas = k === 0 ? props.anotaciones.map((a) => ({
        coord: [a.x, a.y], symbol: 'circle', symbolSize: 0,
        label: { show: true, formatter: a.texto, position: a.posicion ?? 'top', distance: 6, offset: a.desplazar ?? [0, 0], color: c.ink2, fontSize: 11, lineHeight: 14, fontWeight: 400 },
      })) : []
      return {
        id: s.id ?? s.nombre, name: s.nombre, type: 'line', smooth: false, connectNulls: false,
        data: s.datos.map((v, j) => (hueco(j) && v !== null && v !== undefined ? { value: v, symbol: 'circle', symbolSize: 9, itemStyle: vacio } : v)),
        showSymbol: !!s.simbolos, symbol: 'circle', symbolSize: 7, z: s.color === 'deemph' ? 1 : 3,
        lineStyle: { width: s.color === 'deemph' ? 1.5 : 2.5, color: col(s), cap: 'round', join: 'round' },
        itemStyle: { color: col(s), borderColor: c.surface1, borderWidth: 2 },
        areaStyle: s.area ? { color: c.s1Wash } : undefined,
        emphasis: { disabled: true },
        markPoint: puntosFinal.length || notas.length ? {
          symbol: 'circle', symbolSize: 8, itemStyle: { color: col(s), borderColor: c.surface1, borderWidth: 2 }, silent: true,
          label: { show: true, position: 'right', distance: 6, formatter: s.etiquetaFinal ?? '', color: c.ink1, fontSize: 12, fontWeight: 600 },
          data: [...puntosFinal, ...notas],
        } : undefined,
        markLine: k === 0 && props.referencia ? {
          symbol: 'none', silent: true, lineStyle: { color: c.ref, width: 1, type: [4, 4] },
          label: { formatter: props.referencia.etiqueta, position: 'insideEndTop', color: c.ink2, fontSize: 11 },
          data: [{ yAxis: props.referencia.valor }],
        } : undefined,
        markArea: k === 0 && props.banda ? {
          silent: true, itemStyle: { color: c.surface3 }, label: { show: !!props.banda.etiqueta, position: 'insideTop', color: c.ink2, fontSize: 11, formatter: props.banda.etiqueta ?? '' },
          data: [[{ xAxis: props.banda.desde }, { xAxis: props.banda.hasta }]],
        } : undefined,
      }
    }),
  }
})
</script>

<template>
  <figure class="m-0" role="img" :aria-label="descripcion">
    <VChart :style="{ height: `${alto}px` }" class="w-full" :option="option" autoresize />
  </figure>
</template>
