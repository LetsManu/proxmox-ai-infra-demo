<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { api, pollJob } from './api.js'
import VmCreateForm from './components/VmCreateForm.vue'
import PlanPanel from './components/PlanPanel.vue'
import AiSummaryPanel from './components/AiSummaryPanel.vue'
import ValidationPanel from './components/ValidationPanel.vue'
import PromotionPanel from './components/PromotionPanel.vue'
import JobLogPanel from './components/JobLogPanel.vue'
import HistoryTable from './components/HistoryTable.vue'

const env = ref('test')
const health = ref(null)
const pxStatus = ref(null)
const templates = ref([])
const environments = ref([])
const vms = ref([])
const history = ref([])

const form = reactive({
  name: 'demo-web-test',
  template: 'ubuntu-24-04',
  cores: 2,
  memory_mb: 4096,
  disk_gb: 32,
  network: 'test',
  description: '',
  ssh_public_key: '',
  cloud_init: { packages: ['qemu-guest-agent'], commands: [] },
})

const planJob = ref(null)
const plannedSpecJson = ref('')
const planSummary = ref(null)
const summaryLoading = ref(false)
const activeJob = ref(null)
const validationJob = ref(null)
const approvalJob = ref(null)
const approvalSummary = ref(null)
const troubleshootResult = ref(null)
const troubleshootLoading = ref(false)
const busy = ref('')
const error = ref('')
const notice = ref('')

const policy = computed(() => environments.value.find((e) => e.key === env.value))
const spec = computed(() => ({ ...JSON.parse(JSON.stringify(form)), environment: env.value }))
const planMatchesForm = computed(() => plannedSpecJson.value === JSON.stringify(spec.value))
const currentVm = computed(() => vms.value.find((v) => v.name === form.name && v.environment === env.value))
const testVm = computed(() => vms.value.find((v) => v.name === form.name && v.environment === 'test'))
const isMock = computed(() => health.value && !health.value.settings.live_mode)

const can = computed(() => ({
  plan: !busy.value,
  deploy:
    !busy.value &&
    env.value === 'test' &&
    planJob.value?.status === 'success' &&
    planJob.value?.environment === 'test' &&
    planMatchesForm.value &&
    !planJob.value?.result?.applied,
  validate: !busy.value && !!currentVm.value,
  promote: !busy.value && testVm.value?.last_validation === 'PASS',
  recreate: !busy.value && !!currentVm.value,
}))

const deployHint = computed(() => {
  if (env.value !== 'test') return 'Production is only reachable through promotion.'
  if (!planJob.value) return 'Generate a plan first.'
  if (planJob.value.status !== 'success') return 'Plan must succeed first.'
  if (!planMatchesForm.value) return 'Form changed since the plan. Generate a new plan.'
  if (planJob.value.result?.applied) return 'Plan already applied.'
  return ''
})

watch(env, (e) => {
  form.network = e
  const p = policy.value
  if (p) {
    form.cores = Math.min(form.cores, p.max_cores)
    form.memory_mb = Math.min(form.memory_mb, p.max_memory_mb)
    form.disk_gb = Math.min(form.disk_gb, p.max_disk_gb)
  }
})

async function refresh() {
  try {
    ;[vms.value, history.value] = await Promise.all([api.vms(), api.history()])
  } catch (e) {
    error.value = e.message
  }
}

async function loadInventory() {
  try {
    ;[health.value, templates.value, environments.value] = await Promise.all([
      api.health(),
      api.templates(),
      api.environments(),
    ])
    pxStatus.value = await api.proxmoxStatus()
  } catch (e) {
    error.value = `Backend unreachable: ${e.message}`
  }
  await refresh()
}

async function track(kind, start) {
  error.value = ''
  notice.value = ''
  busy.value = kind
  try {
    const { job_id } = await start()
    const job = await pollJob(job_id, (j) => (activeJob.value = j))
    return job
  } catch (e) {
    error.value = e.message
    return null
  } finally {
    busy.value = ''
    refresh()
  }
}

async function summarize(job, target) {
  const text = job?.result?.plan?.text
  if (!text) return
  summaryLoading.value = true
  try {
    target.value = await api.summarizePlan(text, job.environment)
  } catch (e) {
    error.value = `AI summary failed: ${e.message}`
  } finally {
    summaryLoading.value = false
  }
}

