// Responde los indicadores de /estadisticas a partir de un snapshot de agregados (sumas y conteos).
// Emula el contrato v2 de la API: mismos nombres, mismos filtros y misma forma de respuesta.
// El snapshot es pequeño (agregados de la capa oro, nunca filas de procesos), así que se puede reagrupar aquí.
import { INDICADORES } from './indicadores.js'
import { nombreDepartamento } from '../utils/dane.js'
import { nombreSegmento } from '../utils/unspsc.js'
import { nombreModalidad } from '../utils/modalidades.js'

const SIN_DATO = 'SD'

/** Convierte una tabla columnar {cols, filas} en una función de acceso por nombre. */
function tabla(t) {
  const idx = Object.fromEntries((t?.cols ?? []).map((c, i) => [c, i]))
  return { filas: t?.filas ?? [], idx }
}

function nuevoAcumulado() {
  return { procesos: 0, adjudicados: 0, valor: 0, con_of: 0, unico: 0, suma_of: 0, adj_pyme: 0, valor_pyme: 0, hayPyme: false }
}

function sumar(acc, f, I) {
  acc.procesos += f[I.procesos] || 0
  acc.adjudicados += f[I.adjudicados] || 0
  acc.valor += f[I.valor] || 0
  acc.con_of += f[I.con_of] || 0
  acc.unico += f[I.unico] || 0
  if (I.suma_of !== undefined) acc.suma_of += f[I.suma_of] || 0
  if (I.adj_pyme !== undefined && f[I.adj_pyme] !== null && f[I.adj_pyme] !== undefined) {
    acc.hayPyme = true
    acc.adj_pyme += f[I.adj_pyme] || 0
    acc.valor_pyme += f[I.valor_pyme] || 0
  }
}

const razon = (a, b) => (b > 0 ? a / b : null)

/** Medidas que viajan en "valores". Los porcentajes son fracciones 0–1. */
function medidas(acc) {
  return {
    procesos: acc.procesos,
    procesos_adjudicados: acc.adjudicados,
    valor_adjudicado: acc.valor,
    procesos_con_oferentes: acc.con_of,
    procesos_unico_oferente: acc.unico,
    pct_oferente_unico: razon(acc.unico, acc.con_of),
    oferentes_promedio: acc.suma_of ? razon(acc.suma_of, acc.con_of) : null,
    procesos_ganados_pyme: acc.hayPyme ? acc.adj_pyme : null,
    valor_ganado_pyme: acc.hayPyme ? acc.valor_pyme : null,
    pct_procesos_pyme: acc.hayPyme ? razon(acc.adj_pyme, acc.adjudicados) : null,
    pct_valor_pyme: acc.hayPyme ? razon(acc.valor_pyme, acc.valor) : null,
  }
}

function normalizarFiltros(f = {}) {
  const out = {}
  if (f.anio) out.anio = Number(f.anio)
  if (f.departamento) out.departamento = String(f.departamento).padStart(2, '0')
  if (f.segmento) out.segmento = String(f.segmento).padStart(2, '0')
  if (f.modalidad) out.modalidad = String(f.modalidad)
  return out
}

/** Lleva los montos a pesos si el snapshot los trae escalados (p. ej. en millones). */
function desescalar(snapshot) {
  const k = Number(snapshot.escala_valor) || 1
  if (k === 1 || snapshot._desescalado) return snapshot
  const cols = { anual: ['valor', 'valor_pyme'], mensual: ['valor'], mensual_segmento: ['valor'], entidades: ['valor'] }
  for (const [t, nombres] of Object.entries(cols)) {
    const tb = snapshot[t]
    if (!tb) continue
    const idx = nombres.map((n) => tb.cols.indexOf(n)).filter((i) => i >= 0)
    for (const f of tb.filas) for (const i of idx) if (f[i] !== null) f[i] *= k
  }
  snapshot._desescalado = true
  return snapshot
}

