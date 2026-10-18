<script setup>
import { computed } from 'vue'
import { Activity, CircleCheck, CircleX, Circle, LoaderCircle, Stethoscope, RotateCcw, Database } from 'lucide-vue-next'
import StatusPill from './ui/StatusPill.vue'
import Skeleton from './ui/Skeleton.vue'

const props = defineProps({
  job: { type: Object, default: null },
  vm: { type: Object, default: null },
  mock: { type: Boolean, default: false },
  options: { type: Object, required: true },
  running: { type: Boolean, default: false },
  troubleshoot: { type: Object, default: null },
  troubleshootLoading: { type: Boolean, default: false },
})
const emit = defineEmits(['troubleshoot'])
const o = props.options

const validation = computed(() =>
  props.job && props.vm && props.job.vm_name === props.vm.name && props.job.environment === props.vm.environment
    ? props.job.result?.validation
    : null,
)
const CHECKS = [
  { name: 'vm_running', label: 'VM is running' },
  { name: 'cloud_init_completed', label: 'Cloud-init finished' },
  { name: 'guest_agent_ip', label: 'Guest agent reports an IP' },
  { name: 'service_health', label: 'Service responds' },
]
const rows = computed(() => {
  const byName = Object.fromEntries((validation.value?.checks || []).map((c) => [c.name, c]))
  return CHECKS.filter((c) => c.name !== 'service_health' || o.useHealth || byName[c.name]).map((c) => ({
    ...c,
    check: byName[c.name],
  }))
})
const overall = computed(() => validation.value?.overall || props.vm?.last_validation)
</script>

<template>
  <section class="card" aria-labelledby="val-title">
    <div class="card-head">
      <h2 id="val-title" class="title"><Activity :size="17" />Validation</h2>
      <StatusPill v-if="running" tone="info" :icon="LoaderCircle" label="Checking" class="spin-icon" />
      <StatusPill v-else-if="overall" :tone="overall === 'PASS' ? 'ok' : 'err'" :label="overall === 'PASS' ? 'Passed' : 'Failed'" />
    </div>
    <div class="card-body">
      <p v-if="!vm" class="empty">
        <Activity :size="18" />
        <span>Once the VM is deployed, validation checks that it booted, cloud-init finished and the guest agent reports an address.</span>
      </p>
      <template v-else>
        <p class="target small">
          <span class="mono">{{ vm.name }}</span><span class="dim"> · VMID {{ vm.vmid }}</span>
          <span v-if="vm.ip_address" class="dim"> · <span class="mono">{{ vm.ip_address }}</span></span>
        </p>

        <ul class="checks" aria-live="polite">
          <li v-for="r in rows" :key="r.name" :class="r.check ? (r.check.ok ? 'ok' : 'bad') : 'pending'">
            <span class="ic">
              <LoaderCircle v-if="running" :size="17" class="spin" />
              <CircleCheck v-else-if="r.check?.ok" :size="17" />
              <CircleX v-else-if="r.check" :size="17" />
              <Circle v-else :size="17" />
            </span>
            <span class="label">{{ r.label }}<span v-if="r.check && !r.check.ok" class="sr-only"> failed</span></span>
            <span class="detail mono">{{ running ? '' : r.check?.detail || '' }}</span>
          </li>
        </ul>

        <div class="opts">
          <label class="check"><input v-model="o.useHealth" type="checkbox" /> Check TCP port</label>
          <input v-model.number="o.port" class="port mono" type="number" min="1" max="65535" :disabled="!o.useHealth" aria-label="TCP port" />
          <label v-if="mock" class="check sim"><input v-model="o.simulateFailure" type="checkbox" /> Simulate failure (mock)</label>
        </div>

        <div v-if="overall === 'FAIL' && !troubleshoot" class="diag-cta">
          <span class="small muted">Not sure why it failed?</span>
          <button type="button" class="btn sm" :disabled="troubleshootLoading" :aria-busy="troubleshootLoading" @click="emit('troubleshoot')">
            <span v-if="troubleshootLoading" class="spinner" /><Stethoscope v-else :size="15" />Diagnose
          </button>
        </div>

        <div v-if="troubleshootLoading" class="diag"><Skeleton h="12px" /><Skeleton w="70%" h="12px" /></div>
        <div v-else-if="troubleshoot" class="diag">
          <div class="diag-head">
            <Stethoscope :size="16" />
            <h3>Diagnosis</h3>
            <span class="dim small">{{ troubleshoot.source === 'local-fallback' ? 'Local rules' : 'Claude' }}</span>
          </div>
          <p class="cause">{{ troubleshoot.likely_cause }}</p>
          <h4 class="section-label">Check first</h4>
          <ul class="bullets"><li v-for="c in troubleshoot.immediate_checks" :key="c">{{ c }}</li></ul>
          <h4 class="section-label">Safe fix</h4>
          <ol class="bullets"><li v-for="c in troubleshoot.safe_remediation_steps" :key="c">{{ c }}</li></ol>
          <div class="verdicts">
            <StatusPill :tone="troubleshoot.recreate_appropriate ? 'ok' : 'muted'" :icon="RotateCcw" :label="troubleshoot.recreate_appropriate ? 'Recreate is safe' : 'Recreate won’t help'" />
            <StatusPill :tone="troubleshoot.stateful_risk ? 'warn' : 'muted'" :icon="Database" :label="troubleshoot.stateful_risk ? 'May hold data' : 'Stateless'" />
          </div>
          <p class="small muted">{{ troubleshoot.recreate_reasoning }} {{ troubleshoot.stateful_notes }}</p>
        </div>
      </template>
    </div>
  </section>
