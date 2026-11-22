import { describe, it, expect } from 'vitest'
import { crearMotor } from '../src/api/estadisticasLocal.js'

// Snapshot mínimo con la forma del exportado de la capa oro
const snap = () => ({
  fuente: 'simulado', fecha_datos: '2026-11-17', escala_valor: 1e6,
  departamentos: ['05', '11', 'SD'], segmentos: ['72', '00'], modalidades: ['minima_cuantia', 'licitacion_publica'],
  anual: { cols: ['anio', 'd', 's', 'm', 'procesos', 'adjudicados', 'valor', 'con_of', 'unico', 'suma_of', 'adj_pyme', 'valor_pyme'], filas: [
    [2025, 0, 0, 0, 100, 80, 10, 80, 40, 160, 60, 5],
    [2025, 1, 0, 1, 50, 40, 100, 40, 10, 160, 10, 20],
    [2026, 0, 1, 0, 30, 20, 3, 20, 10, 40, 15, 1],
    [2026, 2, 1, 0, 10, 5, 1, 5, 5, 5, 2, 0],
  ] },
  mensual: { cols: ['mes', 'd', 'm', 'procesos', 'adjudicados', 'valor', 'con_of', 'unico'], filas: [['2025-01', 0, 0, 100, 80, 10, 80, 40], ['2025-02', 1, 1, 50, 40, 100, 40, 10]] },
  mensual_segmento: { cols: ['mes', 's', 'procesos', 'adjudicados', 'valor', 'con_of', 'unico'], filas: [['2025-01', 0, 150, 120, 110, 120, 50]] },
  entidades: { cols: ['key', 'nombre', 'd', 'anio', 'procesos', 'con_of', 'unico', 'contratos', 'valor', 'proveedores', 'hhi', 'cuota_principal', 'atipicos'], filas: [
    ['E1', 'Alcaldía A', 0, 2025, 10, 8, 4, 12, 50, 5, 0.2, 0.4, 0], ['E1', 'Alcaldía A', 0, 2026, 10, 8, 2, 12, 150, 6, 0.1, 0.3, 1], ['E2', 'Gobernación B', 1, 2025, 5, 5, 5, 6, 80, 2, 0.5, 0.7, 0],
  ] },
  calidad: { cols: ['semana', 'procesos', 'sin_categoria', 'sin_departamento', 'sin_precio', 'precio_atipico'], filas: [['2026-09-21', 1000, 968, 30, 20, 1]] },
  desempeno: { cols: ['fecha_corte', 'lista', 'ofertas_reales', 'cobertura', 'precision_activas'], filas: [['2026-11-12', 'historial', 1271, 0.585, 0.193]] },
})

describe('motor local de /estadisticas', () => {
  it('suma conteos y calcula porcentajes como razón de sumas (nunca promedio de porcentajes)', () => {
    const m = crearMotor(snap())
    const v = m.consultar('resumen', {}).datos[0].valores
    expect(v.procesos).toBe(190)
    expect(v.valor_adjudicado).toBe(114e6) // desescalado de millones a pesos
    expect(v.pct_oferente_unico).toBeCloseTo(65 / 145)
    expect(v.pct_procesos_pyme).toBeCloseTo(87 / 145)
  })
  it('aplica los filtros globales', () => {
    const m = crearMotor(snap())
    expect(m.consultar('resumen', { anio: '2025' }).datos[0].valores.procesos).toBe(150)
    expect(m.consultar('resumen', { departamento: '05', modalidad: 'minima_cuantia' }).datos[0].valores.procesos).toBe(130)
    expect(m.consultar('resumen', { segmento: '72', anio: 2026 }).datos[0].valores.procesos).toBe(0)
  })
  it('agrupa por departamento con código DANE e ignora su propio filtro (filtro cruzado)', () => {
    const r = crearMotor(snap()).consultar('por-departamento', { departamento: '05' })
    expect(r.datos.map((d) => d.codigo)).toEqual(['05', '11', null])
    expect(r.datos[2].etiqueta).toBe('Sin departamento')
    expect(r.filtros_ignorados).toContain('departamento')
  })
  it('avisa de la caída de la categoría UNSPSC en 2026', () => {
    const r = crearMotor(snap()).consultar('por-categoria', {})
    expect(r.notas.join(' ')).toMatch(/septiembre de 2026/)
  })
  it('la serie mensual por categoría declara los filtros que no puede cruzar', () => {
    const r = crearMotor(snap()).consultar('por-mes', { segmento: '72', departamento: '05' })
    expect(r.filtros_ignorados).toEqual(['departamento'])
    expect(r.datos[0].valores.procesos).toBe(150)
  })
  it('ordena el top de entidades por valor y pondera el HHI por valor', () => {
    const r = crearMotor(snap()).consultar('top-entidades', {}, { limite: 15 })
    expect(r.datos.map((d) => d.codigo)).toEqual(['E1', 'E2'])
    expect(r.datos[0].valores.valor_adjudicado).toBe(200e6)
    expect(r.datos[0].valores.hhi).toBeCloseTo((0.2 * 50 + 0.1 * 150) / 200)
  })
  it('responde 404 para un indicador desconocido', () => {
    expect(() => crearMotor(snap()).consultar('no-existe')).toThrow(/desconocido/)
  })
})
