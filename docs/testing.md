# Automated tests and the review queue

Validate runs three layers for every machine; any failure blocks promotion.

1. **Platform checks**: running, network address, first boot finished, software installed.
2. **Security baseline** (always, not editable by the AI): SSH password login off,
   root login off (key-only on containers), automatic security updates, guest
   agent running; on Windows: firewall on for all profiles, unencrypted WinRM
   (5985) closed. Database/cache ports (3306, 5432, 6379, 27017, 9200, 11211,
   21, 23) must not be reachable from the network unless a test declares them public.
3. **Application tests**: from the approved suite for this machine, otherwise
   derived from its software (profile ports listening, packages installed,
   profile-declared tests, Docker containers running and their published ports open).

## Tests are data, not code

Each test is a typed record such as `{"type": "http", "port": 80, "path": "/", "contains": "WordPress"}`.
Allowed types: `service_running`, `port_listening`, `package_installed`,
`http_local`, `file_contains`, `windows_feature`, `sshd_setting`, `auto_updates`,
`firewall_enabled`, `container_running` (run **inside** via Ansible,
`infra/ansible/tests.yml`) and `tcp_open`, `tcp_closed`, `http` (run **from the
console** over the network). Every field is validated (ports, names, paths,
regexes); the code that executes a type is reviewed code in this repository.

## Review queue

The assistant drafts two kinds of artefacts, both wait in **Review queue** until
a person decides:

| Draft | Automated checks before review | After approval |
|---|---|---|
| Software role (Ansible) for a need no profile covers | only allowed modules (no shell/command/raw/script/PowerShell), HTTPS downloads, no literal secrets, YAML structure, `ansible-playbook --syntax-check` | written to `APPROVED_PROFILES_DIR`, appears as a software profile |
| Test suite for a machine | known types, valid fields; invalid AI checks are dropped and listed | used by Validate for the Test and Production copy of that machine |

Drafts that fail the automated checks cannot be approved. Decisions are recorded
in the history with the approver's name. Production change requests (promotion,
production recreate, stack promotion) are listed in the same queue.
