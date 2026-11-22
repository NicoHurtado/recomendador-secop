import { defineStore } from 'pinia'
import { computed } from 'vue'

/**
 * El sitio solo tiene modo claro (se quitó el selector Claro / Oscuro).
 * Se conserva el store porque las gráficas leen `version` para releer los colores de CSS.
 */
export const useTema = defineStore('tema', () => {
  const preferencia = computed(() => 'light')
  const oscuro = computed(() => false)
  const version = computed(() => 'light')
  document.documentElement.dataset.theme = 'light'
  try { localStorage.removeItem('cm-tema') } catch { /* modo privado */ }
  return { preferencia, oscuro, version }
})
