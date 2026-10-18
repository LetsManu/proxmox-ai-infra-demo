// Turn backend error text into plain language: what happened and what to check.
const RULES = [
  [/template .* does not exist|prepare the platform|not configured/i, 'A template this machine needs is not on the Proxmox node yet.', 'Open Platform and run "Prepare platform".', true],
  [/401|rejected the API token/i, 'Proxmox did not accept the console\'s API token.', 'PROXMOX_USER, PROXMOX_TOKEN_ID and the token secret in the server configuration.', false],
  [/403|permission denied/i, 'The API token is not allowed to do this.', 'The role and ACLs of the automation user (docs/api-token-setup.md).', false],
  [/cannot reach|did not answer|timed out|timeout/i, 'A service did not answer in time.', 'Network access from the console to Proxmox, and that the backend is running.', true],
  [/above|limit|exceeds|max \d/i, 'The request is larger than this environment allows.', 'CPU, memory and disk against the limits shown next to each field.', false],
  [/ansible|configuration failed|unreachable/i, 'The machine was created, but installing the software did not finish.', 'The failing task in the job log; SSH/WinRM access and package mirrors.', true],
  [/validation|check/i, 'Some checks did not pass.', 'The failed checks below, or ask for a diagnosis.', true],
  [/no free vm id/i, 'All VM IDs of this environment are in use.', 'Remove machines you no longer need.', false],
  [/changed after the plan|generate a new plan|already applied|plan the stack again/i, 'The plan no longer matches what you want to deploy.', 'Create a new plan and review it.', true],
]

export function friendly(text = '') {
  for (const [re, summary, check, retry] of RULES) if (re.test(text)) return { summary, check, retry }
  return { summary: text.split('\n')[0].slice(0, 220) || 'Something went wrong.', check: '', retry: true }
}
