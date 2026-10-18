<script setup>
import { CircleCheck, CircleAlert, Info, X } from 'lucide-vue-next'
import { close, toasts } from './toast.js'

const ICON = { success: CircleCheck, error: CircleAlert, info: Info }
function act(t) {
  t.action.run()
  close(t.id)
}
</script>

<template>
  <section class="toasts" aria-label="Notifications">
    <TransitionGroup tag="ol" name="toast" aria-live="polite" aria-relevant="additions text">
      <li v-for="t in toasts" :key="t.id" class="toast" :class="t.kind" :role="t.kind === 'error' ? 'alert' : 'status'">
        <component :is="ICON[t.kind]" :size="18" class="ic" aria-hidden="true" />
        <div class="msg">
          <strong v-if="t.title">{{ t.title }}</strong>
          <span>{{ t.message }}</span>
          <button v-if="t.action" type="button" class="link" @click="act(t)">{{ t.action.label }}</button>
        </div>
        <button type="button" class="btn quiet sm icon" aria-label="Dismiss notification" @click="close(t.id)"><X :size="16" /></button>
      </li>
    </TransitionGroup>
  </section>
</template>

<style scoped>
.toasts { position: fixed; z-index: var(--z-toast); right: 16px; bottom: 16px; width: min(420px, calc(100vw - 32px)); pointer-events: none; }
ol { list-style: none; display: flex; flex-direction: column; gap: 8px; }
.toast {
  pointer-events: auto; display: flex; align-items: flex-start; gap: 10px; padding: 10px 6px 10px 12px;
  background: var(--surface); border: 1px solid var(--line); border-left: 4px solid var(--dim); border-radius: var(--radius); box-shadow: var(--shadow-pop);
}
.ic { margin-top: 2px; }
.success { border-left-color: var(--ok-fg); } .success .ic { color: var(--ok-fg); }
.error { border-left-color: var(--err-fg); } .error .ic { color: var(--err-fg); }
.info { border-left-color: var(--info-fg); } .info .ic { color: var(--info-fg); }
.msg { flex: 1; display: flex; flex-direction: column; gap: 2px; font-size: 14px; line-height: 1.4; overflow-wrap: anywhere; }
.msg strong { font-weight: 600; }
.link { align-self: flex-start; background: none; border: 0; padding: 4px 0; color: var(--link); text-decoration: underline; cursor: pointer; font-weight: 500; }
.toast-enter-active { transition: transform var(--t-med) var(--ease), opacity var(--t-med) var(--ease); }
.toast-leave-active { transition: opacity 140ms ease-in; }
.toast-enter-from { transform: translateY(10px); opacity: 0; }
.toast-leave-to { opacity: 0; }
</style>
