<script setup>
import { computed } from 'vue'
import { Plus, Trash2, Monitor, Box, Container } from 'lucide-vue-next'
import Field from './ui/Field.vue'
import Badge from './ui/Badge.vue'
import { store } from '../store.js'
import { OS_LABEL, gb } from './ui/format.js'

// Edit a drafted architecture: machines (VM or LXC), their software and Docker services.
const stack = defineModel({ type: Object, required: true })
const vmTemplates = computed(() => (store.templates || []).filter((t) => t.kind === 'vm'))
const ctTemplates = computed(() => (store.templates || []).filter((t) => t.kind === 'lxc'))
const totals = computed(() => stack.value.components.reduce((t, c) => ({ cores: t.cores + c.cores, mem: t.mem + c.memory_mb, disk: t.disk + c.disk_gb }), { cores: 0, mem: 0, disk: 0 }))

function osOf(c) {
  return c.kind === 'lxc' ? 'linux' : vmTemplates.value.find((t) => t.key === c.template)?.os_family || 'linux'
}
function setKind(c, kind) {
  c.kind = kind
  c.template = kind === 'lxc' ? 'debian-12-lxc' : 'ubuntu-24-04'
}
function toggle(c, key, on) {
  const s = new Set(c.profiles)
  on ? s.add(key) : s.delete(key)
  c.profiles = [...s]
  if (key === 'docker' && !on) c.services = []
}
function addComponent() {
  const n = stack.value.components.length + 1
  stack.value.components.push({ name: `node${n}`, kind: 'lxc', template: 'debian-12-lxc', cores: 1, memory_mb: 1024, disk_gb: 8, description: '', profiles: [], packages: [], services: [] })
}
function addService(c) {
  c.services.push({ name: `svc${c.services.length + 1}`, image: 'nginx:1.27', ports: [], env: {}, volumes: [] })
}
const listText = (arr) => (arr || []).join(', ')
const parseList = (v) => v.split(/[\s,]+/).filter(Boolean)
const envText = (o) => Object.entries(o || {}).map(([k, v]) => `${k}=${v}`).join('\n')
function parseEnv(v) {
  return Object.fromEntries(v.split('\n').map((l) => l.trim()).filter((l) => l.includes('=')).map((l) => [l.slice(0, l.indexOf('=')).trim(), l.slice(l.indexOf('=') + 1).trim()]))
}
</script>

