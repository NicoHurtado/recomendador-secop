// Cliente HTTP con tiempo de espera y errores clasificados para mostrar mensajes amables.
export class ApiError extends Error {
  constructor(tipo, mensaje, status = null) {
    super(mensaje)
    this.name = 'ApiError'
    this.tipo = tipo // 'red' | 'tiempo' | 'limite' | 'no_encontrado' | 'invalido' | 'sin_publicacion' | 'servidor'
    this.status = status
  }
}

export const MENSAJES = {
  red: 'No pudimos conectarnos con el servicio. Revisa tu conexión e inténtalo de nuevo.',
  tiempo: 'El servicio está tardando más de lo normal. Inténtalo de nuevo en un momento.',
  limite: 'Espera un momento antes de volver a intentar.',
  no_encontrado: 'No encontramos lo que buscas.',
  invalido: 'La consulta no es válida. Revisa los datos e inténtalo de nuevo.',
  sin_publicacion: 'Los datos de hoy todavía no están disponibles. Inténtalo de nuevo más tarde.',
  servidor: 'Algo falló de nuestro lado. Inténtalo de nuevo en un momento.',
}

function tipoPorStatus(s) {
  if (s === 404) return 'no_encontrado'
  if (s === 422 || s === 400) return 'invalido'
  if (s === 429) return 'limite'
  if (s === 503) return 'sin_publicacion'
  return 'servidor'
}

/**
 * GET JSON. La API corre en Lambda: el primer llamado tras un rato sin uso tarda ~5 s,
 * por eso el tiempo de espera es de 15 s (la guía pide no bajar de 10 s).
 */
export async function getJSON(url, { timeout = 15000, signal } = {}) {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(new DOMException('timeout', 'TimeoutError')), timeout)
  const onAbort = () => ctrl.abort(signal.reason)
  if (signal) {
    if (signal.aborted) ctrl.abort(signal.reason)
    else signal.addEventListener('abort', onAbort, { once: true })
  }
  try {
    const res = await fetch(url, { signal: ctrl.signal, headers: { Accept: 'application/json' } })
    if (!res.ok) throw new ApiError(tipoPorStatus(res.status), MENSAJES[tipoPorStatus(res.status)], res.status)
    return await res.json()
  } catch (e) {
    if (e instanceof ApiError) throw e
    if (signal?.aborted) throw e // cancelado por quien llamó (p. ej. el buscador): no es un error para mostrar
    if (e?.name === 'TimeoutError' || ctrl.signal.reason?.name === 'TimeoutError') throw new ApiError('tiempo', MENSAJES.tiempo)
    throw new ApiError('red', MENSAJES.red)
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', onAbort)
  }
}

export function esCancelacion(e) {
  return e?.name === 'AbortError'
}
