import { reactive } from 'vue'
import { api, pollJob } from './api.js'
import { toast } from './components/ui/toast.js'
import { openJob } from './components/ui/drawer.js'

// Shared state for all screens. Loaded once, refreshed every 10 s and after each job.
export const store = reactive({
  health: null,
  pxStatus: null,
  templates: null,
  environments: [],
  profiles: [],
  platform: null,
  vms: null,
  stacks: null,
  history: null,
  awaiting: [],
  proposals: [],
  loadError: '',
  running: [], // jobs started from this browser: [{ id, label, status, action }]
})

export async function loadStatic() {
  try {
    const [health, templates, environments, profiles] = await Promise.all([
      api.health(), api.templates(), api.environments(), api.profiles(),
    ])
    Object.assign(store, { health, templates, environments, profiles, loadError: '' })
    api.proxmoxStatus().then((s) => (store.pxStatus = s)).catch(() => {})
    refreshPlatform()
  } catch (e) {
    store.loadError = e.message
  }
  await refresh()
}

export async function refresh() {
  try {
    const [vms, stacks, history, awaiting, proposals] = await Promise.all([
      api.vms(), api.stacks(), api.history(), api.jobs({ status: 'awaiting_approval', limit: 20 }),
      api.proposals({ status: 'pending' }),
    ])
    Object.assign(store, { vms, stacks, history, awaiting, proposals, loadError: '' })
  } catch (e) {
    store.loadError = e.message
  }
}

export async function refreshPlatform() {
  try {
    ;[store.platform, store.templates] = await Promise.all([api.platform(), api.templates()])
  } catch (e) {
    store.platform = { reachable: false, error: e.message, resources: [] }
  }
}

export async function reloadProfiles() {
  store.profiles = await api.profiles()
  return store.profiles
}

/**
 * Start a backend job and follow it to the end.
 * Successes are reported by the caller (short toast); failures get a persistent
 * toast with "View details", which opens the job log in a drawer.
 */
export async function runJob(label, start, { onUpdate, quiet = false, rethrow = false } = {}) {
  let entry
  try {
    const { job_id } = await start()
    entry = reactive({ id: job_id, label, status: 'queued' })
    store.running.push(entry)
    const job = await pollJob(job_id, (j) => {
      entry.status = j.status
      onUpdate?.(j)
    })
    if (job.status === 'failed' && !quiet) {
      toast.error(job.error || 'The job failed.', {
        title: `${label} failed`,
        action: { label: 'View details', run: () => openJob(job.id, label) },
      })
    }
    return job
  } catch (e) {
    if (rethrow && !entry) throw e // caller shows the error inline (e.g. validation of a form)
    toast.error(e.message, { title: `${label} could not start` })
    return null
  } finally {
    if (entry) store.running.splice(store.running.indexOf(entry), 1)
    refresh()
  }
}

export const isMock = () => store.health && !store.health.settings.live_mode
