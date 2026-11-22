import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { codigoDepartamento, nombreDepartamento, DEPARTAMENTOS, nombreSecop } from '../src/utils/dane.js'

describe('tabla nombre → código DANE', () => {
  it('reconoce cómo escribe SECOP Bogotá y San Andrés', () => {
    expect(codigoDepartamento('Distrito Capital de Bogotá')).toBe('11')
    expect(codigoDepartamento('BOGOTÁ D.C.')).toBe('11')
    expect(codigoDepartamento('San Andrés, Providencia y Santa Catalina')).toBe('88')
    expect(codigoDepartamento('Archipiélago de San Andrés, Providencia y Santa Catalina')).toBe('88')
  })
  it('ignora tildes y mayúsculas', () => {
    expect(codigoDepartamento('BOLIVAR')).toBe('13')
    expect(codigoDepartamento('nariño')).toBe('52')
    expect(codigoDepartamento('Valle del Cauca')).toBe('76')
    expect(codigoDepartamento('<NA>')).toBeNull()
  })
  it('devuelve el nombre que espera la API para filtrar', () => {
    expect(nombreSecop('11')).toBe('Distrito Capital de Bogotá')
    expect(nombreSecop('05')).toBe('Antioquia')
  })
  it('cubre los 33 departamentos del GeoJSON del mapa con los mismos códigos', () => {
    const geo = JSON.parse(readFileSync(resolve(process.cwd(), 'public/geo/colombia-departamentos.json'), 'utf8'))
    const codigosGeo = geo.features.map((f) => f.properties.codigo).sort()
    expect(codigosGeo).toEqual(DEPARTAMENTOS.map((d) => d.codigo).sort())
    for (const c of codigosGeo) expect(nombreDepartamento(c)).toBeTruthy()
  })
})
