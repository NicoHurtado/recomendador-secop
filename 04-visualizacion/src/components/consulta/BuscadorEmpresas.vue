<script setup>
// Combobox accesible (patrón WAI-ARIA): autocompleta desde el 3.er carácter con 300 ms de espera entre teclas.
import { ref, watch, onBeforeUnmount, computed } from 'vue'
import * as api from '../../api/api.js'
import { MENSAJES } from '../../api/http.js'

const props = defineProps({ autofocus: Boolean, etiqueta: { type: String, default: 'Busca tu empresa por nombre' } })
const emit = defineEmits(['elegir'])

const q = ref('')
const resultados = ref([])
const abierto = ref(false)
const activo = ref(-1)
const cargando = ref(false)
const error = ref(null)
const buscado = ref('')
let timer = null
let ctrl = null
const id = `buscador-${Math.random().toString(36).slice(2, 8)}`

watch(q, (v) => {
  clearTimeout(timer)
  ctrl?.abort()
  const t = v.trim()
  error.value = null
  if (t.length < 3) { resultados.value = []; abierto.value = false; cargando.value = false; return }
  cargando.value = true
  timer = setTimeout(async () => {
    ctrl = new AbortController()
    try {
      resultados.value = await api.buscarEmpresas(t, { signal: ctrl.signal })
      buscado.value = t
      activo.value = resultados.value.length ? 0 : -1
      abierto.value = true
    } catch (e) {
      if (e?.name === 'AbortError') return
      error.value = e
      abierto.value = true
    } finally {
      cargando.value = false
    }
  }, 300)
})
onBeforeUnmount(() => { clearTimeout(timer); ctrl?.abort() })

function cerrarLuego() { setTimeout(() => { abierto.value = false }, 150) }
function elegir(e) {
  abierto.value = false
  q.value = ''
  emit('elegir', e)
}
function tecla(ev) {
  if (!abierto.value && ['ArrowDown', 'ArrowUp'].includes(ev.key) && resultados.value.length) { abierto.value = true; return }
  if (ev.key === 'ArrowDown') { ev.preventDefault(); activo.value = Math.min(activo.value + 1, resultados.value.length - 1) }
  else if (ev.key === 'ArrowUp') { ev.preventDefault(); activo.value = Math.max(activo.value - 1, 0) }
  else if (ev.key === 'Enter' && abierto.value && resultados.value[activo.value]) { ev.preventDefault(); elegir(resultados.value[activo.value]) }
  else if (ev.key === 'Escape') { abierto.value = false }
}
const estado = computed(() => {
  if (cargando.value) return 'Buscando…'
  if (q.value.trim().length > 0 && q.value.trim().length < 3) return 'Escribe al menos 3 letras.'
  if (abierto.value && !error.value) return resultados.value.length === 20 ? 'Se muestran las primeras 20 coincidencias; escribe más para precisar.' : `${resultados.value.length} empresas encontradas.`
  return ''
})
</script>

<template>
  <div class="relative">
    <label :for="id" class="rotulo">{{ props.etiqueta }}</label>
    <div class="relative">
      <input
        :id="id" v-model="q" type="search" class="campo !min-h-10 text-[15px]" autocomplete="off" spellcheck="false"
        placeholder="Ej.: construcciones, suministros, ingeniería…" role="combobox" :aria-expanded="abierto" :aria-controls="`${id}-lista`"
        aria-autocomplete="list" :aria-activedescendant="abierto && activo >= 0 ? `${id}-op-${activo}` : undefined" :autofocus="autofocus"
        @keydown="tecla" @blur="cerrarLuego" @focus="resultados.length && (abierto = true)"
      />
      <span v-if="cargando" class="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin rounded-full border-2 border-[var(--border-strong)] border-t-[var(--accent)]" aria-hidden="true"></span>
    </div>
    <p class="sr-only" aria-live="polite">{{ estado }}</p>
    <p class="mt-1 text-xs text-muted">Personas jurídicas que han participado en SECOP II. Escribe al menos 3 letras.</p>

    <div v-if="abierto" class="absolute z-20 mt-1 w-full overflow-hidden rounded-lg border border-line bg-surface shadow-[var(--shadow-flyout)]">
      <p v-if="error" class="px-4 py-3 text-sm text-ink-2">{{ MENSAJES[error.tipo] ?? MENSAJES.servidor }}</p>
      <p v-else-if="!resultados.length" class="px-4 py-3 text-sm text-ink-2">
        No encontramos empresas con «{{ buscado }}». Si tu empresa nunca ha participado en SECOP, <RouterLink :to="{ path: '/recomendador', query: { modo: 'nueva' } }">usa la opción de empresa nueva</RouterLink>.
      </p>
      <ul v-else :id="`${id}-lista`" role="listbox" class="max-h-80 overflow-auto py-1" :aria-label="`Empresas que coinciden con ${buscado}`">
        <li
          v-for="(e, i) in resultados" :id="`${id}-op-${i}`" :key="e.proveedor_key" role="option" :aria-selected="i === activo"
          class="flex cursor-pointer items-center justify-between gap-3 px-4 py-2.5" :class="i === activo ? 'bg-surface-3' : ''"
          @mousedown.prevent="elegir(e)" @mousemove="activo = i"
        >
          <span class="min-w-0">
            <span class="block truncate font-medium text-ink">{{ e.nombre }}</span>
            <span class="block text-xs text-ink-2">{{ e.departamento ?? 'Departamento no publicado' }}</span>
          </span>
          <span v-if="e.es_pyme" class="etiqueta shrink-0">Pyme</span>
        </li>
      </ul>
    </div>
  </div>
</template>
