<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { TriangleAlert } from 'lucide-vue-next'
import { dialog, settle } from './confirm.js'

const el = ref(null)
const cancelBtn = ref(null)
const typed = ref('')
const o = computed(() => dialog.opts)
const ready = computed(() => !o.value.typed || typed.value === o.value.typed)

watch(
  () => dialog.open,
  async (open) => {
    if (!el.value) return
    if (open) {
      typed.value = ''
      el.value.showModal()
      await nextTick()
      cancelBtn.value?.focus() // danger dialogs start on Cancel
    } else if (el.value.open) el.value.close()
  },
)
</script>

<template>
  <dialog
    ref="el"
    class="dialog"
    role="alertdialog"
    aria-labelledby="dlg-title"
    aria-describedby="dlg-body"
    @cancel.prevent="settle(false)"
    @click.self="settle(false)"
  >
    <form method="dialog" @submit.prevent="ready && settle(true)">
      <div class="head">
        <span v-if="o.danger" class="ic"><TriangleAlert :size="20" /></span>
        <h2 id="dlg-title">{{ o.title }}</h2>
      </div>
      <p id="dlg-body" class="body">{{ o.body }}</p>
      <label v-if="o.typed" class="field">
        <span class="label">Type <code>{{ o.typed }}</code> to confirm</span>
        <input v-model="typed" autocomplete="off" spellcheck="false" />
      </label>
      <div class="actions">
        <button ref="cancelBtn" type="button" class="btn ghost" @click="settle(false)">Cancel</button>
        <button type="submit" class="btn" :class="o.danger ? 'danger solid' : 'primary'" :disabled="!ready">
          {{ o.confirmLabel || 'Confirm' }}
        </button>
      </div>
    </form>
  </dialog>
</template>

<style scoped>
.dialog {
  border: 1px solid var(--line-strong); border-radius: 12px; background: var(--surface); color: var(--fg);
  padding: 0; width: min(460px, calc(100vw - 2rem)); box-shadow: var(--shadow-pop);
}
.dialog::backdrop { background: rgba(5, 7, 9, .6); }
.dialog[open] { animation: pop var(--t-med) var(--ease); }
@keyframes pop { from { opacity: 0; transform: translateY(8px) scale(.98); } }
form { padding: 1.25rem; display: flex; flex-direction: column; gap: .9rem; }
.head { display: flex; gap: .6rem; align-items: center; }
.ic { width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center; background: var(--tone-err); color: var(--err); }
h2 { font-size: 1.05rem; }
.body { color: var(--mut); font-size: .92rem; }
.actions { display: flex; justify-content: flex-end; gap: .5rem; margin-top: .25rem; }
</style>
