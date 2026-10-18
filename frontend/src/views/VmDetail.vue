<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { Activity, ShieldCheck, Wrench, RotateCcw, Stethoscope, Server, ArrowRight } from 'lucide-vue-next'
import PageHeader from '../layout/PageHeader.vue'
import Card from '../components/ui/Card.vue'
import Badge from '../components/ui/Badge.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import ProgressSteps from '../components/ui/ProgressSteps.vue'
import StatusCard from '../components/ui/StatusCard.vue'
import ErrorPanel from '../components/ui/ErrorPanel.vue'
import Expandable from '../components/ui/Expandable.vue'
import Skeleton from '../components/ui/Skeleton.vue'
import ValidationChecklist from '../components/ValidationChecklist.vue'
import TestSuitePanel from '../components/TestSuitePanel.vue'
import DiagnosisView from '../components/DiagnosisView.vue'
import { api } from '../api.js'
import { isMock, refresh, runJob, store } from '../store.js'
import { route, links } from '../router.js'
import { ask } from '../components/ui/modal.js'
import { toast } from '../components/ui/toast.js'
import { openDrawer, openJob } from '../components/ui/drawer.js'
import { reviewAndApprove, rejectRequest } from '../production.js'
import { OS_LABEL, gb, relTime } from '../components/ui/format.js'

const env = route.params.env
const name = route.params.name
const vm = computed(() => (store.vms || []).find((v) => v.name === name && v.environment === env))
const loading = computed(() => store.vms === null)
const isTest = env === 'test'
const testName = isTest ? name : `${name}-test`
const prodName = name.replace(/-test$/, '')
const testVm = computed(() => (store.vms || []).find((v) => v.name === testName && v.environment === 'test'))
const prodVm = computed(() => (store.vms || []).find((v) => v.name === prodName && v.environment === 'prod'))
const awaiting = computed(() =>
  (store.awaiting || []).find((j) => (j.action === 'promote' && j.vm_name === prodName) || (j.action === 'recreate' && j.vm_name === name && env === 'prod')),
)
const current = ref(null) // job running from this page
const failure = ref(null)
const validation = ref(null)
const testsVersion = ref(0)
const busy = computed(() => !!current.value && ['queued', 'running'].includes(current.value.status))
const simulateFailure = ref(false)

async function loadValidation() {
  try {
    const [last] = await api.jobs({ vm_name: name, environment: env, action: 'validate', limit: 1 })
    validation.value = last?.result?.validation || null
  } catch {
    validation.value = null
  }
}
onMounted(loadValidation)

const configOk = computed(() => vm.value?.config_status === 'success' || vm.value?.config_status === 'skipped')
const steps = computed(() => {
  const t = testVm.value
  const s = [
    { key: 'deploy', label: 'Deployed to Test', detail: t ? `ID ${t.vmid}` : '', done: !!t },
    { key: 'config', label: 'Software installed', detail: t?.config_status === 'failed' ? 'Failed' : t?.config_status === 'skipped' ? 'Skipped' : '', done: !!t && ['success', 'skipped'].includes(t.config_status), error: t?.config_status === 'failed' },
    { key: 'validate', label: 'Validated', detail: t?.last_validation === 'FAIL' ? 'Failed' : '', done: t?.last_validation === 'PASS', error: t?.last_validation === 'FAIL' },
    { key: 'approve', label: 'Production approval', detail: awaiting.value ? 'Waiting' : '', done: !!prodVm.value },
    { key: 'prod', label: 'In Production', detail: prodVm.value ? `ID ${prodVm.value.vmid}` : '', done: !!prodVm.value },
  ]
  let found = false
  return s.map((x) => {
    let state = x.done ? 'done' : 'todo'
    if (!x.done && !found) {
      state = x.error ? 'error' : 'current'
      found = true
    }
    return { ...x, state }
  })
})
const next = computed(() => {
  if (!vm.value || busy.value) return null
  if (awaiting.value) return 'approve'
  if (isTest && vm.value.config_status === 'failed') return 'configure'
  if (isTest && vm.value.last_validation !== 'PASS') return 'validate'
  // promote when there is no production copy yet, or Test was redeployed (validated) since
  if (isTest && (!prodVm.value || (vm.value.deployed_at || '') > (prodVm.value.deployed_at || ''))) return 'promote'
  if (!isTest && vm.value.last_validation !== 'PASS') return 'validate'
  return null
})

async function track(label, start, after) {
  failure.value = null
  const job = await runJob(label, start, { onUpdate: (j) => (current.value = { ...j, label }), quiet: true })
  current.value = job ? { ...job, label } : null
  // a failed validation is explained by its checklist; other failures get the error panel
  if (job?.status === 'failed' && !['validate', 'stack-validate'].includes(job.action)) failure.value = { ...job, label }
  await after?.(job)
  return job
}