async function generatePlan() {
  const snapshot = JSON.stringify(spec.value)
  planSummary.value = null
  const job = await track('plan', () => api.plan(spec.value))
  if (!job) return
  planJob.value = job
  plannedSpecJson.value = snapshot
  if (job.status === 'success') await summarize(job, planSummary)
}

async function deployTest() {
  const job = await track('deploy', () => api.deployTest(spec.value, planJob.value.id))
  if (job?.status === 'success') {
    planJob.value = { ...planJob.value, result: { ...planJob.value.result, applied: true } }
    notice.value = `Deployed ${form.name} to TEST. Next: Validate.`
  }
}

async function validate(opts) {
  troubleshootResult.value = null
  const job = await track('validate', () =>
    api.validate({ name: form.name, environment: env.value, ...opts }),
  )
  if (job) validationJob.value = job
}

async function troubleshoot() {
  troubleshootLoading.value = true
  try {
    troubleshootResult.value = await api.troubleshoot({
      vm_name: form.name,
      job_logs: validationJob.value?.logs || activeJob.value?.logs || '',
      validation_output: validationJob.value?.result?.validation,
      proxmox_status: currentVm.value,
    })
  } catch (e) {
    error.value = e.message
  } finally {
    troubleshootLoading.value = false
  }
}

async function requestPromotion() {
  approvalSummary.value = null
  const job = await track('promote', () => api.promote({ name: testVm.value.name, stage: 'request' }))
  if (job) {
    approvalJob.value = job
    if (job.status === 'awaiting_approval') await summarize(job, approvalSummary)
  }
}

async function decide({ stage, acknowledge, confirmation }) {
  const job = approvalJob.value
  const body = { stage, approval_job_id: job.id, acknowledge, confirmation }
  const call =
    job.action === 'recreate'
      ? () => api.recreate({ ...body, name: job.vm_name, environment: 'prod' })
      : () => api.promote({ ...body, name: job.params.source_vm })
  if (stage === 'reject') {
    try {
      await call()
      approvalJob.value = { ...job, status: 'failed', result: { ...job.result, decision: 'rejected' } }
      notice.value = 'Rejected. Nothing was changed in production.'
    } catch (e) {
      error.value = e.message
    }
    refresh()
    return
  }
  const result = await track('approve', call)
  if (result) {
    approvalJob.value = { ...job, status: 'success', result: { ...job.result, decision: 'approved' } }
    if (result.status === 'success') notice.value = 'Production change applied.'
  }
}

async function recreate() {
  const where = env.value === 'prod' ? 'PRODUCTION (requires approval)' : 'TEST'
  if (!confirm(`Recreate ${form.name} in ${where}? The VM is destroyed and cloned again from its template.`)) return
  const job = await track('recreate', () => api.recreate({ name: form.name, environment: env.value }))
  if (job?.status === 'awaiting_approval') {
    approvalJob.value = job
    approvalSummary.value = null
    await summarize(job, approvalSummary)
  } else if (job?.status === 'success') {
    planJob.value = job
    notice.value = 'TEST VM recreated. Validation was reset: run Validate again.'
    await summarize(job, planSummary)
  }
}

function applyGeneratedSpec(s) {
  env.value = 'test'
  Object.assign(form, {
    name: s.name,
    template: s.template,
    cores: s.cores,
    memory_mb: s.memory_mb,
    disk_gb: s.disk_gb,
    network: s.network,
    description: s.description || '',
    cloud_init: s.cloud_init,
  })
  notice.value = 'AI draft loaded into the form. Review it, then Generate Plan.'
}

function selectVm(vm) {
  env.value = vm.environment
  Object.assign(form, {
    name: vm.name,
    template: vm.spec.template,
    cores: vm.spec.cores,
    memory_mb: vm.spec.memory_mb,
    disk_gb: vm.spec.disk_gb,
    network: vm.spec.network,
    description: vm.spec.description || '',
    ssh_public_key: vm.spec.ssh_public_key || '',
    cloud_init: vm.spec.cloud_init || { packages: [], commands: [] },
  })
}

