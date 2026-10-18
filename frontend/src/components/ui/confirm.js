import { reactive } from 'vue'

// Promise-based confirmation dialog: `if (await confirm({ title, danger: true })) ...`
export const dialog = reactive({ open: false, opts: {}, resolve: null })

export function confirm(opts) {
  if (dialog.resolve) dialog.resolve(false)
  return new Promise((resolve) => {
    Object.assign(dialog, { open: true, opts, resolve })
  })
}

export function settle(value) {
  dialog.resolve?.(value)
  Object.assign(dialog, { open: false, resolve: null })
}
