<script setup>
import { ChevronDown } from 'lucide-vue-next'

// Progressive disclosure: closed by default, keyboard and screen-reader friendly (<details>).
defineProps({ summary: { type: String, required: true }, open: { type: Boolean, default: false } })
</script>

<template>
  <details class="exp" :open="open">
    <summary><ChevronDown :size="16" class="chev" aria-hidden="true" />{{ summary }}<slot name="aside" /></summary>
    <div class="inner"><slot /></div>
  </details>
</template>

<style scoped>
.exp > summary { list-style: none; cursor: pointer; display: flex; align-items: center; gap: 6px; font-weight: 500; color: var(--link); min-height: 32px; border-radius: var(--radius-sm); }
.exp > summary::-webkit-details-marker { display: none; }
.chev { transition: transform var(--t-fast) var(--ease); transform: rotate(-90deg); }
.exp[open] .chev { transform: none; }
.inner { padding-top: 8px; }
</style>
