# Changelog

## 1.1.0 – 2026-10-18

- Console redesign: flat dark design tokens (contrast-checked), Inter + JetBrains Mono bundled offline, Lucide SVG icons instead of emoji.
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
