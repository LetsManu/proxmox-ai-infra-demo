<script setup>
import { computed } from 'vue'

const props = defineProps({
  job: { type: Object, default: null },
  stale: { type: Boolean, default: false },
  title: { type: String, default: 'Plan' },
  compact: { type: Boolean, default: false },
})

const plan = computed(() => props.job?.result?.plan)

function lineClass(line) {
  const t = line.trimStart()
  if (/will be (destroyed|replaced)|must be replaced/.test(line) || t.startsWith('-/+') || /^- /.test(t)) return 'l-destroy'
  if (t.startsWith('+')) return 'l-create'
  if (t.startsWith('~') || line.includes('updated in-place')) return 'l-update'
  if (t.startsWith('#')) return 'l-comment'
  if (t.startsWith('Plan:')) return 'l-summary'
  return ''
}
const lines = computed(() => (plan.value?.text || '').split('\n').map((text) => ({ text, cls: lineClass(text) })))
const label = { create: '+ create', update: '~ update', destroy: '- destroy', replace: '-/+ replace' }
</script>

<template>
  <section class="card">
    <div class="card-head">
      <h2>{{ title }}</h2>
      <span v-if="job" class="tag" :class="job.environment === 'prod' ? 'tag-prod' : 'tag-test'">
        {{ job.environment === 'prod' ? 'PRODUCTION' : 'TEST' }}
      </span>
    </div>

    <p v-if="!job" class="empty">Fill in the form and click <strong>Generate Plan</strong>.</p>
    <p v-else-if="job.status === 'running' || job.status === 'queued'" class="empty"><span class="spinner" />Planning…</p>
    <p v-else-if="job.status === 'failed' && !plan" class="banner error">Plan failed: {{ job.error }}</p>

    <template v-if="plan">
      <div class="counts">
        <span class="count create" :class="{ zero: !plan.counts.create }">+{{ plan.counts.create }} create</span>
        <span class="count update" :class="{ zero: !plan.counts.update }">~{{ plan.counts.update }} update</span>
        <span class="count destroy" :class="{ hot: plan.counts.destroy }">-{{ plan.counts.destroy }} destroy</span>
        <span v-if="job.result.vmid" class="muted small">VMID {{ job.result.vmid }} · template {{ job.result.template_id }}</span>
      </div>

      <div v-if="plan.has_destroy" class="banner destructive">
        ⛔ DESTRUCTIVE: this plan destroys or replaces existing VMs. Data on their disks will be lost.
      </div>
      <div v-if="stale" class="banner warn">The form changed after this plan was generated.</div>

      <ul class="changes">
        <li v-for="c in plan.changes" :key="c.address" :class="`chg-${c.action}`">
          <span class="chg-label">{{ label[c.action] || c.action }}</span>
          <code>{{ c.address }}</code>
        </li>
      </ul>

      <details :open="!compact">
        <summary>Full {{ plan.text.includes('OpenTofu') ? 'OpenTofu' : 'Terraform' }} plan output</summary>
        <pre class="plan"><span v-for="(l, i) in lines" :key="i" :class="l.cls">{{ l.text }}
</span></pre>
      </details>
    </template>
  </section>
</template>