</template>

<style scoped>
.target { margin-bottom: .7rem; }
.checks { list-style: none; border: 1px solid var(--line); border-radius: var(--radius); overflow: hidden; }
.checks li { display: grid; grid-template-columns: 22px 220px minmax(0, 1fr); gap: .6rem; align-items: center; padding: .6rem .8rem; }
.checks li + li { border-top: 1px solid var(--line); }
.ic { display: grid; color: var(--dim); }
.ok .ic { color: var(--ok); }
.bad { background: rgba(255, 107, 107, .05); }
.bad .ic { color: var(--err); }
.label { font-size: .88rem; font-weight: 500; }
.detail { font-size: .78rem; color: var(--dim); overflow-wrap: anywhere; }
.bad .detail { color: #ffb4b4; }
.opts { display: flex; align-items: center; flex-wrap: wrap; gap: .5rem .9rem; margin-top: .85rem; }
.port { width: 88px; }
.sim { color: var(--mut); margin-left: auto; }
.diag-cta { display: flex; align-items: center; justify-content: space-between; gap: .75rem; margin-top: .9rem; padding: .6rem .8rem; background: var(--surface-2); border-radius: var(--radius); }
.diag { margin-top: .9rem; padding: .9rem; border: 1px solid var(--line); border-radius: var(--radius); background: var(--surface-2); display: flex; flex-direction: column; gap: .4rem; }
.diag-head { display: flex; align-items: center; gap: .5rem; }
.diag-head svg { color: var(--acc); }
.diag-head .dim { margin-left: auto; }
.cause { font-size: .9rem; }
.diag .section-label { margin: .5rem 0 .2rem; }
.bullets { padding-left: 1.1rem; font-size: .86rem; color: var(--mut); display: flex; flex-direction: column; gap: .2rem; }
.verdicts { display: flex; flex-wrap: wrap; gap: .4rem; margin-top: .5rem; }
.spin { animation: spin 1s linear infinite; }
.spin-icon :deep(svg) { animation: spin 1s linear infinite; }
@media (max-width: 640px) {
  .checks li { grid-template-columns: 22px minmax(0, 1fr); }
  .detail { grid-column: 2; }
  .sim { margin-left: 0; }
}
</style>
