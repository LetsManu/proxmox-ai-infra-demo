<script setup>
defineProps({
  summary: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  troubleshoot: { type: Object, default: null },
  troubleshootLoading: { type: Boolean, default: false },
  title: { type: String, default: 'AI plan review' },
})
</script>

<template>
  <section class="card ai-card">
    <div class="card-head">
      <h2>✨ {{ title }}</h2>
      <span v-if="summary" class="muted small">{{ summary.source }}</span>
    </div>

    <p v-if="loading" class="empty"><span class="spinner" />Analysing plan…</p>
    <p v-else-if="!summary && !troubleshoot && !troubleshootLoading" class="empty">
      The AI explains every plan in plain English and rates its risk.
    </p>

    <template v-if="summary && !loading">
      <div class="risk" :class="`risk-${summary.risk_level}`">Risk: {{ summary.risk_level.toUpperCase() }}</div>
      <p class="summary">{{ summary.summary }}</p>

      <div class="ai-lists">
        <div v-if="summary.resources_to_create?.length">
          <h4>Create</h4>
          <ul><li v-for="r in summary.resources_to_create" :key="r"><code>{{ r }}</code></li></ul>
        </div>
        <div v-if="summary.resources_to_update?.length">
          <h4>Update</h4>
          <ul><li v-for="r in summary.resources_to_update" :key="r"><code>{{ r }}</code></li></ul>
        </div>
        <div v-if="summary.resources_to_destroy?.length">
          <h4 class="danger-text">Destroy</h4>
          <ul><li v-for="r in summary.resources_to_destroy" :key="r"><code>{{ r }}</code></li></ul>
        </div>
      </div>

      <h4>Recommended pre-flight checks</h4>
      <ul class="checklist">
        <li v-for="c in summary.recommended_checks" :key="c">☐ {{ c }}</li>
      </ul>
      <p class="recommendation"><strong>Recommendation:</strong> {{ summary.approval_recommendation }}</p>
      <ul v-if="summary.warnings?.length" class="warnings"><li v-for="w in summary.warnings" :key="w">⚠ {{ w }}</li></ul>
      <p class="human-note">🧑‍⚖️ {{ summary.human_approval_note }}</p>
    </template>

    <p v-if="troubleshootLoading" class="empty"><span class="spinner" />Troubleshooting…</p>
    <div v-if="troubleshoot" class="troubleshoot">
      <h3>Troubleshooting <span class="muted small">{{ troubleshoot.source }}</span></h3>
      <p><strong>Likely cause:</strong> {{ troubleshoot.likely_cause }}</p>
      <h4>Immediate checks</h4>
      <ul><li v-for="c in troubleshoot.immediate_checks" :key="c">{{ c }}</li></ul>
      <h4>Safe remediation</h4>
      <ol><li v-for="c in troubleshoot.safe_remediation_steps" :key="c">{{ c }}</li></ol>
      <p>
        <span class="tag" :class="troubleshoot.recreate_appropriate ? 'tag-test' : 'tag-neutral'">
          Recreate {{ troubleshoot.recreate_appropriate ? 'appropriate' : 'not recommended' }}
        </span>
        {{ troubleshoot.recreate_reasoning }}
      </p>
      <p>
        <span class="tag" :class="troubleshoot.stateful_risk ? 'tag-prod' : 'tag-neutral'">
          {{ troubleshoot.stateful_risk ? 'Stateful risk' : 'Stateless' }}
        </span>
        {{ troubleshoot.stateful_notes }}
      </p>
    </div>
  </section>
</template>
