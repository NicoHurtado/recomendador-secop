<script setup>
// Mini-tendencia (SVG): contexto en gris; último punto en el color de acento. Decorativa: el número va al lado.
import { computed } from 'vue'
const props = defineProps({
  valores: { type: Array, default: () => [] },
  ancho: { type: Number, default: 120 },
  alto: { type: Number, default: 32 },
  color: { type: String, default: 'var(--s1)' },
  resaltarUltimo: { type: Boolean, default: true },
  ultimoVacio: Boolean, // último periodo incompleto: punto hueco
})
const puntos = computed(() => {
  const v = props.valores.map((x) => (x === null || x === undefined ? null : Number(x)))
  const val = v.filter((x) => x !== null)
  if (val.length < 2) return []
  const min = Math.min(...val), max = Math.max(...val)
  const rango = max - min || 1
  const paso = props.ancho / (v.length - 1)
  return v.map((x, i) => (x === null ? null : [i * paso, props.alto - 3 - ((x - min) / rango) * (props.alto - 6)]))
})
const ruta = computed(() => puntos.value.filter(Boolean).map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' '))
const ultimo = computed(() => [...puntos.value].reverse().find(Boolean))
</script>

<template>
  <svg v-if="ruta" :width="ancho" :height="alto" :viewBox="`-4 0 ${ancho + 8} ${alto}`" aria-hidden="true" class="overflow-visible">
    <path :d="ruta" fill="none" stroke="var(--axis)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
    <circle v-if="resaltarUltimo && ultimo" :cx="ultimo[0]" :cy="ultimo[1]" r="3.5" :fill="ultimoVacio ? 'var(--surface-1)' : color" :stroke="ultimoVacio ? color : 'var(--surface-1)'" stroke-width="1.5" />
  </svg>
</template>
