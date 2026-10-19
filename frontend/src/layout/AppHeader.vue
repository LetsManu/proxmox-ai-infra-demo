<script setup>
import { computed } from 'vue'
import { Layers, FlaskConical, Radio, Menu, Moon, Sun, ListTodo, User, LogOut } from 'lucide-vue-next'
import { store, isMock, signOut } from '../store.js'
import { openJob } from '../components/ui/drawer.js'

defineProps({ navOpen: { type: Boolean, default: false } })
const emit = defineEmits(['toggle-nav'])
const theme = defineModel('theme', { type: String, default: 'light' })
const running = computed(() => store.running)
const roleLabel = computed(() => {
  const r = store.me?.roles || []
  return r.includes('approver') ? 'Approver' : r.includes('operator') ? 'Operator' : r.includes('viewer') ? 'Viewer' : ''
})
</script>

<template>
  <header class="top">
    <button type="button" class="btn quiet icon nav-btn" :aria-expanded="navOpen" aria-controls="sidenav" aria-label="Navigation" @click="emit('toggle-nav')">
      <Menu :size="20" />
    </button>
    <a class="brand" href="#/dashboard">
      <span class="logo" aria-hidden="true"><Layers :size="17" /></span>
      <span class="name">Infra Console</span>
      <span class="sub hide-sm">for Proxmox VE</span>
    </a>
    <div class="right">
      <template v-if="store.health">
        <span v-if="isMock()" class="mode warn" title="LIVE_MODE=false: Proxmox and OpenTofu are simulated"><FlaskConical :size="15" /><span class="t">Demo mode</span></span>
        <span v-else class="mode ok"><Radio :size="15" /><span class="t">Connected to Proxmox</span></span>
      </template>
      <button
        v-if="running.length"
        type="button"
        class="btn sm tasks"
        :aria-label="`${running.length} task(s) running, open the latest log`"
        @click="openJob(running[running.length - 1].id, running[running.length - 1].label)"
      >
        <span class="spinner" aria-hidden="true" /><span class="t">{{ running[running.length - 1].label }}</span><span v-if="running.length > 1" class="num">+{{ running.length - 1 }}</span>
      </button>
      <span v-else class="idle small hide-sm"><ListTodo :size="15" />No running tasks</span>
      <button
        type="button"
        class="btn quiet icon"
        :aria-label="theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'"
        :title="theme === 'dark' ? 'Light theme' : 'Dark theme'"
        @click="theme = theme === 'dark' ? 'light' : 'dark'"
      >
        <Sun v-if="theme === 'dark'" :size="18" /><Moon v-else :size="18" />
      </button>
      <span v-if="store.me" class="user small hide-sm" :title="`Signed in as ${store.me.username} (${store.me.roles.join(', ')})`">
        <User :size="15" />{{ store.me.display_name }}<span class="role">{{ roleLabel }}</span>
      </span>
      <button v-if="store.me?.auth" type="button" class="btn quiet icon" aria-label="Sign out" title="Sign out" @click="signOut">
        <LogOut :size="18" />
      </button>
    </div>
  </header>
</template>

<style scoped>
.top {
  position: sticky; top: 0; z-index: var(--z-header); height: var(--header-h); background: var(--header);
  border-bottom: 1px solid var(--line); display: flex; align-items: center; gap: 10px; padding: 0 12px;
}
.nav-btn { display: none; }
.brand { display: flex; align-items: center; gap: 10px; color: var(--fg); text-decoration: none; min-width: 0; }
.logo { width: 30px; height: 30px; border-radius: var(--radius); display: grid; place-items: center; color: #fff; background: var(--brand); }
.name { font-size: 16px; font-weight: 700; white-space: nowrap; }
.sub { color: var(--dim); font-size: 13px; white-space: nowrap; }
.right { margin-left: auto; display: flex; align-items: center; gap: 8px; min-width: 0; }
.mode { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 600; padding: 4px 10px; border-radius: 999px; border: 1px solid; white-space: nowrap; }
.mode.warn { color: var(--warn-fg); background: var(--warn-bg); border-color: var(--warn-line); }
.mode.ok { color: var(--ok-fg); background: var(--ok-bg); border-color: var(--ok-line); }
.tasks { max-width: 280px; color: var(--info-fg); border-color: var(--info-line); background: var(--info-bg); }
.tasks .t { overflow: hidden; text-overflow: ellipsis; }
.idle, .user { display: inline-flex; align-items: center; gap: 6px; color: var(--dim); white-space: nowrap; }
.user { color: var(--mut); padding-left: 8px; border-left: 1px solid var(--line); }
.role { font-size: 12px; font-weight: 600; color: var(--dim); border: 1px solid var(--line); border-radius: 999px; padding: 1px 8px; }
@media (max-width: 1024px) { .nav-btn { display: inline-flex; } }
@media (max-width: 640px) { .hide-sm, .mode .t, .tasks .t { display: none; } }
</style>
