import { describe, it, expect, vi, beforeAll } from 'vitest'

// Modo sin red (plan B de la demo): VITE_API_URL vacío → todo sale de src/api/fixtures.
let api
beforeAll(async () => {
  vi.stubEnv('VITE_API_URL', '')
  vi.stubEnv('VITE_ESTADISTICAS', 'local')
  api = await import('../src/api/api.js')
})

describe('api.js sin red', () => {
  it('está en modo sin red', () => {
    expect(api.config.sinRed).toBe(true)
  })
  it('devuelve las dos listas de una empresa de ejemplo', async () => {
    const r = await api.recomendaciones('a9d295a111b3b950287624d5f042c56d1c275dee6d4d84e06ce7410b34e86c86')
    expect(r.tiene_historial).toBe(true)
    // El fixture trae el mismo proceso de IDUVI con dos id_proceso (republicación en SECOP): se muestra una vez
    expect(r.listas.historial.procesos.length).toBe(9)
    expect(r.listas.historial.repetidos).toBe(1)
    expect(r.listas.historial.procesos.filter((p) => p.entidad === 'IDUVI')).toHaveLength(1)
    expect(r.listas.historial.titulo).toBe('Recomendados según tu historial')
    expect(r.listas.historial.procesos[0].motivos.length).toBeGreaterThan(0)
    expect(r.listas.oportunidad.procesos[0]).toHaveProperty('probabilidad')
  })
  it('una llave inexistente responde con listas vacías, como la API real', async () => {
    const r = await api.recomendaciones('no-existe')
    expect(r.tiene_historial).toBe(false)
    expect(r.listas.historial.procesos).toEqual([])
  })
  it('limpia los "<NA>" del buscador', async () => {
    const lista = await api.buscarEmpresas('construcciones')
    expect(lista.length).toBeGreaterThan(0)
    expect(lista.some((e) => e.departamento === '<NA>')).toBe(false)
    expect(lista.some((e) => e.departamento === null)).toBe(true)
  })
  it('no busca con menos de 2 caracteres', async () => {
    expect(await api.buscarEmpresas('a')).toEqual([])
  })
})
