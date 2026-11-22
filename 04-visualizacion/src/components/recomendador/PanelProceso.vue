<script setup>
// Panel lateral de detalle: 480 px a la derecha con fondo al 18 %; pantalla completa en celular.
// <dialog> modal: atrapa el foco y cierra con Esc. Un solo botón para cerrar (X) y un solo botón principal abajo.
// La modalidad no viene en las listas: se pide a GET /procesos/{id_proceso} al abrir.
import { computed, nextTick, ref, watch } from 'vue'
import * as api from '../../api/api.js'
import { esCancelacion } from '../../api/http.js'
import { pesos, probabilidad, cierre, fecha, tituloEntidad, oracion } from '../../utils/formato.js'
import { departamentoLegible } from '../../utils/dane.js'
import { competencia, lote } from './probabilidad.js'

const props = defineProps({
  proceso: { type: Object, default: null },
  origen: { type: String, default: 'historial' }, // historial | oportunidad
})
const emit = defineEmits(['cerrar'])
const dlg = ref(null)
const extra = ref(null) // respuesta de /procesos/{id}
const cargandoExtra = ref(false)
let ctrl = null

watch(() => props.proceso, async (p) => {
  ctrl?.abort()
  extra.value = null
  if (!p) { dlg.value?.close(); return }
  await nextTick()
  if (!dlg.value?.open) dlg.value?.showModal()
  ctrl = new AbortController()
  cargandoExtra.value = true
  try { extra.value = await api.proceso(p.id_proceso, { signal: ctrl.signal }) } catch (e) { if (!esCancelacion(e)) extra.value = null } finally { cargandoExtra.value = false }
})
const p = computed(() => props.proceso)
const dep = computed(() => (p.value ? departamentoLegible(p.value.departamento) ?? p.value.departamento : null))
const c = computed(() => (p.value ? cierre(p.value.fecha_limite_ofertas) : null))
const cierreTxt = computed(() => {
  const x = c.value
  if (!x || x.dias === null) return 'No publicado'
  const f = fecha(p.value.fecha_limite_ofertas)
  if (x.cerrado) return `${f} · cerrado`
  return `${f} · ${x.dias === 0 ? 'hoy' : x.dias === 1 ? 'mañana' : `en ${x.dias} días`}`
})
const origenTxt = computed(() => (props.origen === 'oportunidad' ? 'Oportunidad que normalmente no verías' : 'Recomendado según tu historial'))
const modalidad = computed(() => extra.value?.modalidad ?? (cargandoExtra.value ? 'Cargando…' : 'No publicada'))
const url = computed(() => p.value?.url_proceso ?? extra.value?.url_proceso ?? null)
function clicFondo(e) { if (e.target === dlg.value) dlg.value.close() }
</script>

<template>
  <dialog ref="dlg" class="r-panel" :aria-labelledby="p ? 'panel-objeto' : undefined" @close="emit('cerrar')" @click="clicFondo">
    <template v-if="p">
      <header class="flex items-start justify-between gap-3 border-b border-[var(--r-borde)] px-7 pb-4 pt-5">
        <div class="min-w-0 pt-1">
          <p class="text-[13px] font-medium leading-[18px] r-texto-2">{{ tituloEntidad(p.entidad) }}</p>
          <p class="mt-1 text-[13px] leading-[18px] r-texto-3">{{ [lote(p), origenTxt].filter(Boolean).join(' · ') }}</p>
        </div>
        <button type="button" class="r-cerrar -mr-2" aria-label="Cerrar el detalle" autofocus @click="dlg.close()">
          <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="m3.5 3.5 9 9m0-9-9 9" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" /></svg>
        </button>
      </header>

      <div class="min-h-0 flex-1 overflow-y-auto px-7 pb-6 pt-7">
        <h2 id="panel-objeto" class="text-[20px] font-semibold leading-7">{{ oracion(p.objeto, [p.municipio, dep]) || 'Objeto no publicado' }}</h2>
        <hr class="r-sep my-6" />
        <p class="text-[56px] font-semibold leading-[60px] tracking-tight">{{ probabilidad(p.probabilidad) }}</p>
        <div class="r-barra mt-3" role="meter" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="Math.round((p.probabilidad ?? 0) * 100)" :aria-label="`${probabilidad(p.probabilidad)} de ganar si te presentas`"><span :style="{ width: `${Math.min(1, p.probabilidad ?? 0) * 100}%` }"></span></div>
        <p class="mt-3 text-[15px] leading-[22px] r-texto-2">de ganar si te presentas</p>
        <p v-if="competencia(p.oferentes_esperados)" class="mt-5 text-[15px] leading-[22px]">{{ competencia(p.oferentes_esperados) }}</p>
        <p v-if="origen === 'oportunidad'" class="mt-1 text-[14px] leading-5 r-texto-2">No has trabajado con esta entidad: la estimación usa menos historial.</p>
        <dl class="r-dl mt-6 border-t border-[var(--r-borde)]">
          <div><dt>Precio base</dt><dd>{{ pesos(p.precio_base) }}</dd></div>
          <div><dt>Cierre</dt><dd :class="c?.urgente ? 'r-ambar' : ''">{{ cierreTxt }}</dd></div>
          <div><dt>Lugar</dt><dd>{{ [p.municipio, dep].filter(Boolean).join(', ') || 'No publicado' }}</dd></div>
          <div><dt>Modalidad</dt><dd>{{ modalidad }}</dd></div>
          <div><dt>Identificador</dt><dd>{{ p.id_proceso }}</dd></div>
        </dl>
      </div>

      <footer v-if="url" class="border-t border-[var(--r-borde)] px-7 py-5">
        <a :href="url" target="_blank" rel="noopener noreferrer" class="r-btn r-btn-pri w-full !min-h-12 text-[15px]">Ver el proceso en SECOP II</a>
      </footer>
    </template>
  </dialog>
</template>
