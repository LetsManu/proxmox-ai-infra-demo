<script setup>
import { computed, onMounted, ref } from 'vue'
import { Activity, ShieldCheck, RotateCcw, Boxes, ArrowRight } from 'lucide-vue-next'
import PageHeader from '../layout/PageHeader.vue'
import Card from '../components/ui/Card.vue'
import Badge from '../components/ui/Badge.vue'
import DataTable from '../components/ui/DataTable.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import ProgressSteps from '../components/ui/ProgressSteps.vue'
import StatusCard from '../components/ui/StatusCard.vue'
import ErrorPanel from '../components/ui/ErrorPanel.vue'
import Expandable from '../components/ui/Expandable.vue'
import Skeleton from '../components/ui/Skeleton.vue'
import ValidationChecklist from '../components/ValidationChecklist.vue'
import { api } from '../api.js'
import { isMock, refresh, runJob, store } from '../store.js'
import { route, links, go } from '../router.js'
import { ask } from '../components/ui/modal.js'
import { toast } from '../components/ui/toast.js'
import { openJob } from '../components/ui/drawer.js'
import { reviewAndApprove, rejectRequest } from '../production.js'
import { OS_LABEL, relTime } from '../components/ui/format.js'

const env = route.params.env
const name = route.params.name
const isTest = env === 'test'
const stack = computed(() => (store.stacks || []).find((s) => s.name === name && s.environment === env))
const prod = computed(() => (store.stacks || []).find((s) => s.name === name && s.environment === 'prod'))
const testStack = computed(() => (store.stacks || []).find((s) => s.name === name && s.environment === 'test'))
const awaiting = computed(() => (store.awaiting || []).find((j) => j.action === 'stack-promote' && j.vm_name === name))
const current = ref(null)
const failure = ref(null)
const results = ref(null)
const simulateFailure = ref(false)
const busy = computed(() => !!current.value && ['queued', 'running'].includes(current.value.status))

async function loadResults() {
  try {
    const [last] = await api.jobs({ vm_name: name, environment: env, action: 'stack-validate', limit: 1 })
    results.value = last?.result?.members || null
  } catch {
    results.value = null
  }
}
onMounted(loadResults)

async function track(label, start) {
  failure.value = null
  const job = await runJob(label, start, { onUpdate: (j) => (current.value = { ...j, label }), quiet: true })
  current.value = job ? { ...job, label } : null
  // a failed validation is explained by its checklist; other failures get the error panel
  if (job?.status === 'failed' && !['validate', 'stack-validate'].includes(job.action)) failure.value = { ...job, label }
  return job
}
async function validate() {
  const job = await track(`Validate stack ${name}`, () => api.stackValidate({ name, environment: env, simulate_failure: isMock() && simulateFailure.value }))
  if (job) results.value = job.result?.members || null
  if (job?.status === 'success') toast.success('Every machine passed.', { title: 'Stack validation passed' })
}
async function requestPromotion() {
  const job = await track(`Production plan for stack ${name}`, () => api.stackPromote({ name, stage: 'request' }))
  if (job?.status === 'awaiting_approval') await approve(job)
}
async function approve(job = awaiting.value) {
  const full = await api.job(job.id)
  const applied = await reviewAndApprove(full, { onUpdate: (j) => (current.value = { ...j, label: 'Deploy stack to Production' }) })
  if (applied) current.value = { ...applied, label: 'Deploy stack to Production' }
  if (applied?.status === 'failed') failure.value = { ...applied, label: 'Deploy stack to Production' }
  refresh()
}
async function reject() {
  if (await rejectRequest(awaiting.value)) refresh()
}
async function recreate() {
  const ok = await ask({
    title: `Recreate stack ${name}?`,
    body: 'Use this when the Test stack is broken. Every machine is rebuilt from its template.',
    effects: [`Destroy all ${stack.value.members.length} machines and everything on their disks`, 'Create them again with the same settings',
      'Install software and Docker services again', 'Reset the validation result'],
    danger: true,
    confirmLabel: 'Recreate stack',
  })
  if (!ok) return
  const plan = await track(`Recreate plan for ${name}`, () => api.stackPlan(stack.value.spec, true))
  if (plan?.status !== 'success') return
  const job = await track(`Recreate stack ${name}`, () => api.stackDeploy(plan.id))
  if (job?.status === 'success') {
    results.value = null
    toast.success('Validate it again before promoting.', { title: `Stack ${name} recreated` })
  }
}

