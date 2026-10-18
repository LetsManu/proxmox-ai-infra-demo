<script setup>
const env = defineModel({ type: String, default: 'test' })
const OPTS = [{ key: 'test', label: 'Test' }, { key: 'prod', label: 'Production' }]
</script>

<template>
  <div class="seg" role="radiogroup" aria-label="Environment">
    <button
      v-for="o in OPTS"
      :key="o.key"
      type="button"
      role="radio"
      :aria-checked="env === o.key"
      :class="{ on: env === o.key, prod: o.key === 'prod' }"
      @click="env = o.key"
    >
      {{ o.label }}
    </button>
  </div>
</template>

<style scoped>
.seg { display: inline-flex; border: 1px solid var(--line-strong); border-radius: var(--radius); overflow: hidden; background: var(--surface); }
button { border: 0; background: transparent; color: var(--fg); padding: 0 16px; min-height: 36px; cursor: pointer; font-weight: 500; }
button + button { border-left: 1px solid var(--line-strong); }
button:hover { background: var(--surface-3); }
button.on { background: var(--primary); color: var(--primary-fg); }
@media (pointer: coarse) { button { min-height: 44px; } }
</style>
