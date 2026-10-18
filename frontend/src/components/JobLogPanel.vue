<script setup>
import { nextTick, ref, watch } from 'vue'

const props = defineProps({ job: { type: Object, default: null } })
const pre = ref(null)

watch(
  () => props.job?.logs,
  async () => {
    await nextTick()
    if (pre.value) pre.value.scrollTop = pre.value.scrollHeight
  },
)

function cls(line) {
  if (/ERROR|FAIL|failed|Permission denied|rejected/i.test(line)) return 'log-err'
  if (/Destroying|destroyed|DESTRUCTIVE/.test(line)) return 'log-warn'
  if (/complete|PASS|OK:|Apply complete|-> OK/.test(line)) return 'log-ok'
  if (line.includes('$ ') || line.includes('[mock]')) return 'log-cmd'
  return ''
}
</script>

<template>
  <section class="card">
    <div class="card-head">
      <h2>Job log</h2>
      <div v-if="job" class="row">
        <span class="muted small">{{ job.action }} · {{ job.environment }} · {{ job.vm_name }} · <code>{{ job.id.slice(0, 8) }}</code></span>
        <span class="status" :class="`st-${job.status}`">{{ job.status }}</span>
      </div>
    </div>
    <p v-if="!job" class="empty">Logs of the running job stream here (polling every second).</p>
    <pre v-else ref="pre" class="log"><span v-for="(l, i) in job.logs.split('\n')" :key="i" :class="cls(l)">{{ l }}
</span></pre>
    <p v-if="job?.error" class="banner error">{{ job.error }}</p>
  </section>
</template>
