// Lee los tokens de CSS para que las gráficas usen exactamente la misma paleta que la interfaz (claro/oscuro).
const VARS = ['surface-1', 'surface-2', 'surface-3', 'ink-1', 'ink-2', 'ink-muted', 'axis-label', 'grid', 'axis',
  's1', 's2', 'deemph', 's1-track', 's1-wash', 'accent', 'alerta', 'alerta-ink', 'ref', 'good']

export function leerTema() {
  const cs = getComputedStyle(document.documentElement)
  const t = {}
  for (const v of VARS) t[v.replace(/-(\w)/g, (_, c) => c.toUpperCase())] = cs.getPropertyValue(`--${v}`).trim()
  t.fuente = cs.getPropertyValue('--font').trim() || 'system-ui, sans-serif'
  return t
}

/** Opciones comunes: ejes y cuadrícula recesivos, tooltip tipo "flyout" con el valor primero. */
export function base(t) {
  return {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: t.fuente, color: t.ink2 },
    animationDuration: 300,
    animationDurationUpdate: 250,
    aria: { enabled: true },
    tooltip: {
      backgroundColor: t.surface1,
      borderColor: t.axis,
      borderWidth: 1,
      padding: [8, 12],
      textStyle: { color: t.ink1, fontSize: 12, fontFamily: t.fuente },
      extraCssText: 'box-shadow: 0 8px 16px rgba(0,0,0,.14), 0 0 2px rgba(0,0,0,.12); border-radius: 8px;',
      confine: true,
    },
  }
}

export function ejeCategorias(t, extra = {}) {
  return {
    type: 'category',
    axisLine: { lineStyle: { color: t.axis } },
    axisTick: { show: false },
    axisLabel: { color: t.axisLabel, fontSize: 12 },
    ...extra,
  }
}

export function ejeValores(t, extra = {}) {
  return {
    type: 'value',
    splitLine: { lineStyle: { color: t.grid, width: 1, type: 'solid' } },
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: t.axisLabel, fontSize: 12 },
    nameTextStyle: { color: t.ink2, fontSize: 12 },
    ...extra,
  }
}

/** Escapa texto que viene de la API antes de ponerlo en el HTML del tooltip. */
export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
}

/** Fila de tooltip: etiqueta a la izquierda, valor fuerte a la derecha; clave de serie como trazo corto. */
export function filaTooltip(color, etiqueta, valor) {
  const clave = color ? `<span style="display:inline-block;width:10px;height:3px;border-radius:2px;background:${color};margin-right:6px;vertical-align:middle"></span>` : ''
  return `<div style="display:flex;justify-content:space-between;gap:20px;align-items:center;line-height:20px"><span>${clave}${esc(etiqueta)}</span><strong style="font-weight:600">${esc(valor)}</strong></div>`
}

export function tituloTooltip(texto) {
  return `<div style="font-weight:600;margin-bottom:4px;max-width:280px;white-space:normal">${esc(texto)}</div>`
}
