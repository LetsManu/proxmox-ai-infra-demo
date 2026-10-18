<script setup>
// Panel with a title bar (Proxmox style). Slots: default, actions (right of the title), footer.
defineProps({
  title: { type: String, default: '' },
  icon: { type: [Object, Function], default: null },
  subtitle: { type: String, default: '' },
  flush: { type: Boolean, default: false }, // body without padding (tables)
  tag: { type: String, default: 'section' },
})
</script>

<template>
  <component :is="tag" class="card">
    <header v-if="title || $slots.actions" class="card-head">
      <h2 class="card-title"><component :is="icon" v-if="icon" :size="16" aria-hidden="true" />{{ title }}</h2>
      <span v-if="subtitle" class="dim small sub">{{ subtitle }}</span>
      <div v-if="$slots.actions" class="card-actions"><slot name="actions" /></div>
    </header>
    <div class="card-body" :class="{ flush }"><slot /></div>
    <footer v-if="$slots.footer" class="card-foot"><slot name="footer" /></footer>
  </component>
</template>

<style scoped>
.card { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius-lg); box-shadow: var(--shadow-sm); min-width: 0; }
.card-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 10px 14px; border-bottom: 1px solid var(--line); min-height: 48px; }
.card-title { display: flex; align-items: center; gap: 8px; font-size: 15px; font-weight: 600; }
.card-title svg { color: var(--primary); }
.sub { min-width: 0; }
.card-actions { margin-left: auto; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.card-body { padding: 14px; }
.card-body.flush { padding: 0; }
.card-body.flush :deep(.table-wrap) { border: 0; border-radius: 0 0 var(--radius-lg) var(--radius-lg); }
.card-foot { padding: 10px 14px; border-top: 1px solid var(--line); background: var(--surface-2); border-radius: 0 0 var(--radius-lg) var(--radius-lg); display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
</style>
