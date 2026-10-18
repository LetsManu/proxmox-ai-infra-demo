<script setup>
import { computed, reactive, ref } from 'vue'
import { Sparkles, ArrowLeft, ArrowRight, FileCode, Play, TriangleAlert, Lightbulb } from 'lucide-vue-next'
import PageHeader from '../layout/PageHeader.vue'
import Card from '../components/ui/Card.vue'
import Field from '../components/ui/Field.vue'
import ProgressSteps from '../components/ui/ProgressSteps.vue'
import StatusCard from '../components/ui/StatusCard.vue'
import ErrorPanel from '../components/ui/ErrorPanel.vue'
import StackEditor from '../components/StackEditor.vue'
import PlanReview from '../components/PlanReview.vue'
import { api } from '../api.js'
import { runJob } from '../store.js'
import { go, links } from '../router.js'
import { toast } from '../components/ui/toast.js'
import { openJob } from '../components/ui/drawer.js'

const st = (window.__stackDraft ||= reactive({ step: 0, prompt: '', stack: null, notes: [], warnings: [], source: '' }))
const STEPS = ['Describe', 'Architecture', 'Review and deploy']
const drafting = ref(false)
const draftError = ref(null)
const planJob = ref(null)
const plannedFor = ref('')
const planning = ref(false)
const planError = ref('')
const deployJob = ref(null)

async function assist() {
  drafting.value = true
  draftError.value = null
  try {
    const out = await api.generateStack(st.prompt)
    Object.assign(st, { stack: out.stack, notes: out.notes || [], warnings: out.warnings || [], source: out.source, step: 1 })
    toast.success('Edit anything you want, then review the plan.', { title: 'Architecture drafted' })
  } catch (e) {
    draftError.value = e.detail?.errors || [e.message]
    if (e.detail?.draft) st.stack = e.detail.draft
  } finally {
    drafting.value = false
  }
}
function blank() {
  st.stack = { name: 'myapp', environment: 'test', description: '', components: [
    { name: 'app', kind: 'vm', template: 'ubuntu-24-04', cores: 2, memory_mb: 2048, disk_gb: 16, description: '', profiles: [], packages: [], services: [] },
  ] }
  st.step = 1
}
const payload = computed(() => (st.stack ? { ...JSON.parse(JSON.stringify(st.stack)), environment: 'test' } : null))
const planCurrent = computed(() => planJob.value?.status === 'success' && plannedFor.value === JSON.stringify(payload.value))

async function makePlan() {
  planning.value = true
  planError.value = ''
  const snap = JSON.stringify(payload.value)
  try {
    const job = await runJob(`Plan stack ${st.stack.name}`, () => api.stackPlan(payload.value), { quiet: true, rethrow: true })
    if (job) {
      planJob.value = job
      plannedFor.value = snap
    }
  } catch (e) {
    planError.value = e.message
  } finally {
    planning.value = false
  }
}
async function deploy() {
  const name = st.stack.name
  const job = await runJob(`Deploy stack ${name}`, () => api.stackDeploy(planJob.value.id), { onUpdate: (j) => (deployJob.value = j), quiet: true })
  if (!job) return
  deployJob.value = job
  if (job.status === 'success') {
    toast.success(`Stack ${name} runs in Test. Validate it next.`, { title: 'Stack deployed' })
    window.__stackDraft = null
    go(links.stack('test', name))
  }
}
const stepStates = computed(() => STEPS.map((label, i) => ({ key: label, label, state: i < st.step ? 'done' : i === st.step ? 'current' : 'todo' })))
</script>

