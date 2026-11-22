<script setup>
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useMetadata } from './stores/metadata.js'
import { useTema } from './stores/tema.js'

useTema() // solo modo claro
const route = useRoute()
const meta = useMetadata()
onMounted(() => meta.cargar())
const activo = (prefijo) => (prefijo === '/' ? route.path === '/' : route.path.startsWith(prefijo))
// El recomendador usa márgenes de clamp(16px, 5.5vw, 80px) y fondo blanco; el dashboard conserva los suyos,
// así la barra queda alineada con el contenido de cada página.
const enReco = computed(() => route.path.startsWith('/recomendador'))
const marco = computed(() => (enReco.value ? 'marco' : 'contenedor'))
</script>

<template>
  <a href="#contenido" class="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded focus:bg-surface focus:px-3 focus:py-2">Saltar al contenido</a>
  <div class="flex min-h-screen flex-col" :class="enReco ? 'bg-white' : ''">
    <header class="nav">
      <div class="nav-fila" :class="marco">
        <RouterLink to="/" class="nav-marca">Proyecto Integrador SECOP</RouterLink>
        <nav class="nav-enlaces" aria-label="Secciones">
          <RouterLink to="/" :aria-current="activo('/') ? 'page' : undefined">Dashboard</RouterLink>
          <RouterLink to="/recomendador" :aria-current="activo('/recomendador') ? 'page' : undefined">Recomendador</RouterLink>
        </nav>
        <p class="nav-fecha">Datos al {{ meta.fechaNav ?? '…' }}</p>
      </div>
    </header>
    <main id="contenido" class="flex-1" tabindex="-1">
      <RouterView />
    </main>
    <footer class="pie mt-10">
      <p :class="marco">
        Fuente: SECOP II, Colombia Compra Eficiente (datos.gov.co), licencia CC BY-SA 4.0. Solo se muestran personas jurídicas. Proyecto académico, no es un sitio oficial.
      </p>
    </footer>
  </div>
</template>
