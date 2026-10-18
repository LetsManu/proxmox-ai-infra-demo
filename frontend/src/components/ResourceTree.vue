<script setup>
import { computed, reactive } from 'vue'
import { Building2, ChevronRight, Database, Layers, Monitor, Network, Server } from 'lucide-vue-next'

// Proxmox-style "Server View" resource tree: Datacenter > node > environments > VMs, templates, storage.
const props = defineProps({
  vms: { type: Array, default: null },
  templates: { type: Array, default: null },
  pxStatus: { type: Object, default: null },
  environments: { type: Array, default: () => [] },
  env: { type: String, required: true },
  selected: { type: String, default: '' },
})
const emit = defineEmits(['select-env', 'select-vm'])

const open = reactive({ dc: true, node: true, test: true, prod: true, tmpl: true, storage: false })
const node = computed(() => props.pxStatus?.nodes?.[0]?.node || 'pve')
const online = computed(() => props.pxStatus?.connected !== false)
const envs = computed(() =>
  ['test', 'prod'].map((key) => {
    const e = props.environments.find((x) => x.key === key)
    return {
      key,
      label: key === 'prod' ? 'Production' : 'Test',
      sub: e ? `VLAN ${e.network.vlan}` : '',
      vms: (props.vms || []).filter((v) => v.environment === key).sort((a, b) => a.vmid - b.vmid),
    }
  }),
)
const storage = computed(() => props.pxStatus?.storage || [])
</script>

<template>
  <nav class="tree" aria-label="Resources">
    <div class="view">Server View</div>
    <ul role="tree">
      <li role="treeitem" :aria-expanded="open.dc">
        <button class="row lvl0" @click="open.dc = !open.dc">
          <ChevronRight :size="13" class="caret" :class="{ open: open.dc }" /><Building2 :size="15" class="ic" />Datacenter
        </button>
        <ul v-show="open.dc" role="group">
          <li role="treeitem" :aria-expanded="open.node">
            <button class="row lvl1" @click="open.node = !open.node">
              <ChevronRight :size="13" class="caret" :class="{ open: open.node }" />
              <span class="ic-wrap"><Server :size="15" class="ic" /><i class="badge" :class="online ? 'on' : 'off'" /></span>{{ node }}
            </button>
            <ul v-show="open.node" role="group">
              <li v-for="e in envs" :key="e.key" role="treeitem" :aria-expanded="open[e.key]" :aria-selected="env === e.key && !selected">
                <div class="row-wrap">
                  <button class="caret-btn lvl2" :aria-label="`${open[e.key] ? 'Collapse' : 'Expand'} ${e.label}`" @click="open[e.key] = !open[e.key]">
                    <ChevronRight :size="13" class="caret" :class="{ open: open[e.key] }" />
                  </button>
                  <button class="row flat" :class="{ sel: env === e.key && !selected }" @click="emit('select-env', e.key)">
                    <Network :size="15" class="ic" :class="e.key" />{{ e.label }}<span class="sub">{{ e.sub }}</span>
                  </button>
                </div>
                <ul v-show="open[e.key]" role="group">
                  <li v-for="v in e.vms" :key="v.name" role="treeitem" :aria-selected="selected === `${v.environment}/${v.name}`">
                    <button class="row lvl3" :class="{ sel: selected === `${v.environment}/${v.name}` }" @click="emit('select-vm', v)">
                      <span class="ic-wrap"><Monitor :size="15" class="ic" /><i class="badge" :class="v.status === 'running' ? 'on' : 'off'" /></span>
                      <span class="num">{{ v.vmid }}</span>&nbsp;({{ v.name }})
                    </button>
                  </li>
                  <li v-if="vms && !e.vms.length" class="none lvl3">No VMs</li>
                </ul>
              </li>

              <li role="treeitem" :aria-expanded="open.tmpl">
                <button class="row lvl2" @click="open.tmpl = !open.tmpl">
                  <ChevronRight :size="13" class="caret" :class="{ open: open.tmpl }" /><Layers :size="15" class="ic" />Templates
                </button>
                <ul v-show="open.tmpl" role="group">
                  <li v-for="t in templates || []" :key="t.key" class="leaf lvl3" :class="{ missing: t.available === false }">
                    <Layers :size="15" class="ic tmpl" /><span class="num">{{ t.template_id }}</span>&nbsp;({{ t.label }})
                  </li>
                </ul>
              </li>

              <li role="treeitem" :aria-expanded="open.storage">
                <button class="row lvl2" @click="open.storage = !open.storage">
                  <ChevronRight :size="13" class="caret" :class="{ open: open.storage }" /><Database :size="15" class="ic" />Storage
                </button>
                <ul v-show="open.storage" role="group">
                  <li v-for="s in storage" :key="s.storage" class="leaf lvl3">
                    <Database :size="15" class="ic" />{{ s.storage }} ({{ node }})
                  </li>
                </ul>
              </li>
            </ul>
          </li>
        </ul>
      </li>
    </ul>
  </nav>
</template>

<style scoped>
.tree { font-size: 13px; user-select: none; }
.view { padding: .45rem .75rem; border-bottom: 1px solid var(--line); color: var(--mut); background: var(--surface); }
ul { list-style: none; }
.row, .leaf, .none {
  width: 100%; display: flex; align-items: center; gap: .4rem; min-height: 28px; padding-right: .6rem;
  background: transparent; border: 0; color: var(--fg); font: inherit; text-align: left; cursor: pointer; white-space: nowrap;
}
.leaf, .none { cursor: default; }
.none { color: var(--dim); font-style: italic; }
.row:hover { background: rgba(255, 255, 255, .05); }
.row.sel { background: var(--sel); color: #fff; }
.row.sel .ic, .row.sel .sub { color: #fff; }
.row-wrap { display: flex; align-items: center; }
.row-wrap .row { flex: 1; padding-left: 0; }
.caret-btn { background: transparent; border: 0; color: var(--dim); min-height: 28px; display: grid; place-items: center; cursor: pointer; padding-right: .2rem; }
.lvl0 { padding-left: .4rem; }
.lvl1 { padding-left: 1.2rem; }
.lvl2 { padding-left: 2rem; }
.lvl3 { padding-left: 3.4rem; }
.caret { color: var(--dim); transition: transform var(--t-fast); }
.caret.open { transform: rotate(90deg); }
.ic { color: var(--mut); }
.ic.test { color: var(--info); }
.ic.prod { color: var(--err); }
.ic.tmpl { color: #c9a26b; }
.ic-wrap { position: relative; display: inline-grid; }
.badge { position: absolute; right: -3px; bottom: -2px; width: 7px; height: 7px; border-radius: 50%; border: 1px solid var(--sidebar); }
.badge.on { background: var(--ok); }
.badge.off { background: #8a8a8a; }
.sub { color: var(--dim); margin-left: .35rem; font-size: 12px; }
.missing { color: var(--err); text-decoration: line-through; }
@media (pointer: coarse) { .row, .leaf, .caret-btn { min-height: 40px; } }
</style>