let timer
onMounted(() => {
  loadInventory()
  timer = setInterval(refresh, 10000)
})
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <header class="topbar">
    <div class="brand">
      <div class="logo">PX</div>
      <div>
        <h1>Proxmox AI Infra Console</h1>
        <p class="muted">Template → Plan → Test → Validate → Approve → Production</p>
      </div>
    </div>
    <div class="status-pills">
      <span v-if="health" class="pill" :class="health.settings.live_mode ? 'ok' : 'warn'">
        {{ health.settings.live_mode ? 'LIVE' : 'MOCK MODE' }}
      </span>
      <span v-if="pxStatus" class="pill" :class="pxStatus.connected ? 'ok' : 'bad'" :title="pxStatus.error || ''">
        Proxmox {{ pxStatus.connected ? `${pxStatus.version?.version} · ${pxStatus.nodes?.[0]?.node}` : 'unreachable' }}
      </span>
      <span v-if="health" class="pill neutral">
        IaC: {{ health.settings.iac_binary === 'tofu' ? 'OpenTofu' : 'Terraform' }}
      </span>
      <span v-if="health" class="pill neutral">
        AI: {{ health.settings.ai_model || 'local fallback' }}
      </span>
      <span v-if="health" class="pill neutral">👤 {{ health.settings.user }}</span>
    </div>
  </header>

  <main class="layout">
    <section class="env-bar card">
      <div class="segmented" role="tablist" aria-label="Environment">
        <button :class="{ active: env === 'test' }" @click="env = 'test'">Test</button>
        <button :class="{ active: env === 'prod', prod: true }" @click="env = 'prod'">Production</button>
      </div>
      <p v-if="policy" class="muted env-desc">
        <strong>{{ policy.label }}:</strong> {{ policy.description }}
        VM IDs {{ policy.vmid_min }}–{{ policy.vmid_max }} · {{ policy.network.label }} ·
        {{ policy.full_clone ? 'full clone' : 'linked clone' }} · max {{ policy.max_cores }} vCPU /
        {{ policy.max_memory_mb / 1024 }} GB / {{ policy.max_disk_gb }} GB
      </p>
    </section>

    <div v-if="error" class="banner error" @click="error = ''">⚠ {{ error }}</div>
    <div v-if="notice" class="banner info" @click="notice = ''">✓ {{ notice }}</div>

    <div class="grid two">
      <VmCreateForm
        v-model="form"
        :env="env"
        :policy="policy"
        :templates="templates"
        :environments="environments"
        @apply-spec="applyGeneratedSpec"
      >
        <div class="actions">
          <button class="btn primary" :disabled="!can.plan" @click="generatePlan">
            <span v-if="busy === 'plan'" class="spinner" />Generate Plan
          </button>
          <button class="btn success" :disabled="!can.deploy" :title="deployHint" @click="deployTest">
            <span v-if="busy === 'deploy'" class="spinner" />Deploy to Test
          </button>
          <button class="btn" :disabled="!can.validate" @click="validate({})">
            <span v-if="busy === 'validate'" class="spinner" />Validate
          </button>
          <button
            class="btn warn"
            :disabled="!can.promote"
            :title="can.promote ? '' : 'Requires a PASSING validation of the TEST VM'"
            @click="requestPromotion"
          >
            <span v-if="busy === 'promote'" class="spinner" />Request Production Promotion
          </button>
          <button class="btn danger-outline" :disabled="!can.recreate" @click="recreate">
            <span v-if="busy === 'recreate'" class="spinner" />Recreate VM
          </button>
        </div>
        <p v-if="deployHint && env === 'test' && planJob" class="hint">{{ deployHint }}</p>
      </VmCreateForm>

      <div class="stack">
        <PlanPanel :job="planJob" :stale="!!planJob && !planMatchesForm" />
        <AiSummaryPanel
          :summary="planSummary"
          :loading="summaryLoading && !approvalJob"
          :troubleshoot="troubleshootResult"
          :troubleshoot-loading="troubleshootLoading"
        />
      </div>
    </div>

    <div class="grid two">
      <ValidationPanel
        :job="validationJob"
        :vm="currentVm"
        :env="env"
        :mock="isMock"
        :busy="!!busy"
        :troubleshoot-loading="troubleshootLoading"
        @validate="validate"
        @troubleshoot="troubleshoot"
      />
      <PromotionPanel
        :job="approvalJob"
        :summary="approvalSummary"
        :summary-loading="summaryLoading"
        :test-vm="testVm"
        :busy="!!busy"
        @decide="decide"
      />
    </div>

    <JobLogPanel :job="activeJob" />
    <HistoryTable :history="history" :vms="vms" @select="selectVm" />
  </main>

  <footer class="footer muted">
    The browser never receives Proxmox credentials. Production changes always require human approval.
  </footer>
</template>
