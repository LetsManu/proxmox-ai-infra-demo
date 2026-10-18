// Display helpers shared by the screens.

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

export const STATUS_TONE = { success: 'ok', failed: 'err', running: 'running', queued: 'muted', awaiting_approval: 'warn' }
export const STATUS_LABEL = { success: 'Succeeded', failed: 'Failed', running: 'Running', queued: 'Pending', awaiting_approval: 'Awaiting approval' }

export const ACTION_LABEL = {
  plan: 'Plan', deploy: 'Deploy to Test', validate: 'Validate', configure: 'Install software',
  promote: 'Production request', 'promote-approved': 'Production approved', 'promote-rejected': 'Production rejected',
  'promote-apply': 'Deploy to Production', recreate: 'Recreate', 'recreate-approved': 'Recreate approved',
  'recreate-rejected': 'Recreate rejected', 'recreate-apply': 'Recreate (Production)',
  'platform-plan': 'Platform plan', 'platform-apply': 'Prepare platform',
  'stack-plan': 'Stack plan', 'stack-deploy': 'Stack deploy to Test', 'stack-validate': 'Stack validation',
  'stack-promote': 'Stack production request', 'stack-promote-approved': 'Stack production approved',
  'stack-promote-rejected': 'Stack production rejected', 'stack-promote-apply': 'Stack deploy to Production',
  'role-approved': 'Software role approved', 'role-rejected': 'Software role rejected',
  'tests-approved': 'Tests approved', 'tests-rejected': 'Tests rejected',
}

export const ENV_LABEL = { test: 'Test', prod: 'Production', infra: 'Platform' }
export const OS_LABEL = {
  'ubuntu-24-04': 'Ubuntu 24.04', 'debian-12': 'Debian 12', 'windows-2022': 'Windows Server 2022',
  'debian-12-lxc': 'Debian 12 (container)', 'ubuntu-24-04-lxc': 'Ubuntu 24.04 (container)',
}
export const gb = (mb) => `${+(mb / 1024).toFixed(1)} GB`
export const CHECK_LABEL = {
  vm_running: 'Machine is running', guest_agent_ip: 'Has a network address', cloud_init_completed: 'First boot finished',
  service_health: 'Service answers', configuration_applied: 'Software installed', security_baseline: 'Security baseline',
  app_tests: 'Application tests', exists: 'Machine exists',
}
