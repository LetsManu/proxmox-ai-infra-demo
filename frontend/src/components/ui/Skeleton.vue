<script setup>
defineProps({ w: { type: String, default: '100%' }, h: { type: String, default: '1rem' }, radius: { type: String, default: '4px' } })
</script>

<template>
  <span class="skeleton" :style="{ width: w, height: h, borderRadius: radius, display: 'block' }" aria-hidden="true" />
</template>
