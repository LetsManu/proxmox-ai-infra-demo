# Stacks: VMs, containers and Docker services together

A **stack** is everything one application needs, handled as one unit: one plan,
one deployment, one validation verdict, one production approval.

```
Stack "wordpress"
├── wordpress-app-test      VM (Ubuntu)      profile docker → services: wordpress, db
└── wordpress-monitor-test  LXC (Debian)     profile docker → services: prometheus, grafana
```

## Members are ordinary machines

Each component becomes a machine named `<stack>-<component>[-test]` and is
validated by the same rules as a single VM (templates, TEST/PROD limits, software
profiles, packages). On top, the stack total is limited
(`STACK_LIMITS` in `backend/app/config.py`: TEST 16 vCPU / 32 GB / 384 GB, max 8
members). All members live in the same per-environment OpenTofu state as single
VMs (`var.vms` + `var.containers`), so nothing else changes.

## LXC containers

`infra/modules/lxc` creates unprivileged containers from official Proxmox LXC
templates, which the **platform stack** downloads (`DEBIAN_12_CT_URL`,
`UBUNTU_2404_CT_URL`, stored on `CT_STORAGE`, default `IMAGE_STORAGE`; the
bootstrap enables content `vztmpl` there). Differences to VMs:

- No cloud-init and no guest agent: the IP comes from the container's interfaces API.
- Ansible connects as `root` with the key from `ANSIBLE_SSH_KEY_FILE`; the
  baseline allows root login **only with a key** (`PermitRootLogin prohibit-password`).
- `nesting` is enabled so containers can run Docker. Docker inside unprivileged
  LXC works on most storage setups; for heavy or stateful Docker workloads prefer a VM.

## Docker services

A component with the `docker` profile can run services:

```yaml
services:
  - name: db
    image: mariadb:11.4
    env: { MARIADB_USER: wordpress, MARIADB_PASSWORD: "secret:db_password" }
    volumes: ["db-data:/var/lib/mysql"]
  - name: wordpress
    image: wordpress:6.8-apache
    ports: ["80:80"]
    env: { WORDPRESS_DB_HOST: db, WORDPRESS_DB_PASSWORD: "secret:db_password" }
```

What can be expressed is deliberately small: image, published ports, **named**
volumes and plain settings. No privileged mode, host paths, capabilities, host
networking or commands. Services on the same host reach each other by name over
the compose network; unpublished ports (the database above) are not reachable
from outside.

**Secrets.** A setting whose name looks like a secret must be `secret:<name>`.
The console renders it as `${STACKSECRET_<NAME>}`; the `docker_services` role
generates the value **on the host** into `/opt/stacks/<stack>/.env` (mode 0600)
and keeps it across runs. The value never passes through the console, its
database, its logs or the AI.

## Lifecycle

| Step | API | Notes |
|---|---|---|
| Draft | `POST /api/ai/generate-stack` | Claude (or local recipes) proposes; result is validated and starts in TEST |
| Plan | `POST /api/stacks/plan` | One plan for all members; members removed from the stack are destroyed; `recreate: true` replaces all |
| Deploy | `POST /api/stacks/deploy` | Applies the reviewed plan, then configures every member |
| Validate | `POST /api/stacks/validate` | Platform checks + baseline + app tests + container/port checks per member; PASS only if all pass |
| Promote | `POST /api/stacks/promote` | `request` → PRODUCTION plan (awaiting approval); `approve` needs `acknowledge` + `PROMOTE` |
