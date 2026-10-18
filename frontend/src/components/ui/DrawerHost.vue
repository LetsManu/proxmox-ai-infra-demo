<script setup>
import { nextTick, ref, watch } from 'vue'
import { Copy, LoaderCircle, X } from 'lucide-vue-next'
import CodeView from './CodeView.vue'
import { closeDrawer, drawer } from './drawer.js'
import { toast } from './toast.js'

const panel = ref(null)
const body = ref(null)
let opener = null

watch(
  () => drawer.open,
  async (open) => {
    if (open) {
      opener = document.activeElement
      await nextTick()
      panel.value?.focus()
    } else opener?.focus?.()
  },
)
watch(
  () => drawer.content,
  async () => {
    if (!drawer.live) return
    await nextTick()
    const el = body.value?.querySelector('pre')
    if (el) el.scrollTop = el.scrollHeight
  },
)

async function copy() {
  try {
    await navigator.clipboard.writeText(drawer.content)
    toast.success('Copied to the clipboard.')
  } catch {
    toast.error('The browser blocked clipboard access. Select the text and copy it manually.')
  }
}
function onKey(e) {
  if (e.key === 'Escape') closeDrawer()
}
</script>

<template>
  <Transition name="fade"><div v-if="drawer.open" class="scrim" aria-hidden="true" @click="closeDrawer" /></Transition>
  <Transition name="slide">
    <aside
      v-if="drawer.open"
      ref="panel"
      class="drawer"
      role="dialog"
      aria-modal="false"
      aria-labelledby="drawer-title"
      tabindex="-1"
      @keydown="onKey"
    >
      <header class="head">
        <div class="titles">
          <h2 id="drawer-title">{{ drawer.title }}</h2>
          <p v-if="drawer.subtitle" class="dim small mono">{{ drawer.subtitle }}</p>
        </div>
        <span v-if="drawer.live" class="live small"><LoaderCircle :size="14" class="spin" />Live</span>
        <button v-if="drawer.kind !== 'component'" type="button" class="btn sm" @click="copy"><Copy :size="14" />Copy</button>
        <button type="button" class="btn quiet icon" aria-label="Close panel" @click="closeDrawer"><X :size="18" /></button>
      </header>
      <div ref="body" class="body">
        <component :is="drawer.component" v-if="drawer.kind === 'component'" v-bind="drawer.props" />
        <p v-else-if="drawer.kind === 'text'" class="prose">{{ drawer.content }}</p>
        <CodeView v-else :text="drawer.content || (drawer.live ? 'Waiting for output…' : '(empty)')" :kind="drawer.kind" />
      </div>
    </aside>
  </Transition>
</template>

<style scoped>
.scrim { position: fixed; inset: 0; background: var(--scrim); z-index: calc(var(--z-drawer) - 1); }
.drawer {
  position: fixed; z-index: var(--z-drawer); top: 0; right: 0; bottom: 0; width: min(760px, 92vw);
  background: var(--surface); border-left: 1px solid var(--line); box-shadow: var(--shadow-pop);
  display: flex; flex-direction: column; outline: none;
}
.head { display: flex; align-items: center; gap: 8px; padding: 12px 12px 12px 18px; border-bottom: 1px solid var(--line); }
.titles { flex: 1; min-width: 0; }
.titles h2 { font-size: 16px; }
.live { display: inline-flex; align-items: center; gap: 4px; color: var(--info-fg); }
.body { flex: 1; min-height: 0; overflow: auto; padding: 14px 18px 18px; display: flex; flex-direction: column; }
.body :deep(pre.code) { flex: 1; min-height: 200px; }
.prose { white-space: pre-wrap; line-height: 1.6; }
.slide-enter-active, .slide-leave-active { transition: transform var(--t-med) var(--ease); }
.slide-enter-from, .slide-leave-to { transform: translateX(100%); }
.fade-enter-active, .fade-leave-active { transition: opacity var(--t-med); }
.fade-enter-from, .fade-leave-to { opacity: 0; }
@media (max-width: 640px) { .drawer { width: 100vw; } }
</style>
