<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { Layers, FlaskConical, Radio, Boxes, Bot, ListTodo, User, Menu, Play, ShieldCheck, Activity, FileCode, RotateCcw } from 'lucide-vue-next'
import { api, pollJob } from './api.js'
import VmCreateForm from './components/VmCreateForm.vue'
import PlanPanel from './components/PlanPanel.vue'
import AiSummaryPanel from './components/AiSummaryPanel.vue'
import ValidationPanel from './components/ValidationPanel.vue'
import PromotionPanel from './components/PromotionPanel.vue'
import JobLogPanel from './components/JobLogPanel.vue'
import HistoryTable from './components/HistoryTable.vue'
import WorkflowSteps from './components/WorkflowSteps.vue'
import ResourceTree from './components/ResourceTree.vue'
import Skeleton from './components/ui/Skeleton.vue'
import ToastHost from './components/ui/ToastHost.vue'
import ConfirmDialog from './components/ui/ConfirmDialog.vue'
import { toast } from './components/ui/toast.js'
import { confirm } from './components/ui/confirm.js'

const env = ref('test')
const health = ref(null)
const pxStatus = ref(null)
const templates = ref(null)
const environments = ref([])
const vms = ref(null)
const history = ref(null)
const historyError = ref('')

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
const validateOpts = reactive({ useHealth: true, port: 22, simulateFailure: false })
const approvalJob = ref(null)
const approvalSummary = ref(null)
const approvalSummaryLoading = ref(false)
const troubleshootResult = ref(null)
const troubleshootLoading = ref(false)
const busy = ref('')
const treeOpen = ref(false)
const tasksEl = ref(null)

const policy = computed(() => environments.value.find((e) => e.key === env.value))
const spec = computed(() => ({ ...JSON.parse(JSON.stringify(form)), environment: env.value }))
const planMatchesForm = computed(() => plannedSpecJson.value === JSON.stringify(spec.value))
const vmList = computed(() => vms.value || [])
const currentVm = computed(() => vmList.value.find((v) => v.name === form.name && v.environment === env.value))
const testName = computed(() => (env.value === 'test' ? form.name : `${form.name}-test`))
const prodName = computed(() => form.name.replace(/-test$/, ''))
const testVm = computed(() => vmList.value.find((v) => v.name === testName.value && v.environment === 'test'))
const prodVm = computed(() => vmList.value.find((v) => v.name === prodName.value && v.environment === 'prod'))
const isMock = computed(() => health.value && !health.value.settings.live_mode)
const awaiting = computed(() => approvalJob.value?.status === 'awaiting_approval')

const can = computed(() => ({
  plan: !busy.value,
  deploy:
    !busy.value &&
    env.value === 'test' &&
    planJob.value?.status === 'success' &&
    planJob.value?.environment === 'test' &&
    planJob.value?.action === 'plan' &&
    planMatchesForm.value &&
    !planJob.value?.result?.applied,
  validate: !busy.value && !!currentVm.value,
  promote: !busy.value && testVm.value?.last_validation === 'PASS' && !awaiting.value,
  recreate: !busy.value && !!currentVm.value,
}))

const hints = computed(() => ({
  deploy:
    env.value !== 'test'
      ? 'Production is only reachable through promotion'
      : !planJob.value || planJob.value.action !== 'plan'
        ? 'Generate a plan first'
        : !planMatchesForm.value
          ? 'The form changed since the plan. Generate a new plan.'
          : planJob.value.result?.applied
            ? 'This plan was already applied'
            : '',
  validate: currentVm.value ? '' : `Deploy ${form.name} first`,
  promote: awaiting.value
    ? 'A promotion is waiting for approval'
    : testVm.value?.last_validation === 'PASS'
      ? ''
      : 'Needs a passing validation of the TEST VM',
  recreate: currentVm.value ? '' : 'Nothing deployed under this name',
}))

function planDetail(c) {
  if (!c) return ''
  const parts = [c.create && `${c.create} add`, c.update && `${c.update} change`, c.destroy && `${c.destroy} destroy`].filter(Boolean)
  return parts.join(' · ') || 'No changes'
}

