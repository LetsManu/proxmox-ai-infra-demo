<script setup>
import { computed, ref, watch } from 'vue'
import { ChevronDown, CircleAlert, PenLine, TriangleAlert, Package } from 'lucide-vue-next'
import { api } from '../api.js'
import StatusPill from './ui/StatusPill.vue'
import Skeleton from './ui/Skeleton.vue'

const props = defineProps({
  modelValue: { type: Object, required: true },
  env: { type: String, required: true },
  policy: { type: Object, default: null },
  templates: { type: Array, default: null },
  environments: { type: Array, default: () => [] },
  profiles: { type: Array, default: () => [] },
})
const emit = defineEmits(['apply-spec'])
const f = props.modelValue

const prompt = ref(
  'Create a small Ubuntu test server for a web app with 2 CPUs, 4 GB RAM, 40 GB disk, and Docker installed.',
)
const draftOpen = ref(true)
const drafting = ref(false)
const draft = ref(null)
const draftError = ref(null)

const memoryGb = computed({
  get: () => f.memory_mb / 1024,
  set: (v) => (f.memory_mb = Math.round(Number(v) * 1024)),
})
const packages = computed({
  get: () => (f.cloud_init?.packages || []).join(', '),
  set: (v) => (f.cloud_init.packages = v.split(',').map((s) => s.trim()).filter(Boolean)),
})
const network = computed(() => props.environments.find((e) => e.key === props.env)?.network)
const nameValid = computed(() => /^[a-z][a-z0-9-]{1,40}[a-z0-9]$/.test(f.name))
const selectedTemplate = computed(() => props.templates?.find((t) => t.key === f.template))
const over = computed(() => ({
  cores: props.policy && f.cores > props.policy.max_cores,
  memory: props.policy && f.memory_mb > props.policy.max_memory_mb,
  disk: props.policy && f.disk_gb > props.policy.max_disk_gb,
}))
const OS_LABEL = { 'ubuntu-24-04': 'Ubuntu 24.04', 'debian-12': 'Debian 12', 'windows-2022': 'Windows Server 2022' }
const osFamily = computed(() => selectedTemplate.value?.os_family || 'linux')
const isWindows = computed(() => osFamily.value === 'windows')
const availableProfiles = computed(() => props.profiles.filter((p) => p.os_family === osFamily.value))
const PROFILE_LABEL = computed(() => Object.fromEntries(props.profiles.map((p) => [p.key, p.label])))

// Switching OS family drops profiles that don't apply
watch(osFamily, (fam) => {
  f.profiles = (f.profiles || []).filter((k) => props.profiles.find((p) => p.key === k)?.os_family === fam)
})

function toggleProfile(key, on) {
  const set = new Set(f.profiles || [])
  on ? set.add(key) : set.delete(key)
  f.profiles = props.profiles.map((p) => p.key).filter((k) => set.has(k))
}

async function generate() {
  drafting.value = true
  draft.value = null
  draftError.value = null
  try {
    draft.value = await api.generateSpec(prompt.value)
  } catch (e) {
    draftError.value = e.detail?.errors ? e.detail.errors : [e.message]
  } finally {
    drafting.value = false
  }
}

function useDraft() {
  emit('apply-spec', draft.value.spec)
  draft.value = null
}
</script>

