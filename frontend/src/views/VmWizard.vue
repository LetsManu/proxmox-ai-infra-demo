<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { Sparkles, ArrowLeft, ArrowRight, FileCode, Play, TriangleAlert } from 'lucide-vue-next'
import PageHeader from '../layout/PageHeader.vue'
import Card from '../components/ui/Card.vue'
import Field from '../components/ui/Field.vue'
import Expandable from '../components/ui/Expandable.vue'
import ProgressSteps from '../components/ui/ProgressSteps.vue'
import StatusCard from '../components/ui/StatusCard.vue'
import ErrorPanel from '../components/ui/ErrorPanel.vue'
import SoftwarePicker from '../components/SoftwarePicker.vue'
import PlanReview from '../components/PlanReview.vue'
import { api } from '../api.js'
import { runJob, store } from '../store.js'
import { go, links } from '../router.js'
import { toast } from '../components/ui/toast.js'
import { openJob } from '../components/ui/drawer.js'
import { OS_LABEL, gb } from '../components/ui/format.js'

// Kept at module level: leaving the page and coming back keeps the draft.
const draft = (window.__vmDraft ||= reactive({
  step: 0,
  prompt: '',
  analysis: null,
  warnings: [],
  source: '',
  form: { name: 'web-test', template: 'ubuntu-24-04', cores: 2, memory_mb: 4096, disk_gb: 32, description: '', ssh_public_key: '', profiles: [], packages: [] },
}))
const f = draft.form
const STEPS = ['Describe', 'Basics', 'Software', 'Review and deploy']

const policy = computed(() => store.environments.find((e) => e.key === 'test'))
const vmTemplates = computed(() => (store.templates || []).filter((t) => t.kind === 'vm'))
const template = computed(() => vmTemplates.value.find((t) => t.key === f.template))
const osFamily = computed(() => template.value?.os_family || 'linux')
const memoryGb = computed({ get: () => f.memory_mb / 1024, set: (v) => (f.memory_mb = Math.round(Number(v) * 1024)) })

const errors = computed(() => {
  const e = {}
  const p = policy.value
  if (!/^[a-z][a-z0-9-]{1,40}[a-z0-9]$/.test(f.name)) e.name = 'Use 3–42 lowercase letters, digits or hyphens, starting with a letter.'
  else if (!f.name.endsWith('-test')) e.name = 'Test machines end in -test, for example web-test. Production gets the name without it.'
  else if (!/^[a-z][a-z0-9-]{1,40}[a-z0-9]$/.test(f.name.replace(/-test$/, ''))) e.name = `The production name (${f.name.replace(/-test$/, '')}) needs at least 3 characters before -test.`
  else if (osFamily.value === 'windows' && f.name.length > 15) e.name = 'Windows computer names are limited to 15 characters.'
  if (p && f.cores > p.max_cores) e.cores = `Test allows at most ${p.max_cores} vCPU.`
  if (p && f.memory_mb > p.max_memory_mb) e.memory = `Test allows at most ${p.max_memory_mb / 1024} GB.`
  if (p && f.disk_gb > p.max_disk_gb) e.disk = `Test allows at most ${p.max_disk_gb} GB.`
  if (f.cores < 1) e.cores = 'At least 1 vCPU.'
  if (f.disk_gb < 8) e.disk = 'At least 8 GB.'
  if (template.value?.available === false) e.template = template.value.buildable ? 'This template is not built yet. Prepare the platform first.' : 'This template is not provided yet (docs/windows-template.md).'
  return e
})
const basicsOk = computed(() => !Object.keys(errors.value).length)

watch(osFamily, (fam, old) => {
  if (old && fam !== old) {
    f.profiles = f.profiles.filter((k) => store.profiles.find((p) => p.key === k)?.os_family === fam)
    f.packages = []
    draft.analysis = null
  }
})

const drafting = ref(false)
const draftError = ref(null)
async function assist() {
  drafting.value = true
  draftError.value = null
  try {
    const out = await api.generateSpec(draft.prompt)
    const s = out.spec
    Object.assign(f, { name: s.name, template: s.template, cores: s.cores, memory_mb: s.memory_mb, disk_gb: s.disk_gb,
      description: s.description || '', profiles: s.profiles || [], packages: s.packages || [] })
    Object.assign(draft, { analysis: out.software || null, warnings: out.warnings || [], source: out.source, step: 1 })
    toast.success('Check the values, then continue.', { title: 'Draft ready' })
  } catch (e) {
    draftError.value = e.detail?.errors || [e.message]
  } finally {
    drafting.value = false
  }
}

const spec = computed(() => ({
  ...JSON.parse(JSON.stringify(f)),
  environment: 'test',
  network: 'test',
  cloud_init: { packages: osFamily.value === 'windows' ? [] : ['qemu-guest-agent'], commands: [] },
}))
const planJob = ref(null)
const plannedFor = ref('')
const planning = ref(false)
const deployJob = ref(null)
const planCurrent = computed(() => planJob.value?.status === 'success' && plannedFor.value === JSON.stringify(spec.value))

