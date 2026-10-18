<script setup>
import { Check, X } from 'lucide-vue-next'

// Horizontal steps. state: done | current | error | todo
defineProps({ steps: { type: Array, required: true }, label: { type: String, default: 'Progress' } })
</script>

<template>
  <ol class="steps" :aria-label="label">
    <li v-for="(s, i) in steps" :key="s.key" :class="s.state" :aria-current="s.state === 'current' ? 'step' : undefined">
      <span class="dot" aria-hidden="true">
        <Check v-if="s.state === 'done'" :size="13" />
        <X v-else-if="s.state === 'error'" :size="13" />
        <template v-else>{{ i + 1 }}</template>
      </span>
      <span class="txt">
        <span class="name">{{ s.label }}<span class="sr-only">: {{ { done: 'done', current: 'current step', error: 'failed', todo: 'not started' }[s.state] }}</span></span>
        <span v-if="s.detail" class="detail">{{ s.detail }}</span>
      </span>
      <span v-if="i < steps.length - 1" class="bar" aria-hidden="true" />
    </li>
  </ol>
</template>

<style scoped>
.steps { list-style: none; display: flex; }
li:not(:last-child) { flex: 1; }
li { display: flex; align-items: flex-start; gap: 8px; min-width: 0; }
.bar { flex: 1; min-width: 12px; height: 2px; margin: 11px 8px 0 0; background: var(--line); border-radius: 1px; }
li.done .bar { background: var(--ok-fg); }
.dot {
  position: relative; z-index: 1; width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center; flex: none;
  font-size: 12px; font-weight: 700; background: var(--surface); border: 2px solid var(--line-strong); color: var(--dim);
}
.done .dot { background: var(--ok-fg); border-color: var(--ok-fg); color: var(--surface); }
.current .dot { border-color: var(--primary); color: var(--primary); box-shadow: 0 0 0 3px var(--info-bg); }
.error .dot { background: var(--err-fg); border-color: var(--err-fg); color: var(--surface); }
.txt { display: flex; flex-direction: column; min-width: 0; padding-top: 2px; }
.name { font-size: 13px; font-weight: 600; white-space: nowrap; }
.todo .name { color: var(--dim); font-weight: 500; }
.detail { font-size: 12px; color: var(--dim); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.error .detail { color: var(--err-fg); }
@media (max-width: 860px) {
  .steps { flex-direction: column; gap: 10px; }
  .bar { display: none; }
}
</style>
