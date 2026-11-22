import { computed } from 'vue'
import { useTema } from '../stores/tema.js'
import { leerTema } from '../charts/tema.js'

/** Colores de las gráficas, recalculados cuando cambia el tema. */
export function useTemaGrafica() {
  const tema = useTema()
  return computed(() => {
    void tema.version // dependencia reactiva
    return leerTema()
  })
}
