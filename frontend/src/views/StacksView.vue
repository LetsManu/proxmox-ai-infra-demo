<script setup>
import { computed } from 'vue'
import { Boxes, Plus } from 'lucide-vue-next'
import PageHeader from '../layout/PageHeader.vue'
import Card from '../components/ui/Card.vue'
import Badge from '../components/ui/Badge.vue'
import DataTable from '../components/ui/DataTable.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import { store } from '../store.js'
import { go, links } from '../router.js'
import { ENV_LABEL, relTime } from '../components/ui/format.js'

const COLS = [
  { key: 'name', label: 'Stack', mono: true },
  { key: 'environment', label: 'Environment' },
  { key: 'members', label: 'Machines' },
  { key: 'last_validation', label: 'Validation' },
  { key: 'deployed_at', label: 'Deployed' },
]
const rows = computed(() => store.stacks)
</script>

<template>
  <PageHeader title="Stacks" subtitle="Several VMs, containers and Docker services that are deployed, tested and promoted together.">
    <button type="button" class="btn primary" @click="go('stack-new')"><Plus :size="16" />Create stack</button>
  </PageHeader>
  <Card flush>
    <EmptyState v-if="rows && !rows.length" :icon="Boxes" title="No stacks yet"
      text="Describe an application, for example “WordPress with monitoring”, and the assistant proposes the machines and services it needs.">
      <button type="button" class="btn primary" @click="go('stack-new')"><Plus :size="16" />Create stack</button>
    </EmptyState>
    <DataTable v-else :columns="COLS" :rows="rows" caption="Stacks" :row-key="(r) => r.environment + r.name" clickable @row="(r) => go(links.stack(r.environment, r.name))">
      <template #cell-environment="{ row }"><Badge :tone="row.environment === 'prod' ? 'err' : 'info'" :label="ENV_LABEL[row.environment]" /></template>
      <template #cell-members="{ row }">{{ row.members.length }} <span class="dim small">({{ row.members.map((m) => m.kind === 'lxc' ? 'CT' : 'VM').join(', ') }})</span></template>
      <template #cell-last_validation="{ row }">
        <Badge v-if="row.last_validation" :tone="row.last_validation === 'PASS' ? 'ok' : 'err'" :label="row.last_validation === 'PASS' ? 'Passed' : 'Failed'" />
        <span v-else class="dim">Not validated</span>
      </template>
      <template #cell-deployed_at="{ row }">{{ relTime(row.deployed_at) }}</template>
    </DataTable>
  </Card>
</template>
