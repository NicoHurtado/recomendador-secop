import { describe, it, expect } from 'vitest'
import { pesos, pct, probabilidad, fecha, cierre, tituloEntidad, oracion, limpiar, fechaHoraBogota, mesCorto, pesosCompleto } from '../src/utils/formato.js'

const n = (s) => s.replace(new RegExp(String.fromCharCode(160), "g"), " ")

describe('pesos', () => {
  it('formatea montos legibles en español de Colombia', () => {
    expect(n(pesos(171830020))).toBe('$171,8 millones')
    expect(n(pesos(25880502459))).toBe('$25,9 mil millones')
    expect(n(pesos(35000000))).toBe('$35 millones')
    expect(n(pesos(1e6))).toBe('$1 millón')
    expect(n(pesos(1.1e12))).toBe('$1,1 billones')
    expect(n(pesos(1e12))).toBe('$1 billón')
    expect(pesosCompleto(35000000)).toBe('$35.000.000')
  })
  it('muestra "Valor no publicado" cuando no hay precio', () => {
    expect(pesos(null)).toBe('Valor no publicado')
    expect(pesos('<NA>')).toBe('Valor no publicado')
  })
})

describe('porcentajes y probabilidad', () => {
  it('redondea y usa espacio antes de %', () => {
    expect(n(pct(0.0882))).toBe('9 %')
    expect(n(pct(0.4372, 1))).toBe('43,7 %')
    expect(n(probabilidad(0.003))).toBe('<1 %')
    expect(pct(null)).toBe('—')
  })
})

describe('fechas', () => {
  it('formatea "18 nov 2026" sin desfase de zona horaria', () => {
    expect(fecha('2026-11-18')).toBe('18 nov 2026')
    expect(mesCorto('2026-03')).toBe('mar 2026')
  })
  it('convierte UTC a hora de Colombia', () => {
    expect(fechaHoraBogota('2026-11-18T13:21:49Z')).toMatch(/^18 nov 2026, 8:21/)
  })
  it('calcula el texto de cierre y resalta si quedan menos de 5 días', () => {
    expect(cierre('2026-11-22', '2026-11-18')).toMatchObject({ dias: 4, urgente: true, texto: 'Cierra en 4 días (22 nov)' })
    expect(cierre('2027-01-02', '2026-12-30').texto).toBe('Cierra en 3 días (2 ene 2027)')
    expect(cierre('2026-11-30', '2026-11-18')).toMatchObject({ urgente: false })
    expect(cierre('2026-11-17', '2026-11-18')).toMatchObject({ cerrado: true })
    expect(cierre('2026-11-18', '2026-11-18').texto).toMatch(/^Cierra hoy/)
  })
})

describe('textos de SECOP', () => {
  it('limpia los "<NA>" que a veces devuelve la API', () => {
    expect(limpiar('<NA>')).toBeNull()
    expect(limpiar(' Antioquia ')).toBe('Antioquia')
  })
  it('pasa entidades a formato título y conserva siglas', () => {
    expect(tituloEntidad('ALCALDIA LOCAL DE TEUSAQUILLO(oficial)')).toBe('Alcaldía Local de Teusaquillo')
    expect(tituloEntidad('BOLIVAR - ESE HOSPITAL UNIVERSITARIO DEL CARIBE')).toBe('Bolívar - ESE Hospital Universitario del Caribe')
    expect(tituloEntidad('HOSPITAL (ESE) SAN JUAN')).toBe('Hospital (ESE) San Juan')
    expect(tituloEntidad('EDESAN')).toBe('EDESAN')
    expect(tituloEntidad('CUNDINAMARCA-ALCALDIA MUNICIPIO MOSQUERA')).toBe('Cundinamarca - Alcaldía Municipio Mosquera')
    expect(oracion('OBRAS EN EL MUNICIPIO DE CHÍA CUNDINAMARCA.', ['Chía', 'Cundinamarca'])).toBe('Obras en el municipio de Chía Cundinamarca.')
    expect(oracion('VIAS DEL MUNICIPIO DE GACHANCIPA', ['Gachancipá'])).toBe('Vias del municipio de Gachancipá')
  })
})
