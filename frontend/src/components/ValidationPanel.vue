<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  job: { type: Object, default: null },
  vm: { type: Object, default: null },
  env: { type: String, required: true },
  mock: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
  troubleshootLoading: { type: Boolean, default: false },
})
const emit = defineEmits(['validate', 'troubleshoot'])

const port = ref(22)
const useHealth = ref(true)
const simulateFailure = ref(false)

const validation = computed(() =>
  props.job && props.vm && props.job.vm_name === props.vm.name && props.job.environment === props.vm.environment
    ? props.job.result?.validation
    : null,
)
const LABELS = {
  vm_running: 'VM running',
  cloud_init_completed: 'Cloud-init completed',
  guest_agent_ip: 'QEMU guest agent reports IP',
  service_health: 'Service health check',
}
const rows = computed(() => {
  const order = ['vm_running', 'cloud_init_completed', 'guest_agent_ip', 'service_health']
  const byName = Object.fromEntries((validation.value?.checks || []).map((c) => [c.name, c]))
  return order.map((n) => ({ name: n, label: LABELS[n], check: byName[n] }))
})

function run() {
  emit('validate', {
    health_check_port: useHealth.value ? port.value : null,
    simulate_failure: props.mock && simulateFailure.value,
  })
}
</script>

<template>
  <section class="card">
    <div class="card-head">
      <h2>Validation</h2>
      <span
        v-if="validation"
        class="result-badge"
        :class="validation.overall === 'PASS' ? 'pass' : 'fail'"
      >{{ validation.overall }}</span>
      <span v-else-if="vm?.last_validation" class="result-badge" :class="vm.last_validation === 'PASS' ? 'pass' : 'fail'">
        last: {{ vm.last_validation }}
      </span>
    </div>

    <p v-if="!vm" class="empty">Deploy the VM first, then validate it here.</p>
    <template v-else>
      <p class="muted small">
        {{ vm.name }} · VMID {{ vm.vmid }} · {{ vm.environment.toUpperCase() }}
        <template v-if="vm.ip_address"> · {{ vm.ip_address }}</template>
      </p>
      <ul class="checks">
        <li v-for="r in rows" :key="r.name" :class="r.check ? (r.check.ok ? 'ok' : 'bad') : 'pending'">
          <span class="icon">{{ r.check ? (r.check.ok ? '✔' : '✖') : '○' }}</span>
          <span class="label">{{ r.label }}</span>
          <span class="detail">{{ r.check?.detail || (r.name === 'service_health' && !useHealth ? 'optional' : '') }}</span>
        </li>
      </ul>

      <div class="row wrap">
        <label class="inline"><input v-model="useHealth" type="checkbox" /> Health check TCP port</label>
        <input v-model.number="port" class="port" type="number" min="1" max="65535" :disabled="!useHealth" />
        <label v-if="mock" class="inline muted"><input v-model="simulateFailure" type="checkbox" /> Simulate failure (mock)</label>
      </div>
      <div class="row">
        <button class="btn" :disabled="busy" @click="run">Run validation</button>
        <button v-if="validation?.overall === 'FAIL'" class="btn ai" :disabled="troubleshootLoading" @click="emit('troubleshoot')">
          <span v-if="troubleshootLoading" class="spinner" />✨ Ask AI to troubleshoot
        </button>
      </div>
    </template>
  </section>
</template>
