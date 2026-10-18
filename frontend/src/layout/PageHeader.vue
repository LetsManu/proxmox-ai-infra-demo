<script setup>
import Badge from '../components/ui/Badge.vue'

// Title row of every screen: what you are looking at, where, and the actions for it.
defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
  env: { type: String, default: '' }, // test | prod
  crumbs: { type: Array, default: () => [] }, // [{ label, href }]
})
</script>

<template>
  <div class="ph">
    <nav v-if="crumbs.length" class="crumbs small" aria-label="Breadcrumb">
      <template v-for="(c, i) in crumbs" :key="c.label"><a :href="c.href">{{ c.label }}</a><span aria-hidden="true"> / </span></template>
      <span aria-current="page">{{ title }}</span>
    </nav>
    <div class="row-main">
      <div class="titles">
        <h1>{{ title }}</h1>
        <p v-if="subtitle" class="muted">{{ subtitle }}</p>
      </div>
      <Badge v-if="env" :tone="env === 'prod' ? 'err' : 'info'" :label="env === 'prod' ? 'Production' : 'Test'" />
      <div v-if="$slots.default" class="acts"><slot /></div>
    </div>
  </div>
</template>

<style scoped>
.ph { display: flex; flex-direction: column; gap: 4px; }
.crumbs { color: var(--dim); }
.crumbs a { color: var(--link); text-decoration: none; }
.crumbs a:hover { text-decoration: underline; }
.row-main { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.titles { min-width: 0; margin-right: auto; }
h1 { overflow-wrap: anywhere; }
.acts { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
</style>
