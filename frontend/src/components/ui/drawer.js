import { reactive } from 'vue'
import { api, pollJob } from '../../api.js'

// One side drawer for technical content: plans, logs, API responses, AI explanations.
// kind: 'log' | 'plan' | 'yaml' | 'json' | 'text' | 'component'
export const drawer = reactive({ open: false, title: '', subtitle: '', kind: 'text', content: '', jobId: '', live: false, component: null, props: {} })
let follow = 0

export function openDrawer(opts) {
  follow++
  Object.assign(drawer, { subtitle: '', jobId: '', live: false, component: null, props: {}, ...opts, open: true })
}

export function closeDrawer() {
  follow++
  drawer.open = false
}

// Show a job's log, following it live while it runs.
export async function openJob(jobId, title = 'Job log') {
  const token = ++follow
  Object.assign(drawer, { open: true, title, subtitle: `Job ${jobId}`, kind: 'log', content: '', jobId, live: true, component: null })
  try {
    await pollJob(jobId, (j) => {
      if (token !== follow) throw new Error('closed')
      drawer.content = j.logs + (j.error ? `\nERROR: ${j.error}` : '')
    }, 1000)
  } catch {
    /* drawer closed or switched */
  }
  if (token === follow) drawer.live = false
}

export async function jobLogs(jobId) {
  return (await api.job(jobId)).logs
}
