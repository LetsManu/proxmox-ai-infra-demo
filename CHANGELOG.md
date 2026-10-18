# Changelog

## 1.3.0 – 2026-10-18

Software is per project instead of a fixed list.

- Profiles are discovered at runtime from Ansible roles with a `profile.yml`: built-in roles plus project folders (`EXTRA_PROFILE_DIRS`, default `./profiles` mounted read-only). New folders appear after *Refresh*, without a rebuild. Example project profile: `redis`.
- Free-form **Extra packages** per VM: apt names for Linux, Chocolatey IDs for Windows, installed by `packages_linux` / `packages_windows`. Names are validated, installed only through the package manager, `PACKAGE_DENYLIST` applies.
- AI drafts use the live catalog and can add packages (skipping software a profile already covers).

## 1.2.0 – 2026-10-18

The console now creates everything it needs and configures the VMs it deploys.

- **Bootstrap stack** (`infra/bootstrap`, `infra/scripts/bootstrap.sh`): least-privilege user, role, privilege-separated API token and ACLs, resource pool, image/snippet directory storage, SDN VLAN zone with `vtest`/`vprod` vnets. Run once by an admin; the console never holds admin credentials. The token secret lands in `secrets/`.
- **Platform stack** (`infra/platform`): downloads the official Ubuntu/Debian cloud images and builds the templates as code. New *Platform* panel and workflow step: resource status, *Prepare Platform* (plan) and *Build templates* (apply). Generating a VM plan waits until its template exists.
- **Software configuration with Ansible** (`infra/ansible`) for Linux (SSH) and Windows (WinRM): base role plus profiles `docker`, `nginx`, `postgresql`, `node_exporter`, `iis`, `windows_tools`. Runs after deploy, recreate and approved promotion; *Configure* re-runs it. Validation checks *Software configured*.
- **Windows Server 2022** template support (provided once, cloudbase-init, Administrator password via secret, 15-character names).
- AI drafts pick software only from the profile catalog and recognise Windows requests.
- VMs join the resource pool; Linux VMs get a guest-agent vendor snippet when a snippet store is configured.
- CI validates all three stacks and the playbook syntax.

## 1.1.0 – 2026-10-18

- Console redesign in the style of the Proxmox VE / Datacenter Manager dark theme: top bar with Tasks and user buttons, Server View resource tree (Datacenter › node › Test / Production › VMs, templates, storage), toolbar actions, light-blue panel titles, 13px Helvetica/Arial. Contrast-checked tokens, Lucide SVG icons instead of emoji, monospace bundled offline.
- Workflow progress bar (Define → Production); the next step is the only primary button.
- Toast notifications, confirmation dialog for destructive actions, status pills with icon + text, skeleton loading states.
- Diagnosis shown inside the Validation card; tickable pre-flight checklist in the plan review.
- Tables turn into cards on phones; 44px touch targets on touch devices; reduced-motion support.

## 1.0.0 – 2026-10-18

Initial release for the live demonstration.

- Web console (Vue 3): environment selector, VM form, AI spec drafting, plan, AI review, validation, production approval, job log, history.
- FastAPI backend with SQLite history, background jobs, Proxmox API token client, OpenTofu runner with separate TEST/PROD state.
- OpenTofu root module + reusable `modules/vm` (bpg/proxmox), environment tfvars, policy checks.
- Scripts: cloud-init template builder (Ubuntu 24.04, Debian 12), CLI validation, CLI promotion with typed confirmation.
- AI (Claude) for VM specs, plan summaries and troubleshooting with deterministic guardrails and an offline fallback.
- Mock mode covering the whole workflow without Proxmox or internet.
- Hardened Docker Compose (non-root, read-only, cap_drop, Docker secrets override), CI (tests, build, tofu validate, compose, gitleaks), Dependabot.
