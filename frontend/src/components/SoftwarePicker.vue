<script setup>
import { computed, ref } from 'vue'
import { RefreshCw, X, Sparkles } from 'lucide-vue-next'
import Badge from './ui/Badge.vue'
import Field from './ui/Field.vue'
import { reloadProfiles, store } from '../store.js'
import { toast } from './ui/toast.js'

// What gets installed: assistant recommendations (required / optional), profiles, extra packages.
const model = defineModel({ type: Object, required: true }) // { profiles: [], packages: [] }
const props = defineProps({
  osFamily: { type: String, default: 'linux' },
  analysis: { type: Object, default: null }, // from /ai/generate-vm-spec .software
  idPrefix: { type: String, default: 'sw' },
})

const STATUS = {
  ready: { tone: 'ok', label: 'Ready' },
  available: { tone: 'ok', label: 'In repository' },
  unverified: { tone: 'muted', label: 'Not verified' },
  missing: { tone: 'err', label: 'Not found' },
  invalid: { tone: 'err', label: 'Invalid name' },
  unknown: { tone: 'err', label: 'Unknown profile' },
  pending_review: { tone: 'warn', label: 'Waiting for review' },
  rejected_by_checks: { tone: 'err', label: 'Failed safety checks' },
  unresolved: { tone: 'muted', label: 'No match' },
}
const usable = (i) => ['ready', 'available', 'unverified'].includes(i.status)
const items = computed(() => props.analysis?.items || [])
const required = computed(() => items.value.filter((i) => i.required))
const optional = computed(() => items.value.filter((i) => !i.required))
const profiles = computed(() => store.profiles.filter((p) => p.os_family === props.osFamily))
const analysedNames = computed(() => new Set(items.value.map((i) => i.name)))
const otherProfiles = computed(() => profiles.value.filter((p) => !analysedNames.value.has(p.key)))

function isOn(i) {
  return (i.kind === 'profile' ? model.value.profiles : model.value.packages).includes(i.name)
}
function toggle(kind, name, on) {
  const key = kind === 'profile' ? 'profiles' : 'packages'
  const set = new Set(model.value[key])
  on ? set.add(name) : set.delete(name)
  model.value[key] = [...set]
}

const pkgInput = ref('')
const pkgError = ref('')
const PKG_RE = { linux: /^[a-z0-9][a-z0-9.+-]{0,62}(=[A-Za-z0-9.+:~-]{1,40})?$/, windows: /^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$/ }
function addPackages() {
  const names = pkgInput.value.split(/[\s,]+/).filter(Boolean)
  const bad = names.filter((n) => !PKG_RE[props.osFamily].test(n))
  if (bad.length) {
    pkgError.value = `Not a valid ${props.osFamily === 'windows' ? 'Chocolatey' : 'apt'} package name: ${bad.join(', ')}. Use the exact package name, without commands.`
    return
  }
  pkgError.value = ''
  model.value.packages = [...new Set([...model.value.packages, ...names])]
  pkgInput.value = ''
}
async function reload() {
  try {
    const all = await reloadProfiles()
    toast.success(`${all.length} software profiles available.`, { title: 'Catalog refreshed' })
  } catch (e) {
    toast.error(e.message)
  }
}
</script>

