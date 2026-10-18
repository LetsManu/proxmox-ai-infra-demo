# Live demo script (10–15 minutes)

**Setup the night before:** follow the [checklist](#pre-demo-checklist) at the bottom. Have two browser tabs: the console and the Proxmox UI (if live).

| Time | Section |
|---|---|
| 0:00 | Opening and problem |
| 1:30 | Architecture in one slide |
| 3:00 | AI drafts a VM |
| 4:30 | Plan + AI review |
| 6:00 | Deploy to TEST |
| 7:00 | Validation fails → AI troubleshooting → recreate |
| 9:30 | Validation passes |
| 10:00 | Production promotion with human approval |
| 12:30 | Security model + closing |

---

## 0:00 Opening

> "Every team that runs Proxmox knows this request: *'Can I get a VM?'* Today that's a ticket, a few clicks in the Proxmox UI, a copied template, and nobody really knows whether production looks like test.
>
> I'll show you a small platform that turns that request into a **reviewed, validated and approved change**: Infrastructure as Code underneath, AI to help, and humans in charge of production."

## Problem it solves

> "Three problems:
> 1. **Manual clicks don't scale and aren't reviewable.** We use OpenTofu, so every change is a plan you can read before it happens.
> 2. **Test and production drift.** Production VMs here are promoted from a TEST VM that passed validation, with the same spec.
> 3. **Operators need help, not autopilot.** AI writes drafts and explains plans. It cannot deploy or approve anything."

## 1:30 Architecture

Show the Mermaid diagram in README.md (or the [architecture doc](docs/architecture.md)).

> "The browser only talks to our backend. The backend alone holds a **least-privilege Proxmox API token**: not root, not a password. It runs OpenTofu with separate state for TEST and PRODUCTION. Claude is optional; without it, a local rule engine produces the same structure."

## Start (if not already running)

```bash
cd proxmox-ai-infra-demo
docker compose up -d
docker compose ps          # both services "healthy"
```

Open `http://localhost:8080`. Point at the header and the progress bar below it:

> "Top right: mode (Live or Mock), the Proxmox version and node, OpenTofu, which assistant (Claude or local rules), and who I am for the audit trail. The bar underneath tracks this VM from definition to production; the highlighted orange button is always the next step."

## 3:00 AI drafts a VM (AI moment 1)

The prompt box is pre-filled: *"Create a small Ubuntu test server for a web app with 2 CPUs, 4 GB RAM, 40 GB disk, and Docker installed."* Open **Draft from a description** (open by default) and click **Draft spec**.

**Expected:** a draft card: name `demo-web-test`, Ubuntu 24.04, 2 vCPU · 4 GB · 40 GB, packages `qemu-guest-agent, docker.io`.

> "The AI produces structured JSON, and then **our code validates it**: known template, within TEST limits, safe commands. It's a draft: nothing happened yet."

Optional quick win: replace the prompt with *"production database with 64 cpus and 512 GB RAM"* → **Draft rejected** with the exact limits. Then restore the original prompt (or just keep the first draft).

Click **Use this spec**.

## 4:30 Plan + AI review (AI moment 2)

Click **Generate Plan**.

**Expected:** Plan card `1 to add · 0 to change · 0 to destroy`, a green *Create* row, VMID in 900–999, template 9000; the raw OpenTofu output under *OpenTofu output*. **Plan review** card: *Low risk*, a plain-language summary, a tickable *Before you continue* checklist, and the note that production changes always need a person.

> "This is a real OpenTofu plan. The AI translates it into plain English and rates the risk. Important detail: risk is computed **twice**. If the AI says 'low' but the plan destroys something, our parser overrides it to HIGH. The AI can raise risk, never lower it."

## 6:00 Deploy to TEST

Click **Deploy to Test**. Scroll to the **Job log**.

**Expected:** `Creating... Still creating... Creation complete ... Apply complete! Resources: 1 added`.

> "Deploy applies **exactly the plan we just reviewed**: the saved plan file. If I change the form now, the button disables and the API refuses too. TEST uses linked clones from a cloud-init template, so it's fast and disposable."

(Live mode: switch to the Proxmox tab and show VM 9xx booting.)

## 7:00 Failure → AI troubleshooting → recreate (AI moment 3)

In **Validation**: tick **Simulate failure (mock)** (in live mode, skip this or use a VM on a VLAN without DNS). Click **Validate**.

**Expected:** *VM is running* ✔, *Cloud-init finished* ✖, *Service responds* ✖, status **Failed**; the progress bar marks Validate red.

Click **Diagnose**.

**Expected (inside the Validation card):** likely cause = cloud-init didn't finish (package install, no DNS on test VLAN); *Check first* (`cloud-init status --long`); *Safe fix*; pills *Recreate is safe* and *Stateless*.

> "It tells me what to check, what's safe to do, and, importantly, whether recreating is OK or whether this VM might hold data and needs backup/restore instead. For a disposable TEST VM: recreate."

Click **Recreate VM** → the confirmation dialog explains the data loss → **Recreate**.

**Expected:** Plan card shows a red *Replace* row and the **Destructive change** callout, Plan review says **High risk**; job log `Destroying... Creating...`.

> "Note the AI flags this as HIGH risk because it destroys a VM. In TEST that's fine; in production the same action needs approval."

## 9:30 Validation passes

Untick *Simulate failure*, click **Validate**.

**Expected:** all four checks ✔ (IP from the guest agent, `boot-finished present`, `tcp/…:22 open`), status **Passed**.

## 10:00 Production promotion

Point at the **Production approval** panel gates: *TEST validation passed ✔*.

Click **Request Production Promotion**.

**Expected:** the **Production approval** card gets an amber outline and *Awaiting approval*; production plan `1 to add` for `demo-web`, VMID 100–299; review **Medium risk** (production change).

> "The spec was copied from the validated TEST VM. The production plan is ready, and **nothing has changed yet**. The job is parked."

Show that **Approve** is disabled. Tick *"I understand this will change production"*, type `promote` in lowercase (still disabled), then `PROMOTE`.

> "Checkbox plus typed confirmation. And this isn't just UI: the API checks all of it again, plus that validation is still valid, that the plan is less than an hour old and wasn't already approved."

Click **Approve & promote to production**.

**Expected:** toast *Production updated*; the progress bar completes; History shows *Promotion approved* and *Promote to production · Succeeded*; **Managed VMs** lists `demo-web` in Production.

Optional (30 s): switch to **Production**, select `demo-web` from Managed VMs, click **Recreate VM** → the approval panel asks for `RECREATE`, the plan is DESTRUCTIVE and the AI says **HIGH** risk. Click **Reject**.

## 12:30 Security model and closing

> "Recap of the guardrails:
> - The Proxmox token never leaves the backend, it's least-privilege, scrubbed from logs, and can be a Docker secret.
> - TEST and PRODUCTION have separate state and separate VM ID ranges, and limits are enforced in the API **and** in OpenTofu.
> - Production needs a passing validation and a human: checkbox, typed word, audit trail.
> - The AI makes us faster at the boring parts (writing specs, reading plans, triage), but it has no credentials and no path to production.
>
> And everything you saw also runs fully offline in mock mode, which is how I make sure a live demo survives a dead VPN."

Show the **History** table as the closing image.

---

## Failure fallback (mock mode)

If Proxmox, VPN, DNS or the internet fails before or during the demo:

```bash
sed -i 's/^LIVE_MODE=.*/LIVE_MODE=false/' .env
docker compose up -d backend          # recreates the backend with the new mode (~10 s)
```

The header switches to **Mock mode**; every step above works identically (simulated VM IDs, IPs from 192.0.2.0/24). If the Anthropic API is unreachable, AI answers come from the local fallback automatically (`source: local-fallback`); no action needed.

Say: *"The Proxmox host isn't reachable from here, so I'm switching to the built-in simulation. Same code paths, same guardrails, simulated hypervisor."*

Clean slate between rehearsals: `docker compose down -v && docker compose up -d`.

## Pre-demo checklist

- [ ] `docker compose up -d --build` done, both containers `healthy`
- [ ] `docker compose down -v && docker compose up -d` for empty history
- [ ] Browser zoom 110–125 %, dark mode, notifications off
- [ ] Live mode only: templates 9000/9001 exist, test VLAN has DHCP + DNS, `curl` to the API works from the console host, no leftover VMs in 900–999 / 100–299 with the demo names
- [ ] Mock fallback rehearsed once (`LIVE_MODE=false`)
- [ ] `.env` not on screen (no secrets in the terminal history you show)
