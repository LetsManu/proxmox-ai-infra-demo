<script setup>
import Badge from './ui/Badge.vue'

defineProps({ d: { type: Object, required: true } })
</script>

<template>
  <div class="dg">
    <p class="dim small">{{ d.source === 'local-fallback' ? 'From local rules' : 'From Claude' }} · advisory only, nothing was changed</p>
    <section><h3>Most likely cause</h3><p>{{ d.likely_cause }}</p></section>
    <section><h3>Check first</h3><ul><li v-for="c in d.immediate_checks" :key="c">{{ c }}</li></ul></section>
    <section><h3>Safe way to fix it</h3><ol><li v-for="c in d.safe_remediation_steps" :key="c">{{ c }}</li></ol></section>
    <div class="row">
      <Badge :tone="d.recreate_appropriate ? 'ok' : 'muted'" :label="d.recreate_appropriate ? 'Recreating is safe' : 'Recreating will not help'" />
      <Badge :tone="d.stateful_risk ? 'warn' : 'muted'" :label="d.stateful_risk ? 'May hold data' : 'No data at risk'" />
    </div>
    <p class="muted small">{{ d.recreate_reasoning }} {{ d.stateful_notes }}</p>
  </div>
</template>

<style scoped>
.dg { display: flex; flex-direction: column; gap: 16px; max-width: 70ch; }
h3 { margin-bottom: 4px; }
ul, ol { padding-left: 20px; display: flex; flex-direction: column; gap: 4px; }
</style>
