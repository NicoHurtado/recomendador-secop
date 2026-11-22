<script setup>
// Tarjeta de un proceso recomendado (300 × 420; 284 × 404 en celular). Toda la tarjeta es un botón que abre el detalle.
// Orden: entidad · objeto (4 líneas) · valor y municipio · cierre · probabilidad con su barra · competencia.
// No muestra los motivos de la recomendación.
import { computed } from 'vue'
import { pesos, probabilidad, cierre, tituloEntidad, oracion, normalizar } from '../../utils/formato.js'
import { departamentoLegible } from '../../utils/dane.js'
import { competencia, lote } from './probabilidad.js'

const props = defineProps({ proceso: { type: Object, required: true } })
defineEmits(['abrir'])
const p = computed(() => props.proceso)
const c = computed(() => cierre(p.value.fecha_limite_ofertas))
const dep = computed(() => departamentoLegible(p.value.departamento) ?? p.value.departamento)
const lugar = computed(() => {
  const mun = p.value.municipio
  if (mun && dep.value && normalizar(dep.value).includes(normalizar(mun))) return dep.value
  return mun || dep.value || null
})
const pct = computed(() => probabilidad(p.value.probabilidad))
</script>

<template>
  <button type="button" class="r-tarjeta" :aria-label="`${tituloEntidad(p.entidad)}: ${oracion(p.objeto)}. ${pct} de ganar si te presentas. ${c.texto}.`" @click="$emit('abrir', proceso)">
    <span class="block text-[13px] leading-[18px] r-texto-2"><span class="font-medium">{{ tituloEntidad(p.entidad) }}</span><template v-if="lote(p)"> · {{ lote(p) }}</template></span>
    <span class="r-clamp-4 mt-2 text-[16px] font-semibold leading-[22px]">{{ oracion(p.objeto, [p.municipio, dep]) || 'Objeto no publicado' }}</span>
    <span class="mt-3 block text-[13px] leading-[18px] r-texto-2">{{ [pesos(p.precio_base), lugar].filter(Boolean).join(' · ') }}</span>
    <span class="mt-0.5 block text-[13px] leading-[18px]" :class="c.urgente ? 'r-ambar' : 'r-texto-2'">{{ c.texto }}</span>
    <span class="mt-auto block">
      <span class="block text-[40px] font-semibold leading-[44px] tracking-tight">{{ pct }}</span>
      <span class="r-barra mt-3 block" aria-hidden="true"><span :style="{ width: `${Math.min(1, p.probabilidad ?? 0) * 100}%` }"></span></span>
      <span class="mt-2.5 block text-[13px] leading-[18px] r-texto-2">de ganar si te presentas</span>
      <template v-if="competencia(p.oferentes_esperados)">
        <span class="r-sep mb-4 mt-4 block" aria-hidden="true"></span>
        <span class="block text-[13px] leading-[18px]">{{ competencia(p.oferentes_esperados) }}</span>
      </template>
    </span>
  </button>
</template>
