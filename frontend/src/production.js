// Production approvals: one flow for VM promotion, production recreate and stack promotion.
// The backend enforces every rule (validated TEST source, 60-minute window, acknowledge flag,
// typed word); the modal only collects the human decision.
import { api } from './api.js'
import { runJob, store } from './store.js'
import { ask } from './components/ui/modal.js'
import { toast } from './components/ui/toast.js'

const KIND = {
  promote: {
    word: 'PROMOTE',
    title: (j) => `Deploy ${j.vm_name} to Production?`,
    body: (j) => `The validated Test machine ${j.params?.source_vm} is copied to Production as ${j.vm_name} (full clone, production network).`,
    call: (j, body) => api.promote({ ...body, name: j.params.source_vm }),
    label: (j) => `Deploy ${j.vm_name} to Production`,
  },
  recreate: {
    word: 'RECREATE',
    title: (j) => `Recreate production machine ${j.vm_name}?`,
    body: () => 'The machine is destroyed and created again from its template. Data that only exists on its disk is lost.',
    call: (j, body) => api.recreate({ ...body, name: j.vm_name, environment: 'prod' }),
    label: (j) => `Recreate ${j.vm_name}`,
  },
  'stack-promote': {
    word: 'PROMOTE',
    title: (j) => `Deploy stack ${j.vm_name} to Production?`,
    body: (j) => `All ${Object.keys(j.result?.members || {}).length} machines of the validated Test stack are created in Production together.`,
    call: (j, body) => api.stackPromote({ ...body, name: j.params.source }),
    label: (j) => `Deploy stack ${j.vm_name} to Production`,
  },
}

export const supportsApproval = (job) => job && KIND[job.action] && job.status === 'awaiting_approval'

function effects(job) {
  const ch = job.result?.plan?.changes || []
  const verb = { create: 'Create', update: 'Change', destroy: 'Destroy', replace: 'Destroy and recreate' }
  const what = (c) => (c.address.startsWith('module.lxc') ? `container ${c.name}` : `VM ${c.name}`)
  const list = ch.map((c) => `${verb[c.action] || c.action} ${what(c)}${c.vm_id ? ` (ID ${c.vm_id})` : ''}`)
  list.push('Install the software with Ansible', 'Record the decision in the history with your name')
  return list
}

/** Show the production modal; on confirm, apply the reviewed plan. Returns the apply job or null. */
export async function reviewAndApprove(job, { onUpdate } = {}) {
  const k = KIND[job.action]
  const ok = await ask({
    title: k.title(job),
    body: k.body(job),
    effects: effects(job),
    note: `${job.result?.plan?.summary || ''} The plan was created ${new Date(job.created_at + (job.created_at.endsWith('Z') ? '' : 'Z')).toLocaleTimeString()} and is valid for 60 minutes.`,
    production: true,
    typed: k.word,
    confirmLabel: 'Approve and deploy',
  })
  if (!ok) return null
  store.awaiting = (store.awaiting || []).filter((j) => j.id !== job.id) // decided: no longer waiting
  const applied = await runJob(k.label(job), () => k.call(job, { stage: 'approve', approval_job_id: job.id, acknowledge: true, confirmation: k.word }), { onUpdate })
  if (applied?.status === 'success') toast.success(`${job.vm_name}: ${job.result?.plan?.summary || 'applied'}`, { title: 'Production updated' })
  return applied
}

export async function rejectRequest(job) {
  const k = KIND[job.action]
  const ok = await ask({
    title: 'Reject this production request?',
    body: 'Nothing is changed in Production. The request is closed and recorded in the history.',
    confirmLabel: 'Reject request',
  })
  if (!ok) return false
  try {
    await k.call(job, { stage: 'reject', approval_job_id: job.id })
    store.awaiting = (store.awaiting || []).filter((j) => j.id !== job.id)
    toast.info('Nothing was changed in Production.', { title: 'Request rejected' })
    return true
  } catch (e) {
    toast.error(e.message, { title: 'Could not reject' })
    return false
  }
}
