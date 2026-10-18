<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import AppHeader from './layout/AppHeader.vue'
import SideNav from './layout/SideNav.vue'
import ToastHost from './components/ui/ToastHost.vue'
import ModalHost from './components/ui/ModalHost.vue'
import DrawerHost from './components/ui/DrawerHost.vue'
import DashboardView from './views/DashboardView.vue'
import VmWizard from './views/VmWizard.vue'
import VmDetail from './views/VmDetail.vue'
import StacksView from './views/StacksView.vue'
import StackWizard from './views/StackWizard.vue'
import StackDetail from './views/StackDetail.vue'
import ReviewQueue from './views/ReviewQueue.vue'
import PlatformView from './views/PlatformView.vue'
import ActivityView from './views/ActivityView.vue'
import { route } from './router.js'
import { loadStatic, refresh, store } from './store.js'

const VIEWS = {
  dashboard: DashboardView, 'vm-new': VmWizard, vm: VmDetail, stacks: StacksView, 'stack-new': StackWizard,
  stack: StackDetail, review: ReviewQueue, platform: PlatformView, activity: ActivityView,
}
const view = computed(() => VIEWS[route.name] || DashboardView)
const viewKey = computed(() => `${route.name}/${route.params.env || ''}/${route.params.name || ''}`)
const navOpen = ref(false)

let saved = 'light'
try { saved = localStorage.getItem('theme') || 'light' } catch { /* private mode */ }
const theme = ref(saved)
watch(theme, (t) => {
  document.documentElement.dataset.theme = t
  try { localStorage.setItem('theme', t) } catch { /* ignore */ }
}, { immediate: true })

let timer
onMounted(() => {
  loadStatic()
  timer = setInterval(refresh, 10000)
})
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <a class="skip" href="#main">Skip to content</a>
  <AppHeader v-model:theme="theme" :nav-open="navOpen" @toggle-nav="navOpen = !navOpen" />
  <div class="shell">
    <aside id="sidenav" class="side" :class="{ open: navOpen }">
      <SideNav @navigate="navOpen = false" />
    </aside>
    <div v-if="navOpen" class="side-scrim" aria-hidden="true" @click="navOpen = false" />
    <main id="main" class="main" tabindex="-1">
      <div v-if="store.loadError && !store.health" class="callout err boot" role="alert">
        <span><strong>The console backend is not reachable.</strong> {{ store.loadError }}</span>
      </div>
      <component :is="view" :key="viewKey" />
      <footer class="foot dim small">Proxmox credentials never reach the browser. Production changes always need a person to approve them.</footer>
    </main>
  </div>
  <DrawerHost />
  <ModalHost />
  <ToastHost />
</template>

<style scoped>
.shell { display: grid; grid-template-columns: var(--side-w) minmax(0, 1fr); min-height: calc(100dvh - var(--header-h)); }
.side { background: var(--sidebar); border-right: 1px solid var(--line); position: sticky; top: var(--header-h); height: calc(100dvh - var(--header-h)); overflow-y: auto; }
.side-scrim { display: none; }
.main { min-width: 0; padding: 20px 24px 8px; outline: none; display: flex; flex-direction: column; gap: 16px; max-width: 1440px; width: 100%; }
.boot { margin-bottom: 4px; }
.foot { text-align: center; padding: 18px 0 12px; margin-top: auto; }
@media (max-width: 1024px) {
  .shell { grid-template-columns: 1fr; }
  .side { position: fixed; z-index: var(--z-side); left: 0; top: var(--header-h); width: min(300px, 86vw); transform: translateX(-100%); transition: transform var(--t-med) var(--ease); }
  .side.open { transform: none; box-shadow: var(--shadow-pop); }
  .side-scrim { display: block; position: fixed; inset: var(--header-h) 0 0 0; z-index: calc(var(--z-side) - 1); background: var(--scrim); }
}
@media (max-width: 640px) { .main { padding: 14px 16px 8px; } }
</style>
