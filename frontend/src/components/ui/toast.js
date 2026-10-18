import { reactive } from 'vue'

// Global toast queue (max 3). Errors stay longer; duration 0 = sticky.
export const toasts = reactive([])
let seq = 0

function push(kind, message, opts = {}) {
  const id = ++seq
  const duration = opts.duration ?? (kind === 'error' ? 8000 : 5000)
  toasts.push({ id, kind, message, title: opts.title })
  if (toasts.length > 3) toasts.shift()
  if (duration) setTimeout(() => close(id), duration)
  return id
}

export function close(id) {
  const i = toasts.findIndex((t) => t.id === id)
  if (i >= 0) toasts.splice(i, 1)
}

export const toast = {
  success: (m, o) => push('success', m, o),
  error: (m, o) => push('error', m, o),
  info: (m, o) => push('info', m, o),
}
