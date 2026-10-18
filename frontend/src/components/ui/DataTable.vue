<script setup>
import Skeleton from './Skeleton.vue'

// columns: [{ key, label, cls?, mono? }]; rows: array or null (loading). Slots: cell-<key> ({ row }).
defineProps({
  columns: { type: Array, required: true },
  rows: { type: Array, default: null },
  caption: { type: String, required: true },
  empty: { type: String, default: 'Nothing here yet.' },
  rowKey: { type: [String, Function], default: 'id' },
  clickable: { type: Boolean, default: false },
})
const emit = defineEmits(['row'])
const keyOf = (r, k, i) => (typeof k === 'function' ? k(r) : r[k] ?? i)
</script>

<template>
  <div class="table-wrap">
    <table class="table">
      <caption class="sr-only">{{ caption }}</caption>
      <thead><tr><th v-for="c in columns" :key="c.key" scope="col" :class="c.cls">{{ c.label }}</th></tr></thead>
      <tbody>
        <template v-if="!rows">
          <tr v-for="i in 3" :key="i"><td v-for="c in columns" :key="c.key"><Skeleton h="12px" /></td></tr>
        </template>
        <tr v-else-if="!rows.length"><td :colspan="columns.length" class="empty-cell">{{ empty }}</td></tr>
        <tr
          v-for="(r, i) in rows || []"
          :key="keyOf(r, rowKey, i)"
          :class="{ clickable }"
          :tabindex="clickable ? 0 : undefined"
          @click="clickable && emit('row', r)"
          @keydown.enter="clickable && emit('row', r)"
        >
          <td v-for="c in columns" :key="c.key" :class="[c.cls, { mono: c.mono }]" :data-label="c.label">
            <slot :name="`cell-${c.key}`" :row="r">{{ r[c.key] }}</slot>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.empty-cell { color: var(--dim); text-align: center; padding: 22px 12px; }
.nowrap { white-space: nowrap; }
@media (max-width: 640px) {
  table, thead, tbody, tr, td { display: block; }
  thead { display: none; }
  tr { border-bottom: 1px solid var(--line); padding: 6px 0; }
  .table td { border: 0; padding: 4px 12px; display: grid; grid-template-columns: 110px 1fr; gap: 8px; }
  .table td > * { justify-self: start; }
  .table td::before { content: attr(data-label); color: var(--dim); font-size: 13px; font-family: var(--font); }
  .table td.empty-cell { display: block; }
  .table td.empty-cell::before { content: none; }
}
</style>
