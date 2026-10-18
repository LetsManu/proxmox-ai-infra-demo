<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { FlaskConical, Sparkles } from 'lucide-vue-next'
import Card from './ui/Card.vue'
import Badge from './ui/Badge.vue'
import Expandable from './ui/Expandable.vue'
import { api } from '../api.js'
import { refresh, store } from '../store.js'
import { toast } from './ui/toast.js'
import { go } from '../router.js'

// What Validate will run for this machine: security baseline + application tests.
const props = defineProps({ name: { type: String, required: true }, env: { type: String, required: true }, version: { type: Number, default: 0 } })
const suite = ref(null)
const drafting = ref(false)
const pending = computed(() => (store.proposals || []).find((p) => p.kind === 'tests' && p.target === props.name.replace(/-test$/, '')))
const groups = computed(() => {
  const c = suite.value?.checks || []
  return { baseline: c.filter((x) => x.origin === 'baseline'), app: c.filter((x) => x.origin !== 'baseline') }
})

async function load() {
  try {
    suite.value = await api.tests(props.name, props.env)
  } catch {
    suite.value = null
  }
}
async function draft() {
  drafting.value = true
  try {
    const p = await api.draftTests(props.name, props.env)
    await refresh()
    if (p.review.ok) {
      toast.success(`${p.content.checks.length} checks drafted. They are used after you approve them.`, {
        title: 'Tests drafted', action: { label: 'Open review queue', run: () => go('review') },
      })
    } else toast.error('The drafted tests did not pass the automated checks.', { title: 'Draft rejected' })
  } catch (e) {
    toast.error(e.message, { title: 'Could not draft tests' })
  } finally {
    drafting.value = false
  }
}
onMounted(load)
watch(() => [props.version, store.proposals?.length], load)
</script>

<template>
  <Card title="Automated tests" :icon="FlaskConical" subtitle="Run by Validate; failing tests block promotion">
    <template #actions>
      <Badge v-if="suite" :tone="suite.approved ? 'ok' : 'muted'" :label="suite.approved ? 'Reviewed suite' : 'Rules only'" />
    </template>
    <div class="stack-v">
      <p v-if="suite" class="muted">
        {{ groups.baseline.length }} security checks always run.
        {{ groups.app.length }} application checks {{ suite.approved ? 'come from the approved suite' : 'come from the installed software' }}.
      </p>
      <Expandable v-if="suite" summary="Show the checks">
        <ul class="list">
          <li v-for="c in suite.checks" :key="c.id">
            <Badge :tone="c.origin === 'baseline' ? 'info' : 'muted'" :label="c.origin === 'baseline' ? 'Security' : c.origin === 'ai' ? 'AI-drafted' : 'Rules'" />
            <span>{{ c.title }}</span><span class="dim small">{{ c.where === 'inside' ? 'on the machine' : 'from the network' }}</span>
          </li>
        </ul>
      </Expandable>
      <div v-if="pending" class="callout warn" role="status"><span>A drafted test suite waits for review. <a href="#/review">Open the review queue</a>.</span></div>
    </div>
    <template v-if="env === 'test'" #footer>
      <span class="dim small">The assistant proposes checks for this application; a person approves them.</span>
      <span class="spacer" />
      <button type="button" class="btn" :disabled="drafting || !!pending" :aria-busy="drafting" @click="draft">
        <span v-if="drafting" class="spinner" /><Sparkles v-else :size="16" />Draft tests with assistant
      </button>
    </template>
  </Card>
</template>

<style scoped>
.list { list-style: none; display: flex; flex-direction: column; gap: 6px; }
.list li { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.list .badge { min-width: 86px; }
</style>
