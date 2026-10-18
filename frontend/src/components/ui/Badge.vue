<script setup>
import { computed } from 'vue'
import { CircleCheck, CircleX, Clock, Info, Circle, LoaderCircle } from 'lucide-vue-next'

// Status badge. Never colour alone: always an icon and a word.
// tone: ok | warn | err | info | muted | running
const props = defineProps({
  tone: { type: String, default: 'muted' },
  label: { type: String, default: '' },
  icon: { type: [Object, Function], default: null },
})
const DEFAULT = { ok: CircleCheck, warn: Clock, err: CircleX, info: Info, muted: Circle, running: LoaderCircle }
const ic = computed(() => props.icon || DEFAULT[props.tone] || Circle)
</script>

<template>
  <span class="badge" :class="tone"><component :is="ic" :size="13" :class="{ spin: tone === 'running' }" aria-hidden="true" /><span><slot>{{ label }}</slot></span></span>
</template>

<style scoped>
.badge {
  display: inline-flex; align-items: center; gap: 5px; padding: 2px 8px 2px 6px; border-radius: 999px; border: 1px solid;
  font-size: 12px; font-weight: 600; line-height: 1.5; white-space: nowrap; max-width: 100%;
}
.badge > span { overflow: hidden; text-overflow: ellipsis; }
.ok { background: var(--ok-bg); color: var(--ok-fg); border-color: var(--ok-line); }
.warn { background: var(--warn-bg); color: var(--warn-fg); border-color: var(--warn-line); }
.err { background: var(--err-bg); color: var(--err-fg); border-color: var(--err-line); }
.info, .running { background: var(--info-bg); color: var(--info-fg); border-color: var(--info-line); }
.muted { background: var(--muted-bg); color: var(--mut); border-color: var(--line); }
</style>
