<script setup>
import { computed } from 'vue'
import { CircleCheck, CircleX, Clock, LoaderCircle, Circle, ShieldAlert } from 'lucide-vue-next'

// Inline status of one operation. state: pending | running | success | failed | awaiting
const props = defineProps({
  state: { type: String, required: true },
  title: { type: String, required: true },
  text: { type: String, default: '' },
  details: { type: Boolean, default: false }, // show "Show details" (emits details)
})
const emit = defineEmits(['details'])
const M = {
  pending: { icon: Clock, label: 'Pending', cls: 'muted' },
  queued: { icon: Clock, label: 'Pending', cls: 'muted' },
  running: { icon: LoaderCircle, label: 'Running', cls: 'info' },
  success: { icon: CircleCheck, label: 'Success', cls: 'ok' },
  failed: { icon: CircleX, label: 'Failed', cls: 'err' },
  awaiting: { icon: ShieldAlert, label: 'Awaiting approval', cls: 'warn' },
  awaiting_approval: { icon: ShieldAlert, label: 'Awaiting approval', cls: 'warn' },
}
const m = computed(() => M[props.state] || { icon: Circle, label: props.state, cls: 'muted' })
</script>

<template>
  <div class="sc" :class="m.cls" role="status" aria-live="polite">
    <component :is="m.icon" :size="20" class="ic" :class="{ spin: m.cls === 'info' }" aria-hidden="true" />
    <div class="txt">
      <p class="t"><span class="sr-only">{{ m.label }}: </span>{{ title }}</p>
      <p v-if="text" class="d">{{ text }}</p>
      <slot />
    </div>
    <span class="lbl small">{{ m.label }}</span>
    <button v-if="details" type="button" class="btn sm" @click="emit('details')">Show details</button>
  </div>
</template>

<style scoped>
.sc { display: flex; align-items: center; gap: 12px; padding: 12px 14px; border: 1px solid var(--line); border-left-width: 4px; border-radius: var(--radius); background: var(--surface); flex-wrap: wrap; }
.ic { flex: none; }
.txt { flex: 1; min-width: 200px; }
.t { font-weight: 600; }
.d { color: var(--mut); font-size: 14px; }
.lbl { font-weight: 600; }
.ok { border-left-color: var(--ok-fg); } .ok .ic, .ok .lbl { color: var(--ok-fg); }
.err { border-left-color: var(--err-fg); background: var(--err-bg); } .err .ic, .err .lbl { color: var(--err-fg); }
.warn { border-left-color: var(--warn-fg); background: var(--warn-bg); } .warn .ic, .warn .lbl { color: var(--warn-fg); }
.info { border-left-color: var(--info-fg); } .info .ic, .info .lbl { color: var(--info-fg); }
.muted { border-left-color: var(--line-strong); } .muted .ic, .muted .lbl { color: var(--dim); }
</style>
