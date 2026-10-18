# Changelog

## 2.0.1 – 2026-10-18

- **OVERVIEW.md** now walks through every screen with 40 annotated screenshots (red frames mark what to click): empty environment → platform → Test VM → validation, diagnosis and review queue → Production → stack → end state.
- Fix: after approving a production request, the stale *Awaiting approval* card disappeared only after the next refresh.
- Fix: production machines had no *Validate* action.
- **OVERVIEW.md**: step-by-step setup from a bare Proxmox node to the first promoted VM and stack, with a check after every step, day-2 operations and troubleshooting.
- Docs: fixed `docs/screenshots.md` (pointed to removed images); all docs use the current button names; architecture covers stacks, containers, proposals and tests.
- Fix: secret files must be readable by the backend (uid 10001). The backend now names the unreadable file instead of crashing obscurely; the bootstrap script and `docker-compose.secrets.yml` show the `chown`.
- LXC containers request the `nesting` feature only when they run Docker.

## 2.0.0 – 2026-10-18

The assistant now plans whole applications, and the console is rebuilt for office and IT staff.

**Stacks**
- A stack is several machines deployed, validated and promoted together: VMs, **LXC containers** (new `infra/modules/lxc`, `var.containers`) and **Docker services** on a Docker host in the stack (compose file rendered by the console, run by the `docker_services` role).
- Docker services can only express images, published ports, named volumes and plain settings. Passwords are `secret:<name>` references; the host generates them into `/opt/stacks/<stack>/.env` (mode 0600) and they never reach the console.
- *Create stack*: the assistant (Claude, or local recipes offline) drafts the architecture, you edit it, review one plan for all members and deploy. Whole-stack validation and whole-stack promotion with one typed `PROMOTE` approval. Recreate rebuilds all members; removing a component destroys it.
- The platform stack also downloads the official LXC templates (`DEBIAN_12_CT_URL`, `UBUNTU_2404_CT_URL`).

**Software chosen by the assistant**
- Each need of a request is listed as *required* or *optional* and resolved to an existing profile, a package checked against the real repository (packages.ubuntu.com, packages.debian.org, Chocolatey; cached, with an offline index), or a drafted Ansible role.
- Drafted roles go through automated review (allowed modules only, HTTPS downloads, no literal secrets, `ansible-playbook --syntax-check`) and wait in the **review queue**; approved roles become software profiles.

**Automated tests**
- Validate now runs a **security baseline** (SSH hardening, automatic updates, guest agent, Windows firewall, no exposed database ports) and **application tests**, inside the machine (Ansible, `infra/ansible/tests.yml`) and from the network. Tests are typed, declarative checks; failures block promotion.
- *Draft tests with assistant* proposes an application test suite; it is used after approval.

**Console redesign** (see `UI_GUIDELINES.md`)
- Light Proxmox-style theme by default, optional dark theme; colour only for meaning.
- Dashboard with status cards and recent activity; guided *Create VM* wizard; machine and stack pages with lifecycle steps and one primary action; review queue for production requests and AI drafts; platform and activity pages; shareable URLs.
- Component library: cards, badges, fields, modals with typed confirmation, drawers for plans/logs/AI output, toasts with *View details*, status cards, friendly error panels, data tables, progress steps.

**Fixes**
- Ansible runs with `stdin=/dev/null` (it refused to start under some process managers).
- Test machine names must leave a valid production name (`wp-test` would promote to `wp`).

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
