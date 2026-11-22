<script setup>
// Tarjeta KPI (manual, «Cómo presentar un KPI»): nombre y periodo · valor principal ·
// comparación con la referencia (▲▼ + color + texto, el color nunca va solo) · mini-tendencia desde 2020.
// Toda la tarjeta es clicable: elige el indicador que se ve en la gráfica de tendencia.
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import Sparkline from '../graficas/Sparkline.vue'
import Ayuda from '../ui/Ayuda.vue'

const props = defineProps({
  nombre: { type: String, required: true },
  periodo: { type: String, default: '' },
  valor: { type: String, default: '—' },
  cambio: { type: Object, default: null }, // { flecha: '▲'|'▼'|'=', texto, estado: 'bueno'|'malo'|'neutro' }
  tendencia: { type: Array, default: () => [] },
  ultimoParcial: Boolean,
  desde: { type: String, default: '' },
  hasta: { type: String, default: '' },
  principal: Boolean,
  cargando: Boolean,
  ayuda: { type: String, default: '' },
})
defineEmits(['elegir'])
const caja = ref(null)
const ancho = ref(104)
let ro = null
onMounted(() => {
  if (!caja.value || typeof ResizeObserver === 'undefined') return
  ro = new ResizeObserver(([e]) => { ancho.value = Math.max(40, Math.round(e.contentRect.width)) })
  ro.observe(caja.value)
})
onBeforeUnmount(() => ro?.disconnect())
const colorCambio = computed(() => ({ bueno: 'text-good-ink', malo: 'text-alerta-ink' }[props.cambio?.estado] ?? 'text-ink-2'))
</script>

<template>
  <article class="capa relative min-w-0 px-4 py-3 transition-shadow hover:shadow-[var(--shadow-flyout)]" :class="principal ? 'ring-2 ring-[var(--s1)]' : ''">
    <button type="button" class="absolute inset-0 z-0 rounded-[8px] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]" :aria-pressed="principal" :aria-label="`Ver ${nombre} en la gráfica de tendencia`" @click="$emit('elegir')"></button>
    <p class="pointer-events-none relative text-[13px] leading-[18px] text-ink-2"><Ayuda v-if="ayuda" :texto="ayuda" :titulo="nombre" class="pointer-events-auto relative z-10 font-semibold text-ink">{{ nombre }}</Ayuda><span v-else class="font-semibold text-ink">{{ nombre }}</span><span v-if="periodo" class="text-muted"> · {{ periodo }}</span></p>
    <div class="pointer-events-none relative mt-1 flex items-end justify-between gap-3">
      <div class="shrink-0">
        <div v-if="cargando" class="skeleton h-8 w-28"></div>
        <p v-else class="tabular whitespace-nowrap font-[family-name:var(--font-display)] text-[28px] font-semibold leading-[34px] tracking-tight text-ink">{{ valor }}</p>
      </div>
      <div v-show="tendencia.length > 2" ref="caja" class="min-w-[56px] max-w-[104px] flex-1">
        <Sparkline :valores="tendencia" :ancho="ancho" :alto="30" color="var(--s1)" :ultimo-vacio="ultimoParcial" />
        <div class="tabular flex justify-between text-[10px] leading-3 text-muted"><span>{{ desde }}</span><span>{{ hasta }}</span></div>
      </div>
    </div>
    <p v-if="cambio && !cargando" class="pointer-events-none relative mt-1 text-xs font-semibold leading-4" :class="colorCambio">
      <span aria-hidden="true">{{ cambio.flecha }}</span> {{ cambio.texto }}
    </p>
  </article>
</template>
