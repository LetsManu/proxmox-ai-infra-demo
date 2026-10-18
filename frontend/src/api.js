// All calls go to the backend under /api. The browser never sees Proxmox credentials.

async function request(method, path, body) {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const err = new Error(formatError(data.detail) || `${res.status} ${res.statusText}`)
    err.status = res.status
    err.detail = data.detail
    throw err
  }
  return data
}

function formatError(detail) {
  if (!detail) return ''
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((d) => `${(d.loc || []).slice(1).join('.')}: ${d.msg.replace(/^Value error, /, '')}`).join('; ')
  }
  if (detail.errors) return `${detail.message}: ${detail.errors.join('; ')}`
  return JSON.stringify(detail)
}

export const api = {
  health: () => request('GET', '/health'),
  proxmoxStatus: () => request('GET', '/proxmox/status'),
  templates: () => request('GET', '/templates'),
  environments: () => request('GET', '/environments'),
  vms: () => request('GET', '/vms'),
  history: () => request('GET', '/history?limit=50'),
  job: (id) => request('GET', `/jobs/${id}`),
  plan: (spec) => request('POST', '/vms/plan', { spec }),
  deployTest: (spec, planJobId) => request('POST', '/vms/deploy/test', { spec, plan_job_id: planJobId }),
  validate: (body) => request('POST', '/vms/validate', body),
  promote: (body) => request('POST', '/vms/promote/production', body),
  recreate: (body) => request('POST', '/vms/recreate', body),
  summarizePlan: (planText, environment) => request('POST', '/ai/summarize-plan', { plan_text: planText, environment }),
  generateSpec: (prompt) => request('POST', '/ai/generate-vm-spec', { prompt }),
  troubleshoot: (body) => request('POST', '/ai/troubleshoot', body),
}

const TERMINAL = ['success', 'failed', 'awaiting_approval']

// Poll a job until it reaches a terminal status. onUpdate receives every snapshot.
export async function pollJob(jobId, onUpdate, intervalMs = 800) {
  for (;;) {
    const job = await api.job(jobId)
    onUpdate?.(job)
    if (TERMINAL.includes(job.status)) return job
    await new Promise((r) => setTimeout(r, intervalMs))
  }
}
