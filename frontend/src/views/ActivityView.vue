<script setup>
import { History } from 'lucide-vue-next'
import PageHeader from '../layout/PageHeader.vue'
import Card from '../components/ui/Card.vue'
import Badge from '../components/ui/Badge.vue'
import DataTable from '../components/ui/DataTable.vue'
import { store } from '../store.js'
import { openJob } from '../components/ui/drawer.js'
import { ACTION_LABEL, ENV_LABEL, STATUS_LABEL, STATUS_TONE, fullTime, relTime } from '../components/ui/format.js'

const COLS = [
  { key: 'when', label: 'When' }, { key: 'vm_name', label: 'Resource', mono: true }, { key: 'environment', label: 'Environment' },
  { key: 'action', label: 'What happened' }, { key: 'status', label: 'Result' }, { key: 'user', label: 'By' }, { key: 'plan_summary', label: 'Plan' },
]
</script>

<template>
  <PageHeader title="Activity" subtitle="Every plan, deployment, validation and decision, with who did it." />
  <Card title="History" :icon="History" flush>
    <DataTable :columns="COLS" :rows="store.history" caption="Activity history" :row-key="(r) => r.id" :clickable="true" empty="No activity yet."
      @row="(r) => r.job_id && openJob(r.job_id, ACTION_LABEL[r.action] || r.action)">
      <template #cell-when="{ row }"><span class="num" :title="fullTime(row.timestamp)">{{ relTime(row.timestamp) }}</span></template>
      <template #cell-environment="{ row }"><Badge :tone="row.environment === 'prod' ? 'err' : row.environment === 'test' ? 'info' : 'muted'" :label="ENV_LABEL[row.environment] || row.environment" /></template>
      <template #cell-action="{ row }">{{ ACTION_LABEL[row.action] || row.action }}</template>
      <template #cell-status="{ row }"><Badge :tone="STATUS_TONE[row.status] || 'muted'" :label="STATUS_LABEL[row.status] || row.status" /></template>
      <template #cell-plan_summary="{ row }"><span class="small" :class="{ hot: /[1-9]\d* to destroy/.test(row.plan_summary || '') }">{{ row.plan_summary }}</span></template>
    </DataTable>
  </Card>
  <p class="dim small">Select a row to open its job log.</p>
</template>

<style scoped>
.hot { color: var(--err-fg); font-weight: 600; }
</style>
