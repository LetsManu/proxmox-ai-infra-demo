<script setup>
import { CircleAlert } from 'lucide-vue-next'

// Labelled form field. The control goes in the default slot and should get :id="id".
defineProps({
  id: { type: String, required: true },
  label: { type: String, required: true },
  hint: { type: String, default: '' },
  error: { type: String, default: '' },
  required: { type: Boolean, default: false },
  aside: { type: String, default: '' }, // right of the label, e.g. "max 4"
})
</script>

<template>
  <div class="field">
    <label class="label" :for="id">
      {{ label }}<span v-if="required" class="req" aria-hidden="true"> *</span>
      <span v-if="aside" class="aside">{{ aside }}</span>
    </label>
    <slot />
    <p v-if="error" :id="`${id}-msg`" class="error" role="alert"><CircleAlert :size="14" />{{ error }}</p>
    <p v-else-if="hint" :id="`${id}-msg`" class="hint">{{ hint }}</p>
  </div>
</template>

<style scoped>
.field { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.label { font-size: 14px; font-weight: 500; display: flex; gap: 4px; }
.req { color: var(--err-fg); }
.aside { margin-left: auto; font-weight: 400; color: var(--dim); font-size: 13px; }
.hint { font-size: 13px; color: var(--dim); }
.error { font-size: 13px; color: var(--err-fg); display: flex; gap: 5px; align-items: flex-start; }
.error svg { margin-top: 2px; }
</style>
