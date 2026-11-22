<script setup>
// Profundización: serie anual de una entidad (clic en una barra de P4).
import { ref, watch, nextTick, computed } from 'vue'
import * as api from '../../api/api.js'
import Lineas from '../graficas/Lineas.vue'
import { pesos, pesosEje, pct, numero, tituloEntidad } from '../../utils/formato.js'
import { nombreDepartamento } from '../../utils/dane.js'

const props = defineProps({ entidad: { type: Object, default: null } }) // { codigo, etiqueta }
const emit = defineEmits(['cerrar'])
const dlg = ref(null)
const datos = ref(null)
const error = ref(false)

async function cargar() {
  datos.value = null; error.value = false
  try { datos.value = (await api.estadistica('detalle-entidad', {}, { entidad: props.entidad.codigo })).datos } catch { error.value = true }
}
watch(() => props.entidad, async (e) => {
  if (!e) { dlg.value?.close(); return }
  await nextTick()
  dlg.value?.showModal()
  cargar()
})
const ultimo = computed(() => datos.value?.at(-1)?.valores ?? null)
</script>

<template>
  <dialog ref="dlg" class="m-auto w-[min(860px,calc(100vw-2rem))] rounded-lg border border-line bg-surface p-0 text-ink shadow-[var(--shadow-flyout)] backdrop:bg-black/30" :aria-label="entidad ? `Detalle de ${entidad.etiqueta}` : 'Detalle'" @close="emit('cerrar')">
    <div v-if="entidad" class="p-6">
      <div class="flex items-start justify-between gap-4">
        <div>
          <p class="t-section">Entidad</p>
          <h2 class="t-subtitle mt-0.5">{{ tituloEntidad(entidad.etiqueta) }}</h2>
          <p v-if="ultimo" class="text-[13px] text-ink-2">{{ nombreDepartamento(ultimo.departamento) ?? 'Departamento no publicado' }}<template v-if="ultimo.dependencias >= 3"> · NIT compartido por {{ ultimo.dependencias }} dependencias</template></p>
        </div>
        <button type="button" class="btn btn-sutil" autofocus @click="dlg.close()">Cerrar</button>
      </div>
      <p v-if="error" class="mt-6 text-sm text-ink-2">No se pudo cargar la entidad. <button type="button" class="btn ml-2" @click="cargar">Reintentar</button></p>
      <div v-else-if="!datos" class="skeleton mt-6 h-64"></div>
      <template v-else>
        <div class="mt-5 grid gap-6 md:grid-cols-2">
          <div>
            <p class="text-[13px] font-semibold">% con un solo oferente</p>
            <Lineas :x="datos.map((d) => d.etiqueta)" :series="[{ nombre: 'Oferente único', datos: datos.map((d) => d.valores.pct_oferente_unico), etiquetaFinal: pct(ultimo?.pct_oferente_unico) }]" :formato="(v) => pct(v)" :min="0" :max="1" :intervalo="0.25" :alto="200" descripcion="Porcentaje de oferente único por año" />
          </div>
          <div>
            <p class="text-[13px] font-semibold">Valor adjudicado</p>
            <Lineas :x="datos.map((d) => d.etiqueta)" :series="[{ nombre: 'Valor adjudicado', datos: datos.map((d) => d.valores.valor_adjudicado), area: true }]" :formato="(v) => pesos(v)" :formato-eje="pesosEje" :alto="200" descripcion="Valor adjudicado por año" />
          </div>
        </div>
        <table class="tabla mt-5">
          <thead><tr><th>Año</th><th class="num">Valor adjudicado</th><th class="num">Procesos</th><th class="num">Oferente único</th><th class="num">Proveedores</th><th class="num">HHI</th></tr></thead>
          <tbody><tr v-for="d in datos" :key="d.etiqueta"><td>{{ d.etiqueta }}</td><td class="num">{{ pesos(d.valores.valor_adjudicado) }}</td><td class="num">{{ numero(d.valores.procesos) }}</td><td class="num">{{ pct(d.valores.pct_oferente_unico) }}</td><td class="num">{{ numero(d.valores.proveedores_distintos) }}</td><td class="num">{{ numero(d.valores.hhi, 2) }}</td></tr></tbody>
        </table>
        <p class="mt-2 text-xs text-muted">HHI: concentración del valor de sus contratos entre proveedores (0 = repartido, 1 = un solo proveedor).</p>
      </template>
    </div>
  </dialog>
</template>
