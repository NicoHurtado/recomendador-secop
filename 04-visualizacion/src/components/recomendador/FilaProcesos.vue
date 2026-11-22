<script setup>
// Fila horizontal tipo Netflix. Se desplaza con trackpad, con el dedo o con las flechas (escritorio).
// Contador "1–4 de 10" (en celular "1 de 10") que se actualiza con el scroll; las flechas se ocultan en los extremos
// y cada una avanza 4 tarjetas (o las que quepan).
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import TarjetaProceso from './TarjetaProceso.vue'

const props = defineProps({
  titulo: { type: String, required: true },
  subtitulo: { type: String, default: '' },
  procesos: { type: Array, default: () => [] },
})
defineEmits(['abrir'])
const id = `fila-${Math.random().toString(36).slice(2, 8)}`
const pista = ref(null)
const primero = ref(0)
const visibles = ref(4)
const alInicio = ref(true)
const alFinal = ref(false)
let ro = null
let frame = 0

function paso() {
  const el = pista.value
  const t = el?.firstElementChild
  if (!el || !t) return 316
  const gap = parseFloat(getComputedStyle(el).columnGap) || 16
  return t.getBoundingClientRect().width + gap
}
function medir() {
  frame = 0
  const el = pista.value
  if (!el) return
  const p = paso()
  // ancho útil: sin el margen derecho que deja asomar la siguiente tarjeta
  const util = el.clientWidth - (parseFloat(getComputedStyle(el).paddingRight) || 0)
  visibles.value = Math.max(1, Math.floor((util + 16) / p))
  primero.value = Math.min(props.procesos.length - 1, Math.max(0, Math.round(el.scrollLeft / p)))
  alInicio.value = el.scrollLeft <= 2
  alFinal.value = el.scrollLeft + el.clientWidth >= el.scrollWidth - 2
  if (alFinal.value) primero.value = Math.max(0, props.procesos.length - visibles.value)
}
const alDesplazar = () => { if (!frame) frame = requestAnimationFrame(medir) }
function mover(dir) {
  const el = pista.value
  if (!el) return
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  el.scrollBy({ left: dir * Math.max(1, Math.min(4, visibles.value)) * paso(), behavior: reduce ? 'auto' : 'smooth' })
}
const contador = computed(() => {
  const n = props.procesos.length
  if (!n) return ''
  const desde = primero.value + 1
  const hasta = Math.min(n, primero.value + visibles.value)
  return hasta > desde ? `${desde}–${hasta} de ${n}` : `${desde} de ${n}`
})
onMounted(() => {
  medir()
  if (typeof ResizeObserver !== 'undefined' && pista.value) { ro = new ResizeObserver(alDesplazar); ro.observe(pista.value) }
})
onBeforeUnmount(() => { ro?.disconnect(); if (frame) cancelAnimationFrame(frame) })
watch(() => props.procesos, async () => { await nextTick(); if (pista.value) pista.value.scrollLeft = 0; medir() })
</script>

<template>
  <section class="r-fila" :aria-labelledby="`${id}-t`">
    <header class="mb-3 flex items-end justify-between gap-4">
      <div class="min-w-0">
        <h2 :id="`${id}-t`" class="r-h2">{{ titulo }}</h2>
        <p v-if="subtitulo" class="mt-1 text-[14px] leading-5 r-texto-2">{{ subtitulo }}</p>
      </div>
      <p class="shrink-0 text-[13px] leading-5 r-texto-3" aria-live="polite">{{ contador }}</p>
    </header>
    <div class="relative">
      <button v-show="!alInicio" type="button" class="r-flecha r-flecha-izq" :aria-label="`Procesos anteriores de ${titulo}`" @click="mover(-1)">
        <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M10 3 5 8l5 5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" /></svg>
      </button>
      <div ref="pista" class="r-pista" @scroll.passive="alDesplazar">
        <TarjetaProceso v-for="p in procesos" :key="p.id_proceso" :proceso="p" @abrir="$emit('abrir', $event)" />
      </div>
      <button v-show="!alFinal" type="button" class="r-flecha r-flecha-der" :aria-label="`Más procesos de ${titulo}`" @click="mover(1)">
        <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="m6 3 5 5-5 5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" /></svg>
      </button>
    </div>
  </section>
</template>
