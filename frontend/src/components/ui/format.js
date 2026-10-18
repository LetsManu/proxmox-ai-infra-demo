// Small display helpers shared by the panels.

export function relTime(ts) {
  if (!ts) return '–'
  const d = new Date(ts.endsWith('Z') || ts.includes('+') ? ts : `${ts}Z`)
  const s = Math.round((Date.now() - d.getTime()) / 1000)
  if (s < 45) return 'just now'
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  if (s < 86400) return `${Math.round(s / 3600)} h ago`
  return d.toLocaleDateString()
}

export function fullTime(ts) {
  if (!ts) return ''
  return new Date(ts.endsWith('Z') || ts.includes('+') ? ts : `${ts}Z`).toLocaleString()
}

export const STATUS_TONE = {
  success: 'ok',
  failed: 'err',
  running: 'info',
  queued: 'muted',
  awaiting_approval: 'warn',
}

export const STATUS_LABEL = {
  success: 'Succeeded',
  failed: 'Failed',
  running: 'Running',
  queued: 'Queued',
  awaiting_approval: 'Awaiting approval',
}

export const ACTION_LABEL = {
  plan: 'Plan',
  deploy: 'Deploy',
  validate: 'Validate',
  promote: 'Promotion request',
  'promote-approved': 'Promotion approved',
  'promote-rejected': 'Promotion rejected',
  'promote-apply': 'Promote to production',
  recreate: 'Recreate',
  'recreate-approved': 'Recreate approved',
  'recreate-rejected': 'Recreate rejected',
  'recreate-apply': 'Recreate (production)',
  'platform-plan': 'Platform plan',
  'platform-apply': 'Build platform',
  configure: 'Configure software',
}

export const ENV_LABEL = { test: 'Test', prod: 'Production', infra: 'Platform' }
