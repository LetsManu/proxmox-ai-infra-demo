import { reactive } from 'vue'

// Promise-based modal for critical actions only.
//   const ok = await ask({
//     title, body, effects: ['what will happen', ...], confirmLabel,
//     danger: true,            // red confirm button
//     production: true,        // adds "I understand this will affect the production environment."
//     typed: 'PROMOTE',        // must be typed exactly; confirm stays disabled until then
//   })
export const modal = reactive({ open: false, opts: {}, resolve: null })

export function ask(opts) {
  if (modal.resolve) modal.resolve(false)
  return new Promise((resolve) => Object.assign(modal, { open: true, opts, resolve }))
}

export function settle(value) {
  modal.resolve?.(value)
  Object.assign(modal, { open: false, resolve: null })
}