const steps = computed(() => {
  const t = testStack.value
  const s = [
    { key: 'deploy', label: 'Deployed to Test', detail: t ? `${t.members.length} machines` : '', done: !!t },
    { key: 'validate', label: 'Validated', detail: t?.last_validation === 'FAIL' ? 'Failed' : '', done: t?.last_validation === 'PASS', error: t?.last_validation === 'FAIL' },
    { key: 'approve', label: 'Production approval', detail: awaiting.value ? 'Waiting' : '', done: !!prod.value },
    { key: 'prod', label: 'In Production', detail: prod.value ? `${prod.value.members.length} machines` : '', done: !!prod.value },
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
  if (!stack.value || busy.value) return null
  if (awaiting.value) return 'approve'
  if (isTest && stack.value.last_validation !== 'PASS') return 'validate'
  if (isTest && !prod.value) return 'promote'
  return null
})
const COLS = [
  { key: 'name', label: 'Machine', mono: true },
  { key: 'kind', label: 'Type' },
  { key: 'template', label: 'OS' },
  { key: 'ip_address', label: 'Address', mono: true },
  { key: 'config_status', label: 'Software' },
  { key: 'last_validation', label: 'Validation' },
]
</script>

<template>
  <div v-if="store.stacks === null" class="stack-v"><Skeleton w="40%" h="28px" /><Skeleton h="80px" /></div>
  <template v-else-if="!stack">
    <PageHeader :title="name" :env="env" :crumbs="[{ label: 'Stacks', href: '#/stacks' }]" />
    <Card><EmptyState :icon="Boxes" title="This stack is not deployed here" text="It may exist only in the other environment, or it was never deployed.">
      <button type="button" class="btn primary" @click="go('stack-new')">Create stack</button></EmptyState></Card>
  </template>
  <template v-else>
    <PageHeader :title="`Stack ${name}`" :subtitle="`${stack.members.length} machines · ${stack.spec.description || 'no description'} · deployed ${relTime(stack.deployed_at)}`" :env="env" :crumbs="[{ label: 'Stacks', href: '#/stacks' }]">
      <button v-if="isTest" type="button" class="btn danger" :disabled="busy || !!awaiting" @click="recreate"><RotateCcw :size="16" />Recreate</button>
      <button v-if="next && next !== 'validate'" type="button" class="btn" :disabled="busy" @click="validate"><Activity :size="16" />Validate stack</button>
      <button v-if="next === 'validate'" type="button" class="btn primary" @click="validate"><Activity :size="16" />Validate stack</button>
      <button v-else-if="next === 'promote'" type="button" class="btn primary" @click="requestPromotion"><ShieldCheck :size="16" />Request production approval</button>
      <button v-else-if="next === 'approve'" type="button" class="btn primary" @click="approve()"><ShieldCheck :size="16" />Review and approve</button>
      <button v-else type="button" class="btn" :disabled="busy" @click="validate"><Activity :size="16" />Validate stack</button>
    </PageHeader>

    <Card><ProgressSteps :steps="steps" :label="`Progress of stack ${name}`" /></Card>

    <StatusCard v-if="current && (['queued', 'running'].includes(current.status) || (current.status === 'success' && !(current.action || '').endsWith('validate')))" :state="current.status" :title="current.label"
      :text="current.status === 'success' ? (current.result?.summary || 'Finished.') : 'You can leave this page; the job keeps running.'" details @details="openJob(current.id, current.label)" />
    <ErrorPanel v-if="failure" :what="`${failure.label} failed`" :error="failure.error || ''" :job-id="failure.id" :retry="failure.action === 'stack-validate'" @retry="validate" @log="openJob(failure.id, failure.label)" />
    <StatusCard v-if="awaiting" state="awaiting" :title="`Production request for stack ${name}`" :text="`Requested by ${awaiting.user} ${relTime(awaiting.created_at)}. Nothing changes until someone approves it.`">
      <div class="row acts">
        <button type="button" class="btn sm primary" @click="approve()">Review and approve</button>
        <button type="button" class="btn sm" @click="reject">Reject request</button>
      </div>
    </StatusCard>

    <Card title="Machines" :icon="Boxes" flush>
      <DataTable :columns="COLS" :rows="stack.members" caption="Machines in this stack" :row-key="(r) => r.name" clickable @row="(r) => go(links.vm(env, r.name))">
        <template #cell-kind="{ row }">{{ row.kind === 'lxc' ? 'Container' : 'VM' }} <span class="dim small num">{{ row.vmid }}</span><span v-if="row.services.length" class="dim small"> · {{ row.services.join(', ') }}</span></template>
        <template #cell-template="{ row }">{{ OS_LABEL[row.template] || row.template }}</template>
        <template #cell-ip_address="{ row }">{{ row.ip_address || '–' }}</template>
        <template #cell-config_status="{ row }">
          <Badge v-if="row.config_status" :tone="{ success: 'ok', skipped: 'muted', failed: 'err' }[row.config_status]" :label="{ success: 'Installed', skipped: 'Skipped', failed: 'Failed' }[row.config_status]" />
          <span v-else class="dim">–</span>
        </template>
        <template #cell-last_validation="{ row }">
          <Badge v-if="row.last_validation" :tone="row.last_validation === 'PASS' ? 'ok' : 'err'" :label="row.last_validation === 'PASS' ? 'Passed' : 'Failed'" />
          <span v-else class="dim">Not validated</span>
        </template>
      </DataTable>
    </Card>

    <Card title="Validation" :icon="Activity" :subtitle="stack.last_validation_at ? `Last run ${relTime(stack.last_validation_at)}` : 'Not validated yet'">
      <template #actions><Badge v-if="stack.last_validation" :tone="stack.last_validation === 'PASS' ? 'ok' : 'err'" :label="stack.last_validation === 'PASS' ? 'All machines passed' : 'Some checks failed'" /></template>
      <div v-if="results" class="stack-v">
        <Expandable v-for="(r, n) in results" :key="n" :summary="n" :open="r.overall !== 'PASS'">
          <template #aside><Badge class="ml" :tone="r.overall === 'PASS' ? 'ok' : 'err'" :label="r.overall === 'PASS' ? 'Passed' : 'Failed'" /></template>
          <ValidationChecklist :result="r" />
        </Expandable>
      </div>
      <p v-else class="muted">Validation runs the platform checks, the security baseline, the application tests and the Docker service checks on every machine. The stack passes only if all machines pass.</p>
      <template v-if="isMock() && isTest" #footer>
        <span class="spacer" /><label class="check small"><input v-model="simulateFailure" type="checkbox" />Simulate a failure (demo mode)</label>
      </template>
    </Card>

    <Card v-if="isTest" title="Production" :icon="ShieldCheck">
      <div v-if="prod" class="row">
        <Badge tone="ok" label="In Production" /><span>{{ prod.members.length }} machines</span>
        <a class="btn sm" :href="`#/${links.stack('prod', name)}`">Open<ArrowRight :size="14" /></a>
      </div>
      <p v-else class="muted">The whole stack is promoted at once: one plan for all machines, one approval (type PROMOTE), full clones on the production network.</p>
    </Card>
  </template>
</template>

<style scoped>
.acts { margin-top: 8px; }
.ml { margin-left: 8px; }
</style>
