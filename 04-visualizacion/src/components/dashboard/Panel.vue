<script setup>
import Ayuda from '../ui/Ayuda.vue'
// Panel de una visual: la pregunta que responde (P1…P5), unidad/periodo, la gráfica, la respuesta y una nota opcional.
defineProps({
  titulo: { type: String, default: '' },
  detalle: { type: String, default: '' },
  nota: { type: String, default: '' },
  cargando: Boolean,
  primeraCarga: Boolean,
  error: { type: Object, default: null },
  vacio: Boolean,
  alto: { type: Number, default: 260 },
  ayuda: { type: String, default: '' },
  respuesta: { type: String, default: '' }, // manual: «Respuesta P1: …» debajo de cada gráfica
})
defineEmits(['reintentar'])
</script>

<template>
  <section class="capa flex min-w-0 flex-col px-4 pb-3 pt-3.5">
    <header class="mb-2 flex items-start justify-between gap-3">
      <div class="min-w-0">
        <h2 class="text-[15px] font-semibold leading-5 text-ink">
          <span v-if="primeraCarga && !error" class="skeleton inline-block h-5 w-72 max-w-full align-middle"></span>
          <template v-else>{{ titulo }}</template>
        </h2>
        <p v-if="detalle" class="mt-0.5 text-xs text-muted">{{ detalle }}</p>
      </div>
      <div v-if="$slots.control || ayuda" class="flex shrink-0 items-center gap-2"><slot name="control" /><Ayuda v-if="ayuda" variante="boton" :texto="ayuda" titulo="Qué muestra esta gráfica" /></div>
    </header>
    <div class="relative min-h-0 flex-1">
      <div v-if="error" class="flex flex-col items-start gap-2 py-8">
        <p class="text-sm text-ink-2">No se pudieron cargar estos datos.</p>
        <button type="button" class="btn" @click="$emit('reintentar')">Reintentar</button>
      </div>
      <div v-else-if="primeraCarga" class="skeleton w-full" :style="{ height: `${alto}px` }"></div>
      <p v-else-if="vacio" class="py-10 text-sm text-ink-2">Sin datos para esta combinación de filtros.</p>
      <div v-else class="transition-opacity" :class="cargando ? 'opacity-50' : ''"><slot /></div>
    </div>
    <p v-if="respuesta && !primeraCarga && !error && !vacio" class="mt-2 border-t border-line pt-2 text-[13px] leading-5 text-ink"><strong class="font-semibold">Respuesta:</strong> {{ respuesta }}</p>
    <p v-if="nota && !primeraCarga" class="mt-1.5 text-xs text-muted">{{ nota }}</p>
  </section>
</template>
