# AI-assisted operations

The console uses Claude (Anthropic API) for three tasks. In all of them the AI **advises**; deterministic code decides. Without a key (`AI_PROVIDER=none`), or if the provider fails, a local rule-based fallback produces conservative output, so the demo works offline.

Configuration:

```dotenv
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=<key>          # or ANTHROPIC_API_KEY_FILE via docker-compose.secrets.yml
AI_MODEL=claude-opus-5-5
AI_MAX_TOKENS=4000
```

Responses are requested as structured JSON (`output_config.format` with a JSON schema) at low effort, so they parse reliably and come back quickly.

## 1. Generate a VM specification

`POST /api/ai/generate-vm-spec`

```json
{ "prompt": "Create a small Ubuntu test server for a web app with 2 CPUs, 4 GB RAM, 40 GB disk, and Docker installed." }
```

Response (shape):

```json
{
  "spec": {
    "name": "demo-web-test", "environment": "test", "template": "ubuntu-24-04",
    "cores": 2, "memory_mb": 4096, "disk_gb": 40, "network": "test",
    "cloud_init": { "packages": ["qemu-guest-agent", "docker.io"], "commands": ["systemctl enable --now docker"] }
  },
  "warnings": [],
  "source": "anthropic:claude-opus-5-5",
  "note": "Generated spec is a draft. Review it, then Generate Plan. Nothing is deployed automatically."
}
```

Guardrails applied to every AI answer:

| Rule | Behaviour |
|---|---|
| Environment | Always forced to `test` (+ warning). Production is only reachable through promotion. |
| Template | Must be a configured key (`ubuntu-24-04`, `debian-12`), else **rejected**. |
| Size | Must fit TEST limits (4 vCPU / 8 GB / 64 GB), else **rejected** with the exact limit. |
| cloud-init commands | Single line, < 300 chars, no `rm -rf /`, `mkfs`, `dd if=`, `curl … \| sh`, fork bombs, reboot/shutdown: else **rejected**. |
| Packages | Valid package names; `qemu-guest-agent` is added if missing. |
| Name | Normalised to lowercase, `-test` suffix. |
| Secrets | The prompt never contains secrets; the AI is told never to invent keys; SSH keys are not part of AI output. |

Rejections return HTTP 422 with the list of reasons, which the UI shows. Good demo prompt: *"production database with 64 cpus and 512 GB RAM"*.

## 2. Explain a Terraform/OpenTofu plan

`POST /api/ai/summarize-plan` with `{ "plan_text": "...", "environment": "prod" }` returns:

```json
{
  "summary": "This Production plan creates 1, updates 0 and destroys 0 resource(s) ...",
  "resources_to_create": ["module.vm[\"demo-web\"].proxmox_virtual_environment_vm.this"],
  "resources_to_update": [],
  "resources_to_destroy": [],
  "risk_level": "medium",
  "recommended_checks": ["Confirm the TEST VM with the same spec passed validation", "..."],
  "approval_recommendation": "Eligible for human review once TEST validation passed. A human must review ...",
  "human_approval_required": true,
  "human_approval_note": "A human must review and explicitly approve every production change. ...",
  "source": "anthropic:claude-opus-5-5"
}
```

Guardrails:

- The plan is also parsed locally. The AI's risk level can only be **raised**, never lowered: any destroy/replace is `high`; production create/update is at least `medium`.
- Destroyed resources found by the parser are always listed, even if the AI omitted them.
- The word "approved" is removed from the recommendation. The response always states that a human must approve.
- The endpoint has no side effects: it cannot trigger apply or approval.

## 3. Troubleshooting

`POST /api/ai/troubleshoot` with VM name, job logs, validation output and optional Proxmox status returns:

```json
{
  "likely_cause": "cloud-init did not finish: usually package installation failing (no DNS/Internet on the test VLAN) ...",
  "immediate_checks": ["Open the VM console in Proxmox and run: cloud-init status --long", "..."],
  "safe_remediation_steps": ["Fix network/DNS on the test VLAN or the cloud-init snippet", "Recreate the TEST VM ..."],
  "recreate_appropriate": true,
  "recreate_reasoning": "Recreating is safe only for disposable TEST VMs where all config comes from cloud-init.",
  "stateful_risk": false,
  "stateful_notes": "No sign of persistent data; VM appears disposable."
}
```

For production VMs `stateful_risk` is forced to `true`: the answer then recommends backup/restore over recreate.

The local fallback recognises: 401 token errors, 403 permission errors, cloud-init not finished, guest agent/IP missing, VM ID collisions, network timeouts, storage problems.

## Why the AI must not have unrestricted production access

- **Non-determinism**: the same prompt can yield different plans. Production changes must be reproducible and reviewable: a saved plan file, applied as reviewed.
- **Prompt injection**: logs, VM descriptions and plan text are untrusted input. A model that can act on them can be steered by them. Here they can only influence advice text.
- **Accountability**: an approval must be attributable to a person who understood the impact (checkbox + typed word, recorded in history).
- **Blast radius**: a wrong destroy in production loses data. Risk ratings are floored by deterministic rules, and the approval path has no AI step.
- **Least privilege applies to automation too**: the AI has no credentials at all. It never sees the Proxmox token; it receives plan text and logs, from which secrets are scrubbed.

## Example prompts for the demo

| Prompt | Expected result |
|---|---|
| "Create a small Ubuntu test server for a web app with 2 CPUs, 4 GB RAM, 40 GB disk, and Docker installed." | Valid TEST spec with `docker.io` |
| "Debian box for a Postgres database, 2 cores, 8 GB RAM" | `debian-12`, `postgresql` package |
| "Put a web server straight into production" | Spec forced to TEST, warning about promotion |
| "production database with 64 cpus and 512 GB RAM" | Rejected: exceeds limits |
| Plan with a recreate in production | Risk HIGH, destroy listed, backup check first |
| Failed validation (simulate failure) → **Diagnose** | cloud-init cause, recreate appropriate for TEST |
