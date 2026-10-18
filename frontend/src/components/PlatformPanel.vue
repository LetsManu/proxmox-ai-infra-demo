<script setup>
import { computed } from 'vue'
import { Boxes, ChevronDown, Copy, Hammer, RefreshCw } from 'lucide-vue-next'
import PlanPanel from './PlanPanel.vue'
import StatusPill from './ui/StatusPill.vue'
import Skeleton from './ui/Skeleton.vue'
import { toast } from './ui/toast.js'

const props = defineProps({
  status: { type: Object, default: null },
  planJob: { type: Object, default: null },
  busy: { type: String, default: '' },
})
const emit = defineEmits(['plan', 'apply', 'refresh'])

const TONE = { present: 'ok', missing: 'err', unknown: 'muted' }
const OWNER = { bootstrap: 'Bootstrap (admin, once)', platform: 'This console', manual: 'Provided once' }
const presentCount = computed(() => props.status?.resources.filter((r) => r.status === 'present').length || 0)
const missingManual = computed(() => props.status?.resources.filter((r) => r.owner === 'manual' && r.status === 'missing') || [])
const canApply = computed(
  () => props.planJob?.status === 'success' && !props.planJob.result?.applied && props.planJob.result?.plan?.changes?.length,
)
const BOOTSTRAP_CMD = 'infra/scripts/bootstrap.sh -var node_name=pve'

async function copyCmd() {
  try {
    await navigator.clipboard.writeText(BOOTSTRAP_CMD)
    toast.success('Command copied.')
  } catch {
    toast.error('The browser blocked clipboard access.')
  }
}
</script>

<template>
  <section class="card" aria-labelledby="pf-title">
    <div class="card-head">
      <h2 id="pf-title" class="title"><Boxes :size="17" />Platform</h2>
      <div class="head-right">
        <StatusPill v-if="status" :tone="status.ready ? 'ok' : status.reachable ? 'warn' : 'err'"
          :label="status.ready ? 'Ready' : status.reachable ? 'Resources missing' : 'Unreachable'" />
        <button type="button" class="btn quiet icon" aria-label="Refresh platform status" title="Refresh" @click="emit('refresh')"><RefreshCw :size="15" /></button>
      </div>
    </div>
    <div class="card-body">
      <p class="intro small muted">
        Everything VMs depend on. The console builds what it may (cloud images and templates, as OpenTofu code);
        identity, storage and networks come from a one-time admin bootstrap.
      </p>

      <div v-if="!status" class="loading"><Skeleton h="12px" /><Skeleton h="12px" /><Skeleton w="70%" h="12px" /></div>
      <details v-else class="disclosure" :open="!status.ready">
        <summary>{{ presentCount }} of {{ status.resources.length }} resources present <ChevronDown :size="15" /></summary>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Type</th><th>Resource</th><th>Purpose</th><th>Created by</th><th>Status</th></tr></thead>
          <tbody>
            <tr v-for="r in status.resources" :key="r.kind + r.name">
              <td data-label="Type">{{ r.kind }}</td>
              <td data-label="Resource" class="mono">{{ r.name }}</td>
              <td data-label="Purpose" class="muted">{{ r.detail }}</td>
              <td data-label="Created by" class="muted">{{ OWNER[r.owner] }}</td>
              <td data-label="Status"><StatusPill :tone="r.status === 'missing' && r.owner === 'manual' ? 'warn' : TONE[r.status]" :label="r.status === 'present' ? 'Present' : r.status === 'missing' ? 'Missing' : 'Unknown'" /></td>
            </tr>
          </tbody>
        </table>
      </div>
      </details>

      <div v-if="status?.needs_bootstrap" class="callout warn">
        <div>
          <strong>Bootstrap needed.</strong> An administrator runs this once from a workstation with admin credentials
          (the console never holds them):
          <div class="cmd"><code>{{ BOOTSTRAP_CMD }}</code><button type="button" class="btn sm" @click="copyCmd"><Copy :size="13" />Copy</button></div>
        </div>
      </div>
      <div v-if="missingManual.length" class="callout info">
        <div><strong>Windows template.</strong> Microsoft publishes no redistributable cloud image, so it is provided once
          (sysprep + cloudbase-init). Guide: <code>docs/windows-template.md</code>.</div>
      </div>

      <div v-if="status && status.needs_platform_apply" class="actions">
        <button type="button" class="btn" :class="{ primary: !canApply }" :disabled="!!busy" :aria-busy="busy === 'platform-plan'" @click="emit('plan')">
          <span v-if="busy === 'platform-plan'" class="spinner" /><Hammer v-else :size="14" />Prepare Platform
        </button>
        <button v-if="canApply" type="button" class="btn primary" :disabled="!!busy" :aria-busy="busy === 'platform-apply'" @click="emit('apply')">
          <span v-if="busy === 'platform-apply'" class="spinner" />Build templates
        </button>
        <span class="small dim">Plan first, then build: downloads the official cloud images and creates the templates.</span>
      </div>

      <div v-if="planJob && planJob.result?.plan && !planJob.result.applied" class="plan-box"><PlanPanel :job="planJob" embedded /></div>
    </div>
  </section>
</template>

<style scoped>
.head-right { display: flex; align-items: center; gap: .3rem; }
.intro { margin-bottom: .6rem; }
.loading { display: flex; flex-direction: column; gap: .5rem; }
.table-wrap { margin-top: .4rem; overflow-x: auto; border: 1px solid var(--line); border-radius: var(--radius); }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; font-weight: 700; padding: .4rem .7rem; background: var(--surface-2); border-bottom: 1px solid var(--line); white-space: nowrap; }
td { padding: .35rem .7rem; border-bottom: 1px solid #404040; vertical-align: middle; }
tbody tr:last-child td { border-bottom: 0; }
.callout { margin-top: .7rem; }
.cmd { display: flex; align-items: center; gap: .5rem; margin-top: .4rem; flex-wrap: wrap; }
.cmd code { background: #1b1b1b; padding: .25rem .5rem; border-radius: 3px; color: var(--fg); }
.actions { display: flex; align-items: center; flex-wrap: wrap; gap: .5rem; margin-top: .8rem; }
.plan-box { margin-top: .8rem; border: 1px solid var(--line); border-radius: var(--radius); padding: .7rem .8rem; background: var(--surface-2); }
@media (max-width: 720px) {
  thead { display: none; }
  table, tbody, tr, td { display: block; width: 100%; }
  tr { padding: .5rem .7rem; border-bottom: 1px solid var(--line); }
  td { border: 0; padding: .1rem 0; display: flex; justify-content: space-between; gap: 1rem; text-align: right; }
  td::before { content: attr(data-label); color: var(--dim); font-size: 12px; text-align: left; }
}
</style>
