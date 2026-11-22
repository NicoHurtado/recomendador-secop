<script setup>
// Ayuda contextual al pasar el mouse (o al enfocar con teclado, o al tocar en celular).
// Variante "termino": subraya el texto con puntos. Variante "boton": muestra «¿Qué es?».
// La burbuja se dibuja en <body> para que ningún contenedor la recorte.
import { ref, nextTick, onBeforeUnmount } from 'vue'

defineOptions({ inheritAttrs: false })
const props = defineProps({
  texto: { type: String, required: true },
  titulo: { type: String, default: '' },
  variante: { type: String, default: 'termino' }, // termino | boton
})
const id = `ayuda-${Math.random().toString(36).slice(2, 8)}`
const visible = ref(false)
const ancla = ref(null)
const burbuja = ref(null)
const pos = ref({ top: 0, left: 0 })
let timer = null

async function mostrar() {
  clearTimeout(timer)
  timer = setTimeout(async () => {
    visible.value = true
    await nextTick()
    ubicar()
  }, 120)
}
function ocultar() { clearTimeout(timer); visible.value = false }
function alternar() { visible.value ? ocultar() : mostrar() }
function ubicar() {
  const a = ancla.value?.getBoundingClientRect()
  const b = burbuja.value?.getBoundingClientRect()
  if (!a || !b) return
  const m = 8
  let left = a.left
  if (left + b.width > window.innerWidth - m) left = Math.max(m, a.right - b.width)
  let top = a.bottom + 6
  if (top + b.height > window.innerHeight - m) top = Math.max(m, a.top - b.height - 6)
  pos.value = { top, left }
}
function tecla(e) { if (e.key === 'Escape') ocultar() }
onBeforeUnmount(() => clearTimeout(timer))
</script>

<template>
  <span
    ref="ancla"
    v-bind="$attrs"
    :class="props.variante === 'boton'
      ? 'inline-flex cursor-help items-center rounded px-1.5 py-0.5 text-[12px] font-semibold text-accent hover:bg-accent-soft'
      : 'cursor-help underline decoration-dotted decoration-[var(--ink-muted)] underline-offset-[3px]'"
    tabindex="0"
    :aria-describedby="visible ? id : undefined"
    @mouseenter="mostrar" @mouseleave="ocultar" @focus="mostrar" @blur="ocultar" @keydown="tecla" @click.stop.prevent="alternar"
  ><slot>{{ props.variante === 'boton' ? '¿Qué es?' : '' }}</slot></span>
  <Teleport to="body">
    <div v-if="visible" :id="id" ref="burbuja" role="tooltip"
      class="pointer-events-none fixed z-50 max-w-[320px] rounded-lg border border-[var(--border-strong)] bg-surface px-3 py-2.5 text-[12.5px] font-normal normal-case leading-[18px] tracking-normal text-ink shadow-[var(--shadow-flyout)]"
      :style="{ top: `${pos.top}px`, left: `${pos.left}px` }">
      <p v-if="props.titulo" class="mb-1 font-semibold">{{ props.titulo }}</p>
      <p class="text-ink-2">{{ props.texto }}</p>
    </div>
  </Teleport>
</template>
