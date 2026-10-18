# Live demo script (10–15 minutes)

**Setup the night before:** follow the [checklist](#pre-demo-checklist) at the bottom. Two browser tabs: the console and the Proxmox UI (if live).

| Time | Section |
|---|---|
| 0:00 | Opening and problem |
| 1:00 | Dashboard and architecture |
| 2:00 | Platform: the console builds its own templates |
| 3:00 | Create VM: the assistant picks the software (AI moment 1) |
| 5:00 | Plan in plain language + risk (AI moment 2) |
| 6:00 | Deploy to Test |
| 7:00 | Validation fails → diagnosis (AI moment 3) → passes |
| 8:30 | AI-drafted tests and roles in the review queue |
| 10:00 | Production with human approval |
| 11:30 | Stack: WordPress + monitoring as VM, container and Docker services |
| 13:30 | Security model and closing |

---

## 0:00 Opening

> "Every team that runs Proxmox knows this request: *'Can I get a server for X?'* Today that's a ticket, clicks in the Proxmox UI, a copied template, some software installed by hand, and nobody knows whether production looks like test.
>
> I'll show you a console that turns that request into a **reviewed, tested and approved change**: Infrastructure as Code underneath, AI to help, and people in charge of production."

## 1:00 Dashboard and architecture

Open `http://localhost:8080`. It looks like Proxmox on purpose: navigation and resource tree on the left, Test and Production machines in the tree.

> "Four numbers: what runs, what's being deployed, the last validation, and what waits for a person. One blue button: Create VM."

Optional: show the README architecture diagram. *"The browser only talks to our backend. Only the backend holds a least-privilege Proxmox API token. OpenTofu with separate state for Test and Production, Ansible for software, Claude optional."*

Optional: moon icon top right switches to the dark theme.

## 2:00 Platform

The amber banner says the platform is not ready. Click **Open Platform**.

> "The console lists everything it depends on and who creates it: networks, storage and pool came from a one-time admin bootstrap; templates are created by the console itself."

Click **Check what is missing**. **Expected:** *Plan: 6 to add*: two cloud images, two VM templates, two LXC templates, risk *Low*. Click **Prepare platform** → dialog lists exactly what will happen → **Prepare platform**. Toast *Platform ready*; all resources *Present*.

## 3:00 Create VM (AI moment 1)

Click **Create VM**. Type: *A WordPress site for the marketing team*. Click **Draft with assistant**.

**Basics** opens with name, Ubuntu, 2 vCPU / 4 GB / 32 GB. Change the name to `wpsite-test`.

> "Only what matters is visible. Description and SSH key are under Advanced options. Limits are shown next to each field and checked again on the server."

Click **Continue**. **Software** shows *Recommended for your request*:

> "The assistant listed what WordPress **needs**, split into required and optional, and matched each need: Nginx is an existing profile, PHP and MariaDB are packages it **looked up in the real Ubuntu repository**, WordPress itself has no profile, so it **drafted an Ansible role**, which waits for review and can't be used yet. Backups, monitoring and fail2ban are optional: I decide."

Tick *Monitoring* if you like. Click **Continue**.

## 5:00 Plan (AI moment 2)

Click **Create plan**. **Expected:** *Plan: 1 to add* in a sentence, one green *Create VM* row, risk badge *Low risk*. Click **Why?** for the explanation and the pre-flight checks. Click **View full plan** → the raw OpenTofu output in a side panel (copyable), Esc closes it.

> "This is a real OpenTofu plan. The AI explains it and rates the risk, but our parser computes risk too: if anything is destroyed it's HIGH, and the AI can only raise risk, never lower it."

## 6:00 Deploy to Test

Click **Deploy to Test**. The status card shows *Running*; **Show details** opens the live log (OpenTofu apply, then Ansible). The page switches to the machine when done.

> "It applies exactly the plan we reviewed. Then Ansible installs the software: Linux over SSH, Windows over WinRM."

## 7:00 Validation fails, diagnosis, passes (AI moment 3)

Tick **Simulate a failure (demo mode)** (live: skip), click **Validate**.

**Expected:** the checklist shows *First boot finished* and *Application tests* in red; Security baseline green. Progress step *Validated* is red.

Click **Ask for a diagnosis** → side panel: likely cause, what to check, safe fix, *Recreating is safe*, *No data at risk*.

> "Advice only. It also tells me whether recreating is safe or whether this machine may hold data."

Untick the simulation, click **Validate** → *Passed*. Click **Show details (20 tests)**: security baseline (SSH keys only, no root login, automatic updates, no exposed database ports) and application tests, run on the machine and from the network.

## 8:30 Review queue

In **Automated tests**, click **Draft tests with assistant** → toast *Tests drafted*, **Open review queue**.

> "Everything the AI writes waits here for a person: the WordPress role and the test suite. Both passed automated safety checks: only allowed Ansible modules, HTTPS downloads, no secrets, syntax check."

Click **Show details** on the role: YAML with highlighting. **Approve** the role, then the test suite (simple confirmation, your name is recorded).

## 10:00 Production with human approval

Back on `wpsite-test` (resource tree). Click **Validate** (now with the approved suite), then **Request production approval**.

**Expected:** a dialog *Deploy wpsite to Production?* with *What will happen* (create VM wpsite, ID 100, install software, record the decision), the plan's age, a checkbox and a typed word. **Approve and deploy** is disabled. Tick *"I understand this will affect the production environment."*, type `promote` (still disabled), then `PROMOTE`.

> "Checkbox and typed word, and the API checks everything again: validation still valid, plan younger than an hour, not decided before. If I close this dialog the request waits in the review queue for someone else."

Click **Approve and deploy**. Progress steps all green, `100 wpsite` appears under Production.

## 11:30 Stack (VM + container + Docker)

Click **Stacks → Create stack**. Type *WordPress for marketing with monitoring*, **Draft with assistant**.

> "Now a whole application. The assistant proposes a VM as Docker host running WordPress and MariaDB, and a lightweight LXC container running Prometheus and Grafana. I can edit everything. Passwords are `secret:` references: the machine generates them, they never pass through this console."

**Continue → Create plan** (one plan for both machines) → **Deploy stack to Test** → on the stack page **Validate stack** (container checks, published ports, baseline on each machine) → **Request production approval** → same dialog, `PROMOTE`, for the whole stack at once.

## 13:30 Security model and closing

> "Recap:
> - The Proxmox token never leaves the backend, it is least-privilege and can be a Docker secret.
> - Test and Production have separate state, ID ranges and limits, enforced in the API and in OpenTofu.
> - Production needs a passing validation and a person: checkbox, typed word, audit trail.
> - The AI drafts, explains and diagnoses. It can't install anything nobody approved, and it has no path to production."

Close on **Activity**: every step with who did it.

---

## Failure fallback (mock mode)

If Proxmox, VPN, DNS or the internet fails before or during the demo:

```bash
sed -i 's/^LIVE_MODE=.*/LIVE_MODE=false/' .env
docker compose up -d backend          # recreates the backend with the new mode (~10 s)
```

The header shows **Demo mode**; every step above works identically (simulated IDs, IPs from 192.0.2.0/24, repository lookups from the bundled index). Without the Anthropic API the assistant answers from local rules automatically.

Say: *"The Proxmox host isn't reachable from here, so I'm switching to the built-in simulation. Same code paths, same guardrails."*

Clean slate between rehearsals: `docker compose down -v && docker compose up -d`.

## Pre-demo checklist

- [ ] `docker compose up -d --build` done, both containers `healthy`
- [ ] `docker compose down -v && docker compose up -d` for an empty history (templates start missing so you can show the platform step; `MOCK_PLATFORM_READY=true` skips it)
- [ ] `DEBIAN_12_CT_URL` / `UBUNTU_2404_CT_URL` set (for the stack part)
- [ ] Browser zoom 110–125 %, notifications off, light theme (dark as an optional show-off)
- [ ] Live mode only: bootstrap done, test VLAN has DHCP + DNS, `ANSIBLE_SSH_KEY_FILE` set, no leftover machines with the demo names
- [ ] Mock fallback rehearsed once (`LIVE_MODE=false`)
- [ ] `.env` and `secrets/` not on screen
