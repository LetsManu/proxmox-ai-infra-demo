<script setup>
import { computed, ref, watch } from 'vue'
import PlanPanel from './PlanPanel.vue'

const props = defineProps({
  job: { type: Object, default: null },
  summary: { type: Object, default: null },
  summaryLoading: { type: Boolean, default: false },
  testVm: { type: Object, default: null },
  busy: { type: Boolean, default: false },
})
const emit = defineEmits(['decide'])

const acknowledge = ref(false)
const confirmation = ref('')
watch(() => props.job?.id, () => {
  acknowledge.value = false
  confirmation.value = ''
})

const word = computed(() => props.job?.result?.required_confirmation || 'PROMOTE')
const awaiting = computed(() => props.job?.status === 'awaiting_approval')
const validated = computed(() => props.testVm?.last_validation === 'PASS')
// Recreate approvals don't depend on TEST validation; promotions do.
const gateOk = computed(() => props.job?.action === 'recreate' || validated.value)
const canApprove = computed(
  () => awaiting.value && gateOk.value && acknowledge.value && confirmation.value === word.value && !props.busy,
)
</script>

<template>
  <section class="card promotion" :class="{ armed: awaiting }">
    <div class="card-head">
      <h2>Production approval</h2>
      <span class="tag tag-prod">HUMAN APPROVAL REQUIRED</span>
    </div>

    <ul class="gates">
      <li :class="validated ? 'ok' : 'bad'">
        {{ validated ? '✔' : '✖' }} TEST validation passed
        <span class="muted small" v-if="testVm">({{ testVm.name }}: {{ testVm.last_validation || 'not validated' }})</span>
      </li>
      <li :class="awaiting ? 'ok' : 'pending'">{{ awaiting ? '✔' : '○' }} Production plan generated</li>
      <li :class="acknowledge ? 'ok' : 'pending'">{{ acknowledge ? '✔' : '○' }} Impact acknowledged</li>
      <li :class="confirmation === word ? 'ok' : 'pending'">{{ confirmation === word ? '✔' : '○' }} Typed {{ word }}</li>
    </ul>

    <p v-if="!job" class="empty">
      After a passing validation, click <strong>Request Production Promotion</strong>. A production plan is generated
      and parked here. Nothing changes until a human approves.
    </p>

    <template v-if="job">
      <p class="muted small">
        {{ job.action === 'recreate' ? 'Recreate' : 'Promotion' }} of <strong>{{ job.vm_name }}</strong> · job
        <code>{{ job.id.slice(0, 8) }}</code> · status <strong>{{ job.status }}</strong>
        <template v-if="job.result?.decision"> · {{ job.result.decision }}</template>
      </p>
      <PlanPanel :job="job" title="Production plan" compact />

      <div v-if="summaryLoading" class="empty"><span class="spinner" />AI is reviewing the production plan…</div>
      <div v-else-if="summary" class="mini-summary" :class="`risk-${summary.risk_level}`">
        <strong>AI risk: {{ summary.risk_level.toUpperCase() }}</strong> – {{ summary.summary }}
        <div class="muted small">{{ summary.approval_recommendation }}</div>
      </div>

      <div v-if="awaiting" class="approve-box">
        <label class="inline">
          <input v-model="acknowledge" type="checkbox" />
          I understand this will change production
        </label>
        <label>
          <span class="lbl">Type <code>{{ word }}</code> to confirm</span>
          <input v-model="confirmation" :placeholder="word" autocomplete="off" spellcheck="false" />
        </label>
        <div class="row">
          <button
            class="btn danger"
            :disabled="!canApprove"
            @click="emit('decide', { stage: 'approve', acknowledge, confirmation })"
          >
            {{ job.action === 'recreate' ? 'Approve recreate' : 'Approve & promote to production' }}
          </button>
          <button class="btn" :disabled="busy" @click="emit('decide', { stage: 'reject', acknowledge: false, confirmation: '' })">
            Reject
          </button>
        </div>
        <p v-if="!gateOk" class="err small">Disabled: the TEST VM has not passed validation.</p>
      </div>
    </template>
  </section>
</template>
