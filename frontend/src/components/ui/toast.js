import { reactive } from 'vue'

// Toast queue (max 3, newest last).
//  success / info: auto-dismiss after 5 s
//  error: stays until dismissed; may carry an action such as "View details"
// Never use a toast to confirm a production change: that is a modal.
export const toasts = reactive([])
let seq = 0

function push(kind, message, opts = {}) {
  const id = ++seq
  const duration = opts.duration ?? (kind === 'error' ? 0 : 5000)
  toasts.push({ id, kind, message, title: opts.title, action: opts.action })
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
