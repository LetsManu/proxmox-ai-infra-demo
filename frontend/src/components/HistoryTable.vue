<script setup>
import { ref } from 'vue'
import { History, Server, RefreshCw } from 'lucide-vue-next'
import StatusPill from './ui/StatusPill.vue'
import Skeleton from './ui/Skeleton.vue'
import { ACTION_LABEL, ENV_LABEL, STATUS_LABEL, STATUS_TONE, fullTime, relTime } from './ui/format.js'

defineProps({
  history: { type: Array, default: null }, // null = loading
  vms: { type: Array, default: null },
  error: { type: String, default: '' },
})
const emit = defineEmits(['select', 'retry'])
const tab = ref('history')
const OS = { 'ubuntu-24-04': 'Ubuntu 24.04', 'debian-12': 'Debian 12' }
</script>

<template>
  <section class="card" aria-label="Activity">
    <div class="card-head tabs-head">
      <div class="tabs" role="tablist">
        <button role="tab" :aria-selected="tab === 'history'" :class="{ on: tab === 'history' }" @click="tab = 'history'">
          <History :size="15" />History
        </button>
        <button role="tab" :aria-selected="tab === 'vms'" :class="{ on: tab === 'vms' }" @click="tab = 'vms'">
          <Server :size="15" />Managed VMs<span v-if="vms" class="count num">{{ vms.length }}</span>
        </button>
      </div>
    </div>

    <div v-if="error" class="card-body">
      <div class="callout err" role="alert">
        <span>Could not load the activity: {{ error }}</span>
        <button type="button" class="btn sm" @click="emit('retry')"><RefreshCw :size="14" />Retry</button>
      </div>
    </div>

    <div v-else-if="tab === 'history'" class="table-wrap">
      <table>
        <caption class="sr-only">Deployment history</caption>
        <thead>
          <tr><th>When</th><th>VM</th><th>Environment</th><th>Action</th><th>Status</th><th>User</th><th>Plan summary</th></tr>
        </thead>
        <tbody>
          <template v-if="!history">
            <tr v-for="i in 3" :key="i"><td v-for="j in 7" :key="j"><Skeleton h="12px" /></td></tr>
          </template>
          <tr v-else-if="!history.length"><td colspan="7" class="empty-cell">No activity yet. Plans, deployments and approvals appear here.</td></tr>
          <tr v-for="h in history || []" :key="h.id">
            <td data-label="When" class="nowrap num" :title="fullTime(h.timestamp)">{{ relTime(h.timestamp) }}</td>
            <td data-label="VM" class="mono primary-cell">{{ h.vm_name }}</td>
            <td data-label="Environment"><span class="env" :class="h.environment">{{ ENV_LABEL[h.environment] || h.environment }}</span></td>
            <td data-label="Action">{{ ACTION_LABEL[h.action] || h.action }}</td>
            <td data-label="Status"><StatusPill :tone="STATUS_TONE[h.status] || 'muted'" :label="STATUS_LABEL[h.status] || h.status" /></td>
            <td data-label="User" class="muted">{{ h.user }}</td>
            <td data-label="Summary" class="summary" :class="{ hot: /[1-9]\d* to destroy/.test(h.plan_summary) }">{{ h.plan_summary }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-else class="table-wrap">
      <table>
        <caption class="sr-only">Managed virtual machines</caption>
        <thead>
          <tr><th>Name</th><th>Environment</th><th>VMID</th><th>OS</th><th>Size</th><th>IP address</th><th>Validation</th><th>Deployed</th></tr>
        </thead>
        <tbody>
          <tr v-if="vms && !vms.length"><td colspan="8" class="empty-cell">No VMs yet. Deploy one to Test to get started.</td></tr>
          <tr v-for="v in vms || []" :key="v.environment + v.name" class="clickable" tabindex="0" @click="emit('select', v)" @keydown.enter="emit('select', v)">
            <td data-label="Name" class="mono primary-cell">{{ v.name }}</td>
            <td data-label="Environment"><span class="env" :class="v.environment">{{ ENV_LABEL[v.environment] }}</span></td>
            <td data-label="VMID" class="num">{{ v.vmid }}</td>
            <td data-label="OS">{{ OS[v.spec.template] || v.spec.template }}</td>
            <td data-label="Size" class="nowrap num">{{ v.spec.cores }} vCPU · {{ v.spec.memory_mb / 1024 }} GB · {{ v.spec.disk_gb }} GB</td>
            <td data-label="IP address" class="mono">{{ v.ip_address || '–' }}</td>
            <td data-label="Validation">
              <StatusPill v-if="v.last_validation" :tone="v.last_validation === 'PASS' ? 'ok' : 'err'" :label="v.last_validation === 'PASS' ? 'Passed' : 'Failed'" />
              <span v-else class="dim">Not run</span>
            </td>
            <td data-label="Deployed" class="nowrap num" :title="fullTime(v.deployed_at)">{{ relTime(v.deployed_at) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.tabs-head { padding-top: 0; padding-bottom: 0; }
.tabs { display: flex; gap: .25rem; align-self: stretch; }
.tabs button {
  font: inherit; font-size: 15px; font-weight: 400; background: transparent; border: 0; color: var(--mut); cursor: pointer;
  display: inline-flex; align-items: center; gap: .45rem; padding: 0 .75rem; min-height: 40px; border-bottom: 2px solid transparent;
}
.tabs button:hover { color: var(--fg); }
.tabs button.on { color: var(--title); border-bottom-color: var(--acc); }
.count { background: var(--surface-3); color: var(--mut); border-radius: 99px; padding: 0 .45rem; font-size: .74rem; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; font-weight: 700; font-size: 13px; color: var(--fg); padding: .45rem .9rem; border-bottom: 1px solid var(--line); border-top: 1px solid var(--line); white-space: nowrap; background: var(--surface-2); }
td { padding: .45rem .9rem; border-bottom: 1px solid #404040; vertical-align: middle; }
tbody tr:last-child td { border-bottom: 0; }
.nowrap { white-space: nowrap; }
.summary { color: var(--mut); max-width: 380px; }
.summary.hot { color: var(--err); }
.env { font-size: .8rem; font-weight: 600; display: inline-flex; align-items: center; gap: .4rem; }
.env::before { content: ''; width: 7px; height: 7px; border-radius: 50%; background: var(--info); }
.env.prod::before { background: var(--err); }
.clickable { cursor: pointer; transition: background var(--t-fast); }
.clickable:hover td, .clickable:focus-visible td { background: rgba(255, 255, 255, .025); }
.empty-cell { color: var(--mut); text-align: center; padding: 2rem 1rem; }
.callout { justify-content: space-between; align-items: center; }

/* Phones: rows become cards */
@media (max-width: 720px) {
  thead { display: none; }
  table, tbody, tr, td { display: block; width: 100%; }
  tr { padding: .75rem 1rem; border-bottom: 1px solid var(--line); }
  td { border: 0; padding: .15rem 0; display: flex; justify-content: space-between; gap: 1rem; text-align: right; }
  td::before { content: attr(data-label); color: var(--dim); font-size: .78rem; text-align: left; }
  td.primary-cell { font-size: .95rem; font-weight: 600; padding-bottom: .35rem; }
  td.primary-cell::before { content: none; }
  .summary { max-width: none; }
  .empty-cell { display: block; text-align: center; }
  .empty-cell::before { content: none; }
}
</style>