export function crearMotor(snapshot) {
  desescalar(snapshot)
  const D = snapshot.departamentos
  const S = snapshot.segmentos
  const M = snapshot.modalidades
  const anual = tabla(snapshot.anual)
  const mensual = tabla(snapshot.mensual)
  const mensualSeg = tabla(snapshot.mensual_segmento)
  const entidades = tabla(snapshot.entidades)
  const calidad = tabla(snapshot.calidad)
  const desempeno = tabla(snapshot.desempeno)
  const idxDe = (arr, v) => (v === undefined ? -2 : arr.indexOf(v))

  function filtroAnual(f, ignorar = []) {
    const I = anual.idx
    const a = ignorar.includes('anio') ? undefined : f.anio
    const d = ignorar.includes('departamento') ? -2 : idxDe(D, f.departamento)
    const s = ignorar.includes('segmento') ? -2 : idxDe(S, f.segmento)
    const m = ignorar.includes('modalidad') ? -2 : idxDe(M, f.modalidad)
    return (r) => (a === undefined || r[I.anio] === a) && (d === -2 || r[I.d] === d) && (s === -2 || r[I.s] === s) && (m === -2 || r[I.m] === m)
  }

  function agrupar(t, pasa, clave) {
    const grupos = new Map()
    for (const r of t.filas) {
      if (!pasa(r)) continue
      const k = clave(r)
      let acc = grupos.get(k)
      if (!acc) grupos.set(k, (acc = nuevoAcumulado()))
      sumar(acc, r, t.idx)
    }
    return grupos
  }

  const notaCategoria = 'Desde mediados de septiembre de 2026 SECOP publica casi todos los procesos sin categoría UNSPSC ("UNSPECIFIED"). Esos procesos aparecen como "Sin categoría".'

  const resolvers = {
    resumen(f) {
      const g = agrupar(anual, filtroAnual(f), () => 'total')
      return { datos: [{ etiqueta: 'Total', codigo: null, valores: medidas(g.get('total') ?? nuevoAcumulado()) }] }
    },

    'por-departamento'(f) {
      const I = anual.idx
      const g = agrupar(anual, filtroAnual(f, ['departamento']), (r) => D[r[I.d]])
      const datos = [...g.entries()].map(([cod, acc]) => ({
        etiqueta: cod === SIN_DATO ? 'Sin departamento' : nombreDepartamento(cod) ?? cod,
        codigo: cod === SIN_DATO ? null : cod,
        valores: medidas(acc),
      })).sort((a, b) => b.valores.procesos - a.valores.procesos)
      return { datos, filtros_ignorados: ['departamento'] }
    },

    'por-categoria'(f) {
      const I = anual.idx
      const g = agrupar(anual, filtroAnual(f, ['segmento']), (r) => S[r[I.s]])
      const datos = [...g.entries()].map(([cod, acc]) => ({
        etiqueta: nombreSegmento(cod), codigo: cod, valores: medidas(acc),
      })).sort((a, b) => b.valores.valor_adjudicado - a.valores.valor_adjudicado)
      const notas = !f.anio || f.anio >= 2026 ? [notaCategoria] : []
      return { datos, filtros_ignorados: ['segmento'], notas }
    },

    'por-mes'(f) {
      const ignorados = []
      let g
      if (f.segmento) {
        const I = mensualSeg.idx
        const s = S.indexOf(f.segmento)
        if (f.departamento) ignorados.push('departamento')
        if (f.modalidad) ignorados.push('modalidad')
        g = agrupar(mensualSeg, (r) => r[I.s] === s && (!f.anio || String(r[I.mes]).startsWith(String(f.anio))), (r) => r[I.mes])
      } else {
        const I = mensual.idx
        const d = idxDe(D, f.departamento)
        const m = idxDe(M, f.modalidad)
        g = agrupar(mensual, (r) => (d === -2 || r[I.d] === d) && (m === -2 || r[I.m] === m) && (!f.anio || String(r[I.mes]).startsWith(String(f.anio))), (r) => r[I.mes])
      }
      const datos = [...g.entries()].sort(([a], [b]) => (a < b ? -1 : 1)).map(([mes, acc]) => ({ etiqueta: mes, codigo: mes, valores: medidas(acc) }))
      const notas = ignorados.length ? ['La serie mensual por categoría no se cruza con departamento ni modalidad; se muestra solo con el filtro de categoría.'] : []
      return { datos, filtros_ignorados: ignorados, notas }
    },

    'por-modalidad'(f) {
      const I = anual.idx
      const g = agrupar(anual, filtroAnual(f, ['modalidad', 'anio']), (r) => `${M[r[I.m]]}|${r[I.anio]}`)
      const datos = [...g.entries()].map(([k, acc]) => {
        const [cod, anio] = k.split('|')
        return { etiqueta: nombreModalidad(cod), codigo: cod, anio: Number(anio), valores: medidas(acc) }
      }).sort((a, b) => a.codigo.localeCompare(b.codigo) || a.anio - b.anio)
      return { datos, filtros_ignorados: ['modalidad', 'anio'] }
    },

    'pymes-por-anio'(f) {
      const I = anual.idx
      const g = agrupar(anual, filtroAnual(f, ['anio']), (r) => r[I.anio])
      const datos = [...g.entries()].sort(([a], [b]) => a - b).map(([anio, acc]) => ({ etiqueta: String(anio), codigo: String(anio), valores: medidas(acc) }))
      return { datos, filtros_ignorados: ['anio'] }
    },

    'top-entidades'(f, extra = {}) {
      const I = entidades.idx
      const d = idxDe(D, f.departamento)
      const por = new Map()
      for (const r of entidades.filas) {
        if (f.anio && r[I.anio] !== f.anio) continue
        if (d !== -2 && r[I.d] !== d) continue
        const k = r[I.key]
        let e = por.get(k)
        if (!e) por.set(k, (e = { nombre: r[I.nombre], d: r[I.d], dependencias: I.dependencias !== undefined ? r[I.dependencias] : 1, valor: 0, procesos: 0, con_of: 0, unico: 0, contratos: 0, proveedores: 0, hhiPond: 0, cuotaPond: 0, atipicos: 0 }))
        e.valor += r[I.valor]; e.procesos += r[I.procesos]; e.con_of += r[I.con_of]; e.unico += r[I.unico]
        e.contratos += r[I.contratos]; e.proveedores = Math.max(e.proveedores, r[I.proveedores]); e.atipicos += r[I.atipicos] || 0
        e.hhiPond += (r[I.hhi] ?? 0) * r[I.valor]; e.cuotaPond += (r[I.cuota_principal] ?? 0) * r[I.valor]
      }
      const limite = Math.min(Number(extra.limite) || 15, 200)
      const datos = [...por.entries()].sort((a, b) => b[1].valor - a[1].valor).slice(0, limite).map(([key, e]) => ({
        etiqueta: e.nombre,
        codigo: key,
        valores: {
          valor_adjudicado: e.valor,
          procesos: e.procesos,
          procesos_con_oferentes: e.con_of,
          procesos_unico_oferente: e.unico,
          pct_oferente_unico: razon(e.unico, e.con_of),
          contratos: e.contratos,
          proveedores_distintos: e.proveedores,
          hhi: razon(e.hhiPond, e.valor),
          cuota_proveedor_principal: razon(e.cuotaPond, e.valor),
          contratos_valor_atipico: e.atipicos,
          departamento: D[e.d] === SIN_DATO ? null : D[e.d],
          dependencias: e.dependencias,
        },
      }))
      const ignorados = ['segmento', 'modalidad'].filter((k) => f[k])
      const notas = ignorados.length ? ['El ranking de entidades se calcula por entidad y año; no se cruza con categoría ni modalidad.'] : []
      return { datos, filtros_ignorados: ignorados, notas }
    },

    'detalle-entidad'(f, extra = {}) {
      const I = entidades.idx
      const datos = entidades.filas.filter((r) => r[I.key] === extra.entidad).sort((a, b) => a[I.anio] - b[I.anio]).map((r) => ({
        etiqueta: String(r[I.anio]), codigo: String(r[I.anio]), nombre: r[I.nombre],
        valores: {
          valor_adjudicado: r[I.valor], procesos: r[I.procesos], pct_oferente_unico: razon(r[I.unico], r[I.con_of]),
          contratos: r[I.contratos], proveedores_distintos: r[I.proveedores], hhi: r[I.hhi], cuota_proveedor_principal: r[I.cuota_principal],
          departamento: D[r[I.d]] === SIN_DATO ? null : D[r[I.d]],
          dependencias: I.dependencias !== undefined ? r[I.dependencias] : 1,
        },
      }))
      return { datos, filtros_ignorados: ['anio', 'departamento', 'segmento', 'modalidad'] }
    },

    'calidad-fuente'() {
      const I = calidad.idx
      const datos = calidad.filas.map((r) => ({
        etiqueta: r[I.semana], codigo: r[I.semana],
        valores: {
          procesos: r[I.procesos],
          pct_sin_categoria: razon(r[I.sin_categoria], r[I.procesos]),
          pct_sin_departamento: razon(r[I.sin_departamento], r[I.procesos]),
          pct_sin_precio: razon(r[I.sin_precio], r[I.procesos]),
        },
      }))
      return { datos, filtros_ignorados: ['anio', 'departamento', 'segmento', 'modalidad'] }
    },

    'desempeno-recomendaciones'() {
      const I = desempeno.idx
      const datos = desempeno.filas.map((r) => ({
        etiqueta: r[I.fecha_corte], codigo: r[I.lista], lista: r[I.lista],
        valores: { ofertas_reales: r[I.ofertas_reales], cobertura: r[I.cobertura], precision_empresas_activas: r[I.precision_activas], gano: r[I.gano] ?? null, ganes_esperados: r[I.ganes_esperados] ?? null },
      }))
      return { datos, filtros_ignorados: [], notas: snapshot.desempeno?.nota ? [snapshot.desempeno.nota] : [] }
    },
  }

  return {
    indicadores: Object.keys(resolvers),
    consultar(indicador, filtros = {}, extra = {}) {
      const fn = resolvers[indicador]
      if (!fn) {
        const e = new Error(`Indicador desconocido: ${indicador}`)
        e.status = 404
        throw e
      }
      const f = normalizarFiltros(filtros)
      const r = fn(f, extra)
      const aplicados = Object.fromEntries(Object.entries(f).filter(([k]) => !(r.filtros_ignorados ?? []).includes(k)))
      return {
        indicador,
        descripcion: INDICADORES[indicador]?.descripcion ?? '',
        unidad: INDICADORES[indicador]?.unidad ?? '',
        fecha_datos: snapshot.fecha_datos,
        filtros_aplicados: aplicados,
        filtros_ignorados: r.filtros_ignorados ?? [],
        notas: r.notas ?? [],
        datos: r.datos,
      }
    },
  }
}