// Workflow progress for the VM lineage <name>-test -> <name>
const steps = computed(() => {
  const planned = planJob.value?.status === 'success' && planJob.value.environment === 'test'
  const deployed = !!testVm.value
  const validation = testVm.value?.last_validation
  const s = [
    { key: 'define', label: 'Define', detail: testName.value, done: true },
    { key: 'plan', label: 'Plan', detail: planned ? planDetail(planJob.value.result?.plan?.counts) : '', done: planned || deployed },
    { key: 'deploy', label: 'Deploy to Test', detail: deployed ? `VMID ${testVm.value.vmid}` : '', done: deployed },
    {
      key: 'validate', label: 'Validate',
      detail: validation === 'PASS' ? 'Passed' : validation === 'FAIL' ? 'Failed' : '',
      done: validation === 'PASS', error: validation === 'FAIL',
    },
    { key: 'approve', label: 'Approval', detail: awaiting.value ? 'Waiting for you' : prodVm.value ? 'Approved' : '', done: !!prodVm.value },
    { key: 'prod', label: 'Production', detail: prodVm.value ? `VMID ${prodVm.value.vmid}` : '', done: !!prodVm.value },
  ]
  let foundCurrent = false
  return s.map((x) => {
    let state = x.done ? 'done' : 'todo'
    if (!x.done && !foundCurrent) {
      state = x.error ? 'error' : 'current'
      foundCurrent = true
    }
    return { ...x, state }
  })
})

// The one primary button is always the next step.
const nextAction = computed(() => {
  const cur = steps.value.find((s) => s.state === 'current' || s.state === 'error')?.key
  if (env.value === 'prod' || awaiting.value) return null
  return { plan: 'plan', define: 'plan', deploy: can.value.deploy ? 'deploy' : 'plan', validate: 'validate', approve: 'promote' }[cur] || null
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
    historyError.value = ''
  } catch (e) {
    historyError.value = e.message
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
    toast.error(e.message, { title: 'Backend unreachable', duration: 0 })
  }
  await refresh()
}

async function track(kind, start) {
  busy.value = kind
  try {
    const { job_id } = await start()
    return await pollJob(job_id, (j) => (activeJob.value = j))
  } catch (e) {
    toast.error(e.message)
    return null
  } finally {
    busy.value = ''
    refresh()
  }
}

async function summarize(job, target, loading) {
  const text = job?.result?.plan?.text
  if (!text) return
  loading.value = true
  try {
    target.value = await api.summarizePlan(text, job.environment)
  } catch (e) {
    toast.error(e.message, { title: 'Plan review failed' })
  } finally {
    loading.value = false
  }
}

async function generatePlan() {
  const snapshot = JSON.stringify(spec.value)
  planSummary.value = null
  const job = await track('plan', () => api.plan(spec.value))
  if (!job) return
  planJob.value = job
  plannedSpecJson.value = snapshot
  if (job.status === 'success') await summarize(job, planSummary, summaryLoading)
  else toast.error(job.error || 'Plan failed', { title: 'Plan failed' })
}

async function deployTest() {
  const job = await track('deploy', () => api.deployTest(spec.value, planJob.value.id))
  if (job?.status === 'success') {
    planJob.value = { ...planJob.value, result: { ...planJob.value.result, applied: true } }
    toast.success(`${form.name} is running in Test. Validate it next.`, { title: 'Deployed' })
  } else if (job) toast.error(job.error || 'Deployment failed', { title: 'Deployment failed' })
}

async function validate() {
  troubleshootResult.value = null
  const job = await track('validate', () =>
    api.validate({
      name: form.name,
      environment: env.value,
      health_check_port: validateOpts.useHealth ? validateOpts.port : null,
      simulate_failure: isMock.value && validateOpts.simulateFailure,
    }),
  )
  if (!job) return
  validationJob.value = job
  const overall = job.result?.validation?.overall
  if (overall === 'PASS') toast.success(`All checks passed for ${form.name}.`, { title: 'Validation passed' })
  else if (overall === 'FAIL') toast.error('Some checks failed. Ask the assistant for a diagnosis.', { title: 'Validation failed' })
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
    toast.error(e.message)
  } finally {
    troubleshootLoading.value = false
  }
}

async function requestPromotion() {
  approvalSummary.value = null
  const job = await track('promote', () => api.promote({ name: testVm.value.name, stage: 'request' }))
  if (!job) return
  approvalJob.value = job
  if (job.status === 'awaiting_approval') {
    toast.info('Review the production plan below. Nothing has changed yet.', { title: 'Approval required' })
    await summarize(job, approvalSummary, approvalSummaryLoading)
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
      toast.info('Nothing was changed in production.', { title: 'Rejected' })
    } catch (e) {
      toast.error(e.message)
    }
    refresh()
    return
  }
  const result = await track('approve', call)
  if (!result) return
  approvalJob.value = { ...job, status: 'success', result: { ...job.result, decision: 'approved' } }
  if (result.status === 'success') toast.success(result.result?.summary || 'Change applied.', { title: 'Production updated' })
  else toast.error(result.error || 'Apply failed', { title: 'Production apply failed' })
}

