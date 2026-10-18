import { reactive } from 'vue'

// Tiny hash router: every screen has a shareable URL (#/vm/test/web-test).
// Routes: dashboard | vm-new | vm/:env/:name | stacks | stack-new | stack/:env/:name | review | platform | activity
export const route = reactive({ name: 'dashboard', params: {} })

function parse() {
  const parts = (location.hash.replace(/^#\/?/, '') || 'dashboard').split('/').map(decodeURIComponent)
  const [head, a, b] = parts
  if (head === 'vm' && a && b) return { name: 'vm', params: { env: a, name: b } }
  if (head === 'stack' && a && b) return { name: 'stack', params: { env: a, name: b } }
  const known = ['dashboard', 'vm-new', 'stacks', 'stack-new', 'review', 'platform', 'activity']
  return { name: known.includes(head) ? head : 'dashboard', params: {} }
}

function sync() {
  Object.assign(route, parse())
  // focus-on-route-change: move screen readers and keyboard users to the new content
  requestAnimationFrame(() => document.getElementById('main')?.focus({ preventScroll: true }))
  window.scrollTo({ top: 0 })
}

export function go(path) {
  const target = `#/${path}`
  if (location.hash === target) sync()
  else location.hash = target
}

export const links = {
  vm: (env, name) => `vm/${env}/${encodeURIComponent(name)}`,
  stack: (env, name) => `stack/${env}/${encodeURIComponent(name)}`,
}

window.addEventListener('hashchange', sync)
Object.assign(route, parse())