<template>
  <div class="sp">
    <section v-if="items.length" class="group" aria-labelledby="sp-rec">
      <h3 id="sp-rec"><Sparkles :size="15" aria-hidden="true" />Recommended for your request</h3>
      <p class="dim small">Each need is matched to a profile, a package from the official repository, or a new role that a person must review first.</p>
      <template v-for="[label, list] in [['Required', required], ['Optional', optional]]" :key="label">
        <h4 v-if="list.length" class="sub">{{ label }}</h4>
        <ul class="needs">
          <li v-for="i in list" :key="i.kind + i.name">
            <label class="check">
              <input type="checkbox" :checked="isOn(i)" :disabled="!usable(i)" @change="toggle(i.kind, i.name, $event.target.checked)" />
              <span class="need">
                <span class="name">{{ i.need }} <span class="mono dim">{{ i.label || i.name }}</span></span>
                <span class="why small">{{ i.reason }}</span>
              </span>
            </label>
            <Badge :tone="STATUS[i.status]?.tone" :label="STATUS[i.status]?.label || i.status" :title="i.detail" />
            <a v-if="i.proposal_id" class="small" href="#/review">Review</a>
          </li>
        </ul>
      </template>
    </section>

    <section class="group" aria-labelledby="sp-prof">
      <div class="row">
        <h3 id="sp-prof">{{ items.length ? 'Other software profiles' : 'Software profiles' }}</h3>
        <span class="spacer" />
        <button type="button" class="btn quiet sm" @click="reload"><RefreshCw :size="14" />Refresh catalog</button>
      </div>
      <ul class="profiles">
        <li v-for="p in otherProfiles" :key="p.key">
          <label class="check">
            <input type="checkbox" :checked="model.profiles.includes(p.key)" @change="toggle('profile', p.key, $event.target.checked)" />
            <span class="need">
              <span class="name">{{ p.label }} <Badge v-if="p.source !== 'built-in'" tone="info" :label="p.source === 'approved' ? 'Approved' : 'Project'" /></span>
              <span class="why small">{{ p.description }}</span>
            </span>
          </label>
        </li>
      </ul>
      <p v-if="!otherProfiles.length" class="dim small">No more profiles for this operating system.</p>
    </section>

    <Field :id="`${idPrefix}-pkg`" label="Extra packages" :aside="osFamily === 'windows' ? 'Chocolatey IDs' : 'apt names'" :error="pkgError"
      :hint="`Installed with the ${osFamily === 'windows' ? 'Chocolatey' : 'apt'} package manager, never as a command. Press Enter to add.`">
      <div class="chips" :class="{ invalid: pkgError }">
        <span v-for="p in model.packages.filter((x) => !analysedNames.has(x))" :key="p" class="chip mono">{{ p }}<button type="button" :aria-label="`Remove ${p}`" @click="toggle('package', p, false)"><X :size="12" /></button></span>
        <input
          :id="`${idPrefix}-pkg`"
          v-model="pkgInput"
          class="mono-input"
          :placeholder="osFamily === 'windows' ? 'googlechrome vscode' : 'redis-server git'"
          autocomplete="off"
          spellcheck="false"
          :aria-describedby="`${idPrefix}-pkg-msg`"
          @keydown.enter.prevent="addPackages"
          @blur="pkgInput && addPackages()"
        />
      </div>
    </Field>
    <p class="dim small">Always applied: security updates, guest agent, {{ osFamily === 'windows' ? 'time zone and firewall rules' : 'SSH hardening (keys only, no root login)' }}.</p>
  </div>
</template>

<style scoped>
.sp { display: flex; flex-direction: column; gap: 18px; }
.group { display: flex; flex-direction: column; gap: 6px; }
h3 { display: flex; align-items: center; gap: 6px; font-size: 14px; }
h3 svg { color: var(--primary); }
.sub { font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: var(--dim); margin-top: 6px; }
.needs, .profiles { list-style: none; border: 1px solid var(--line); border-radius: var(--radius); }
.needs li, .profiles li { display: flex; align-items: center; gap: 10px; padding: 8px 12px; flex-wrap: wrap; }
li + li { border-top: 1px solid var(--line); }
.needs .check, .profiles .check { flex: 1; min-width: 220px; }
.need { display: flex; flex-direction: column; }
.name { font-weight: 500; display: inline-flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.why { color: var(--dim); }
.chips { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; border: 1px solid var(--line-strong); border-radius: var(--radius); padding: 4px 6px; min-height: 36px; background: var(--surface); }
.chips:focus-within { border-color: var(--focus); box-shadow: 0 0 0 3px var(--info-bg); }
.chips.invalid { border-color: var(--err-fg); }
.chips input { flex: 1; min-width: 140px; border: 0; padding: 2px 4px; min-height: 26px; box-shadow: none !important; }
.chip { display: inline-flex; align-items: center; gap: 2px; background: var(--surface-3); border-radius: var(--radius-sm); padding: 2px 2px 2px 8px; }
.chip button { background: transparent; border: 0; color: var(--mut); cursor: pointer; display: grid; place-items: center; width: 24px; height: 24px; border-radius: var(--radius-sm); }
.chip button:hover { background: var(--line); color: var(--fg); }
</style>
