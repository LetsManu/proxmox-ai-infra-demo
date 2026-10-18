<script setup>
import { computed } from 'vue'
import { CircleCheck, CircleX } from 'lucide-vue-next'
import Badge from './ui/Badge.vue'
import CodeView from './ui/CodeView.vue'

// Content of an AI draft as a reviewer needs it: automated checks first, then the artefact.
const props = defineProps({ p: { type: Object, required: true } })
const c = computed(() => props.p.content || {})
</script>

<template>
  <div class="pv">
    <p class="muted small">Drafted by {{ p.source === 'local-rules' ? 'local rules' : p.source.replace('anthropic:', 'Claude ') }} for {{ p.created_by }}.
      {{ p.kind === 'role' ? 'Once approved it becomes a software profile for new machines.' : 'Once approved, Validate runs these checks and they gate promotion.' }}</p>
    <section>
      <h3>Automated safety checks</h3>
      <ul class="checks">
        <li v-for="ch in p.review.checks" :key="ch.name" :class="ch.ok ? 'ok' : 'bad'">
          <CircleCheck v-if="ch.ok" :size="16" aria-hidden="true" /><CircleX v-else :size="16" aria-hidden="true" />
          <span>{{ ch.name }}<span class="sr-only">{{ ch.ok ? ' passed' : ' failed' }}</span></span>
          <span v-if="ch.detail" class="dim small">{{ ch.detail }}</span>
        </li>
      </ul>
    </section>
    <template v-if="p.kind === 'role'">
      <section><h3>{{ c.label }} <span class="dim small">({{ c.os_family }}{{ c.port ? `, port ${c.port}` : '' }})</span></h3><p class="muted">{{ c.description }}</p></section>
      <section><h3>tasks/main.yml</h3><CodeView :text="c.tasks_yaml" kind="yaml" /></section>
      <section v-if="c.handlers_yaml"><h3>handlers/main.yml</h3><CodeView :text="c.handlers_yaml" kind="yaml" /></section>
      <section v-if="c.tests?.length"><h3>Tests shipped with the role</h3><CodeView :text="JSON.stringify(c.tests, null, 2)" kind="json" /></section>
    </template>
    <section v-else>
      <h3>{{ c.checks?.length }} checks</h3>
      <ul class="list">
        <li v-for="t in c.checks" :key="t.id">
          <Badge :tone="t.origin === 'ai' ? 'info' : 'muted'" :label="t.origin === 'ai' ? 'AI-drafted' : 'Rules'" />
          <span>{{ t.title }}</span>
          <span class="dim small mono">{{ t.type }}{{ t.port ? ` :${t.port}` : '' }}{{ t.path || '' }}</span>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.pv { display: flex; flex-direction: column; gap: 18px; }
h3 { margin-bottom: 6px; }
.checks, .list { list-style: none; display: flex; flex-direction: column; gap: 6px; }
.checks li, .list li { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.ok svg { color: var(--ok-fg); }
.bad svg { color: var(--err-fg); }
.list .badge { min-width: 90px; }
</style>
