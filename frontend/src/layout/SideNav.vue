<script setup>
import { computed, reactive } from 'vue'
import { LayoutDashboard, Server, Boxes, ClipboardCheck, Database, History, ChevronRight, Monitor, Box, Network } from 'lucide-vue-next'
import { store } from '../store.js'
import { route, links } from '../router.js'

const emit = defineEmits(['navigate'])
const open = reactive({ test: true, prod: true })
const pending = computed(() => (store.proposals?.length || 0) + (store.awaiting?.length || 0))
const NAV = computed(() => [
  { to: 'dashboard', label: 'Dashboard', icon: LayoutDashboard, match: ['dashboard'] },
  { to: 'vm-new', label: 'Create VM', icon: Server, match: ['vm-new'] },
  { to: 'stacks', label: 'Stacks', icon: Boxes, match: ['stacks', 'stack-new', 'stack'] },
  { to: 'review', label: 'Review queue', icon: ClipboardCheck, match: ['review'], badge: pending.value },
  { to: 'platform', label: 'Platform', icon: Database, match: ['platform'], warn: store.platform && !store.platform.ready },
  { to: 'activity', label: 'Activity', icon: History, match: ['activity'] },
])
const envs = computed(() =>
  ['test', 'prod'].map((key) => ({
    key,
    label: key === 'prod' ? 'Production' : 'Test',
    stacks: (store.stacks || []).filter((s) => s.environment === key),
    vms: (store.vms || []).filter((v) => v.environment === key && !v.spec.stack).sort((a, b) => a.vmid - b.vmid),
  })),
)
const isSel = (env, name, kind) => route.name === kind && route.params.env === env && route.params.name === name
</script>

<template>
  <nav class="nav" aria-label="Main">
    <ul class="menu">
      <li v-for="n in NAV" :key="n.to">
        <a :href="`#/${n.to}`" class="item" :class="{ active: n.match.includes(route.name) }" :aria-current="n.match.includes(route.name) ? 'page' : undefined" @click="emit('navigate')">
          <component :is="n.icon" :size="17" aria-hidden="true" />{{ n.label }}
          <span v-if="n.badge" class="count num" :aria-label="`${n.badge} waiting`">{{ n.badge }}</span>
          <span v-else-if="n.warn" class="dot" title="Something is missing" aria-label="needs attention" />
        </a>
      </li>
    </ul>

    <div class="tree-title">Resources<span class="dim small">{{ store.pxStatus?.nodes?.[0]?.node || 'pve' }}</span></div>
    <ul class="tree" role="tree" aria-label="Machines by environment">
      <li v-for="e in envs" :key="e.key" role="treeitem" :aria-expanded="open[e.key]">
        <button type="button" class="node" @click="open[e.key] = !open[e.key]">
          <ChevronRight :size="14" class="caret" :class="{ open: open[e.key] }" aria-hidden="true" />
          <Network :size="15" :class="['env-ic', e.key]" aria-hidden="true" />{{ e.label }}
          <span class="dim small num">{{ e.vms.length + e.stacks.reduce((n, s) => n + s.members.length, 0) }}</span>
        </button>
        <ul v-show="open[e.key]" role="group">
          <li v-for="s in e.stacks" :key="`s-${s.name}`" role="treeitem">
            <a :href="`#/${links.stack(e.key, s.name)}`" class="leaf" :class="{ sel: isSel(e.key, s.name, 'stack') }" @click="emit('navigate')">
              <Boxes :size="15" aria-hidden="true" />{{ s.name }}<span class="dim small">stack</span>
            </a>
          </li>
          <li v-for="v in e.vms" :key="v.name" role="treeitem">
            <a :href="`#/${links.vm(e.key, v.name)}`" class="leaf" :class="{ sel: isSel(e.key, v.name, 'vm') }" @click="emit('navigate')">
              <span class="ic-wrap"><component :is="v.spec.kind === 'lxc' ? Box : Monitor" :size="15" aria-hidden="true" /><i class="state" :class="v.status === 'running' ? 'on' : 'off'" /></span>
              <span class="num dim">{{ v.vmid }}</span>{{ v.name }}
            </a>
          </li>
          <li v-if="store.vms && !e.vms.length && !e.stacks.length" class="none">No machines yet</li>
        </ul>
      </li>
    </ul>
  </nav>
</template>

<style scoped>
.nav { display: flex; flex-direction: column; padding: 10px 8px 16px; gap: 6px; }
.menu { list-style: none; display: flex; flex-direction: column; gap: 2px; }
.item {
  display: flex; align-items: center; gap: 10px; min-height: 38px; padding: 0 10px; border-radius: var(--radius);
  color: var(--fg); text-decoration: none; font-weight: 500;
}
.item svg { color: var(--mut); }
.item:hover { background: var(--surface-3); }
.item.active { background: var(--sel); color: var(--sel-fg); }
.item.active svg { color: var(--sel-fg); }
.count { margin-left: auto; min-width: 22px; height: 20px; padding: 0 6px; border-radius: 999px; background: var(--warn-fg); color: var(--surface); font-size: 12px; font-weight: 700; display: grid; place-items: center; }
.dot { margin-left: auto; width: 8px; height: 8px; border-radius: 50%; background: var(--warn-fg); }
.tree-title { display: flex; justify-content: space-between; align-items: baseline; margin: 14px 10px 4px; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: var(--dim); }
.tree, .tree ul { list-style: none; }
.node, .leaf {
  width: 100%; display: flex; align-items: center; gap: 7px; min-height: 32px; padding: 0 8px; border: 0; background: transparent;
  color: var(--fg); text-align: left; cursor: pointer; border-radius: var(--radius); text-decoration: none; white-space: nowrap; overflow: hidden;
}
.node { font-weight: 600; }
.node .dim { margin-left: auto; }
.leaf { padding-left: 32px; font-size: 14px; }
.leaf .dim:last-child { margin-left: auto; }
.node:hover, .leaf:hover { background: var(--surface-3); }
.leaf.sel { background: var(--sel); color: var(--sel-fg); }
.leaf.sel .dim { color: var(--sel-fg); }
.caret { color: var(--dim); transition: transform var(--t-fast); }
.caret.open { transform: rotate(90deg); }
.env-ic.test { color: var(--info-fg); }
.env-ic.prod { color: var(--err-fg); }
.ic-wrap { position: relative; display: inline-grid; color: var(--mut); }
.state { position: absolute; right: -3px; bottom: -2px; width: 7px; height: 7px; border-radius: 50%; border: 1px solid var(--sidebar); }
.state.on { background: var(--ok-fg); }
.state.off { background: var(--dim); }
.none { padding: 4px 8px 4px 32px; color: var(--dim); font-size: 13px; font-style: italic; }
@media (pointer: coarse) { .node, .leaf, .item { min-height: 44px; } }
</style>
