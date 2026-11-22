import { ref, shallowRef, watch, onScopeDispose } from 'vue'
import { esCancelacion } from '../api/http.js'

/**
 * Carga asíncrona con estado. Al recargar conserva los datos anteriores (la gráfica no parpadea):
 * `cargando` sirve para atenuar y `primeraCarga` para mostrar esqueletos solo la primera vez.
 */
export function useRecurso(fn, fuente, { inmediato = true } = {}) {
  const datos = shallowRef(null)
  const error = ref(null)
  const cargando = ref(false)
  const primeraCarga = ref(true)
  let ctrl = null
  let turno = 0

  async function cargar() {
    ctrl?.abort()
    ctrl = new AbortController()
    const mio = ++turno
    cargando.value = true
    error.value = null
    try {
      const r = await fn(fuente ? fuente() : undefined, ctrl.signal)
      if (mio !== turno) return
      datos.value = r
      primeraCarga.value = false
    } catch (e) {
      if (mio !== turno || esCancelacion(e)) return
      error.value = e
    } finally {
      if (mio === turno) cargando.value = false
    }
  }

  if (fuente) watch(fuente, cargar, { deep: true, immediate: inmediato })
  else if (inmediato) cargar()
  onScopeDispose(() => ctrl?.abort())
  return { datos, error, cargando, primeraCarga, recargar: cargar }
}