async function validate() {
  const job = await track(`Validate ${name}`, () => api.validate({ name, environment: env, simulate_failure: isMock() && simulateFailure.value }))
  if (!job) return
  validation.value = job.result?.validation || null
  testsVersion.value++
  if (validation.value?.overall === 'PASS') {
    failure.value = null
    toast.success('All checks passed.', { title: 'Validation passed' })
  }
}
async function configure() {
  const job = await track(`Install software on ${name}`, () => api.configure({ name, environment: env }))
  if (job?.status === 'success') toast.success(job.result?.config_status === 'skipped' ? 'Skipped: no credentials configured for Ansible.' : 'Software installed.', { title: 'Software' })
}
async function requestPromotion() {
  const job = await track(`Production plan for ${prodName}`, () => api.promote({ name: testName, stage: 'request' }))
  if (job?.status === 'awaiting_approval') await approve(job)
}
async function approve(job = awaiting.value) {
  const full = await api.job(job.id)
  const applied = await reviewAndApprove(full, { onUpdate: (j) => (current.value = { ...j, label: 'Deploy to Production' }) })
  if (applied) current.value = { ...applied, label: 'Deploy to Production' }
  if (applied?.status === 'failed') failure.value = { ...applied, label: 'Deploy to Production' }
  refresh()
}
async function reject() {
  if (await rejectRequest(awaiting.value)) refresh()
}
async function recreate() {
  if (!isTest) {
    const job = await track(`Recreate plan for ${name}`, () => api.recreate({ name, environment: 'prod' }))
    if (job?.status === 'awaiting_approval') await approve(job)
    return
  }
  const ok = await ask({
    title: `Recreate ${name}?`,
    body: 'Use this when a Test machine is broken. It is rebuilt from its template.',
    effects: ['Destroy the machine and everything on its disk', 'Create it again from the same template and size', 'Install the software again', 'Reset the validation result'],
    danger: true,
    confirmLabel: 'Recreate',
  })
  if (!ok) return
  const job = await track(`Recreate ${name}`, () => api.recreate({ name, environment: 'test' }))
  if (job?.status === 'success') {
    validation.value = null
    toast.success('Validate it again before promoting.', { title: `${name} recreated` })
  }
}
const diagnosing = ref(false)
async function diagnose() {
  diagnosing.value = true
  try {
    const logs = failure.value ? (await api.job(failure.value.id)).logs : ''
    const d = await api.troubleshoot({ vm_name: name, job_logs: logs, validation_output: validation.value, proxmox_status: vm.value })
    openDrawer({ title: 'Diagnosis', subtitle: name, kind: 'component', component: DiagnosisView, props: { d } })
  } catch (e) {
    toast.error(e.message, { title: 'Diagnosis unavailable' })
  } finally {
    diagnosing.value = false
  }
}
const subtitle = computed(() => {
  const v = vm.value
  if (!v) return ''
  const kind = v.spec.kind === 'lxc' ? 'Container' : 'VM'
  return `${kind} ${v.vmid} · ${OS_LABEL[v.spec.template] || v.spec.template} · ${v.spec.cores} vCPU · ${gb(v.spec.memory_mb)} · ${v.spec.disk_gb} GB` + (v.ip_address ? ` · ${v.ip_address}` : '')
})
const software = computed(() => [
  ...(vm.value?.spec.profiles || []).map((k) => store.profiles.find((p) => p.key === k)?.label || k),
  ...(vm.value?.spec.packages || []),
])
watch(() => vm.value?.last_validation_at, loadValidation)
</script>

