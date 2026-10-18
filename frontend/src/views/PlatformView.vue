<script setup>
import { computed, onMounted, ref } from 'vue'
import { Database, FileCode, Hammer, RefreshCw } from 'lucide-vue-next'
import PageHeader from '../layout/PageHeader.vue'
import Card from '../components/ui/Card.vue'
import Badge from '../components/ui/Badge.vue'
import DataTable from '../components/ui/DataTable.vue'
import StatusCard from '../components/ui/StatusCard.vue'
import ErrorPanel from '../components/ui/ErrorPanel.vue'
import PlanReview from '../components/PlanReview.vue'
import { api } from '../api.js'
import { refreshPlatform, runJob, store } from '../store.js'
import { ask } from '../components/ui/modal.js'
import { toast } from '../components/ui/toast.js'
import { openJob } from '../components/ui/drawer.js'

const plan = ref(null)
const current = ref(null)
const COLS = [{ key: 'kind', label: 'Resource' }, { key: 'name', label: 'Name', mono: true }, { key: 'status', label: 'Status' }, { key: 'owner', label: 'Created by' }, { key: 'detail', label: 'Notes' }]
const OWNER = { bootstrap: 'Admin bootstrap (once)', platform: 'This console', manual: 'An administrator' }
const STATUS = { present: ['ok', 'Present'], missing: ['err', 'Missing'], unknown: ['muted', 'Unknown'], 'not configured': ['muted', 'Not configured'] }
const p = computed(() => store.platform)

async function makePlan() {
  const job = await runJob('Platform plan', () => api.platformPlan(), { onUpdate: (j) => (current.value = j), quiet: true })
  current.value = job
  if (job?.status === 'success') plan.value = job
}
async function apply() {
  const pl = plan.value.result.plan
  const ok = await ask({
    title: 'Prepare the platform?',
    body: 'Downloads the official images onto the Proxmox node and turns them into templates. This takes a few minutes.',
    effects: pl.changes.map((c) => `${c.action === 'create' ? 'Create' : c.action} ${c.address}`),
    danger: pl.has_destroy,
    typed: pl.has_destroy ? 'PLATFORM' : undefined,
    confirmLabel: 'Prepare platform',
  })
  if (!ok) return
  const job = await runJob('Prepare platform', () => api.platformApply(plan.value.id, pl.has_destroy), { onUpdate: (j) => (current.value = j), quiet: true })
  current.value = job
  if (job?.status === 'success') {
    plan.value = null
    toast.success(pl.summary, { title: 'Platform ready' })
  }
  refreshPlatform()
}
onMounted(refreshPlatform)
</script>

<template>
  <PageHeader title="Platform" subtitle="Everything the console needs on the Proxmox side, and who creates it.">
    <button type="button" class="btn quiet" @click="refreshPlatform"><RefreshCw :size="16" />Refresh</button>
    <button v-if="!plan" type="button" class="btn" :class="{ primary: p?.needs_platform_apply }" :disabled="current && ['queued', 'running'].includes(current.status)" @click="makePlan"><FileCode :size="16" />Check what is missing</button>
    <button v-else type="button" class="btn primary" :disabled="!plan.result.plan.changes.length" @click="apply"><Hammer :size="16" />Prepare platform</button>
  </PageHeader>

  <div v-if="p" class="callout" :class="p.ready ? 'ok' : p.needs_bootstrap ? 'err' : 'warn'" role="status">
    <Database :size="18" />
    <span v-if="!p.reachable">Proxmox is not reachable: {{ p.error }}</span>
    <span v-else-if="p.ready">Ready. All templates and storage exist.</span>
    <span v-else-if="p.needs_bootstrap">An administrator must run the one-time bootstrap first (docs/proxmox-setup.md). Storage or networks are missing.</span>
    <span v-else>Templates are missing. Check what is missing, review the plan, then prepare the platform.</span>
  </div>

  <StatusCard v-if="current && ['queued', 'running'].includes(current.status)" :state="current.status" :title="current.action === 'platform-apply' ? 'Preparing the platform' : 'Checking the platform'" details @details="openJob(current.id, 'Platform')" />
  <ErrorPanel v-else-if="current?.status === 'failed'" what="The platform job failed" :error="current.error" :job-id="current.id" retry @retry="makePlan" @log="openJob(current.id, 'Platform')" />
  <Card v-if="plan" title="Plan" :icon="FileCode"><PlanReview :job="plan" /></Card>

  <Card title="Resources" :icon="Database" flush>
    <DataTable :columns="COLS" :rows="p?.resources || null" caption="Platform resources" :row-key="(r) => r.kind + r.name">
      <template #cell-status="{ row }"><Badge :tone="STATUS[row.status]?.[0]" :label="STATUS[row.status]?.[1] || row.status" /></template>
      <template #cell-owner="{ row }">{{ OWNER[row.owner] || row.owner }}</template>
      <template #cell-detail="{ row }"><span class="dim small">{{ row.detail }}</span></template>
    </DataTable>
  </Card>
</template>