async function recreate() {
  const prod = env.value === 'prod'
  const ok = await confirm({
    title: `Recreate ${form.name}?`,
    body: prod
      ? 'A destroy-and-recreate plan is prepared for production. It still needs your approval before anything happens.'
      : 'The VM is destroyed and cloned again from its template. Anything stored on its disk is lost.',
    danger: true,
    confirmLabel: prod ? 'Prepare plan' : 'Recreate',
  })
  if (!ok) return
  const job = await track('recreate', () => api.recreate({ name: form.name, environment: env.value }))
  if (job?.status === 'awaiting_approval') {
    approvalJob.value = job
    approvalSummary.value = null
    toast.info('Destructive plan prepared. Approve it below or reject it.', { title: 'Approval required' })
    await summarize(job, approvalSummary, approvalSummaryLoading)
  } else if (job?.status === 'success') {
    planJob.value = job
    toast.success('Validation was reset. Run Validate again.', { title: `${form.name} recreated` })
    await summarize(job, planSummary, summaryLoading)
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
  toast.info('Review the values, then generate a plan.', { title: 'Draft applied' })
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
  treeOpen.value = false
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

const selectedKey = computed(() => (currentVm.value ? `${currentVm.value.environment}/${currentVm.value.name}` : ''))
const pageTitle = computed(() =>
  currentVm.value
    ? `Virtual Machine ${currentVm.value.vmid} (${currentVm.value.name}) on node '${currentVm.value.node}'`
    : `New virtual machine (${env.value === 'prod' ? 'Production' : 'Test'})`,
)
const runningTasks = computed(() => (busy.value ? 1 : 0) + (awaiting.value ? 1 : 0))

function selectEnv(key) {
  env.value = key
  treeOpen.value = false
}

function showTasks() {
  tasksEl.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

let timer
onMounted(() => {
  loadInventory()
  timer = setInterval(refresh, 10000)
})
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <a class="skip" href="#main">Skip to content</a>
  <header class="topbar">
    <button type="button" class="tree-toggle" :aria-expanded="treeOpen" aria-controls="resource-tree" aria-label="Resource tree" @click="treeOpen = !treeOpen">
      <Menu :size="18" />
    </button>
    <div class="brand">
      <span class="logo" aria-hidden="true"><Layers :size="17" /></span>
      <span class="name">Infra Console</span>
      <span class="version">1.1.0</span>
    </div>
    <div class="bar-right">
      <template v-if="health">
        <span v-if="isMock" class="mode warn" title="LIVE_MODE=false: simulated Proxmox and OpenTofu"><FlaskConical :size="14" /><span class="t">Mock mode</span></span>
        <span v-else class="mode ok"><Radio :size="14" /><span class="t">Live</span></span>
        <span class="meta hide-md"><Boxes :size="14" />{{ health.settings.iac_binary === 'tofu' ? 'OpenTofu' : 'Terraform' }}</span>
        <span class="meta hide-md" :title="health.settings.ai_model || 'No AI key configured: deterministic local analysis'"><Bot :size="14" />{{ health.settings.ai_model ? 'Claude' : 'Local rules' }}</span>
      </template>
      <Skeleton v-else w="160px" h="18px" />
      <button type="button" class="tb-btn tasks" :aria-label="`Tasks: ${runningTasks} running`" @click="showTasks"><ListTodo :size="14" /><span class="t">Tasks: </span>{{ runningTasks }}</button>
      <span v-if="health" class="tb-btn user" :title="`Signed in as ${health.settings.user}`"><User :size="14" />{{ health.settings.user }}@pve</span>
    </div>
  </header>

  <div class="shell">
    <aside id="resource-tree" class="sidebar" :class="{ open: treeOpen }">
      <ResourceTree
        :vms="vms"
        :templates="templates"
        :px-status="pxStatus"
        :environments="environments"
        :env="env"
        :selected="selectedKey"
        @select-env="selectEnv"
        @select-vm="selectVm"
      />
    </aside>
    <div v-if="treeOpen" class="scrim" @click="treeOpen = false" />

    <main id="main" class="content">
      <div class="toolbar">
        <h1 class="page-title">{{ pageTitle }}</h1>
        <div class="env" role="radiogroup" aria-label="Environment">
          <button
            v-for="e in [{ key: 'test', label: 'Test' }, { key: 'prod', label: 'Production' }]"
            :key="e.key"
            type="button"
            role="radio"
            :aria-checked="env === e.key"
            :class="['seg', { active: env === e.key, prod: e.key === 'prod' }]"
            @click="env = e.key"
          >
            <span class="seg-dot" aria-hidden="true" />{{ e.label }}
          </button>
        </div>
        <div class="actions">
          <button class="btn" :class="{ primary: nextAction === 'plan' }" :disabled="!can.plan" :aria-busy="busy === 'plan'" @click="generatePlan">
            <span v-if="busy === 'plan'" class="spinner" /><FileCode v-else :size="14" />Generate Plan
          </button>
          <button class="btn" :class="{ primary: nextAction === 'deploy' }" :disabled="!can.deploy" :title="hints.deploy" :aria-busy="busy === 'deploy'" @click="deployTest">
            <span v-if="busy === 'deploy'" class="spinner" /><Play v-else :size="14" />Deploy to Test
          </button>
          <button class="btn" :class="{ primary: nextAction === 'validate' }" :disabled="!can.validate" :title="hints.validate" :aria-busy="busy === 'validate'" @click="validate">
            <span v-if="busy === 'validate'" class="spinner" /><Activity v-else :size="14" />Validate
          </button>
          <button class="btn" :class="{ primary: nextAction === 'promote' }" :disabled="!can.promote" :title="hints.promote" :aria-busy="busy === 'promote'" @click="requestPromotion">
            <span v-if="busy === 'promote'" class="spinner" /><ShieldCheck v-else :size="14" />Request Production Promotion
          </button>
          <button class="btn danger" :disabled="!can.recreate" :title="hints.recreate" :aria-busy="busy === 'recreate'" @click="recreate">
            <span v-if="busy === 'recreate'" class="spinner" /><RotateCcw v-else :size="14" />Recreate VM
          </button>
        </div>
      </div>
      <p v-if="env === 'test' && planJob && hints.deploy && ['plan', 'deploy'].includes(nextAction)" class="hint">{{ hints.deploy }}</p>
      <p v-else-if="env === 'prod'" class="hint">Production VMs are created only by promoting a validated Test VM.</p>

      <WorkflowSteps :steps="steps" />

      <div class="cols">
        <div class="col-left">
          <VmCreateForm
            v-model="form"
            :env="env"
            :policy="policy"
            :templates="templates"
            :environments="environments"
            @apply-spec="applyGeneratedSpec"
          />
        </div>

        <div class="col-right">
          <PlanPanel :job="planJob" :stale="!!planJob && planJob.action === 'plan' && !planMatchesForm" :busy="busy === 'plan'" />
          <AiSummaryPanel :summary="planSummary" :loading="summaryLoading" />
          <ValidationPanel
            :job="validationJob"
            :vm="currentVm"
            :mock="isMock"
            :options="validateOpts"
            :running="busy === 'validate'"
            :troubleshoot="troubleshootResult"
            :troubleshoot-loading="troubleshootLoading"
            @troubleshoot="troubleshoot"
          />
          <PromotionPanel
            :job="approvalJob"
            :summary="approvalSummary"
            :summary-loading="approvalSummaryLoading"
            :test-vm="testVm"
            :busy="!!busy"
            :approving="busy === 'approve'"
            @decide="decide"
          />
        </div>
      </div>

      <div ref="tasksEl" class="dock">
        <JobLogPanel :job="activeJob" />
        <HistoryTable :history="history" :vms="vms" :error="historyError" @select="selectVm" @retry="refresh" />
      </div>

      <footer class="footer">
        Proxmox credentials never reach the browser. Production changes always need a person to approve them.
      </footer>
    </main>
  </div>

  <ToastHost />
  <ConfirmDialog />
</template>

<style scoped>
.topbar {
  position: sticky; top: 0; z-index: 50; height: var(--header-h); background: var(--topbar); border-bottom: 1px solid #111;
  display: flex; align-items: center; gap: .75rem; padding: 0 var(--pad-x);
}
.tree-toggle { display: none; background: transparent; border: 0; color: var(--fg); width: 36px; height: 36px; place-items: center; cursor: pointer; border-radius: var(--radius); }
.tree-toggle:hover { background: rgba(255, 255, 255, .08); }
.brand { display: flex; align-items: center; gap: .55rem; min-width: 0; }
.logo { width: 28px; height: 28px; border-radius: 4px; display: grid; place-items: center; color: #fff; background: var(--brand); }
.name { font-size: 16px; font-weight: 700; letter-spacing: .01em; white-space: nowrap; }
.version { color: var(--mut); font-size: 14px; }
.bar-right { margin-left: auto; display: flex; align-items: center; gap: .5rem; min-width: 0; }
.mode, .meta { display: inline-flex; align-items: center; gap: .35rem; font-size: 13px; color: var(--mut); padding: 0 .4rem; white-space: nowrap; }
.mode.warn { color: var(--warn); }
.mode.ok { color: var(--ok); }
.tb-btn {
  display: inline-flex; align-items: center; gap: .4rem; height: 28px; padding: 0 .7rem; border-radius: var(--radius);
  font: inherit; font-size: 13px; color: #fff; border: 0; white-space: nowrap;
}
.tasks { background: var(--acc-fill); cursor: pointer; }
.tasks:hover { background: var(--acc-fill-hover); }
.user { background: var(--user); }

.shell { display: grid; grid-template-columns: 250px minmax(0, 1fr); min-height: calc(100vh - var(--header-h)); }
.sidebar { background: var(--sidebar); border-right: 1px solid #1c1c1c; position: sticky; top: var(--header-h); height: calc(100vh - var(--header-h)); overflow-y: auto; }
.scrim { display: none; }
.content { min-width: 0; padding: 0 var(--pad-x) var(--pad-x); display: flex; flex-direction: column; gap: 10px; }

.toolbar { display: flex; align-items: center; flex-wrap: wrap; gap: .6rem 1rem; padding: 10px 0 0; }
.page-title { font-size: 15px; font-weight: 400; color: var(--fg); margin-right: auto; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
.actions { display: flex; flex-wrap: wrap; gap: .35rem; }
.hint { font-size: 12px; color: var(--dim); margin-top: -4px; }

.env { display: inline-flex; border: 1px solid #5c5c5c; border-radius: var(--radius); overflow: hidden; }
.seg { font: inherit; font-size: 13px; border: 0; background: #444; color: var(--fg); padding: 0 .75rem; min-height: 28px; cursor: pointer; display: inline-flex; align-items: center; gap: .4rem; }
.seg + .seg { border-left: 1px solid #5c5c5c; }
.seg:hover { background: #505050; }
.seg-dot { width: 7px; height: 7px; border-radius: 50%; background: #8a8a8a; }
.seg.active { background: var(--sel); color: #fff; }
.seg.active .seg-dot { background: #fff; }
@media (pointer: coarse) { .seg { min-height: 40px; } }

.cols { display: grid; grid-template-columns: minmax(340px, 420px) minmax(0, 1fr); gap: 10px; align-items: start; }
.col-left { position: sticky; top: calc(var(--header-h) + 10px); }
.col-right { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
.dock { display: flex; flex-direction: column; gap: 10px; scroll-margin-top: calc(var(--header-h) + 10px); }
.footer { text-align: center; color: var(--dim); font-size: 12px; padding: 1rem 0 1.5rem; }

@media (max-width: 1280px) { .hide-md { display: none; } }
@media (max-width: 1100px) { .cols { grid-template-columns: 1fr; } .col-left { position: static; } }
@media (max-width: 900px) {
  .shell { grid-template-columns: 1fr; }
  .tree-toggle { display: grid; }
  .sidebar { position: fixed; z-index: 60; left: 0; top: var(--header-h); width: min(300px, 85vw); transform: translateX(-100%); transition: transform var(--t-med) var(--ease); }
  .sidebar.open { transform: none; box-shadow: var(--shadow-pop); }
  .scrim { display: block; position: fixed; inset: var(--header-h) 0 0 0; z-index: 55; background: rgba(0, 0, 0, .45); }
  .page-title { width: 100%; white-space: normal; }
}
@media (max-width: 560px) {
  .version, .meta, .user, .bar-right .t { display: none; }
  .mode { padding: 0; }
  .actions .btn { flex: 1 1 calc(50% - .35rem); }
}
</style>
