<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { FileCode, ScanSearch } from 'lucide-vue-next'
import Badge from './ui/Badge.vue'
import Expandable from './ui/Expandable.vue'
import Skeleton from './ui/Skeleton.vue'
import { api } from '../api.js'
import { openDrawer } from './ui/drawer.js'

// Human-readable plan: what changes, how risky, why. The raw plan opens in a drawer.
const props = defineProps({ job: { type: Object, required: true } })
const plan = computed(() => props.job.result?.plan)
const review = ref(null)
const loading = ref(false)
const failed = ref('')

const ACTION = {
  create: { label: 'Create', tone: 'ok' }, update: { label: 'Change', tone: 'warn' },
  destroy: { label: 'Destroy', tone: 'err' }, replace: { label: 'Replace', tone: 'err' },
}
const RISK = { low: 'ok', medium: 'warn', high: 'err' }
function what(ch) {
  const a = ch.address
  if (a.includes('proxmox_download_file.ct')) return `LXC template ${ch.name}`
  if (a.includes('download_file')) return `Cloud image ${ch.name}`
  if (a.includes('.template[')) return `Template ${ch.name}`
  if (a.startsWith('module.lxc')) return `Container ${ch.name}`
  return `VM ${ch.name}`
}
const sentence = computed(() => {
  const c = plan.value?.counts
  if (!c) return ''
  if (!plan.value.changes.length) return 'Nothing will change. The infrastructure already matches.'
  const parts = []
  if (c.create) parts.push(`${c.create} to create`)
  if (c.update) parts.push(`${c.update} to change`)
  if (c.destroy) parts.push(`${c.destroy} to destroy`)
  return `${parts.join(', ')}.` + (c.destroy ? ' Data on destroyed machines is lost unless it is backed up.' : '')
})

async function load() {
  if (!plan.value?.text) return
  loading.value = true
  failed.value = ''
  try {
    review.value = await api.summarizePlan(plan.value.text, props.job.environment === 'prod' ? 'prod' : 'test') // platform plans are judged like Test
  } catch (e) {
    failed.value = e.message
  } finally {
    loading.value = false
  }
}
function full() {
  openDrawer({ title: 'Full plan', subtitle: `Job ${props.job.id}`, kind: 'plan', content: plan.value.text })
}
onMounted(load)
watch(() => props.job.id, load)
</script>

<template>
  <div class="pr">
    <div class="head">
      <p class="sentence"><strong>{{ plan?.summary }}</strong> {{ sentence }}</p>
      <button type="button" class="btn sm" @click="full"><FileCode :size="14" />View full plan</button>
    </div>
    <ul v-if="plan?.changes.length" class="changes">
      <li v-for="ch in plan.changes" :key="ch.address">
        <Badge :tone="ACTION[ch.action]?.tone" :label="ACTION[ch.action]?.label || ch.action" />
        <span>{{ what(ch) }}</span>
        <span v-if="ch.vm_id" class="dim small num">ID {{ ch.vm_id }}</span>
      </li>
    </ul>

    <div class="risk">
      <ScanSearch :size="16" class="ric" aria-hidden="true" />
      <template v-if="loading"><Skeleton w="110px" h="22px" radius="999px" /><Skeleton w="50%" h="12px" /></template>
      <template v-else-if="review">
        <Badge :tone="RISK[review.risk_level]" :label="`${review.risk_level[0].toUpperCase()}${review.risk_level.slice(1)} risk`" />
        <span class="dim small">{{ review.source === 'local-fallback' ? 'Assessed by local rules' : 'Assessed by Claude' }} · advisory only</span>
      </template>
      <span v-else-if="failed" class="dim small">Risk assessment unavailable: {{ failed }}</span>
    </div>
    <Expandable v-if="review" summary="Why?">
      <div class="why">
        <p>{{ review.summary }}</p>
        <h3 class="small">Check before you continue</h3>
        <ul><li v-for="c in review.recommended_checks" :key="c">{{ c }}</li></ul>
        <p class="dim small">{{ review.approval_recommendation }}</p>
      </div>
    </Expandable>
  </div>
</template>

<style scoped>
.pr { display: flex; flex-direction: column; gap: 12px; }
.head { display: flex; gap: 12px; align-items: flex-start; justify-content: space-between; flex-wrap: wrap; }
.sentence { max-width: 70ch; }
.changes { list-style: none; display: flex; flex-direction: column; gap: 6px; border: 1px solid var(--line); border-radius: var(--radius); padding: 10px 12px; background: var(--surface-2); }
.changes li { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.changes li .badge { min-width: 76px; }
.risk { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.ric { color: var(--mut); }
.why { display: flex; flex-direction: column; gap: 8px; max-width: 75ch; }
.why ul { padding-left: 18px; display: flex; flex-direction: column; gap: 2px; }
</style>
