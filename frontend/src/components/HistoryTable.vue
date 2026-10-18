<script setup>
import { ref } from 'vue'

defineProps({
  history: { type: Array, default: () => [] },
  vms: { type: Array, default: () => [] },
})
const emit = defineEmits(['select'])
const tab = ref('history')

const fmt = (ts) => (ts ? new Date(ts.endsWith('Z') || ts.includes('+') ? ts : `${ts}Z`).toLocaleString() : '–')
</script>

<template>
  <section class="card">
    <div class="card-head">
      <div class="segmented small">
        <button :class="{ active: tab === 'history' }" @click="tab = 'history'">History</button>
        <button :class="{ active: tab === 'vms' }" @click="tab = 'vms'">Managed VMs ({{ vms.length }})</button>
      </div>
    </div>

    <div class="table-wrap">
      <table v-if="tab === 'history'">
        <thead>
          <tr><th>Timestamp</th><th>VM name</th><th>Environment</th><th>Action</th><th>Status</th><th>User</th><th>Plan summary</th></tr>
        </thead>
        <tbody>
          <tr v-if="!history.length"><td colspan="7" class="empty">No activity yet.</td></tr>
          <tr v-for="h in history" :key="h.id">
            <td class="nowrap">{{ fmt(h.timestamp) }}</td>
            <td>{{ h.vm_name }}</td>
            <td><span class="tag" :class="h.environment === 'prod' ? 'tag-prod' : 'tag-test'">{{ h.environment }}</span></td>
            <td>{{ h.action }}</td>
            <td><span class="status" :class="`st-${h.status}`">{{ h.status }}</span></td>
            <td>{{ h.user }}</td>
            <td class="summary-cell" :class="{ 'danger-text': /[1-9]\d* to destroy/.test(h.plan_summary) }">{{ h.plan_summary }}</td>
          </tr>
        </tbody>
      </table>

      <table v-else>
        <thead>
          <tr><th>Name</th><th>Env</th><th>VMID</th><th>OS</th><th>Size</th><th>IP</th><th>Validation</th><th>Deployed</th></tr>
        </thead>
        <tbody>
          <tr v-if="!vms.length"><td colspan="8" class="empty">No VMs deployed yet.</td></tr>
          <tr v-for="v in vms" :key="v.environment + v.name" class="clickable" @click="emit('select', v)">
            <td>{{ v.name }}</td>
            <td><span class="tag" :class="v.environment === 'prod' ? 'tag-prod' : 'tag-test'">{{ v.environment }}</span></td>
            <td>{{ v.vmid }}</td>
            <td>{{ v.spec.template }}</td>
            <td class="nowrap">{{ v.spec.cores }} vCPU / {{ v.spec.memory_mb / 1024 }} GB / {{ v.spec.disk_gb }} GB</td>
            <td>{{ v.ip_address || '–' }}</td>
            <td><span v-if="v.last_validation" class="result-badge" :class="v.last_validation === 'PASS' ? 'pass' : 'fail'">{{ v.last_validation }}</span><span v-else class="muted">–</span></td>
            <td class="nowrap">{{ fmt(v.deployed_at) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