async function makePlan() {
  planning.value = true
  const snapshot = JSON.stringify(spec.value)
  const job = await runJob('Plan', () => api.plan(spec.value), { quiet: true })
  planning.value = false
  if (job) {
    planJob.value = job
    plannedFor.value = snapshot
  }
}
async function deploy() {
  const job = await runJob(`Deploy ${f.name}`, () => api.deployTest(spec.value, planJob.value.id), {
    onUpdate: (j) => (deployJob.value = j), quiet: true,
  })
  if (!job) return
  deployJob.value = job
  if (job.status === 'success') {
    toast.success(`${f.name} is running in Test. Validate it next.`, { title: 'Deployed' })
    const name = f.name
    window.__vmDraft = null
    go(links.vm('test', name))
  }
}
const stepStates = computed(() => STEPS.map((label, i) => ({ key: label, label, state: i < draft.step ? 'done' : i === draft.step ? 'current' : 'todo' })))
const canNext = computed(() => [true, basicsOk.value, true][draft.step])
</script>

<template>
  <PageHeader title="Create VM" subtitle="New machines always start in Test. Production is reached by promotion." env="test"
    :crumbs="[{ label: 'Dashboard', href: '#/dashboard' }]" />

  <Card>
    <ProgressSteps :steps="stepStates" label="Create VM steps" />
  </Card>

  <!-- 1. Describe -->
  <Card v-if="draft.step === 0" title="Describe what you need" :icon="Sparkles">
    <div class="stack-v">
      <Field id="vm-prompt" label="What should this machine do?" hint="Plain language is fine. The assistant suggests size, operating system and software; you review everything before anything is created.">
        <textarea id="vm-prompt" v-model="draft.prompt" rows="4" aria-describedby="vm-prompt-msg"
          placeholder="Example: A small Ubuntu server for our WordPress marketing site, with monitoring." />
      </Field>
      <ErrorPanel v-if="draftError" what="The draft could not be used" :error="draftError.join('\n')" />
    </div>
    <template #footer>
      <button type="button" class="btn" @click="draft.step = 1">Skip, fill in myself</button>
      <span class="spacer" />
      <button type="button" class="btn primary" :disabled="drafting || draft.prompt.trim().length < 5" :aria-busy="drafting" @click="assist">
        <span v-if="drafting" class="spinner" /><Sparkles v-else :size="16" />Draft with assistant
      </button>
    </template>
  </Card>

  <!-- 2. Basics -->
  <Card v-else-if="draft.step === 1" title="Basics">
    <div class="stack-v">
      <div v-if="draft.warnings.length" class="callout warn" role="status">
        <TriangleAlert :size="18" />
        <ul class="plain"><li v-for="w in draft.warnings" :key="w">{{ w }}</li></ul>
      </div>
      <div class="grid2">
        <Field id="vm-name" label="Name" required :error="errors.name" hint="Also the hostname. Example: web-test.">
          <input id="vm-name" v-model.trim="f.name" class="mono-input" :aria-invalid="!!errors.name" aria-describedby="vm-name-msg" autocomplete="off" spellcheck="false" />
        </Field>
        <Field id="vm-os" label="Operating system" required :error="errors.template" :hint="template ? `Template ${template.template_id}` : ''">
          <select id="vm-os" v-model="f.template" :aria-invalid="!!errors.template" aria-describedby="vm-os-msg">
            <option v-for="t in vmTemplates" :key="t.key" :value="t.key">{{ t.label }}{{ t.available === false ? ' (not available yet)' : '' }}</option>
          </select>
        </Field>
      </div>
      <div class="grid3">
        <Field id="vm-cpu" label="CPU" :aside="`max ${policy?.max_cores ?? ''}`" :error="errors.cores">
          <span class="unit"><input id="vm-cpu" v-model.number="f.cores" type="number" min="1" :max="policy?.max_cores" inputmode="numeric" :aria-invalid="!!errors.cores" aria-describedby="vm-cpu-msg" /><span>vCPU</span></span>
        </Field>
        <Field id="vm-mem" label="Memory" :aside="`max ${policy ? policy.max_memory_mb / 1024 : ''} GB`" :error="errors.memory">
          <span class="unit"><input id="vm-mem" v-model.number="memoryGb" type="number" min="1" step="1" inputmode="numeric" :aria-invalid="!!errors.memory" aria-describedby="vm-mem-msg" /><span>GB</span></span>
        </Field>
        <Field id="vm-disk" label="Disk" :aside="`max ${policy?.max_disk_gb ?? ''} GB`" :error="errors.disk">
          <span class="unit"><input id="vm-disk" v-model.number="f.disk_gb" type="number" min="8" inputmode="numeric" :aria-invalid="!!errors.disk" aria-describedby="vm-disk-msg" /><span>GB</span></span>
        </Field>
      </div>
      <Expandable summary="Advanced options">
        <div class="stack-v">
          <Field id="vm-desc" label="Description" hint="Shown in Proxmox. Optional.">
            <input id="vm-desc" v-model="f.description" maxlength="500" aria-describedby="vm-desc-msg" />
          </Field>
          <Field v-if="osFamily !== 'windows'" id="vm-key" label="SSH public key" hint="Leave empty to use the default key from the server configuration. Never paste a private key.">
            <input id="vm-key" v-model.trim="f.ssh_public_key" class="mono-input" placeholder="ssh-ed25519 AAAA… you@laptop" autocomplete="off" spellcheck="false" aria-describedby="vm-key-msg" />
          </Field>
          <p class="dim small">Network: isolated Test VLAN. Linked clone from the template.</p>
        </div>
      </Expandable>
    </div>
    <template #footer>
      <button type="button" class="btn" @click="draft.step = 0"><ArrowLeft :size="16" />Back</button>
      <span class="spacer" />
      <button type="button" class="btn primary" :disabled="!canNext" @click="draft.step = 2">Continue<ArrowRight :size="16" /></button>
    </template>
  </Card>

  <!-- 3. Software -->
  <Card v-else-if="draft.step === 2" title="Software" subtitle="Installed by Ansible right after the machine boots">
    <SoftwarePicker v-model="draft.form" :os-family="osFamily" :analysis="draft.analysis" id-prefix="vm-sw" />
    <template #footer>
      <button type="button" class="btn" @click="draft.step = 1"><ArrowLeft :size="16" />Back</button>
      <span class="spacer" />
      <button type="button" class="btn primary" @click="draft.step = 3">Continue<ArrowRight :size="16" /></button>
    </template>
  </Card>

  <!-- 4. Review and deploy -->
  <template v-else>
    <Card title="Review">
      <dl class="summary">
        <div><dt>Name</dt><dd class="mono">{{ f.name }}</dd></div>
        <div><dt>Operating system</dt><dd>{{ OS_LABEL[f.template] || f.template }}</dd></div>
        <div><dt>Size</dt><dd class="num">{{ f.cores }} vCPU · {{ gb(f.memory_mb) }} memory · {{ f.disk_gb }} GB disk</dd></div>
        <div><dt>Software</dt><dd>{{ f.profiles.map((k) => store.profiles.find((p) => p.key === k)?.label || k).join(', ') || 'Base system only' }}</dd></div>
        <div v-if="f.packages.length"><dt>Packages</dt><dd class="mono">{{ f.packages.join(', ') }}</dd></div>
        <div><dt>Environment</dt><dd>Test (isolated network, disposable)</dd></div>
      </dl>
      <template #footer>
        <button type="button" class="btn" :disabled="!!deployJob && deployJob.status === 'running'" @click="draft.step = 2"><ArrowLeft :size="16" />Back</button>
        <span class="spacer" />
        <button v-if="!planCurrent" type="button" class="btn primary" :disabled="planning || !basicsOk" :aria-busy="planning" @click="makePlan">
          <span v-if="planning" class="spinner" /><FileCode v-else :size="16" />Create plan
        </button>
        <button v-else type="button" class="btn primary" :disabled="!!deployJob && ['queued', 'running'].includes(deployJob.status)" @click="deploy">
          <Play :size="16" />Deploy to Test
        </button>
      </template>
    </Card>

    <StatusCard v-if="planning" state="running" title="Creating the plan" text="OpenTofu compares what you want with what exists. Nothing changes yet." />
    <ErrorPanel v-else-if="planJob?.status === 'failed'" what="The plan could not be created" :error="planJob.error" :job-id="planJob.id" retry @retry="makePlan" @log="openJob(planJob.id, 'Plan')" />
    <Card v-else-if="planCurrent" title="Plan" :icon="FileCode" subtitle="Review what will happen before you deploy">
      <PlanReview :job="planJob" />
    </Card>
    <p v-else-if="planJob" class="dim small">The settings changed after the last plan. Create a new plan.</p>

    <StatusCard v-if="deployJob && deployJob.status !== 'failed'" :state="deployJob.status" :title="`Deploying ${f.name}`"
      text="Creating the machine, waiting for it to boot, then installing the software." details @details="openJob(deployJob.id, `Deploy ${f.name}`)" />
    <ErrorPanel v-else-if="deployJob?.status === 'failed'" what="The deployment failed" :error="deployJob.error" :job-id="deployJob.id" @log="openJob(deployJob.id, 'Deploy')" />
  </template>
</template>

<style scoped>
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.grid3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; max-width: 640px; }
.plain { list-style: none; display: flex; flex-direction: column; gap: 2px; }
.summary { margin: 0; display: grid; gap: 8px; }
.summary > div { display: grid; grid-template-columns: 160px 1fr; gap: 12px; }
dt { color: var(--dim); }
dd { margin: 0; overflow-wrap: anywhere; }
@media (max-width: 720px) {
  .grid2, .grid3 { grid-template-columns: 1fr; }
  .summary > div { grid-template-columns: 1fr; gap: 0; }
}
</style>
