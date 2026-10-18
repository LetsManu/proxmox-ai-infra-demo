<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { Copy, SquareTerminal } from 'lucide-vue-next'
import StatusPill from './ui/StatusPill.vue'
import { toast } from './ui/toast.js'
import { ACTION_LABEL, ENV_LABEL, STATUS_LABEL, STATUS_TONE } from './ui/format.js'

const props = defineProps({ job: { type: Object, default: null } })
const pre = ref(null)
const follow = ref(true)

watch(
  () => props.job?.logs,
  async () => {
    await nextTick()
    if (pre.value && follow.value) pre.value.scrollTop = pre.value.scrollHeight
  },
)

function onScroll() {
  const el = pre.value
  follow.value = el.scrollHeight - el.scrollTop - el.clientHeight < 24
}

function cls(line) {
  if (/failed=0/.test(line)) return 'l-ok' // Ansible PLAY RECAP without failures
  if (/ERROR|FAIL|failed|fatal:|UNREACHABLE!|Permission denied|rejected/i.test(line)) return 'l-err'
  if (/Destroying|Destruction|DESTRUCTIVE/.test(line)) return 'l-warn'
  if (/complete|-> OK|PASS|ready/i.test(line)) return 'l-ok'
  if (line.includes('$ ') || line.includes('[mock]')) return 'l-cmd'
  return ''
}
const lines = computed(() =>
  (props.job?.logs || '')
    .trimEnd()
    .split('\n')
    .map((l) => {
      const m = l.match(/^\[(\d\d:\d\d:\d\d)\] ?(.*)$/)
      return m ? { t: m[1], text: m[2], cls: cls(m[2]) } : { t: '', text: l, cls: cls(l) }
    }),
)

async function copy() {
  try {
    await navigator.clipboard.writeText(props.job.logs)
    toast.success('Log copied to the clipboard.')
  } catch {
    toast.error('The browser blocked clipboard access.')
  }
}
</script>

<template>
  <section class="card" aria-labelledby="log-title">
    <div class="card-head">
      <h2 id="log-title" class="title">
        <SquareTerminal :size="17" />Job log
        <span v-if="job" class="sub">{{ ACTION_LABEL[job.action] || job.action }} · {{ ENV_LABEL[job.environment] }} · <span class="mono">{{ job.vm_name }}</span></span>
      </h2>
      <div v-if="job" class="head-right">
        <StatusPill :tone="STATUS_TONE[job.status]" :label="STATUS_LABEL[job.status]" />
        <button type="button" class="btn quiet icon" aria-label="Copy log" title="Copy log" @click="copy"><Copy :size="16" /></button>
      </div>
    </div>
    <div class="card-body">
      <p v-if="!job" class="empty"><SquareTerminal :size="18" /><span>Output of the running job streams here: OpenTofu, Proxmox API calls and validation steps.</span></p>
      <pre v-else ref="pre" class="code log" tabindex="0" aria-label="Job output" @scroll="onScroll"><span v-for="(l, i) in lines" :key="i" class="line"><span class="ts">{{ l.t }}</span><span :class="l.cls">{{ l.text }}</span>
</span></pre>
      <div v-if="job?.error" class="callout err err-box" role="alert"><span><strong>Error.</strong> {{ job.error }}</span></div>
    </div>
  </section>
</template>

<style scoped>
.head-right { display: flex; align-items: center; gap: .35rem; }
.log { max-height: 320px; min-height: 140px; margin: 0; }
.line { display: block; }
.ts { color: #56606b; margin-right: 1.1rem; user-select: none; }
.l-err { color: #ff8f8f; }
.l-warn { color: #f3c969; }
.l-ok { color: #7ee2a0; }
.l-cmd { color: #8fc3ff; }
.err-box { margin-top: .75rem; }
@media (max-width: 720px) { .sub { display: none; } .ts { display: none; } }
</style>