<template>
  <section class="card" aria-labelledby="vm-title">
    <div class="card-head">
      <h2 id="vm-title" class="title">Virtual machine</h2>
      <StatusPill :tone="env === 'prod' ? 'err' : 'info'" :label="env === 'prod' ? 'Production' : 'Test'" />
    </div>

    <div class="assist" :class="{ open: draftOpen }">
      <button type="button" class="assist-toggle" :aria-expanded="draftOpen" aria-controls="assist-body" @click="draftOpen = !draftOpen">
        <PenLine :size="16" />
        <span>Draft from a description</span>
        <span class="dim small">Assistant</span>
        <ChevronDown :size="16" class="chev" />
      </button>
      <div v-show="draftOpen" id="assist-body" class="assist-body">
        <label class="field">
          <span class="sr-only">Describe the VM</span>
          <textarea v-model="prompt" rows="3" placeholder="e.g. Debian box for a Postgres database, 2 cores, 8 GB RAM" />
        </label>
        <div class="assist-row">
          <span class="dim small">Creates a draft only. Values are checked against the Test limits.</span>
          <button type="button" class="btn sm" :disabled="drafting || prompt.length < 5" :aria-busy="drafting" @click="generate">
            <span v-if="drafting" class="spinner" />Draft spec
          </button>
        </div>

        <div v-if="draftError" class="callout err" role="alert">
          <CircleAlert :size="16" />
          <div>
            <strong>Draft rejected</strong>
            <ul class="plain"><li v-for="e in draftError" :key="e">{{ e }}</li></ul>
          </div>
        </div>

        <div v-if="draft" class="draft">
          <dl>
            <div><dt>Name</dt><dd class="mono">{{ draft.spec.name }}</dd></div>
            <div><dt>OS</dt><dd>{{ OS_LABEL[draft.spec.template] }}</dd></div>
            <div><dt>Size</dt><dd class="num">{{ draft.spec.cores }} vCPU · {{ draft.spec.memory_mb / 1024 }} GB · {{ draft.spec.disk_gb }} GB</dd></div>
            <div><dt>Software</dt><dd>{{ (draft.spec.profiles || []).map((k) => PROFILE_LABEL[k] || k).join(', ') || 'Base only' }}</dd></div>
            <div v-if="draft.spec.cloud_init.packages.length"><dt>Packages</dt><dd class="mono">{{ draft.spec.cloud_init.packages.join(', ') }}</dd></div>
          </dl>
          <ul v-if="draft.warnings?.length" class="warnings">
            <li v-for="w in draft.warnings" :key="w"><TriangleAlert :size="14" />{{ w }}</li>
          </ul>
          <div class="assist-row">
            <span class="dim small">{{ draft.source === 'local-fallback' ? 'Local rules' : draft.source.replace('anthropic:', 'Claude · ') }}</span>
            <div class="row-gap">
              <button type="button" class="btn quiet sm" @click="draft = null">Discard</button>
              <button type="button" class="btn sm primary" @click="useDraft">Use this spec</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="card-body form">
      <label class="field span2">
        <span class="label">Name</span>
        <input v-model.trim="f.name" class="mono-input" :aria-invalid="!nameValid" aria-describedby="name-msg" autocomplete="off" spellcheck="false" />
        <span v-if="!nameValid" id="name-msg" class="error"><CircleAlert :size="13" />Lowercase letters, digits and hyphens, 3–42 characters</span>
        <span v-else id="name-msg" class="hint">Also the hostname. Test VMs end in <code>-test</code>.</span>
      </label>

      <label class="field">
        <span class="label">Operating system</span>
        <select v-if="templates" v-model="f.template">
          <optgroup label="Linux">
            <option v-for="t in templates.filter((x) => x.os_family === 'linux')" :key="t.key" :value="t.key">{{ t.label }}{{ t.available === false ? ' (not built yet)' : '' }}</option>
          </optgroup>
          <optgroup label="Windows">
            <option v-for="t in templates.filter((x) => x.os_family === 'windows')" :key="t.key" :value="t.key">{{ t.label }}{{ t.available === false ? ' (not provided yet)' : '' }}</option>
          </optgroup>
        </select>
        <Skeleton v-else h="40px" radius="6px" />
        <span v-if="selectedTemplate?.available === false" class="error"><CircleAlert :size="13" />{{ selectedTemplate.buildable ? 'Not built yet: use Prepare Platform' : 'Not provided yet: see docs/windows-template.md' }}</span>
        <span v-else-if="selectedTemplate" class="hint">Template VMID {{ selectedTemplate.template_id }}</span>
      </label>

      <label class="field">
        <span class="label">Network</span>
        <select v-model="f.network" :disabled="!network">
          <option v-if="network" :value="network.key">{{ network.label }}</option>
        </select>
        <span class="hint">{{ env === 'prod' ? 'Production VLAN' : 'Isolated test VLAN' }}</span>
      </label>

      <div class="span2 sizes">
        <label class="field">
          <span class="label">CPU <span class="hint-inline">max {{ policy?.max_cores }}</span></span>
          <span class="unit"><input v-model.number="f.cores" type="number" min="1" :max="policy?.max_cores" :aria-invalid="over.cores" inputmode="numeric" /><span>vCPU</span></span>
        </label>
        <label class="field">
          <span class="label">Memory <span class="hint-inline">max {{ policy ? policy.max_memory_mb / 1024 : '' }}</span></span>
          <span class="unit"><input v-model.number="memoryGb" type="number" min="1" :max="policy ? policy.max_memory_mb / 1024 : 64" :aria-invalid="over.memory" inputmode="numeric" /><span>GB</span></span>
        </label>
        <label class="field">
          <span class="label">Disk <span class="hint-inline">max {{ policy?.max_disk_gb }}</span></span>
          <span class="unit"><input v-model.number="f.disk_gb" type="number" min="8" :max="policy?.max_disk_gb" :aria-invalid="over.disk" inputmode="numeric" /><span>GB</span></span>
        </label>
      </div>
      <p v-if="over.cores || over.memory || over.disk" class="span2 field-error" role="alert">
        <CircleAlert :size="13" />Above the {{ policy.label }} limits. The plan will be refused.
      </p>

      <fieldset class="span2 software">
        <legend><Package :size="15" />Software <span class="dim">installed by Ansible after deploy</span></legend>
        <label v-for="p in availableProfiles" :key="p.key" class="sw">
          <input type="checkbox" :checked="(f.profiles || []).includes(p.key)" @change="toggleProfile(p.key, $event.target.checked)" />
          <span><span class="sw-name">{{ p.label }}</span><span class="sw-desc">{{ p.description }}</span></span>
        </label>
        <p class="dim small">Base configuration (updates, guest agent, {{ isWindows ? 'time zone, firewall' : 'SSH hardening' }}) is always applied.</p>
      </fieldset>

      <details class="disclosure span2">
        <summary>Optional settings <ChevronDown :size="15" /></summary>
        <div class="optional">
          <label v-if="!isWindows" class="field">
            <span class="label">Extra packages</span>
            <input v-model="packages" class="mono-input" placeholder="qemu-guest-agent, docker.io" />
            <span class="hint">Comma separated, installed by cloud-init</span>
          </label>
          <label class="field">
            <span class="label">Description</span>
            <input v-model="f.description" maxlength="500" placeholder="What is this VM for?" />
          </label>
          <label v-if="!isWindows" class="field">
            <span class="label">SSH public key</span>
            <input v-model.trim="f.ssh_public_key" class="mono-input" placeholder="ssh-ed25519 AAAA… you@laptop" autocomplete="off" spellcheck="false" />
            <span class="hint">Empty uses the default key from the server configuration</span>
          </label>
        </div>
      </details>
    </div>

    <div v-if="$slots.default" class="card-foot">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.assist { border-bottom: 1px solid var(--line); }
