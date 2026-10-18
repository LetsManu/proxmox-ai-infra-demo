<script setup>
import { computed, ref } from 'vue'
import { Server, Boxes, Activity, ShieldAlert, Loader, Plus, Database, ArrowRight } from 'lucide-vue-next'
import PageHeader from '../layout/PageHeader.vue'
import EnvSwitch from '../components/EnvSwitch.vue'
import Card from '../components/ui/Card.vue'
import Badge from '../components/ui/Badge.vue'
import DataTable from '../components/ui/DataTable.vue'
import Skeleton from '../components/ui/Skeleton.vue'
import { store } from '../store.js'
import { go, links } from '../router.js'
import { ACTION_LABEL, ENV_LABEL, STATUS_LABEL, STATUS_TONE, relTime, fullTime } from '../components/ui/format.js'

const env = ref('test')
const machines = computed(() => (store.vms || []).filter((v) => v.environment === env.value))
const running = computed(() => machines.value.filter((v) => v.status === 'running').length)
const inProgress = computed(() => store.running.length)
const lastValidation = computed(() =>
  machines.value.filter((v) => v.last_validation_at).sort((a, b) => b.last_validation_at.localeCompare(a.last_validation_at))[0],
)
const approvals = computed(() => (store.awaiting || []).length)
const reviews = computed(() => (store.proposals || []).length)
const activity = computed(() => (store.history ? store.history.filter((h) => h.environment === env.value || h.environment === 'infra').slice(0, 8) : null))
const COLS = [
  { key: 'when', label: 'When', cls: 'nowrap' },
  { key: 'vm_name', label: 'Resource', mono: true },
  { key: 'action', label: 'What happened' },
  { key: 'status', label: 'Result' },
  { key: 'user', label: 'By' },
]
function openRow(h) {
  const vm = (store.vms || []).find((v) => v.name === h.vm_name && v.environment === h.environment)
  const st = (store.stacks || []).find((s) => s.name === h.vm_name && s.environment === h.environment)
  if (st) go(links.stack(st.environment, st.name))
  else if (vm) go(links.vm(vm.environment, vm.name))
  else go('activity')
}
const loading = computed(() => store.vms === null)
</script>

<template>
  <PageHeader title="Dashboard" subtitle="What runs where, and what needs your attention.">
    <EnvSwitch v-model="env" />
    <button type="button" class="btn" @click="go('stack-new')"><Boxes :size="16" />Create stack</button>
    <button type="button" class="btn primary" @click="go('vm-new')"><Plus :size="16" />Create VM</button>
  </PageHeader>

  <div v-if="store.platform && !store.platform.ready" class="callout warn" role="status">
    <Database :size="18" />
    <div class="row grow">
      <span><strong>The platform is not ready yet.</strong> Some templates are missing, so new machines cannot be created.</span>
      <a class="btn sm" href="#/platform">Open Platform<ArrowRight :size="14" /></a>
    </div>
  </div>

  <div class="stats">
    <Card tag="article">
      <div class="stat">
        <Server :size="20" class="si" aria-hidden="true" />
        <div><p class="label">Running machines</p><p class="value num"><Skeleton v-if="loading" w="40px" h="26px" /><template v-else>{{ running }}<span class="of"> of {{ machines.length }}</span></template></p></div>
      </div>
    </Card>
    <Card tag="article">
      <div class="stat">
        <Loader :size="20" class="si" :class="{ spin: inProgress }" aria-hidden="true" />
        <div><p class="label">Deployments in progress</p><p class="value num">{{ inProgress }}</p>
          <p class="hint small">{{ inProgress ? store.running.map((r) => r.label).join(', ') : 'Nothing running' }}</p></div>
      </div>
    </Card>
    <Card tag="article">
      <div class="stat">
        <Activity :size="20" class="si" aria-hidden="true" />
        <div>
          <p class="label">Last validation</p>
          <p v-if="lastValidation" class="value"><Badge :tone="lastValidation.last_validation === 'PASS' ? 'ok' : 'err'" :label="lastValidation.last_validation === 'PASS' ? 'Passed' : 'Failed'" /></p>
          <p v-else class="value muted small">No validation yet</p>
          <p v-if="lastValidation" class="hint small"><a :href="`#/${links.vm(lastValidation.environment, lastValidation.name)}`">{{ lastValidation.name }}</a> · {{ relTime(lastValidation.last_validation_at) }}</p>
        </div>
      </div>
    </Card>
    <Card tag="article">
      <div class="stat">
        <ShieldAlert :size="20" class="si" :class="{ warn: approvals + reviews }" aria-hidden="true" />
        <div>
          <p class="label">Pending approvals</p>
          <p class="value num">{{ approvals + reviews }}</p>
          <p class="hint small"><a v-if="approvals + reviews" href="#/review">{{ approvals }} production · {{ reviews }} AI drafts</a><template v-else>Nothing waiting</template></p>
        </div>
      </div>
    </Card>
  </div>

  <Card title="Recent activity" :icon="Activity" flush>
    <template #actions><a class="btn sm quiet" href="#/activity">View all</a></template>
    <DataTable :columns="COLS" :rows="activity" caption="Recent activity" :row-key="(r) => r.id" clickable empty="No activity yet. Create a VM to get started." @row="openRow">
      <template #cell-when="{ row }"><span class="num" :title="fullTime(row.timestamp)">{{ relTime(row.timestamp) }}</span></template>
      <template #cell-action="{ row }">{{ ACTION_LABEL[row.action] || row.action }}<span class="dim small"> · {{ ENV_LABEL[row.environment] }}</span></template>
      <template #cell-status="{ row }"><Badge :tone="STATUS_TONE[row.status] || 'muted'" :label="STATUS_LABEL[row.status] || row.status" /></template>
    </DataTable>
  </Card>
</template>

<style scoped>
.grow { flex: 1; justify-content: space-between; }
.stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.stat { display: flex; gap: 12px; align-items: flex-start; }
.si { color: var(--primary); margin-top: 2px; }
.si.warn { color: var(--warn-fg); }
.label { color: var(--mut); font-size: 13px; font-weight: 500; }
.value { font-size: 26px; font-weight: 700; line-height: 1.2; margin: 2px 0; min-height: 32px; display: flex; align-items: center; }
.value.small { font-size: 14px; font-weight: 400; }
.of { font-size: 14px; font-weight: 400; color: var(--dim); margin-left: 4px; }
.hint { color: var(--dim); overflow-wrap: anywhere; }
@media (max-width: 1100px) { .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 560px) { .stats { grid-template-columns: 1fr; } }
</style>
