# Changelog

## 2.1.0 – 2026-10-19

Sign-in with your directory, and releases that install in a few minutes.

**Sign-in and roles** ([docs/authentication.md](docs/authentication.md))
- `AUTH_MODE=oidc` for Authentik, Microsoft Entra ID, AD FS and other OpenID Connect providers (authorization code flow with PKCE; ID token signature, issuer, audience and nonce checked; groups from the token or userinfo).
- `AUTH_MODE=ldap` for Active Directory (nested groups, sign-in by short name or UPN), OpenLDAP and the Authentik LDAP outpost. TLS is required (LDAPS or StartTLS); filter input is escaped; empty passwords are refused; five failures lock a username for five minutes.
- Roles from groups: **viewer**, **operator**, **approver**. Writes need operator; production approvals, the platform apply and AI drafts need approver. `AUTH_FOUR_EYES=true` keeps a requester from deciding their own production change.
- Server-side sessions (only a hash of the token is stored), `HttpOnly`/`SameSite` cookie, CSRF token on every change, origin check on sign-in. Jobs, approvals and the history record the signed-in user; sign-ins are in the history too.
- UI: sign-in page, name and role in the header, sign-out, approval buttons only for approvers, read-only note for viewers, warning banner when `AUTH_MODE=none`.
- `/api/health` tells anonymous callers only `{"status": "ok"}`.
- Tested against OpenLDAP (LDAPS and StartTLS), Samba Active Directory (nested groups, UPN) and Authentik (OIDC, real browser). Found and fixed on the way: wrong passwords answered with 502 and were not counted, OpenLDAP groups were not read (`memberOf` is operational), and the four-eyes rule could be bypassed on AD by signing in once by name and once by UPN.

**Install, upgrade, backup**
- Releases ([docs/releasing.md](docs/releasing.md)): *Actions → Release → Run workflow* with a version (or a pushed tag `vX.Y.Z` / `-rc.N`) runs the full CI, publishes backend and frontend images to ghcr.io with SBOM and provenance, creates the tag on the tested commit and attaches an install archive with its SHA-256.
- `scripts/install.sh` asks for Proxmox and sign-in, writes `.env` (mode 600) and `secrets/` (owned by uid 10001), pulls the images and waits until the console is healthy. `--build` builds locally, `--non-interactive` reads answers from the environment.
- `scripts/upgrade.sh` backs up first, creates secret files new releases expect, lists new settings, pulls and restarts.
- `scripts/backup.sh` / `scripts/restore.sh` (`python -m app.cli backup|verify|restore`): database (online copy), OpenTofu state, approved AI roles and SSH host keys; no secrets, no sessions. Restore refuses links and paths outside the data directories and checks the database before replacing anything.
- One version number in backend, frontend and changelog, checked in CI; shown in the UI footer.

**Upgrading from 2.0.x**
- Two new secret files: `secrets/oidc_client_secret` and `secrets/ldap_bind_password` (empty if unused). `scripts/upgrade.sh` creates them.
- Sign-in is off until you set `AUTH_MODE` (the console then shows a warning). Set it before others use the console.
- `docker-compose.yml` now names images (`IMAGE_REGISTRY`, `VERSION`); `docker compose up --build` keeps building from a checkout.

## 2.0.3 – 2026-10-19

Windows Server 2022 run end to end: template built per `docs/windows-template.md`, linked clone with a Proxmox-style `configdrive2` cloud-init drive, the console's Ansible configuration and Windows tests (details: [docs/windows-template.md](docs/windows-template.md#verification)).

**Security**
- The template steps created the WinRM certificate before sysprep, so every clone shared one private key. The template now only opens the firewall port; cloudbase-init creates a new certificate per clone (verified).
- The unencrypted WinRM listener (5985) stayed active, so the Windows security baseline failed on every machine. The template steps now remove it on first boot (`LocalScripts`).

**Fixes**
- Validation took a link-local address (`169.254.x.x`, reported by Windows before DHCP answers) as the guest IP.
- Validation reported Windows ready as soon as the guest agent answered, minutes before cloudbase-init set the password. It now also waits for WinRM HTTPS (5986).
- Inside checks whose id was all digits (e.g. `00523341`) lost their result: Ansible turned the id into a number. Results are now matched by position.
- The VM module sets the cloud-init format to `configdrive2` for Windows instead of relying on Proxmox's ostype default.

**Tests**
- `tofu test` for the VM module with a mocked provider (Windows/Linux settings, password and VMID preconditions), run in CI.
- Backend tests for guest agent parsing, Windows readiness and result matching.

## 2.0.2 – 2026-10-18

Results of an error and security review.

**Security**
- **Critical:** values passed to Ansible (Docker service settings, test checks, compose files, profile names) were evaluated as Jinja on the console host, so `{{ lookup('pipe', ...) }}` in a setting or an AI-drafted test could run commands there. All playbook data is now written as YAML tagged `!unsafe`. Template characters are also rejected in service settings and test fields.
- The guest-reported IP is validated before it reaches the inventory.
- Ansible runs with a minimal environment: no API token or AI key.
- The review of AI-drafted roles now also rejects:
  - lookups/`query()` anywhere, including bare `when`/`until` expressions;
  - `hostvars`/`vars` access;
  - `copy`/`unarchive` with a source on the console;
  - `delegate_to`/`local_action`;
  - `pip`.
- Production approvals use a compare-and-set update, so two simultaneous approvals cannot both apply.
- Cloud-init `commands` are no longer accepted (no free-form commands for people or the AI).
- `file_contains` tests match literal text (no regular expressions) and may not read secrets (`/etc/shadow`, SSH keys, stack `.env`, …).
- The console binds to `127.0.0.1` by default (`FRONTEND_BIND`); nginx sends a strict Content-Security-Policy and Permissions-Policy. The theme script moved out of `index.html`.

**Fixes**
- Inside tests never ran in live mode: `command:` with a bare list is rejected by ansible-core 2.21 (now `argv:`). Each check is now isolated: one error is reported as FAIL and the others still run.
- Changing only software (services, packages, profiles) of a deployed machine or stack was not saved and could reach Production unvalidated. The new spec is now stored and the validation reset.
- The Docker profile failed on Debian 12 (no Compose v2 package). It now installs Docker Engine + Compose from Docker's apt repository on Debian and Ubuntu; verified on Debian 12.
- Minimal LXC templates without Python are bootstrapped before Ansible runs.
- AI stack drafting always fell back to local rules: the structured-output schema used an open object for service settings.
- *Create stack* with the name of an existing stack would have planned the old members for destruction; it is now refused.
- Production can be updated from a Test machine or stack that was changed and validated after the last promotion.

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
