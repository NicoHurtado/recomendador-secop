<script setup>
// Recomendador. Dos caminos:
//  · Empresa con historial: las dos listas del modelo (API /empresas/{key}/recomendaciones), con su título y su orden,
//    en filas horizontales; el detalle se abre en un panel lateral.
//  · Empresa nueva: búsqueda guiada sobre /procesos/abiertos por coincidencia con su descripción
//    (sin historial no hay probabilidad). Nada de lo que se escribe se guarda.
import { computed, reactive, ref, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as api from '../api/api.js'
import { esCancelacion } from '../api/http.js'
import { useRecurso } from '../composables/useRecurso.js'
import BuscadorEmpresas from '../components/consulta/BuscadorEmpresas.vue'
import FilaProcesos from '../components/recomendador/FilaProcesos.vue'
import PanelProceso from '../components/recomendador/PanelProceso.vue'
import { cierre, pesos, fecha, numero, tituloEntidad, oracion } from '../utils/formato.js'
import { departamentoLegible, DEPARTAMENTOS_ORDENADOS, nombreSecop, nombreDepartamento } from '../utils/dane.js'
import { palabrasClave, puntuar, coincidencias } from '../utils/relevancia.js'
import { EJEMPLOS_CONSULTA } from '../demo.js'

// Lo que el modelo sabe de cada empresa está fijo a esta fecha (guía de la API, sección 6.2). La API no la entrega.
const HISTORIAL_AL = '2026-10-27'

const props = defineProps({ proveedorKey: { type: String, default: null } })
const route = useRoute()
const router = useRouter()

const modo = computed(() => (props.proveedorKey ? 'existente' : route.query.modo === 'nueva' ? 'nueva' : route.query.modo === 'existente' ? 'existente' : null))
const irModo = (m) => router.push({ path: '/recomendador', query: m ? { modo: m } : {} })

// =================== Empresa con historial ===================
const empresa = computed(() => ({
  nombre: typeof route.query.nombre === 'string' ? route.query.nombre : null,
  departamento: typeof route.query.depto === 'string' ? route.query.depto : null,
  es_pyme: route.query.pyme === '1' ? true : route.query.pyme === '0' ? false : null,
}))
function abrirEmpresa(e) {
  router.push({ name: 'recomendador-empresa', params: { proveedorKey: e.proveedor_key }, query: { nombre: e.nombre, ...(e.departamento ? { depto: e.departamento } : {}), pyme: e.es_pyme ? '1' : '0' } })
}
const reco = useRecurso((key, signal) => (key ? api.recomendaciones(key, { signal }) : Promise.resolve(null)), () => props.proveedorKey)
const listas = computed(() => reco.datos.value?.listas ?? {})
const historial = computed(() => listas.value.historial?.procesos ?? [])
const oportunidad = computed(() => listas.value.oportunidad?.procesos ?? [])
const sinListas = computed(() => reco.datos.value && !historial.value.length && !oportunidad.value.length)
const detalleEmpresa = computed(() => [departamentoLegible(empresa.value.departamento) ?? empresa.value.departamento, empresa.value.es_pyme === null ? null : empresa.value.es_pyme ? 'Pyme' : 'No es Pyme'].filter(Boolean).join(' · '))
const abierto = ref(null) // { proceso, origen }

// =================== Empresa nueva ===================
const f = reactive({ descripcion: '', departamentos: [], valorMax: '' })
const errores = ref({})
const buscando = ref(false)
const errorNueva = ref(null)
const resultado = ref(null)
let ctrl = null
const EJEMPLOS = [
  { t: 'papelería en Antioquia', d: { descripcion: 'Vendemos útiles de oficina, papelería, tóner, cartuchos, resmas de papel y elementos de aseo para oficinas y colegios.', departamentos: ['05'], valorMax: '200000000' } },
  { t: 'obras civiles en Cundinamarca', d: { descripcion: 'Empresa de ingeniería civil: construcción, mejoramiento y mantenimiento de vías, placa huella, alcantarillado, acueducto e infraestructura educativa.', departamentos: ['25', '11'], valorMax: '' } },
  { t: 'salud en el Valle', d: { descripcion: 'Prestamos servicios de salud, suministro de medicamentos, dispositivos médicos, insumos hospitalarios y mantenimiento de equipos biomédicos.', departamentos: ['76'], valorMax: '' } },
]
const TOPES = [{ v: '50000000', t: 'Hasta $50 millones' }, { v: '200000000', t: 'Hasta $200 millones' }, { v: '1000000000', t: 'Hasta $1.000 millones' }, { v: '', t: 'Sin límite' }]
const valorMax = computed(() => (f.valorMax ? Number(f.valorMax) : null))
const depDisponibles = computed(() => DEPARTAMENTOS_ORDENADOS.filter((d) => !f.departamentos.includes(d.codigo)))
function agregarDep(e) {
  const v = e.target.value
  if (v && !f.departamentos.includes(v)) f.departamentos.push(v)
  e.target.value = ''
  errores.value = { ...errores.value, departamentos: undefined }
}
const quitarDep = (c) => { f.departamentos = f.departamentos.filter((x) => x !== c) }
const enumerar = (xs) => (xs.length <= 1 ? xs.join('') : `${xs.slice(0, -1).join(', ')} y ${xs.at(-1)}`)

function validar() {
  const e = {}
  if (f.descripcion.trim().length < 30) e.descripcion = `Escribe al menos 30 caracteres (llevas ${f.descripcion.trim().length}).`
  if (!f.departamentos.length) e.departamentos = 'Elige al menos un departamento.'
  errores.value = e
  return !Object.keys(e).length
}
async function buscar() {
  if (!validar()) return
  ctrl?.abort(); ctrl = new AbortController()
  buscando.value = true; errorNueva.value = null
  try {
    const listasDep = await Promise.all(f.departamentos.map((c) => api.procesosAbiertos({ departamento: nombreSecop(c), limite: 100 }, { signal: ctrl.signal })))
    const vistos = new Map() // sin duplicados: un proceso por identificador
    for (const p of listasDep.flat()) vistos.set(p.id_proceso, p)
    const claves = palabrasClave(f.descripcion)
    const todos = [...vistos.values()].filter((p) => valorMax.value === null || (p.precio_base ?? Infinity) <= valorMax.value)
      .map((p) => ({ ...p, _s: puntuar(p, claves), coincide: coincidencias(p, claves) }))
    const parecidos = todos.filter((p) => p._s > 0).sort((a, b) => b._s - a._s || String(a.fecha_limite_ofertas).localeCompare(String(b.fecha_limite_ofertas)))
    resultado.value = {
      revisados: vistos.size,
      parecidos,
      sinCoincidencia: parecidos.length ? [] : [...todos].sort((a, b) => String(a.fecha_limite_ofertas).localeCompare(String(b.fecha_limite_ofertas))).slice(0, 15),
      departamentos: f.departamentos.map(nombreDepartamento),
      valorMax: valorMax.value,
    }
    ordenNueva.value = 'coincidencia'
    await nextTick()
    document.getElementById('resultados-nueva')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  } catch (e) {
    if (!esCancelacion(e)) errorNueva.value = e
  } finally {
    buscando.value = false
  }
}
const ordenNueva = ref('coincidencia')
const ORDENES = [{ id: 'coincidencia', t: 'Más coincidencias' }, { id: 'cierre', t: 'Cierre más próximo' }, { id: 'valor', t: 'Mayor valor' }]
const filasNueva = computed(() => {
  const a = [...(resultado.value?.parecidos?.length ? resultado.value.parecidos : resultado.value?.sinCoincidencia ?? [])]
  if (ordenNueva.value === 'valor') a.sort((x, y) => (y.precio_base ?? 0) - (x.precio_base ?? 0))
  if (ordenNueva.value === 'cierre') a.sort((x, y) => String(x.fecha_limite_ofertas).localeCompare(String(y.fecha_limite_ofertas)))
  return a
})
const tituloNueva = computed(() => {
  const r = resultado.value
  if (!r) return ''
  const n = r.parecidos.length, donde = enumerar(r.departamentos)
  if (!n) return `Ningún proceso abierto en ${donde} coincide con lo que describiste`
  return n === 1 ? `1 proceso abierto en ${donde} coincide con lo que describiste` : `${numero(n)} procesos abiertos en ${donde} coinciden con lo que describiste`
})
function usarEjemplo(e) {
  Object.assign(f, { ...e.d, departamentos: [...e.d.departamentos] })
  errores.value = {}
  buscar()
}
const lugarFila = (p) => p.municipio || departamentoLegible(p.departamento) || p.departamento || null
</script>

<template>
  <div class="reco marco pt-10 pb-6">
    <!-- ===================== Elegir camino ===================== -->
    <template v-if="!modo">
      <p class="r-eyebrow">Recomendador de procesos</p>
      <h1 class="r-h1 mt-2">¿Tu empresa ya ha participado en SECOP II?</h1>
      <div class="mt-8 grid max-w-4xl gap-4 md:grid-cols-2">
        <button v-for="o in [{ id: 'existente', t: 'Sí, ya ha participado', d: 'Recomendaciones personalizadas con su probabilidad de ganar.' }, { id: 'nueva', t: 'No, es nueva en SECOP', d: 'Procesos abiertos que encajan con lo que hace la empresa.' }]" :key="o.id"
          type="button" class="r-tarjeta !h-auto !w-auto" @click="irModo(o.id)">
          <span class="text-[18px] font-semibold leading-6">{{ o.t }}</span>
          <span class="mt-1 text-[14px] leading-5 r-texto-2">{{ o.d }}</span>
        </button>
      </div>
    </template>

    <!-- ===================== EMPRESA CON HISTORIAL ===================== -->
    <template v-else-if="modo === 'existente'">
      <!-- Buscar la empresa -->
      <template v-if="!proveedorKey">
        <p class="r-eyebrow">Recomendador de procesos</p>
        <h1 class="r-h1 mt-2">Busca tu empresa</h1>
        <div class="mt-6 max-w-2xl"><BuscadorEmpresas autofocus etiqueta="Nombre o razón social" @elegir="abrirEmpresa" /></div>
        <div class="mt-5 flex flex-wrap items-center gap-2">
          <span class="text-[14px] r-texto-2">O prueba con:</span>
          <button v-for="e in EJEMPLOS_CONSULTA" :key="e.proveedor_key" type="button" class="r-btn r-btn-sec" @click="abrirEmpresa(e)">{{ tituloEntidad(e.nombre) }}</button>
        </div>
        <p class="mt-8 text-[14px] r-texto-2">¿Tu empresa nunca ha contratado con el Estado? <RouterLink :to="{ path: '/recomendador', query: { modo: 'nueva' } }" class="underline">Describe lo que hace</RouterLink>.</p>
      </template>

      <!-- Recomendaciones -->
      <template v-else>
        <header class="flex flex-wrap items-end justify-between gap-x-8 gap-y-4 pb-7">
          <div class="min-w-0">
            <p class="r-eyebrow">Recomendador de procesos</p>
            <h1 class="r-h1 mt-2">{{ empresa.nombre ? tituloEntidad(empresa.nombre) : 'Empresa' }}</h1>
            <p class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[15px] leading-[22px] r-texto-2">
              <span v-if="detalleEmpresa">{{ detalleEmpresa }}</span>
              <span v-if="detalleEmpresa" class="h-4 w-px bg-[var(--r-borde-control)]" aria-hidden="true"></span>
              <span>Historial al {{ fecha(HISTORIAL_AL) }}</span>
            </p>
          </div>
          <button type="button" class="r-btn r-btn-sec" @click="irModo('existente')">Cambiar empresa</button>
        </header>
        <hr class="r-sep" />

        <div v-if="reco.error.value" class="py-10">
          <p class="text-[15px] r-texto-2">No se pudieron cargar las recomendaciones.</p>
          <button type="button" class="r-btn r-btn-sec mt-3" @click="reco.recargar()">Reintentar</button>
        </div>
        <div v-else-if="reco.primeraCarga.value" class="mt-10 space-y-10" aria-busy="true" aria-label="Cargando recomendaciones">
          <div v-for="k in 2" :key="k"><div class="skeleton h-7 w-80"></div><div class="mt-4 flex gap-4 overflow-hidden"><div v-for="i in 5" :key="i" class="skeleton h-[420px] w-[300px] shrink-0"></div></div></div>
        </div>
        <div v-else-if="sinListas" class="py-10">
          <h2 class="r-h2">Hoy no hay recomendaciones para esta empresa</h2>
          <p class="mt-2 text-[15px] r-texto-2">No tiene participaciones recientes en SECOP II o ningún proceso abierto encaja con su historial.</p>
          <div class="mt-5 flex flex-wrap gap-2"><button type="button" class="r-btn r-btn-pri" @click="irModo('nueva')">Buscar como empresa nueva</button><button type="button" class="r-btn r-btn-sec" @click="irModo('existente')">Consultar otra empresa</button></div>
        </div>
        <div v-else class="mt-10 space-y-12">
          <FilaProcesos v-if="historial.length" :titulo="listas.historial.titulo || 'Recomendados según tu historial'"
            subtitulo="Ordenados por qué tan probable es que te interese el proceso, no por la probabilidad de ganar." :procesos="historial"
            @abrir="(p) => (abierto = { proceso: p, origen: 'historial' })" />
          <FilaProcesos v-if="oportunidad.length" :titulo="listas.oportunidad.titulo || 'Oportunidades que normalmente no verías'"
            subtitulo="Entidades con las que no has trabajado. Estimación con menos historial." :procesos="oportunidad"
            @abrir="(p) => (abierto = { proceso: p, origen: 'oportunidad' })" />
        </div>
      </template>
      <PanelProceso :proceso="abierto?.proceso ?? null" :origen="abierto?.origen ?? 'historial'" @cerrar="abierto = null" />
    </template>

    <!-- ===================== EMPRESA NUEVA ===================== -->
    <template v-else-if="modo === 'nueva'">
      <p class="r-eyebrow">Recomendador de procesos · Empresa nueva en SECOP</p>
      <div class="mt-8 grid gap-x-14 gap-y-10 lg:grid-cols-[300px_minmax(0,1fr)]">
        <form class="h-fit lg:sticky lg:top-24" novalidate aria-labelledby="t-describe" @submit.prevent="buscar">
          <h2 id="t-describe" class="text-[16px] font-semibold leading-6">Describe tu empresa</h2>
          <p class="mt-1 text-[13px] leading-[18px] r-texto-2">Buscamos procesos abiertos cuyo objeto use las mismas palabras.</p>

          <label class="mt-6 block text-[13px] font-semibold leading-[18px]" for="desc">¿Qué vende o qué servicios presta?</label>
          <textarea id="desc" v-model="f.descripcion" rows="5" class="campo mt-2 !min-h-28 text-[14px] leading-5" :aria-invalid="!!errores.descripcion" :aria-describedby="errores.descripcion ? 'desc-error desc-ejemplos' : 'desc-ejemplos'"></textarea>
          <p v-if="errores.descripcion" id="desc-error" class="mt-1 text-[12px] font-semibold text-[#a4262c]">{{ errores.descripcion }}</p>
          <p id="desc-ejemplos" class="mt-1.5 text-[12px] leading-[17px] r-texto-3">Ejemplos:
            <template v-for="(e, i) in EJEMPLOS" :key="e.t"><button type="button" class="r-enlace-texto" @click="usarEjemplo(e)">{{ e.t }}</button>{{ i < EJEMPLOS.length - 1 ? ', ' : '.' }}</template>
          </p>

          <fieldset class="mt-6">
            <legend class="text-[13px] font-semibold leading-[18px]">¿Dónde opera?</legend>
            <div class="mt-2 flex flex-wrap gap-2">
              <button v-for="c in f.departamentos" :key="c" type="button" class="r-chip" :aria-label="`Quitar ${nombreDepartamento(c)}`" @click="quitarDep(c)">{{ nombreDepartamento(c) }} <span aria-hidden="true">×</span></button>
              <label class="sr-only" for="agregar-dep">Agregar departamento</label>
              <select id="agregar-dep" class="r-agregar" @change="agregarDep">
                <option value="">Agregar departamento</option>
                <option v-for="d in depDisponibles" :key="d.codigo" :value="d.codigo">{{ d.nombre }}</option>
              </select>
            </div>
            <p v-if="errores.departamentos" class="mt-1 text-[12px] font-semibold text-[#a4262c]">{{ errores.departamentos }}</p>
          </fieldset>

          <label class="mt-6 block text-[13px] font-semibold leading-[18px]" for="vmax">Valor máximo del proceso</label>
          <select id="vmax" v-model="f.valorMax" class="campo mt-2 text-[14px]">
            <option v-for="t in TOPES" :key="t.t" :value="t.v">{{ t.t }}</option>
          </select>

          <button type="submit" class="r-btn r-btn-pri mt-6" :disabled="buscando">{{ buscando ? 'Buscando…' : resultado ? 'Actualizar resultados' : 'Ver resultados' }}</button>
        </form>

        <section id="resultados-nueva" class="min-w-0 scroll-mt-20" aria-live="polite">
          <div v-if="buscando" class="space-y-4" aria-busy="true"><div class="skeleton h-9 w-3/4"></div><div class="skeleton h-5 w-80"></div><div class="skeleton h-20"></div><div class="skeleton h-72"></div></div>
          <div v-else-if="errorNueva" class="py-4"><p class="text-[15px] r-texto-2">No se pudieron consultar los procesos abiertos.</p><button type="button" class="r-btn r-btn-sec mt-3" @click="buscar">Reintentar</button></div>
          <template v-else-if="resultado">
            <h1 class="text-[28px] font-semibold leading-9">{{ tituloNueva }}</h1>
            <p class="mt-2 text-[15px] r-texto-2">{{ [resultado.valorMax ? `Hasta ${pesos(resultado.valorMax)}` : null, `${numero(resultado.revisados)} procesos abiertos revisados`].filter(Boolean).join(' · ') }}</p>

            <div class="r-aviso mt-6 flex flex-wrap items-center justify-between gap-x-6 gap-y-3 px-4 py-3.5">
              <p class="min-w-0 flex-1 basis-72 text-[14px] leading-5"><strong class="font-semibold">Esto no es una recomendación del modelo.</strong> Sin historial en SECOP no podemos estimar tu probabilidad de ganar.</p>
              <button type="button" class="r-btn r-btn-sec shrink-0" @click="irModo('existente')">¿Ya contrataste con el Estado? Busca tu empresa</button>
            </div>

            <template v-if="filasNueva.length">
              <div class="mt-6 flex flex-wrap items-center justify-between gap-3 border-b border-[var(--r-ink-2)] pb-3">
                <p class="text-[14px] font-medium">{{ resultado.parecidos.length ? `${numero(filasNueva.length)} ${filasNueva.length === 1 ? 'proceso' : 'procesos'}` : 'Procesos abiertos que cierran primero' }}</p>
                <div class="flex flex-wrap items-center gap-3">
                  <span id="ordenar-por" class="text-[13px] r-texto-2">Ordenar por:</span>
                  <div class="r-seg" role="group" aria-labelledby="ordenar-por">
                    <button v-for="o in ORDENES" :key="o.id" type="button" :aria-pressed="ordenNueva === o.id" :disabled="o.id === 'coincidencia' && !resultado.parecidos.length" @click="ordenNueva = o.id">{{ o.t }}</button>
                  </div>
                </div>
              </div>
              <ul class="m-0 list-none p-0">
                <li v-for="p in filasNueva" :key="p.id_proceso" class="grid grid-cols-[minmax(0,1fr)_auto] gap-x-8 gap-y-1 border-b border-[var(--r-borde)] py-4">
                  <div class="min-w-0">
                    <p class="text-[12px] font-medium leading-4 r-texto-2">{{ tituloEntidad(p.entidad) }}</p>
                    <p class="mt-1 line-clamp-3 text-[15px] font-semibold leading-[22px]" :title="oracion(p.objeto)">{{ oracion(p.objeto, [p.municipio, departamentoLegible(p.departamento)]) || 'Objeto no publicado' }}</p>
                    <p v-if="p.coincide?.length" class="mt-1.5 text-[12px] leading-4 r-texto-3">Coincide: {{ p.coincide.join(', ') }}</p>
                  </div>
                  <div class="text-right text-[12px] leading-[18px]">
                    <p class="text-[15px] font-semibold leading-[22px]">{{ pesos(p.precio_base) }}</p>
                    <p v-if="lugarFila(p)" class="r-texto-2">{{ lugarFila(p) }}</p>
                    <p :class="cierre(p.fecha_limite_ofertas).urgente ? 'r-ambar' : 'r-texto-2'">{{ cierre(p.fecha_limite_ofertas).texto }}</p>
                    <a v-if="p.url_proceso" :href="p.url_proceso" target="_blank" rel="noopener noreferrer" class="mt-1 inline-flex min-h-6 items-center underline">Ver en SECOP II<span class="sr-only">: {{ oracion(p.objeto) }} (se abre en otra pestaña)</span></a>
                  </div>
                </li>
              </ul>
            </template>
            <p v-else class="mt-6 text-[15px] r-texto-2">No hay procesos abiertos en esos departamentos con ese valor máximo.</p>
          </template>
          <div v-else class="flex min-h-[320px] flex-col justify-center border-l border-[var(--r-borde)] pl-8">
            <h1 class="text-[22px] font-semibold leading-7">Tus resultados aparecerán aquí</h1>
            <p class="mt-2 max-w-md text-[15px] r-texto-2">Cuéntanos qué hace tu empresa y dónde opera, o prueba con uno de los ejemplos.</p>
          </div>
        </section>
      </div>
    </template>
  </div>
</template>
