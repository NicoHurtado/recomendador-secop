import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as api from '../api/api.js'
import { fecha, fechaHoraBogota } from '../utils/formato.js'

/** /metadata se pide una vez por visita: fecha de los datos, versiones de los modelos y métricas. */
export const useMetadata = defineStore('metadata', () => {
  const datos = ref(null)
  const error = ref(null)
  const cargando = ref(false)
  let promesa = null

  function cargar(forzar = false) {
    if (promesa && !forzar) return promesa
    cargando.value = true
    error.value = null
    promesa = api.metadata()
      .then((d) => { datos.value = d })
      .catch((e) => { error.value = e; promesa = null })
      .finally(() => { cargando.value = false })
    return promesa
  }

  const fechaDatos = computed(() => (datos.value?.fecha_datos ? fecha(datos.value.fecha_datos) : null))
  // Fecha de corte que muestra la barra superior: la de los datos de la página abierta. El dashboard la fija con
  // la de su snapshot de estadísticas; el resto del sitio usa la de /metadata. Así cada página tiene una sola fecha.
  const fechaPagina = ref(null)
  const fechaNav = computed(() => (fechaPagina.value ? fecha(fechaPagina.value) : fechaDatos.value))
  const ultimaPublicacion = computed(() => (datos.value?.ultima_publicacion ? fechaHoraBogota(datos.value.ultima_publicacion) : null))
  const simulados = computed(() => datos.value?.datos_simulados === true)

  return { datos, error, cargando, cargar, fechaDatos, fechaPagina, fechaNav, ultimaPublicacion, simulados }
})
