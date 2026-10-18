<script setup>
import { computed, ref } from 'vue'
import { api } from '../api.js'

const props = defineProps({
  modelValue: { type: Object, required: true },
  env: { type: String, required: true },
  policy: { type: Object, default: null },
  templates: { type: Array, default: () => [] },
  environments: { type: Array, default: () => [] },
})
const emit = defineEmits(['apply-spec'])
const f = props.modelValue

const prompt = ref(
  'Create a small Ubuntu test server for a web app with 2 CPUs, 4 GB RAM, 40 GB disk, and Docker installed.',
)
const aiLoading = ref(false)
const aiResult = ref(null)
const aiError = ref(null)

const memoryGb = computed({
  get: () => f.memory_mb / 1024,
  set: (v) => (f.memory_mb = Math.round(Number(v) * 1024)),
})
const packages = computed({
  get: () => (f.cloud_init?.packages || []).join(', '),
  set: (v) => (f.cloud_init.packages = v.split(',').map((s) => s.trim()).filter(Boolean)),
})
const networkOptions = computed(() =>
  props.environments.filter((e) => e.key === props.env).map((e) => ({ key: e.network.key, label: `${e.label} · ${e.network.label}` })),
)
const nameValid = computed(() => /^[a-z][a-z0-9-]{1,40}[a-z0-9]$/.test(f.name))

async function generate() {
  aiLoading.value = true
  aiResult.value = null
  aiError.value = null
  try {
    aiResult.value = await api.generateSpec(prompt.value)
  } catch (e) {
    aiError.value = e.detail?.errors ? e.detail : { message: e.message, errors: [] }
  } finally {
    aiLoading.value = false
  }
}
</script>

<template>
  <section class="card">
    <div class="card-head">
      <h2>Virtual machine</h2>
      <span class="tag" :class="env === 'prod' ? 'tag-prod' : 'tag-test'">{{ env === 'prod' ? 'PRODUCTION' : 'TEST' }}</span>
    </div>

    <details class="ai-box" open>
      <summary>✨ Describe it in plain English (AI)</summary>
      <textarea v-model="prompt" rows="2" aria-label="Describe the VM" />
      <div class="row">
        <button class="btn ai" :disabled="aiLoading || prompt.length < 5" @click="generate">
          <span v-if="aiLoading" class="spinner" />Generate VM spec
        </button>
        <span class="muted small">Draft only. Nothing is deployed.</span>
      </div>
      <div v-if="aiError" class="ai-result bad">
        <strong>Rejected by safety validation</strong>
        <ul><li v-for="e in aiError.errors" :key="e">{{ e }}</li></ul>
        <p v-if="!aiError.errors?.length">{{ aiError.message }}</p>
      </div>
      <div v-if="aiResult" class="ai-result">
        <div class="row between">
          <strong>Draft spec <span class="muted small">({{ aiResult.source }})</span></strong>
          <button class="btn small" @click="emit('apply-spec', aiResult.spec)">Use this spec</button>
        </div>
        <pre class="json">{{ JSON.stringify(aiResult.spec, null, 2) }}</pre>
        <ul v-if="aiResult.warnings?.length" class="warnings">
          <li v-for="w in aiResult.warnings" :key="w">⚠ {{ w }}</li>
        </ul>
      </div>
    </details>

    <div class="form-grid">
      <label class="span2">
        <span class="lbl">VM name</span>
        <input v-model.trim="f.name" :class="{ invalid: !nameValid }" placeholder="demo-web-test" />
        <small v-if="!nameValid" class="err">lowercase letters, digits, hyphens (3–42)</small>
      </label>
      <label>
        <span class="lbl">Operating system</span>
        <select v-model="f.template">
          <option v-for="t in templates" :key="t.key" :value="t.key">
            {{ t.label }} (template {{ t.template_id }}){{ t.available === false ? ' – missing!' : '' }}
          </option>
        </select>
      </label>
      <label>
        <span class="lbl">Network</span>
        <select v-model="f.network">
          <option v-for="n in networkOptions" :key="n.key" :value="n.key">{{ n.label }}</option>
        </select>
      </label>
      <label>
        <span class="lbl">CPU cores <span class="muted small">max {{ policy?.max_cores }}</span></span>
        <input v-model.number="f.cores" type="number" min="1" :max="policy?.max_cores" />
      </label>
      <label>
        <span class="lbl">RAM (GB) <span class="muted small">max {{ policy ? policy.max_memory_mb / 1024 : '' }}</span></span>
        <input v-model.number="memoryGb" type="number" min="1" step="1" :max="policy ? policy.max_memory_mb / 1024 : 64" />
      </label>
      <label>
        <span class="lbl">Disk (GB) <span class="muted small">max {{ policy?.max_disk_gb }}</span></span>
        <input v-model.number="f.disk_gb" type="number" min="8" :max="policy?.max_disk_gb" />
      </label>
      <label>
        <span class="lbl">Packages (cloud-init)</span>
        <input v-model="packages" placeholder="qemu-guest-agent, docker.io" />
      </label>
      <label class="span2">
        <span class="lbl">Description <span class="muted small">optional</span></span>
        <input v-model="f.description" maxlength="500" placeholder="What is this VM for?" />
      </label>
      <label class="span2">
        <span class="lbl">SSH public key <span class="muted small">optional – defaults to DEFAULT_SSH_PUBLIC_KEY</span></span>
        <input v-model.trim="f.ssh_public_key" placeholder="ssh-ed25519 AAAA… user@laptop" autocomplete="off" />
      </label>
    </div>

    <slot />
  </section>
</template>
