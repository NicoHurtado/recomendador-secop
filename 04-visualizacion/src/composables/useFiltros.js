import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { FILTROS } from '../api/indicadores.js'
import { nombreDepartamento } from '../utils/dane.js'
import { nombreSegmento } from '../utils/unspsc.js'
import { nombreModalidad } from '../utils/modalidades.js'

/** Los filtros globales del dashboard viven en la URL (?anio=&departamento=&segmento=&modalidad=) para compartir una vista. */
export function useFiltros() {
  const route = useRoute()
  const router = useRouter()

  const filtros = computed(() => {
    const q = route.query
    const f = {}
    if (/^\d{4}$/.test(q.anio ?? '')) f.anio = String(q.anio)
    if (/^\d{2}$/.test(q.departamento ?? '') && nombreDepartamento(q.departamento)) f.departamento = String(q.departamento)
    if (/^\d{2}$/.test(q.segmento ?? '')) f.segmento = String(q.segmento)
    if (typeof q.modalidad === 'string' && /^[a-z_]+$/.test(q.modalidad)) f.modalidad = q.modalidad
    return f
  })

  function poner(cambios) {
    const query = { ...route.query }
    for (const [k, v] of Object.entries(cambios)) {
      if (!FILTROS.includes(k)) continue
      if (v === null || v === undefined || v === '') delete query[k]
      else query[k] = String(v)
    }
    router.replace({ query })
  }
  /** Clic en una barra o departamento: si ya estaba seleccionado, se quita. */
  function alternar(clave, valor) {
    poner({ [clave]: filtros.value[clave] === String(valor) ? null : valor })
  }
  function limpiar() {
    poner(Object.fromEntries(FILTROS.map((k) => [k, null])))
  }

  const activos = computed(() => {
    const f = filtros.value
    const out = []
    if (f.anio) out.push({ clave: 'anio', texto: f.anio })
    if (f.departamento) out.push({ clave: 'departamento', texto: nombreDepartamento(f.departamento) })
    if (f.segmento) out.push({ clave: 'segmento', texto: nombreSegmento(f.segmento) })
    if (f.modalidad) out.push({ clave: 'modalidad', texto: nombreModalidad(f.modalidad) })
    return out
  })

  return { filtros, poner, alternar, limpiar, activos }
}
