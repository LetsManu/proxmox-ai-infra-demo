<script setup>
import { computed, onMounted, ref } from 'vue'
import { ShieldCheck, Sparkles, ClipboardCheck } from 'lucide-vue-next'
import PageHeader from '../layout/PageHeader.vue'
import Card from '../components/ui/Card.vue'
import Badge from '../components/ui/Badge.vue'
import DataTable from '../components/ui/DataTable.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import Expandable from '../components/ui/Expandable.vue'
import ProposalView from '../components/ProposalView.vue'
import { api } from '../api.js'
import { refresh, store } from '../store.js'
import { ask } from '../components/ui/modal.js'
import { toast } from '../components/ui/toast.js'
import { openDrawer } from '../components/ui/drawer.js'
import { reviewAndApprove, rejectRequest } from '../production.js'
import { ACTION_LABEL, ENV_LABEL, relTime } from '../components/ui/format.js'

const decided = ref(null)
async function loadDecided() {
  const all = await api.proposals().catch(() => [])
  decided.value = all.filter((p) => p.status !== 'pending').slice(0, 20)
}
onMounted(loadDecided)

const KIND = { role: 'Software role', tests: 'Test suite' }
const PROD_COLS = [
  { key: 'what', label: 'Request' }, { key: 'summary', label: 'Plan' }, { key: 'user', label: 'Requested by' }, { key: 'when', label: 'When' }, { key: 'act', label: '' },
]
const DRAFT_COLS = [
  { key: 'kind', label: 'Type' }, { key: 'name', label: 'Name', mono: true }, { key: 'review', label: 'Automated checks' }, { key: 'when', label: 'Drafted' }, { key: 'act', label: '' },
]
const OLD_COLS = [{ key: 'kind', label: 'Type' }, { key: 'name', label: 'Name', mono: true }, { key: 'status', label: 'Decision' }, { key: 'decided_by', label: 'By' }]

async function approveProd(j) {
  await reviewAndApprove(await api.job(j.id))
  refresh()
}
async function rejectProd(j) {
  if (await rejectRequest(j)) refresh()
}
function open(p) {
  openDrawer({ title: `${KIND[p.kind]}: ${p.name}`, subtitle: `Proposal ${p.id}`, kind: 'component', component: ProposalView, props: { p } })
}
async function decide(p, approve) {
  if (approve) {
    const ok = await ask({
      title: `Approve ${KIND[p.kind].toLowerCase()} “${p.name}”?`,
      body: p.kind === 'role'
        ? 'The role is installed into the approved profiles folder and can be selected for new machines right away.'
        : `Validate runs these ${p.content.checks.length} checks for ${p.target} in Test and Production; failures block promotion.`,
      effects: ['Your name is recorded as the approver', 'Older approved versions are replaced'],
      confirmLabel: 'Approve',
    })
    if (!ok) return
  }
  try {
    await (approve ? api.approveProposal(p.id) : api.rejectProposal(p.id))
    toast.success(approve ? `${KIND[p.kind]} approved.` : 'Draft rejected. Nothing was installed.', { title: p.name })
  } catch (e) {
    toast.error(e.message, { title: 'Could not record the decision' })
  }
  await refresh()
  loadDecided()
}
const prodRows = computed(() => store.awaiting)
const draftRows = computed(() => store.proposals)
</script>

<template>
  <PageHeader title="Review queue" subtitle="Everything that waits for a person: production changes and drafts written by the assistant." />

  <Card title="Production approvals" :icon="ShieldCheck" flush>
    <EmptyState v-if="prodRows && !prodRows.length" :icon="ShieldCheck" title="No production changes waiting" text="Requests appear here after a Test machine or stack passed validation." />
    <DataTable v-else :columns="PROD_COLS" :rows="prodRows" caption="Production requests" :row-key="(r) => r.id">
      <template #cell-what="{ row }"><strong>{{ ACTION_LABEL[row.action] || row.action }}</strong><br /><span class="mono small">{{ row.vm_name }}</span> <Badge tone="err" :label="ENV_LABEL[row.environment]" /></template>
      <template #cell-summary="{ row }"><span :class="{ hot: /[1-9]\d* to destroy/.test(row.result?.plan?.summary || '') }">{{ row.result?.plan?.summary }}</span></template>
      <template #cell-when="{ row }">{{ relTime(row.created_at) }}</template>
      <template #cell-act="{ row }">
        <div class="row nowrap">
          <button type="button" class="btn sm primary" @click="approveProd(row)">Review and approve</button>
          <button type="button" class="btn sm" @click="rejectProd(row)">Reject</button>
        </div>
      </template>
    </DataTable>
  </Card>

  <Card title="Drafts from the assistant" :icon="Sparkles" subtitle="Software roles and test suites are only used after approval" flush>
    <EmptyState v-if="draftRows && !draftRows.length" :icon="ClipboardCheck" title="No drafts waiting"
      text="When a request needs software no profile covers, or when you draft tests for a machine, the draft waits here." />
    <DataTable v-else :columns="DRAFT_COLS" :rows="draftRows" caption="Drafts waiting for review" :row-key="(r) => r.id">
      <template #cell-kind="{ row }">{{ KIND[row.kind] }}</template>
      <template #cell-name="{ row }">{{ row.name }}<span v-if="row.target" class="dim small"> · {{ row.target }}</span></template>
      <template #cell-review="{ row }">
        <Badge :tone="row.review.ok ? 'ok' : 'err'" :label="row.review.ok ? `All ${row.review.checks.length} passed` : 'Failed, cannot be approved'" />
      </template>
      <template #cell-when="{ row }">{{ relTime(row.created_at) }}</template>
      <template #cell-act="{ row }">
        <div class="row nowrap">
          <button type="button" class="btn sm" @click="open(row)">Show details</button>
          <button type="button" class="btn sm primary" :disabled="!row.review.ok" @click="decide(row, true)">Approve</button>
          <button type="button" class="btn sm quiet" @click="decide(row, false)">Reject</button>
        </div>
      </template>
    </DataTable>
  </Card>

  <Card title="Decided">
    <Expandable summary="Show earlier decisions">
      <DataTable :columns="OLD_COLS" :rows="decided" caption="Earlier decisions" :row-key="(r) => r.id" empty="No decisions yet.">
        <template #cell-kind="{ row }">{{ KIND[row.kind] }}</template>
        <template #cell-status="{ row }"><Badge :tone="row.status === 'approved' ? 'ok' : 'muted'" :label="row.status" /></template>
      </DataTable>
    </Expandable>
  </Card>
</template>

<style scoped>
.nowrap { flex-wrap: nowrap; }
.hot { color: var(--err-fg); font-weight: 600; }
</style>
