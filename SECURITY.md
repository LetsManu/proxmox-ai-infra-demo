# Security policy

## Reporting a vulnerability

Please do **not** open a public issue for security problems. Report them privately through GitHub:
**Security → Report a vulnerability** on this repository. Include what you found, how to reproduce it and the
commit you tested. You can expect a first answer within a week.

## Scope and assumptions

This is a demonstration platform. It assumes:

- the console runs on a trusted host behind a reverse proxy that terminates HTTPS, with `AUTH_MODE=oidc` or `ldap`
  (`none` is for a single person on localhost);
- the Proxmox API token is a dedicated, least-privilege, privilege-separated token (see `docs/api-token-setup.md`);
- `.env`, `secrets/`, Terraform state and plan files never leave the host (all are gitignored).

## Built-in safeguards

- Proxmox credentials stay in the backend; they are scrubbed from job logs and never returned by the API.
- Production changes require a passing TEST validation, a saved plan, an acknowledgement and a typed confirmation, all
  verified server-side; approvals expire after 60 minutes and cannot be applied twice.
- AI output is advisory and validated; the AI has no credentials and no path to apply or approve.
- Sign-in through your directory (OIDC or LDAP over TLS); roles from groups; writes need the operator role, production
  decisions the approver role and, with `AUTH_FOUR_EYES`, a second person. Sessions are server-side, cookies `HttpOnly`,
  every write carries a CSRF token (docs/authentication.md).
- Backups (`scripts/backup.sh`) contain no secrets and no sign-in sessions; restores refuse archives with links or
  paths outside the data directories.
- Containers run as non-root with a read-only root filesystem, no capabilities and `no-new-privileges`.
- gitleaks runs in CI and in the optional pre-commit hook (`git config core.hooksPath .githooks`).
