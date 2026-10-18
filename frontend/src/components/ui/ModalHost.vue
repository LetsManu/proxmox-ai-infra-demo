<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { ShieldAlert, TriangleAlert, X } from 'lucide-vue-next'
import { modal, settle } from './modal.js'

// Native <dialog>: focus trap, Escape and inert background come from the browser.
const el = ref(null)
const cancelBtn = ref(null)
const typed = ref('')
const understood = ref(false)
let opener = null
const o = computed(() => modal.opts)
const ready = computed(() => (!o.value.typed || typed.value === o.value.typed) && (!o.value.production || understood.value))

watch(
  () => modal.open,
  async (open) => {
    if (!el.value) return
    if (open) {
      opener = document.activeElement
      typed.value = ''
      understood.value = false
      el.value.showModal()
      await nextTick()
      cancelBtn.value?.focus() // critical dialogs start on Cancel
    } else {
      if (el.value.open) el.value.close()
      opener?.focus?.()
    }
  },
)
</script>

<template>
  <dialog ref="el" class="modal" aria-labelledby="modal-title" aria-describedby="modal-body" @cancel.prevent="settle(false)">
    <form method="dialog" @submit.prevent="ready && settle(true)">
      <header class="head">
        <span v-if="o.production" class="ic prod"><ShieldAlert :size="20" /></span>
        <span v-else-if="o.danger" class="ic danger"><TriangleAlert :size="20" /></span>
        <h2 id="modal-title">{{ o.title }}</h2>
        <button type="button" class="btn quiet icon close" aria-label="Close dialog" @click="settle(false)"><X :size="18" /></button>
      </header>
      <div id="modal-body" class="body">
        <p v-if="o.body">{{ o.body }}</p>
        <div v-if="o.effects?.length" class="effects">
          <h3 class="small">What will happen</h3>
          <ul><li v-for="e in o.effects" :key="e">{{ e }}</li></ul>
        </div>
        <p v-if="o.note" class="dim small">{{ o.note }}</p>
        <label v-if="o.production" class="check ack">
          <input v-model="understood" type="checkbox" />
          <span>I understand this will affect the production environment.</span>
        </label>
        <label v-if="o.typed" class="typed">
          <span>Type <code>{{ o.typed }}</code> to confirm</span>
          <input v-model="typed" class="mono-input" autocomplete="off" spellcheck="false" :aria-invalid="typed.length > 0 && typed !== o.typed" />
        </label>
      </div>
      <footer class="actions">
        <button ref="cancelBtn" type="button" class="btn" @click="settle(false)">Cancel</button>
        <button type="submit" class="btn" :class="o.danger || o.production ? 'danger solid' : 'primary'" :disabled="!ready">
          {{ o.confirmLabel || 'Confirm' }}
        </button>
      </footer>
    </form>
  </dialog>
</template>

<style scoped>
.modal {
  border: 1px solid var(--line); border-radius: var(--radius-lg); background: var(--surface); color: var(--fg);
  padding: 0; width: min(520px, calc(100vw - 32px)); box-shadow: var(--shadow-pop);
}
.modal::backdrop { background: var(--scrim); }
.modal[open] { animation: pop var(--t-med) var(--ease); }
@keyframes pop { from { opacity: 0; transform: translateY(6px) scale(.98); } }
.head { display: flex; align-items: center; gap: 10px; padding: 16px 12px 8px 20px; }
.head h2 { flex: 1; font-size: 17px; }
.ic { width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center; }
.ic.danger, .ic.prod { background: var(--err-bg); color: var(--err-fg); }
.body { padding: 4px 20px 8px; display: flex; flex-direction: column; gap: 12px; color: var(--mut); }
.effects { border: 1px solid var(--line); border-radius: var(--radius); background: var(--surface-2); padding: 10px 12px; }
.effects h3 { color: var(--fg); margin-bottom: 4px; }
.effects ul { padding-left: 18px; display: flex; flex-direction: column; gap: 2px; color: var(--fg); font-size: 14px; }
.ack { color: var(--fg); font-weight: 500; padding: 8px 10px; border: 1px solid var(--err-line); background: var(--err-bg); border-radius: var(--radius); }
.typed { display: flex; flex-direction: column; gap: 6px; color: var(--fg); }
.actions { display: flex; justify-content: flex-end; gap: 8px; padding: 12px 20px 18px; }
</style>
