<script setup>
defineProps({
  icon: { type: [Object, Function], default: null },
  title: { type: String, required: true },
  text: { type: String, default: '' },
})
</script>

<template>
  <div class="empty">
    <span v-if="icon" class="ic"><component :is="icon" :size="22" /></span>
    <h3>{{ title }}</h3>
    <p v-if="text" class="muted">{{ text }}</p>
    <div v-if="$slots.default" class="row act"><slot /></div>
  </div>
</template>

<style scoped>
.empty { display: flex; flex-direction: column; align-items: center; text-align: center; gap: 6px; padding: 28px 16px; }
.ic { width: 44px; height: 44px; border-radius: 50%; display: grid; place-items: center; background: var(--info-bg); color: var(--info-fg); margin-bottom: 4px; }
h3 { font-size: 15px; }
p { max-width: 52ch; font-size: 14px; }
.act { margin-top: 8px; justify-content: center; }
</style>
