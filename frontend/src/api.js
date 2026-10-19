// All calls go to the backend under /api. The browser never sees Proxmox credentials.

// Session: HttpOnly cookie set by the backend. Writes echo the session's CSRF token.
let csrf = ''
let unauthorized = () => {}
export const setCsrf = (t) => { csrf = t || '' }
export const onUnauthorized = (fn) => { unauthorized = fn }

async function request(method, path, body) {
  let res
  const headers = {}
  if (body) headers['Content-Type'] = 'application/json'
  if (method !== 'GET' && csrf) headers['X-CSRF-Token'] = csrf
  try {
    res = await fetch(`/api${path}`, {
      method,
      headers,
      credentials: 'same-origin',
      body: body ? JSON.stringify(body) : undefined,
    })
  } catch {
    const err = new Error('The console backend did not answer. Check that the backend container is running.')
    err.network = true
    throw err
  }
  const data = await res.json().catch(() => ({}))
  if (res.status === 401 && !path.startsWith('/auth/')) unauthorized()
  if (!res.ok) {
    const err = new Error(formatError(data.detail) || `${res.status} ${res.statusText}`)
    err.status = res.status
    err.detail = data.detail
    throw err
  }
  return data
}

export function formatError(detail) {
  if (!detail) return ''
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((d) => `${(d.loc || []).slice(1).join('.')}: ${String(d.msg).replace(/^Value error, /, '')}`).join('; ')
  }
  if (detail.errors) return `${detail.message}: ${detail.errors.join('; ')}`
  return JSON.stringify(detail)
}

const q = (o) => {
  const s = new URLSearchParams(Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== '')).toString()
  return s ? `?${s}` : ''
}

export const api = {
  authConfig: () => request('GET', '/auth/config'),
  me: () => request('GET', '/auth/me'),
  login: (username, password) => request('POST', '/auth/login', { username, password }),
  logout: () => request('POST', '/auth/logout'),
  health: () => request('GET', '/health'),
  proxmoxStatus: () => request('GET', '/proxmox/status'),
  templates: () => request('GET', '/templates'),
  profiles: () => request('GET', '/profiles'),
  environments: () => request('GET', '/environments'),
  platform: () => request('GET', '/platform'),
  platformPlan: () => request('POST', '/platform/plan'),
  platformApply: (planJobId, confirmDestroy = false) =>
    request('POST', '/platform/apply', { plan_job_id: planJobId, confirm_destroy: confirmDestroy }),

  vms: () => request('GET', '/vms'),
  history: (limit = 50) => request('GET', `/history?limit=${limit}`),
  jobs: (params = {}) => request('GET', `/jobs${q(params)}`),
  job: (id) => request('GET', `/jobs/${id}`),
  plan: (spec) => request('POST', '/vms/plan', { spec }),
  deployTest: (spec, planJobId) => request('POST', '/vms/deploy/test', { spec, plan_job_id: planJobId }),
  configure: (body) => request('POST', '/vms/configure', body),
  validate: (body) => request('POST', '/vms/validate', body),
  promote: (body) => request('POST', '/vms/promote/production', body),
  recreate: (body) => request('POST', '/vms/recreate', body),
  power: (body) => request('POST', '/vms/power', body),
  tests: (name, environment) => request('GET', `/vms/tests${q({ name, environment })}`),
  draftTests: (name, environment = 'test') => request('POST', '/vms/tests/draft', { name, environment }),

  stacks: () => request('GET', '/stacks'),
  stackPlan: (stack, recreate = false) => request('POST', '/stacks/plan', { stack, recreate }),
  stackDeploy: (planJobId) => request('POST', '/stacks/deploy', { plan_job_id: planJobId }),
  stackValidate: (body) => request('POST', '/stacks/validate', body),
  stackPromote: (body) => request('POST', '/stacks/promote', body),

  proposals: (params = {}) => request('GET', `/proposals${q(params)}`),
  approveProposal: (id) => request('POST', `/proposals/${id}/approve`),
  rejectProposal: (id) => request('POST', `/proposals/${id}/reject`),

  summarizePlan: (planText, environment) => request('POST', '/ai/summarize-plan', { plan_text: planText, environment }),
  generateSpec: (prompt) => request('POST', '/ai/generate-vm-spec', { prompt }),
  generateStack: (prompt) => request('POST', '/ai/generate-stack', { prompt }),
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
