<script setup>
import { computed, ref } from 'vue'
import { Layers, LogIn, ShieldCheck } from 'lucide-vue-next'
import Field from '../components/ui/Field.vue'
import { api, setCsrf } from '../api.js'
import { loadStatic, store } from '../store.js'

// Sign-in: single sign-on (OIDC: Authentik, Microsoft Entra ID, AD FS) or directory password (LDAP / Active Directory).
const cfg = computed(() => store.authConfig || { mode: 'none' })
const username = ref('')
const password = ref('')
const busy = ref(false)
const params = new URLSearchParams(location.search)
const error = ref(params.get('login_error') || '')
if (error.value) history.replaceState(null, '', location.pathname + location.hash) // do not keep the message in the URL

function sso() {
  busy.value = true
  const target = location.hash ? `/${location.hash}` : '/'
  location.assign(`/api/auth/login?return_to=${encodeURIComponent(target)}`)
}

async function submit() {
  if (!username.value || !password.value) {
    error.value = 'Enter your username and password.'
    return
  }
  busy.value = true
  error.value = ''
  try {
    const me = await api.login(username.value.trim(), password.value)
    password.value = ''
    setCsrf(me.csrf)
    Object.assign(store, { me, needLogin: false })
    await loadStatic()
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main id="main" class="login">
    <section class="panel" aria-labelledby="login-title">
      <div class="brand">
        <span class="logo" aria-hidden="true"><Layers :size="20" /></span>
        <div>
          <h1 id="login-title">Infra Console</h1>
          <p class="dim small">for Proxmox VE</p>
        </div>
      </div>

      <div v-if="error" class="callout err" role="alert">{{ error }}</div>

      <template v-if="cfg.mode === 'oidc'">
        <p class="mut">Sign in with your company account.</p>
        <button type="button" class="btn primary wide" :aria-busy="busy" :disabled="busy" @click="sso">
          <LogIn :size="16" />Sign in with {{ cfg.provider_name }}
        </button>
      </template>

      <form v-else-if="cfg.mode === 'ldap'" class="form" novalidate @submit.prevent="submit">
        <p class="mut">Sign in with your {{ cfg.provider_name }} account.</p>
        <Field id="login-user" label="Username">
          <input id="login-user" v-model="username" name="username" autocomplete="username" autocapitalize="none" spellcheck="false" required>
        </Field>
        <Field id="login-pass" label="Password">
          <input id="login-pass" v-model="password" name="password" type="password" autocomplete="current-password" required>
        </Field>
        <button type="submit" class="btn primary wide" :aria-busy="busy" :disabled="busy">
          <LogIn :size="16" />{{ busy ? 'Signing in…' : 'Sign in' }}
        </button>
      </form>

      <p class="foot dim small"><ShieldCheck :size="14" aria-hidden="true" />Your password goes to your directory only; the console stores no passwords.</p>
    </section>
  </main>
</template>

<style scoped>
.login { min-height: 100dvh; display: grid; place-items: center; padding: 24px 16px; background: var(--bg); }
.panel { width: min(400px, 100%); background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius-lg, 10px); padding: 28px; display: flex; flex-direction: column; gap: 16px; box-shadow: var(--shadow-pop); }
.brand { display: flex; align-items: center; gap: 12px; }
.brand h1 { font-size: 20px; margin: 0; }
.brand p { margin: 0; }
.logo { width: 40px; height: 40px; border-radius: var(--radius); display: grid; place-items: center; color: #fff; background: var(--brand); }
.form { display: flex; flex-direction: column; gap: 14px; }
.wide { width: 100%; justify-content: center; min-height: 44px; }
.mut { margin: 0; }
.foot { display: flex; gap: 6px; align-items: center; margin: 0; }
</style>
