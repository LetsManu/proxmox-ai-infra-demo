<script setup>
import { computed } from 'vue'
import { Check, X } from 'lucide-vue-next'

// steps: [{ key, label, detail, state: 'done' | 'current' | 'error' | 'todo' }]
const props = defineProps({ steps: { type: Array, required: true } })
const current = computed(() => props.steps.findIndex((s) => s.state === 'current' || s.state === 'error'))
</script>

<template>
  <nav class="steps" aria-label="Workflow progress">
    <p class="compact">
      Step {{ (current < 0 ? steps.length : current + 1) }} of {{ steps.length }}:
      <strong>{{ (steps[current] || steps[steps.length - 1]).label }}</strong>
    </p>
    <ol>
      <li v-for="(s, i) in steps" :key="s.key" :class="s.state" :aria-current="s.state === 'current' ? 'step' : undefined">
        <span class="dot">
          <Check v-if="s.state === 'done'" :size="13" :stroke-width="3" />
          <X v-else-if="s.state === 'error'" :size="13" :stroke-width="3" />
          <span v-else class="n">{{ i + 1 }}</span>
        </span>
        <span class="txt">
          <span class="label">{{ s.label }}</span>
          <span class="detail">{{ s.detail || ' ' }}</span>
        </span>
      </li>
    </ol>
  </nav>
</template>

<style scoped>
.steps { border-bottom: 1px solid var(--line); background: var(--bg); }
ol { list-style: none; display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); max-width: 1440px; margin: 0 auto; padding: .85rem var(--pad-x); gap: .5rem; }
li { display: flex; align-items: center; gap: .6rem; position: relative; min-width: 0; }
li:not(:last-child)::after { content: ''; flex: 1; height: 1px; background: var(--line-strong); margin-left: .25rem; min-width: 12px; }
li.done:not(:last-child)::after { background: rgba(74, 222, 128, .45); }
.dot {
  width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center; flex: none;
  border: 1.5px solid var(--line-strong); color: var(--dim); font-size: .75rem; font-weight: 600;
}
.done .dot { background: var(--tone-ok); border-color: transparent; color: var(--ok); }
.current .dot { border-color: var(--acc); color: var(--acc); box-shadow: 0 0 0 3px var(--acc-tone); }
.error .dot { background: var(--tone-err); border-color: transparent; color: var(--err); }
.txt { display: flex; flex-direction: column; min-width: 0; }
.label { font-size: .84rem; font-weight: 600; color: var(--mut); white-space: nowrap; }
.current .label, .error .label { color: var(--fg); }
.done .label { color: var(--fg); }
.detail { font-size: .74rem; color: var(--dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.error .detail { color: var(--err); }
.compact { display: none; padding: .7rem var(--pad-x); font-size: .88rem; color: var(--mut); }
.compact strong { color: var(--fg); }
@media (max-width: 1100px) { li:not(:last-child)::after { display: none; } }
@media (max-width: 860px) { ol { display: none; } .compact { display: block; } }
</style>