.assist-toggle {
  width: 100%; display: flex; align-items: center; gap: .55rem; padding: .75rem 1.1rem; min-height: 48px;
  background: transparent; border: 0; color: var(--fg); font: inherit; font-size: .9rem; font-weight: 600; cursor: pointer; text-align: left;
}
.assist-toggle:hover { background: rgba(255, 255, 255, .02); }
.assist-toggle > svg:first-child { color: var(--acc); }
.assist-toggle .chev { margin-left: auto; color: var(--dim); transition: transform var(--t-fast) var(--ease); }
.assist.open .chev { transform: rotate(180deg); }
.assist-body { padding: 0 1.1rem 1rem; display: flex; flex-direction: column; gap: .65rem; }
.assist-row { display: flex; align-items: center; justify-content: space-between; gap: .75rem; }
.row-gap { display: flex; gap: .4rem; }
.draft { border: 1px solid var(--line); border-radius: var(--radius); background: var(--surface-2); padding: .75rem .85rem; display: flex; flex-direction: column; gap: .6rem; }
dl { margin: 0; display: grid; gap: .35rem; }
dl > div { display: grid; grid-template-columns: 76px 1fr; gap: .5rem; font-size: .86rem; }
dt { color: var(--dim); }
dd { margin: 0; overflow-wrap: anywhere; }
.warnings { list-style: none; display: flex; flex-direction: column; gap: .3rem; font-size: .82rem; color: #ffe2b0; }
.warnings li { display: flex; gap: .4rem; align-items: flex-start; }
.warnings svg { color: var(--warn); margin-top: .2rem; }
.plain { list-style: none; margin-top: .2rem; }

.form { display: grid; grid-template-columns: 1fr 1fr; gap: .95rem .9rem; }
.span2 { grid-column: span 2; }
.sizes { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .9rem; }
.mono-input { font-family: var(--mono); font-size: .86rem; }
.field-error { font-size: .8rem; color: var(--err); display: flex; gap: .35rem; align-items: center; margin-top: -.4rem; }
.optional { display: flex; flex-direction: column; gap: .9rem; padding-top: .6rem; }
.software { border: 1px solid var(--line); border-radius: var(--radius); padding: .5rem .75rem .65rem; margin: 0; display: flex; flex-direction: column; gap: .15rem; }
.software legend { display: flex; align-items: center; gap: .4rem; padding: 0 .3rem; font-size: 13px; }
.software legend svg { color: var(--title); }
.software legend .dim { font-size: 12px; }
.sw { display: flex; gap: .55rem; align-items: flex-start; padding: .3rem 0; cursor: pointer; }
.sw input { margin-top: .15rem; }
.sw > span { display: flex; flex-direction: column; }
.sw-name { color: var(--fg); }
.sw-desc { color: var(--dim); font-size: 12px; }
.card-foot { background: var(--surface-2); border-radius: 0 0 var(--radius-lg) var(--radius-lg); }
@media (max-width: 520px) {
  .form { grid-template-columns: 1fr; }
  .span2 { grid-column: span 1; }
  .sizes { grid-template-columns: 1fr 1fr; }
}
</style>
