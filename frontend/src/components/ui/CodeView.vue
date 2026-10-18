<script setup>
import { computed } from 'vue'

// Read-only code with light syntax highlighting for plans, logs, YAML and JSON.
const props = defineProps({ text: { type: String, default: '' }, kind: { type: String, default: 'text' } })

function planClass(line) {
  const t = line.trimStart()
  if (/will be (destroyed|replaced)|must be replaced/.test(line) || t.startsWith('-/+') || /^- /.test(t)) return 'c-del'
  if (t.startsWith('+')) return 'c-add'
  if (t.startsWith('~') || line.includes('updated in-place')) return 'c-chg'
  if (t.startsWith('#')) return 'c-com'
  if (t.startsWith('Plan:') || t.startsWith('Apply complete')) return 'c-sum'
  return ''
}
function logClass(line) {
  if (/failed=0/.test(line)) return 'c-add'
  if (/ERROR|FAIL\b|fatal:|UNREACHABLE!|Permission denied|failed:/i.test(line)) return 'c-del'
  if (/Destroying|Destruction|SKIP|WARN/i.test(line)) return 'c-chg'
  if (/complete|-> OK|PASS|passed|ok:/i.test(line)) return 'c-add'
  if (/^\$ |\[mock\]|^TASK |^PLAY /.test(line.replace(/^\[\d\d:\d\d:\d\d\] /, ''))) return 'c-key'
  return ''
}
function yamlParts(line) {
  if (/^\s*#/.test(line)) return [{ t: line, c: 'c-com' }]
  const m = line.match(/^(\s*-?\s*)([A-Za-z0-9_.@-]+)(:)(.*)$/)
  if (!m) return [{ t: line, c: '' }]
  return [{ t: m[1], c: '' }, { t: m[2], c: 'c-key' }, { t: m[3], c: '' }, { t: m[4], c: /^\s*["']/.test(m[4]) ? 'c-str' : '' }]
}
function jsonParts(line) {
  const m = line.match(/^(\s*)("[^"]+")(\s*:\s*)(.*)$/)
  if (!m) return [{ t: line, c: '' }]
  return [{ t: m[1], c: '' }, { t: m[2], c: 'c-key' }, { t: m[3], c: '' }, { t: m[4], c: m[4].startsWith('"') ? 'c-str' : '' }]
}

const lines = computed(() =>
  props.text.replace(/\s+$/, '').split('\n').map((l) => {
    if (props.kind === 'plan') return [{ t: l, c: planClass(l) }]
    if (props.kind === 'log') return [{ t: l, c: logClass(l) }]
    if (props.kind === 'yaml') return yamlParts(l)
    if (props.kind === 'json') return jsonParts(l)
    return [{ t: l, c: '' }]
  }),
)
</script>

<template>
  <pre class="code" tabindex="0"><span v-for="(parts, i) in lines" :key="i" class="ln"><span v-for="(p, j) in parts" :key="j" :class="p.c">{{ p.t }}</span>
</span></pre>
</template>

<style scoped>
.ln { display: block; min-height: 1.55em; }
</style>
