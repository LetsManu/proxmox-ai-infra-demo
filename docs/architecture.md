# Architecture

## Components

```mermaid
flowchart TB
    subgraph browser["Browser"]
        ui["Vue 3 console<br/>polls /api/jobs/{id}"]
    end
    subgraph fe["frontend container (nginx, uid 101, read-only)"]
        static["static files"]
        proxy["/api reverse proxy"]
    end
    subgraph be["backend container (FastAPI, uid 10001, read-only)"]
        routes["routes/<br/>vms · plans · validation · promotion · ai"]
        runner["workers/job_runner<br/>thread pool + per-env lock"]
        svc_px["proxmox_service<br/>(live | mock)"]
        svc_tf["terraform_service<br/>(live | mock)"]
        svc_val["validation_service"]
        svc_ai["ai_service<br/>guardrails + local fallback"]
        db[("SQLite (WAL)<br/>jobs · virtual_machines · history")]
    end
    ws[("workspace volume<br/>test/ prod/ state/")]
    pve["Proxmox VE API"]
    claude["Claude API"]

    ui --> static
    ui --> proxy --> routes
    routes --> runner
    runner --> svc_tf --> ws
    runner --> svc_val --> svc_px
    routes --> svc_ai --> claude
    svc_tf -- "tofu + bpg/proxmox" --> pve
    svc_px -- "PVEAPIToken" --> pve
    routes --> db
    runner --> db
```

## Data model

| Table | Purpose |
|---|---|
| `jobs` | Every long-running action: status (`queued`, `running`, `success`, `failed`, `awaiting_approval`), params, logs, result, error, timestamps |
| `virtual_machines` | Desired state per (name, environment): spec, VM ID, IP, last validation. Rendered into OpenTofu `var.vms`. |
| `history` | Audit trail: timestamp, VM, environment, action, status, user, plan summary |

SQLite is enough for one backend replica (WAL mode + busy timeout). SQLAlchemy keeps the code portable: switching to PostgreSQL is a `DATABASE_URL` change.

## Desired state and OpenTofu

- The database is the source of the desired VM list. For each plan the backend writes `/workspace/<env>/generated.tfvars.json` (placement from `.env` + `vms` map) and runs the root module with `-var-file=environments/<env>.tfvars -var-file=generated.tfvars.json`.
- `for_each` over `var.vms` creates one `modules/vm` instance per VM, keyed by name, so adding a VM never touches the others and recreate is `-replace='module.vm["name"].proxmox_virtual_environment_vm.this'`.
- **Separate state**: `tofu init -backend-config=path=/workspace/state/<env>/terraform.tfstate` and a separate `TF_DATA_DIR` per environment. A per-environment lock in the job runner ensures one writer per state.
- **Plan/apply integrity**: plans are saved with `-out`; deploy/approve apply that exact file. If the infrastructure changed in between, OpenTofu refuses (`Saved plan is stale`).
- **Policy in two places**: the API rejects specs over the environment limits; the OpenTofu config repeats the guardrails (`check "resource_limits"`, VM ID range `precondition`), so a manual `tofu apply` with bad input fails too.
- The provider is pre-downloaded into the backend image (`TF_PLUGIN_CACHE_DIR`), and `.terraform.lock.hcl` is committed.

## Job lifecycle

```mermaid
stateDiagram-v2
    [*] --> queued
    queued --> running
    running --> success
    running --> failed
    running --> awaiting_approval: promote / prod recreate
    awaiting_approval --> success: approve (ack + typed word)
    awaiting_approval --> failed: reject
    success --> [*]
    failed --> [*]
```

Approval creates a separate `promote-apply` / `recreate-apply` job that applies the parked plan. On backend restart, jobs left in `queued`/`running` are marked failed.

## Promotion sequence

```mermaid
sequenceDiagram
    actor Op as Operator
    participant UI
    participant API
    participant Tofu as OpenTofu (prod state)
    participant AI
    Op->>UI: Request Production Promotion
    UI->>API: POST /vms/promote/production {stage: request}
    API->>API: TEST validation == PASS and newer than deploy?
    API->>Tofu: plan -out (prod)
    API-->>UI: job awaiting_approval (plan)
    UI->>AI: summarize-plan (prod)
    AI-->>UI: risk + checks (advisory)
    Op->>UI: tick acknowledgement, type PROMOTE
    UI->>API: {stage: approve, approval_job_id, acknowledge, confirmation}
    API->>API: re-check all gates, plan age < 60 min, not already decided
    API->>Tofu: apply saved plan
    API-->>UI: promote-apply job (logs)
```

## Mock mode

`LIVE_MODE=false` swaps `ProxmoxClient` for `MockProxmox` and runs the mock OpenTofu planner/applier. Everything else (database, jobs, gates, AI guardrails, UI) is the same code path. The mock:

- lists two templates (IDs from `.env`), storage pools and a VLAN-aware bridge
- renders plan text in OpenTofu format with create / update / destroy / replace
- simulates apply progress, guest-agent IPs from RFC 5737 documentation ranges, cloud-init completion
- can fail validation on demand (UI checkbox or `MOCK_FAIL_VALIDATION=true`)
- rehydrates simulated VMs from the database after a restart
