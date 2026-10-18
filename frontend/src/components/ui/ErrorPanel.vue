<script setup>
import { computed } from 'vue'
import { CircleAlert, RotateCcw } from 'lucide-vue-next'
import Expandable from './Expandable.vue'
import { friendly } from './errors.js'

// Friendly error: what failed, what to check, whether retry helps. Technical text behind a toggle.
const props = defineProps({
  what: { type: String, required: true }, // e.g. "The deployment failed"
  error: { type: String, default: '' },
  jobId: { type: String, default: '' },
  retry: { type: Boolean, default: false },
})
const emit = defineEmits(['retry', 'log'])
const f = computed(() => friendly(props.error || ''))
</script>

<template>
  <div class="ep" role="alert">
    <CircleAlert :size="20" class="ic" aria-hidden="true" />
    <div class="txt">
      <p class="t">{{ what }}</p>
      <p class="d">{{ f.summary }}</p>
      <p v-if="f.check" class="d"><strong>What to check:</strong> {{ f.check }}</p>
      <p class="d dim small">{{ f.retry && retry ? 'Retrying is safe once the cause is fixed.' : 'Retrying will not help until the cause is fixed.' }}</p>
      <div class="row acts">
        <button v-if="retry" type="button" class="btn sm" @click="emit('retry')"><RotateCcw :size="14" />Try again</button>
        <button v-if="jobId" type="button" class="btn sm quiet" @click="emit('log')">Open job log</button>
      </div>
      <Expandable summary="Show technical details">
        <pre class="code small">{{ error }}{{ jobId ? `\n\nJob ID: ${jobId}` : '' }}</pre>
      </Expandable>
    </div>
  </div>
</template>

<style scoped>
.ep { display: flex; gap: 12px; padding: 12px 14px; border: 1px solid var(--err-line); border-left: 4px solid var(--err-fg); background: var(--err-bg); border-radius: var(--radius); }
.ic { color: var(--err-fg); margin-top: 2px; }
.txt { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.t { font-weight: 600; }
.d { font-size: 14px; }
.acts { margin: 4px 0; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 240px; }
</style>