<template>
  <PageHeader title="Create stack" subtitle="Machines, containers and Docker services for one application. Starts in Test." env="test"
    :crumbs="[{ label: 'Stacks', href: '#/stacks' }]" />
  <Card><ProgressSteps :steps="stepStates" label="Create stack steps" /></Card>

  <Card v-if="st.step === 0" title="Describe the application" :icon="Sparkles">
    <div class="stack-v">
      <Field id="st-prompt" label="What should run?" hint="The assistant proposes the machines, containers and services. You edit and approve everything.">
        <textarea id="st-prompt" v-model="st.prompt" rows="4" aria-describedby="st-prompt-msg"
          placeholder="Example: WordPress for the marketing team with monitoring. Or: 3 web servers in containers and a PostgreSQL database." />
      </Field>
      <ErrorPanel v-if="draftError" what="The drafted architecture is not valid" :error="draftError.join('\n')" />
      <button v-if="draftError && st.stack" type="button" class="btn" @click="st.step = 1">Fix it in the editor</button>
    </div>
    <template #footer>
      <button type="button" class="btn" @click="blank">Start from scratch</button>
      <span class="spacer" />
      <button type="button" class="btn primary" :disabled="drafting || st.prompt.trim().length < 5" :aria-busy="drafting" @click="assist">
        <span v-if="drafting" class="spinner" /><Sparkles v-else :size="16" />Draft with assistant
      </button>
    </template>
  </Card>

  <template v-else-if="st.step === 1">
    <div v-if="st.notes.length || st.warnings.length" class="callout info" role="status">
      <Lightbulb :size="18" />
      <div class="stack-v tight">
        <strong>{{ st.source === 'local-fallback' ? 'Notes (local rules)' : 'Notes from the assistant' }}</strong>
        <ul class="plain"><li v-for="n in st.notes" :key="n">{{ n }}</li><li v-for="w in st.warnings" :key="w"><TriangleAlert :size="14" /> {{ w }}</li></ul>
      </div>
    </div>
    <Card title="Architecture" subtitle="Change anything; limits are checked when you create the plan">
      <StackEditor v-model="st.stack" />
      <template #footer>
        <button type="button" class="btn" @click="st.step = 0"><ArrowLeft :size="16" />Back</button>
        <span class="spacer" />
        <button type="button" class="btn primary" @click="st.step = 2">Continue<ArrowRight :size="16" /></button>
      </template>
    </Card>
  </template>

  <template v-else>
    <Card title="Review">
      <ul class="members">
        <li v-for="c in st.stack.components" :key="c.name">
          <span class="mono">{{ st.stack.name }}-{{ c.name }}-test</span>
          <span class="dim">{{ c.kind === 'lxc' ? 'Container' : 'VM' }} · {{ c.cores }} vCPU · {{ c.memory_mb }} MB · {{ c.disk_gb }} GB</span>
          <span>{{ [...c.profiles, ...c.packages].join(', ') || 'Base system' }}<template v-if="c.services.length"> · services: {{ c.services.map((s) => s.name).join(', ') }}</template></span>
        </li>
      </ul>
      <template #footer>
        <button type="button" class="btn" @click="st.step = 1"><ArrowLeft :size="16" />Back</button>
        <span class="spacer" />
        <button v-if="!planCurrent" type="button" class="btn primary" :disabled="planning" :aria-busy="planning" @click="makePlan">
          <span v-if="planning" class="spinner" /><FileCode v-else :size="16" />Create plan
        </button>
        <button v-else type="button" class="btn primary" :disabled="!!deployJob && ['queued', 'running'].includes(deployJob.status)" @click="deploy">
          <Play :size="16" />Deploy stack to Test
        </button>
      </template>
    </Card>
    <ErrorPanel v-if="planError" what="The stack is not valid yet" :error="planError" />
    <StatusCard v-if="planning" state="running" title="Creating the plan" text="One plan for all machines of the stack. Nothing changes yet." />
    <ErrorPanel v-else-if="planJob?.status === 'failed'" what="The plan could not be created" :error="planJob.error" :job-id="planJob.id" retry @retry="makePlan" @log="openJob(planJob.id, 'Stack plan')" />
    <Card v-else-if="planCurrent" title="Plan" :icon="FileCode"><PlanReview :job="planJob" /></Card>
    <StatusCard v-if="deployJob && deployJob.status !== 'failed'" :state="deployJob.status" :title="`Deploying stack ${st.stack.name}`"
      text="Creating every machine, then installing software and Docker services on each." details @details="openJob(deployJob.id, 'Deploy stack')" />
    <ErrorPanel v-else-if="deployJob?.status === 'failed'" what="The stack deployment failed" :error="deployJob.error" :job-id="deployJob.id" @log="openJob(deployJob.id, 'Deploy stack')" />
  </template>
</template>

<style scoped>
.plain { list-style: none; display: flex; flex-direction: column; gap: 2px; }
.tight { gap: 4px; }
.members { list-style: none; display: flex; flex-direction: column; }
.members li { display: grid; grid-template-columns: minmax(200px, 1fr) minmax(200px, 1fr) 2fr; gap: 12px; padding: 8px 0; border-bottom: 1px solid var(--line); }
.members li:last-child { border-bottom: 0; }
@media (max-width: 860px) { .members li { grid-template-columns: 1fr; gap: 2px; } }
</style>
