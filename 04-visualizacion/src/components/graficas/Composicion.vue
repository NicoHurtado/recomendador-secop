<script setup>
// Composición 100 %: una barra por medida (procesos ganados, valor adjudicado), partida en Pyme / no Pyme.
// Las Pymes usan su propio color (--pyme) para no confundirse con el azul del indicador protagonista.
// La marca vertical punteada es la referencia del año anterior para la parte Pyme.
import { pct } from '../../utils/formato.js'
defineProps({
  barras: { type: Array, required: true }, // [{ nombre, parte, referencia }]  parte/referencia = fracción Pyme 0–1
  etiquetaParte: { type: String, default: 'Pymes' },
  etiquetaResto: { type: String, default: 'Otras empresas' },
  etiquetaReferencia: { type: String, default: '' },
  decimales: { type: Number, default: 1 },
})
</script>

<template>
  <div>
    <div class="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-2">
      <span class="inline-flex items-center gap-1.5"><span class="inline-block h-2.5 w-2.5 rounded-sm" style="background: var(--pyme)"></span>{{ etiquetaParte }}</span>
      <span class="inline-flex items-center gap-1.5"><span class="inline-block h-2.5 w-2.5 rounded-sm" style="background: var(--deemph)"></span>{{ etiquetaResto }}</span>
      <span v-if="etiquetaReferencia" class="inline-flex items-center gap-1.5"><span class="inline-block h-3 border-l-2 border-dashed" style="border-color: var(--ref)"></span>{{ etiquetaReferencia }}</span>
    </div>
    <dl class="space-y-4">
      <div v-for="b in barras" :key="b.nombre">
        <dt class="mb-1 flex justify-between text-[13px]"><span class="font-semibold text-ink">{{ b.nombre }}</span><span v-if="b.referencia !== null && b.referencia !== undefined" class="tabular text-xs text-muted">{{ etiquetaReferencia }}: {{ pct(b.referencia, decimales) }}</span></dt>
        <dd class="relative m-0 flex h-7 overflow-hidden rounded" :aria-label="`${b.nombre}: ${etiquetaParte} ${pct(b.parte, decimales)}, ${etiquetaResto} ${pct(1 - b.parte, decimales)}`">
          <div class="flex items-center px-2 text-xs font-semibold" :style="{ width: `${b.parte * 100}%`, background: 'var(--pyme)', color: 'var(--pyme-ink)' }">{{ b.parte >= 0.12 ? pct(b.parte, decimales) : '' }}</div>
          <div class="ml-0.5 flex flex-1 items-center justify-end px-2 text-xs font-semibold text-ink" style="background: var(--deemph)">{{ 1 - b.parte >= 0.12 ? pct(1 - b.parte, decimales) : '' }}</div>
          <div v-if="b.referencia !== null && b.referencia !== undefined" class="absolute inset-y-0 border-l-2 border-dashed" :style="{ left: `${b.referencia * 100}%`, borderColor: 'var(--ink-1)' }" aria-hidden="true"></div>
        </dd>
      </div>
    </dl>
  </div>
</template>
