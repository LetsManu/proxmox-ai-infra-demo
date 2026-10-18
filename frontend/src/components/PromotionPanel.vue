<script setup>
import { computed, ref, watch } from 'vue'
import { ShieldCheck, CircleCheck, Circle, CircleX, ScanSearch } from 'lucide-vue-next'
import PlanPanel from './PlanPanel.vue'
import StatusPill from './ui/StatusPill.vue'
import Skeleton from './ui/Skeleton.vue'
import { STATUS_LABEL, STATUS_TONE } from './ui/format.js'

const props = defineProps({
  job: { type: Object, default: null },
  summary: { type: Object, default: null },
  summaryLoading: { type: Boolean, default: false },
  testVm: { type: Object, default: null },
  busy: { type: Boolean, default: false },
  approving: { type: Boolean, default: false },
})
const emit = defineEmits(['decide'])

const acknowledge = ref(false)
const confirmation = ref('')
watch(
  () => props.job?.id,
  () => {
    acknowledge.value = false
    confirmation.value = ''
  },
)

const isRecreate = computed(() => props.job?.action === 'recreate')
const word = computed(() => props.job?.result?.required_confirmation || 'PROMOTE')
const awaiting = computed(() => props.job?.status === 'awaiting_approval')
const validated = computed(() => props.testVm?.last_validation === 'PASS')
const gates = computed(() => [
  ...(isRecreate.value
    ? []
    : [{ label: 'Test validation passed', state: validated.value ? 'ok' : 'bad', detail: props.testVm ? props.testVm.name : 'no Test VM' }]),
  { label: 'Production plan ready', state: awaiting.value || props.job?.status === 'success' ? 'ok' : 'todo' },
  { label: 'Impact acknowledged', state: acknowledge.value ? 'ok' : 'todo' },
  { label: `Typed ${word.value}`, state: confirmation.value === word.value ? 'ok' : 'todo' },
])
const gateOk = computed(() => isRecreate.value || validated.value)
const canApprove = computed(
  () => awaiting.value && gateOk.value && acknowledge.value && confirmation.value === word.value && !props.busy,
)
const RISK = { low: 'ok', medium: 'warn', high: 'err' }
</script>

<template>
  <section class="card approval" :class="{ armed: awaiting }" aria-labelledby="appr-title">
    <div class="card-head">
      <h2 id="appr-title" class="title"><ShieldCheck :size="17" />Production approval</h2>
      <StatusPill v-if="job" :tone="STATUS_TONE[job.status]" :label="job.result?.decision === 'rejected' ? 'Rejected' : STATUS_LABEL[job.status]" />
    </div>

    <div class="card-body">
      <ul class="gates">
        <li v-for="g in gates" :key="g.label" :class="g.state">
          <CircleCheck v-if="g.state === 'ok'" :size="16" />
          <CircleX v-else-if="g.state === 'bad'" :size="16" />
          <Circle v-else :size="16" />
          <span>{{ g.label }}</span>
        </li>
      </ul>

      <p v-if="!job" class="empty">
        <ShieldCheck :size="18" />
        <span>After a passing validation, request a promotion. The production plan waits here until a person approves it. Nothing changes before that.</span>
      </p>

      <template v-else>
        <p class="who small muted">
          {{ isRecreate ? 'Recreate' : 'Promote' }} <span class="mono fg">{{ job.vm_name }}</span>
          <template v-if="!isRecreate"> from <span class="mono fg">{{ job.params?.source_vm }}</span></template>
          · requested by {{ job.user }}
        </p>

        <div class="plan-box"><PlanPanel :job="job" embedded /></div>

        <div v-if="summaryLoading" class="review"><Skeleton w="90px" h="22px" radius="99px" /><Skeleton h="12px" /></div>
        <div v-else-if="summary" class="review">
          <div class="review-head">
            <ScanSearch :size="15" />
            <StatusPill :tone="RISK[summary.risk_level]" :label="`${summary.risk_level[0].toUpperCase()}${summary.risk_level.slice(1)} risk`" />
          </div>
          <p class="small muted">{{ summary.summary }}</p>
        </div>

        <form v-if="awaiting" class="approve" @submit.prevent="canApprove && emit('decide', { stage: 'approve', acknowledge, confirmation })">
          <label class="check ack">
            <input v-model="acknowledge" type="checkbox" />
            <span>I understand this will change production</span>
          </label>
          <label class="field">
            <span class="label">Type <code class="word">{{ word }}</code> to confirm</span>
            <input v-model="confirmation" class="mono confirm-input" :placeholder="word" autocomplete="off" spellcheck="false" aria-describedby="appr-hint" />
          </label>
          <p id="appr-hint" class="small" :class="gateOk ? 'dim' : 'err-text'">
            {{ gateOk ? 'Your name and the time are recorded in the history.' : 'Disabled: the Test VM has not passed validation.' }}
          </p>
          <div class="approve-actions">
            <button type="button" class="btn ghost" :disabled="busy" @click="emit('decide', { stage: 'reject', acknowledge: false, confirmation: '' })">Reject</button>
            <button type="submit" class="btn" :class="isRecreate ? 'danger solid' : 'primary'" :disabled="!canApprove" :aria-busy="approving">
              <span v-if="approving" class="spinner" />{{ isRecreate ? 'Approve recreate' : 'Approve & promote to production' }}
            </button>
          </div>
        </form>
      </template>
    </div>
  </section>
</template>

<style scoped>
.approval { transition: border-color var(--t-med), box-shadow var(--t-med); }
.approval.armed { border-color: rgba(245, 166, 35, .55); box-shadow: 0 0 0 1px rgba(245, 166, 35, .25); }
.gates { list-style: none; display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: .4rem .9rem; margin-bottom: 1rem; }
.gates li { display: flex; align-items: center; gap: .45rem; font-size: .86rem; color: var(--dim); }
.gates .ok { color: var(--fg); } .gates .ok svg { color: var(--ok); }
.gates .bad { color: var(--fg); } .gates .bad svg { color: var(--err); }
.who { margin-bottom: .7rem; }
.fg { color: var(--fg); }
.plan-box { border: 1px solid var(--line); border-radius: var(--radius); padding: .85rem .9rem; background: var(--surface-2); }
.review { margin-top: .8rem; display: flex; flex-direction: column; gap: .4rem; }
.review-head { display: flex; align-items: center; gap: .5rem; color: var(--mut); }
.approve { margin-top: 1rem; padding-top: 1rem; border-top: 1px solid var(--line); display: flex; flex-direction: column; gap: .75rem; }
.ack { font-weight: 500; }
.confirm-input { max-width: 260px; letter-spacing: .08em; }
.word { color: var(--fg); background: var(--surface-3); padding: .05rem .35rem; border-radius: 4px; }
.err-text { color: var(--err); }
.approve-actions { display: flex; justify-content: flex-end; gap: .5rem; flex-wrap: wrap; }
</style>
