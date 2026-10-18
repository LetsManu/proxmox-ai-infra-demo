<script setup>
import { computed } from 'vue'
import { ChevronDown, FileCode, OctagonAlert, TriangleAlert } from 'lucide-vue-next'
import StatusPill from './ui/StatusPill.vue'
import Skeleton from './ui/Skeleton.vue'

const props = defineProps({
  job: { type: Object, default: null },
  stale: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
  title: { type: String, default: 'Plan' },
  embedded: { type: Boolean, default: false },
})

const plan = computed(() => props.job?.result?.plan)

function lineClass(line) {
  const t = line.trimStart()
  if (/will be (destroyed|replaced)|must be replaced/.test(line) || t.startsWith('-/+') || /^- /.test(t)) return 'c-del'
  if (t.startsWith('+')) return 'c-add'
  if (t.startsWith('~') || line.includes('updated in-place')) return 'c-chg'
  if (t.startsWith('#')) return 'c-com'
  if (t.startsWith('Plan:')) return 'c-sum'
  return ''
}
const lines = computed(() => (plan.value?.text || '').split('\n').map((text) => ({ text, cls: lineClass(text) })))
const ACTION = {
  create: { label: 'Create', tone: 'ok' },
  update: { label: 'Update', tone: 'warn' },
  destroy: { label: 'Destroy', tone: 'err' },
  replace: { label: 'Replace', tone: 'err' },
}
const shortAddr = (a) => a.replace('.proxmox_virtual_environment_vm.this', '')
const tool = computed(() => (plan.value?.text.includes('OpenTofu') ? 'OpenTofu' : 'Terraform'))
</script>

<template>
  <component :is="embedded ? 'div' : 'section'" :class="{ card: !embedded }" aria-label="Plan">
    <div v-if="!embedded" class="card-head">
      <h2 class="title"><FileCode :size="17" />{{ title }}</h2>
      <StatusPill v-if="job" :tone="job.environment === 'prod' ? 'err' : 'info'" :label="job.environment === 'prod' ? 'Production' : 'Test'" />
    </div>

    <div :class="{ 'card-body': !embedded }">
      <div v-if="busy" class="loading" aria-busy="true">
        <Skeleton w="45%" h="14px" />
        <Skeleton h="12px" />
        <Skeleton w="80%" h="12px" />
      </div>
      <p v-else-if="!job" class="empty">
        <FileCode :size="18" />
        <span>Generate a plan to see exactly what will be created, change or destroy before anything happens.</span>
      </p>
      <div v-else-if="job.status === 'failed' && !plan" class="callout err" role="alert">
        <TriangleAlert :size="16" /><div><strong>Plan failed.</strong> {{ job.error }}</div>
      </div>

      <template v-if="plan && !busy">
        <div class="summary">
          <span class="stat"><b class="num">{{ plan.counts.create }}</b> to add</span>
          <span class="sep" />
          <span class="stat"><b class="num">{{ plan.counts.update }}</b> to change</span>
          <span class="sep" />
          <span class="stat" :class="{ hot: plan.counts.destroy }"><b class="num">{{ plan.counts.destroy }}</b> to destroy</span>
          <span v-if="job.result.vmid" class="meta mono">VMID {{ job.result.vmid }} · template {{ job.result.template_id }}</span>
        </div>

        <div v-if="plan.has_destroy" class="callout err" role="alert">
          <OctagonAlert :size="16" />
          <div><strong>Destructive change.</strong> Existing VMs are destroyed or replaced. Data on their disks is lost unless backed up.</div>
        </div>
        <div v-if="stale" class="callout warn">
          <TriangleAlert :size="16" /><div>The form changed after this plan was generated. Generate a new plan before deploying.</div>
        </div>

        <ul class="changes">
          <li v-for="c in plan.changes" :key="c.address">
            <StatusPill :tone="ACTION[c.action]?.tone || 'muted'" :label="ACTION[c.action]?.label || c.action" />
            <code>{{ shortAddr(c.address) }}</code>
          </li>
          <li v-if="!plan.changes.length" class="dim small">No changes. Infrastructure matches the configuration.</li>
        </ul>

        <details class="disclosure">
          <summary>{{ tool }} output <ChevronDown :size="15" /></summary>
          <pre class="code"><span v-for="(l, i) in lines" :key="i" :class="l.cls">{{ l.text }}
</span></pre>
        </details>
      </template>
    </div>
  </component>
</template>

<style scoped>
.loading { display: flex; flex-direction: column; gap: .6rem; padding: .25rem 0; }
.summary { display: flex; align-items: center; flex-wrap: wrap; gap: .75rem; margin-bottom: .85rem; }
.stat { font-size: .9rem; color: var(--mut); }
.stat b { color: var(--fg); font-size: 1.15rem; font-weight: 650; margin-right: .2rem; }
.stat.hot, .stat.hot b { color: var(--err); }
.sep { width: 1px; height: 18px; background: var(--line); }
.meta { margin-left: auto; color: var(--dim); font-size: .78rem; }
.callout { margin-bottom: .75rem; }
.changes { list-style: none; display: flex; flex-direction: column; gap: .45rem; margin-bottom: .5rem; }
.changes li { display: flex; align-items: center; gap: .6rem; min-width: 0; }
.changes code { color: var(--fg); overflow-wrap: anywhere; }
@media (max-width: 600px) { .meta { margin-left: 0; width: 100%; } }
</style>