<template>
  <div v-if="loading" class="stack-v"><Skeleton w="40%" h="28px" /><Skeleton h="80px" /></div>
  <template v-else-if="!vm">
    <PageHeader :title="name" :crumbs="[{ label: 'Dashboard', href: '#/dashboard' }]" :env="env" />
    <Card><EmptyState :icon="Server" title="This machine does not exist (anymore)" text="It may have been recreated under another name or never been deployed.">
      <a class="btn primary" href="#/vm-new">Create VM</a></EmptyState></Card>
  </template>
  <template v-else>
    <PageHeader :title="name" :subtitle="subtitle" :env="env" :crumbs="[{ label: 'Dashboard', href: '#/dashboard' }]">
      <a v-if="vm.spec.stack" class="btn quiet" :href="`#/${links.stack(env, vm.spec.stack)}`">Part of stack {{ vm.spec.stack }}</a>
      <button v-if="isTest" type="button" class="btn quiet" :disabled="busy" @click="configure"><Wrench :size="16" />Install software again</button>
      <button v-if="next && next !== 'validate'" type="button" class="btn" :disabled="busy" @click="validate"><Activity :size="16" />Validate</button>
      <button type="button" class="btn danger" :disabled="busy || !!awaiting" @click="recreate"><RotateCcw :size="16" />Recreate</button>
      <button v-if="next === 'validate'" type="button" class="btn primary" @click="validate"><Activity :size="16" />Validate</button>
      <button v-else-if="next === 'configure'" type="button" class="btn primary" @click="configure"><Wrench :size="16" />Install software</button>
      <button v-else-if="next === 'promote'" type="button" class="btn primary" @click="requestPromotion"><ShieldCheck :size="16" />Request production approval</button>
      <button v-else-if="next === 'approve'" type="button" class="btn primary" @click="approve()"><ShieldCheck :size="16" />Review and approve</button>
      <button v-else type="button" class="btn" :disabled="busy" @click="validate"><Activity :size="16" />Validate</button>
    </PageHeader>

    <Card v-if="!vm.spec.stack"><ProgressSteps :steps="steps" :label="`Progress of ${prodName}`" /></Card>

    <StatusCard v-if="current && (['queued', 'running'].includes(current.status) || (current.status === 'success' && !(current.action || '').endsWith('validate')))" :state="current.status" :title="current.label"
      :text="current.status === 'success' ? (current.result?.summary || 'Finished.') : 'You can leave this page; the job keeps running.'" details @details="openJob(current.id, current.label)" />
    <ErrorPanel v-if="failure" :what="`${failure.label || 'The job'} failed`" :error="failure.error || ''" :job-id="failure.id" :retry="['validate', 'configure'].includes(failure.action)"
      @retry="failure.action === 'validate' ? validate() : failure.action === 'configure' ? configure() : null" @log="openJob(failure.id, failure.label)" />

    <StatusCard v-if="awaiting" state="awaiting" :title="`Production request for ${awaiting.vm_name}`"
      :text="`Requested by ${awaiting.user} ${relTime(awaiting.created_at)}. Nothing changes until someone approves it.`">
      <div class="row acts">
        <button type="button" class="btn sm primary" @click="approve()">Review and approve</button>
        <button type="button" class="btn sm" @click="reject">Reject request</button>
      </div>
    </StatusCard>

    <div class="cols">
      <Card title="Validation" :icon="Activity" :subtitle="vm.last_validation_at ? `Last run ${relTime(vm.last_validation_at)}` : 'Not validated yet'">
        <template #actions>
          <Badge v-if="vm.last_validation" :tone="vm.last_validation === 'PASS' ? 'ok' : 'err'" :label="vm.last_validation === 'PASS' ? 'Passed' : 'Failed'" />
        </template>
        <ValidationChecklist v-if="validation" :result="validation" />
        <p v-else class="muted">Validation checks that the machine runs, has a network address, finished its first boot, has its software and passes the security and application tests.</p>
        <template v-if="vm.last_validation === 'FAIL' || (isMock() && isTest)" #footer>
          <button v-if="vm.last_validation === 'FAIL'" type="button" class="btn" :disabled="diagnosing" :aria-busy="diagnosing" @click="diagnose">
            <span v-if="diagnosing" class="spinner" /><Stethoscope v-else :size="16" />Ask for a diagnosis
          </button>
          <span class="spacer" />
          <label v-if="isMock() && isTest" class="check small"><input v-model="simulateFailure" type="checkbox" />Simulate a failure (demo mode)</label>
        </template>
      </Card>

      <TestSuitePanel :name="name" :env="env" :version="testsVersion" />
    </div>

    <Card v-if="isTest" title="Production" :icon="ShieldCheck">
      <div v-if="prodVm" class="row">
        <Badge tone="ok" label="In Production" />
        <span>{{ prodVm.name }} · ID {{ prodVm.vmid }}</span>
        <a class="btn sm" :href="`#/${links.vm('prod', prodVm.name)}`">Open<ArrowRight :size="14" /></a>
      </div>
      <p v-else class="muted">
        Production gets a full copy of this machine named <span class="mono">{{ prodName }}</span>.
        It can be requested once validation passed, and a person must approve it by typing PROMOTE.
      </p>
    </Card>

    <Card title="Details">
      <Expandable summary="Show configuration">
        <dl class="kv">
          <div><dt>Software</dt><dd>{{ software.join(', ') || 'Base system only' }}</dd></div>
          <div><dt>Software status</dt><dd>{{ { success: 'Installed', skipped: 'Skipped (no credentials)', failed: 'Failed' }[vm.config_status] || 'Not run' }}{{ vm.configured_at ? ` · ${relTime(vm.configured_at)}` : '' }}</dd></div>
          <div v-if="vm.spec.services?.length"><dt>Docker services</dt><dd>{{ vm.spec.services.map((s) => `${s.name} (${s.image})`).join(', ') }}</dd></div>
          <div><dt>Node</dt><dd>{{ vm.node }}</dd></div>
          <div><dt>Deployed</dt><dd>{{ relTime(vm.deployed_at) }}</dd></div>
          <div v-if="vm.spec.description"><dt>Description</dt><dd>{{ vm.spec.description }}</dd></div>
        </dl>
      </Expandable>
    </Card>
  </template>
</template>

<style scoped>
.cols { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr); gap: 16px; align-items: start; }
.acts { margin-top: 8px; }
.kv { margin: 0; display: grid; gap: 6px; }
.kv > div { display: grid; grid-template-columns: 160px 1fr; gap: 12px; }
dt { color: var(--dim); }
dd { margin: 0; overflow-wrap: anywhere; }
@media (max-width: 1100px) { .cols { grid-template-columns: 1fr; } }
@media (max-width: 600px) { .kv > div { grid-template-columns: 1fr; gap: 0; } }
</style>
