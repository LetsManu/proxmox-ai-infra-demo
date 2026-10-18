<script setup>
import { ref, watch } from 'vue'
import { ScanSearch, ShieldCheck, TriangleAlert } from 'lucide-vue-next'
import StatusPill from './ui/StatusPill.vue'
import Skeleton from './ui/Skeleton.vue'

const props = defineProps({
  summary: { type: Object, default: null },
  loading: { type: Boolean, default: false },
})

const RISK = { low: 'ok', medium: 'warn', high: 'err' }
const checked = ref({})
watch(() => props.summary, () => (checked.value = {}))
const source = (s) => (s === 'local-fallback' ? 'Local rules' : s?.replace('anthropic:', 'Claude · '))
</script>

<template>
  <section class="card" aria-labelledby="review-title">
    <div class="card-head">
      <h2 id="review-title" class="title"><ScanSearch :size="17" />Plan review</h2>
      <span v-if="summary" class="dim small">{{ source(summary.source) }}</span>
    </div>
    <div class="card-body">
      <div v-if="loading" class="loading" aria-busy="true">
        <Skeleton w="90px" h="22px" radius="99px" />
        <Skeleton h="12px" /><Skeleton w="85%" h="12px" /><Skeleton w="60%" h="12px" />
      </div>
      <p v-else-if="!summary" class="empty">
        <ScanSearch :size="18" />
        <span>After each plan the assistant explains it in plain language, rates the risk and lists checks to do first. It can't approve or apply anything.</span>
      </p>
      <template v-else>
        <div class="risk-row">
          <StatusPill :tone="RISK[summary.risk_level]" :label="`${summary.risk_level[0].toUpperCase()}${summary.risk_level.slice(1)} risk`" />
          <span v-if="summary.resources_to_destroy?.length" class="small err-text">
            {{ summary.resources_to_destroy.length }} resource{{ summary.resources_to_destroy.length > 1 ? 's' : '' }} destroyed
          </span>
        </div>
        <p class="text">{{ summary.summary }}</p>

        <h3 class="section-label">Before you continue</h3>
        <ul class="checks">
          <li v-for="(c, i) in summary.recommended_checks" :key="c">
            <label class="check"><input v-model="checked[i]" type="checkbox" /><span :class="{ done: checked[i] }">{{ c }}</span></label>
          </li>
        </ul>

        <h3 class="section-label">Recommendation</h3>
        <p class="text">{{ summary.approval_recommendation }}</p>

        <ul v-if="summary.warnings?.length" class="warn-list">
          <li v-for="w in summary.warnings" :key="w"><TriangleAlert :size="14" />{{ w }}</li>
        </ul>
        <p class="note"><ShieldCheck :size="15" />Production changes always need a person to approve them.</p>
      </template>
    </div>
  </section>
</template>

<style scoped>
.loading { display: flex; flex-direction: column; gap: .6rem; }
.risk-row { display: flex; align-items: center; gap: .75rem; margin-bottom: .6rem; }
.err-text { color: var(--err); }
.text { color: var(--mut); font-size: .9rem; }
.checks { list-style: none; display: flex; flex-direction: column; gap: .1rem; }
.check { align-items: flex-start; font-size: .88rem; color: var(--fg); }
.check input { margin-top: .2rem; }
.check .done { color: var(--dim); text-decoration: line-through; }
.warn-list { list-style: none; margin-top: .75rem; font-size: .82rem; color: #ffe2b0; }
.warn-list li { display: flex; gap: .4rem; align-items: flex-start; }
.warn-list svg { color: var(--warn); margin-top: .2rem; }
.note { display: flex; gap: .45rem; align-items: center; margin-top: 1rem; padding-top: .8rem; border-top: 1px solid var(--line); font-size: .82rem; color: var(--dim); }
</style>