<template>
  <div class="se">
    <div class="grid2">
      <Field id="st-name" label="Stack name" required hint="Machines are named <stack>-<component>-test.">
        <input id="st-name" v-model.trim="stack.name" class="mono-input" autocomplete="off" spellcheck="false" aria-describedby="st-name-msg" />
      </Field>
      <Field id="st-desc" label="Description">
        <input id="st-desc" v-model="stack.description" maxlength="500" />
      </Field>
    </div>
    <p class="dim small num">Total: {{ totals.cores }} vCPU · {{ gb(totals.mem) }} memory · {{ totals.disk }} GB disk · {{ stack.components.length }} machine(s)</p>

    <article v-for="(c, i) in stack.components" :key="i" class="comp">
      <header class="ch">
        <component :is="c.kind === 'lxc' ? Box : Monitor" :size="18" aria-hidden="true" />
        <h3 class="mono">{{ stack.name }}-{{ c.name }}</h3>
        <Badge :tone="c.kind === 'lxc' ? 'info' : 'muted'" :label="c.kind === 'lxc' ? 'Container (LXC)' : 'Virtual machine'" />
        <span class="dim small">{{ OS_LABEL[c.template] || c.template }} · {{ c.cores }} vCPU · {{ gb(c.memory_mb) }} · {{ c.disk_gb }} GB</span>
        <span class="spacer" />
        <button type="button" class="btn quiet sm" :disabled="stack.components.length === 1" :aria-label="`Remove ${c.name}`" @click="stack.components.splice(i, 1)"><Trash2 :size="15" />Remove</button>
      </header>
      <div class="cb">
        <div class="grid4">
          <Field :id="`c${i}-name`" label="Component"><input :id="`c${i}-name`" v-model.trim="c.name" class="mono-input" /></Field>
          <Field :id="`c${i}-kind`" label="Type">
            <select :id="`c${i}-kind`" :value="c.kind" @change="setKind(c, $event.target.value)">
              <option value="vm">Virtual machine</option><option value="lxc">Container (LXC)</option>
            </select>
          </Field>
          <Field :id="`c${i}-os`" label="Operating system">
            <select :id="`c${i}-os`" v-model="c.template">
              <option v-for="t in c.kind === 'lxc' ? ctTemplates : vmTemplates" :key="t.key" :value="t.key">{{ t.label }}{{ t.available === false ? ' (not available yet)' : '' }}</option>
            </select>
          </Field>
          <div class="sizes">
            <Field :id="`c${i}-cpu`" label="vCPU"><input :id="`c${i}-cpu`" v-model.number="c.cores" type="number" min="1" max="4" /></Field>
            <Field :id="`c${i}-mem`" label="MB"><input :id="`c${i}-mem`" v-model.number="c.memory_mb" type="number" min="256" step="256" /></Field>
            <Field :id="`c${i}-disk`" label="GB"><input :id="`c${i}-disk`" v-model.number="c.disk_gb" type="number" min="4" /></Field>
          </div>
        </div>
        <fieldset class="profiles">
          <legend class="small">Software profiles</legend>
          <label v-for="p in store.profiles.filter((p) => p.os_family === osOf(c))" :key="p.key" class="check small">
            <input type="checkbox" :checked="c.profiles.includes(p.key)" @change="toggle(c, p.key, $event.target.checked)" />{{ p.label }}
          </label>
        </fieldset>
        <Field :id="`c${i}-pkg`" label="Extra packages" hint="Space or comma separated package names.">
          <input :id="`c${i}-pkg`" class="mono-input" :value="listText(c.packages)" @change="c.packages = parseList($event.target.value)" />
        </Field>

        <div v-if="c.profiles.includes('docker')" class="services">
          <h4 class="small"><Container :size="15" aria-hidden="true" />Docker services on this machine</h4>
          <div v-for="(s, j) in c.services" :key="j" class="svc">
            <div class="grid4">
              <Field :id="`c${i}s${j}-n`" label="Service"><input :id="`c${i}s${j}-n`" v-model.trim="s.name" class="mono-input" /></Field>
              <Field :id="`c${i}s${j}-i`" label="Image" hint="Pinned tag, e.g. postgres:17"><input :id="`c${i}s${j}-i`" v-model.trim="s.image" class="mono-input" /></Field>
              <Field :id="`c${i}s${j}-p`" label="Published ports" hint="HOST:CONTAINER"><input :id="`c${i}s${j}-p`" class="mono-input" :value="listText(s.ports)" @change="s.ports = parseList($event.target.value)" /></Field>
              <Field :id="`c${i}s${j}-v`" label="Volumes" hint="name:/path"><input :id="`c${i}s${j}-v`" class="mono-input" :value="listText(s.volumes)" @change="s.volumes = parseList($event.target.value)" /></Field>
            </div>
            <Field :id="`c${i}s${j}-e`" label="Settings" hint="One KEY=value per line. Passwords must be secret:<name>; the machine generates them and they never reach the console.">
              <textarea :id="`c${i}s${j}-e`" class="mono-input" rows="3" :value="envText(s.env)" @change="s.env = parseEnv($event.target.value)" />
            </Field>
            <button type="button" class="btn quiet sm" @click="c.services.splice(j, 1)"><Trash2 :size="15" />Remove service</button>
          </div>
          <button type="button" class="btn sm" @click="addService(c)"><Plus :size="15" />Add service</button>
        </div>
      </div>
    </article>
    <button type="button" class="btn" :disabled="stack.components.length >= 8" @click="addComponent"><Plus :size="16" />Add machine</button>
  </div>
</template>

<style scoped>
.se { display: flex; flex-direction: column; gap: 14px; }
.grid2 { display: grid; grid-template-columns: 1fr 2fr; gap: 16px; }
.grid4 { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.sizes { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; }
.comp { border: 1px solid var(--line); border-radius: var(--radius); }
.ch { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 8px 12px; background: var(--surface-2); border-bottom: 1px solid var(--line); }
.ch svg { color: var(--primary); }
.cb { padding: 12px; display: flex; flex-direction: column; gap: 12px; }
.profiles { border: 0; padding: 0; margin: 0; display: flex; flex-wrap: wrap; gap: 4px 18px; }
.profiles legend { font-weight: 500; margin-bottom: 4px; }
.services { border-top: 1px dashed var(--line); padding-top: 10px; display: flex; flex-direction: column; gap: 10px; }
.services h4 { display: flex; align-items: center; gap: 6px; }
.svc { border-left: 3px solid var(--info-line); padding-left: 12px; display: flex; flex-direction: column; gap: 8px; align-items: flex-start; }
.svc > * { width: 100%; }
.svc > .btn { width: auto; }
@media (max-width: 1100px) { .grid4 { grid-template-columns: 1fr 1fr; } }
@media (max-width: 640px) { .grid2, .grid4 { grid-template-columns: 1fr; } }
</style>
