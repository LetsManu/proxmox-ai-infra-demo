<script setup>
import { computed, ref } from 'vue'
import { CircleCheck, CircleX, CircleMinus } from 'lucide-vue-next'
import { CHECK_LABEL } from './ui/format.js'

// Compact verdict per check; the individual tests are behind "Show details".
const props = defineProps({ result: { type: Object, required: true } })
const showTests = ref(false)
const checks = computed(() => props.result.checks || [])
const tests = computed(() => props.result.tests || [])
const failedTests = computed(() => tests.value.filter((t) => !t.ok))
</script>

<template>
  <div class="vc">
    <ul class="checks">
      <li v-for="c in checks" :key="c.name" :class="c.ok ? 'ok' : 'bad'">
        <CircleCheck v-if="c.ok" :size="17" aria-hidden="true" /><CircleX v-else :size="17" aria-hidden="true" />
        <span class="lbl">{{ CHECK_LABEL[c.name] || c.name }}<span class="sr-only">{{ c.ok ? ' passed' : ' failed' }}</span></span>
        <span class="det small">{{ c.detail }}</span>
      </li>
    </ul>
    <div v-if="tests.length" class="row">
      <button type="button" class="btn sm" :aria-expanded="showTests" @click="showTests = !showTests">
        {{ showTests ? 'Hide details' : `Show details (${tests.length} tests${failedTests.length ? `, ${failedTests.length} failed` : ''})` }}
      </button>
      <span class="dim small">{{ result.tests_reviewed ? 'Reviewed test suite' : 'Rules-based tests; draft and approve a suite for this application' }}</span>
    </div>
    <ul v-if="showTests" class="tests">
      <li v-for="t in tests" :key="t.id" :class="t.skipped ? 'skip' : t.ok ? 'ok' : 'bad'">
        <CircleMinus v-if="t.skipped" :size="15" aria-hidden="true" />
        <CircleCheck v-else-if="t.ok" :size="15" aria-hidden="true" /><CircleX v-else :size="15" aria-hidden="true" />
        <span class="lbl">{{ t.title }}</span>
        <span class="where small">{{ t.where === 'inside' ? 'on the machine' : 'from the network' }} · {{ t.origin === 'baseline' ? 'security' : t.origin === 'ai' ? 'AI-drafted' : 'rules' }}</span>
        <span class="det small mono">{{ t.detail }}</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.vc { display: flex; flex-direction: column; gap: 10px; }
.checks, .tests { list-style: none; border: 1px solid var(--line); border-radius: var(--radius); overflow: hidden; }
.checks li, .tests li { display: grid; grid-template-columns: 20px minmax(160px, 220px) minmax(0, 1fr); gap: 10px; align-items: center; padding: 8px 12px; }
.tests li { grid-template-columns: 18px minmax(180px, 1.2fr) 190px minmax(0, 1fr); }
li + li { border-top: 1px solid var(--line); }
.ok svg { color: var(--ok-fg); }
.bad { background: var(--err-bg); }
.bad svg { color: var(--err-fg); }
.skip svg { color: var(--dim); }
.lbl { font-weight: 500; }
.det, .where { color: var(--dim); overflow-wrap: anywhere; }
@media (max-width: 760px) {
  .checks li, .tests li { grid-template-columns: 20px minmax(0, 1fr); }
  .det, .where { grid-column: 2; }
}
</style>
