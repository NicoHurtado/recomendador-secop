import { createRouter, createWebHistory } from 'vue-router'

const TITULO = 'Proyecto Integrador SECOP'

const routes = [
  { path: '/', name: 'dashboard', component: () => import('./views/DashboardView.vue'), meta: { titulo: 'Dashboard de la contratación pública' } },
  { path: '/recomendador', name: 'recomendador', component: () => import('./views/RecomendadorView.vue'), meta: { titulo: 'Recomendador de procesos' } },
  { path: '/recomendador/:proveedorKey', name: 'recomendador-empresa', component: () => import('./views/RecomendadorView.vue'), props: true, meta: { titulo: 'Recomendaciones de tu empresa' } },
  // Direcciones de versiones anteriores de la página
  { path: '/analitica', redirect: (to) => ({ path: '/', query: to.query }) },
  { path: '/como-funciona', redirect: '/' },
  { path: '/consulta', redirect: '/recomendador' },
  { path: '/consulta/:proveedorKey', redirect: (to) => ({ path: `/recomendador/${to.params.proveedorKey}`, query: to.query }) },
  { path: '/simular', redirect: { path: '/recomendador', query: { modo: 'nueva' } } },
  { path: '/:pathMatch(.*)*', name: 'no-encontrada', component: () => import('./views/NoEncontradaView.vue'), meta: { titulo: 'Página no encontrada' } },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
  scrollBehavior(to, from, saved) {
    if (saved) return saved
    if (to.path === from.path) return false
    return { top: 0 }
  },
})

router.afterEach((to) => {
  document.title = `${to.meta.titulo ?? 'Inicio'} · ${TITULO}`
})

export default router
