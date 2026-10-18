<script setup>
import { computed } from 'vue'
import { CircleCheck, CircleAlert, CircleX, Clock, Info, Circle } from 'lucide-vue-next'

// Never colour alone: every pill has an icon and a text.
const props = defineProps({
  tone: { type: String, default: 'muted' }, // ok | warn | err | info | muted | acc
  label: { type: String, default: '' },
  icon: { type: [Object, Function], default: null },
})
const DEFAULT = { ok: CircleCheck, warn: Clock, err: CircleX, info: Info, muted: Circle, acc: CircleAlert }
const ic = computed(() => props.icon || DEFAULT[props.tone])
</script>

<template>
  <span class="pill" :class="tone"><component :is="ic" :size="14" aria-hidden="true" /><span><slot>{{ label }}</slot></span></span>
</template>

<style scoped>
.pill {
  display: inline-flex; align-items: center; gap: .35rem; padding: .18rem .6rem .18rem .45rem; border-radius: 99px;
  font-size: .78rem; font-weight: 600; line-height: 1.4; white-space: nowrap; max-width: 100%;
}
.pill > span { overflow: hidden; text-overflow: ellipsis; }
.ok { background: var(--tone-ok); color: var(--ok); }
.warn { background: var(--tone-warn); color: var(--warn); }
.err { background: var(--tone-err); color: var(--err); }
.info { background: var(--tone-info); color: var(--info); }
.muted { background: var(--tone-muted); color: var(--mut); }
.acc { background: var(--acc-tone); color: var(--acc); }
</style>
