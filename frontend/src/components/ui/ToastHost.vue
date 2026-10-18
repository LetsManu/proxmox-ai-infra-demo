<script setup>
import { CircleCheck, CircleAlert, Info, X } from 'lucide-vue-next'
import { close, toasts } from './toast.js'

const ICON = { success: CircleCheck, error: CircleAlert, info: Info }
</script>

<template>
  <section class="toasts" aria-label="Notifications">
    <TransitionGroup tag="ol" name="toast" aria-live="polite" aria-relevant="additions text">
      <li v-for="t in toasts" :key="t.id" class="toast" :class="t.kind">
        <component :is="ICON[t.kind]" :size="18" class="ic" aria-hidden="true" />
        <div class="msg">
          <strong v-if="t.title">{{ t.title }}</strong>
          <span><span v-if="t.kind === 'error'" class="sr-only">Error: </span>{{ t.message }}</span>
        </div>
        <button type="button" class="btn quiet icon" aria-label="Dismiss" @click="close(t.id)"><X :size="16" /></button>
      </li>
    </TransitionGroup>
  </section>
</template>

<style scoped>
.toasts { position: fixed; z-index: 120; right: 1.2rem; bottom: 1.2rem; width: min(420px, calc(100vw - 2rem)); pointer-events: none; }
ol { list-style: none; display: flex; flex-direction: column; gap: .5rem; }
.toast {
  pointer-events: auto; display: flex; align-items: center; gap: .65rem; padding: .5rem .45rem .5rem .85rem; min-height: 52px;
  background: #20262d; border: 1px solid #323a43; border-left: 3px solid var(--mut); border-radius: 8px; box-shadow: var(--shadow-pop);
}
.success { border-left-color: var(--ok); } .success .ic { color: var(--ok); }
.error { border-left-color: var(--err); } .error .ic { color: var(--err); }
.info { border-left-color: var(--info); } .info .ic { color: var(--info); }
.msg { flex: 1; display: flex; flex-direction: column; font-size: .9rem; line-height: 1.35; overflow-wrap: anywhere; }
.msg strong { font-weight: 600; }
.toast-enter-active { transition: transform var(--t-med) var(--ease), opacity var(--t-med) var(--ease); }
.toast-leave-active { transition: opacity 140ms ease-in; }
.toast-enter-from { transform: translateY(12px); opacity: 0; }
.toast-leave-to { opacity: 0; }
@media (max-width: 720px) { .toasts { left: 50%; right: auto; transform: translateX(-50%); } }
</style>
