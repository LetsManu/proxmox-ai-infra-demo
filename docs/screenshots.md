# Screenshots

Captured from mock mode (`LIVE_MODE=false`) with a headless browser walking through the full workflow. All IPs are RFC 5737 documentation addresses.

| | |
|---|---|
| ![Platform missing](images/00-platform-missing.png) **0. Platform** – the console notices missing templates | ![Platform plan](images/00b-platform-plan.png) **0b. Prepare Platform** – cloud images + templates as a plan |
| ![Configured](images/03b-configured.png) **3b. Deploy + Ansible** – software installed after deploy | ![Windows](images/09-windows-form.png) **9. Windows** – IIS and admin tools profiles |
| ![Dashboard](images/01-dashboard.png) **1. Console** – Proxmox-style resource tree, toolbar, progress bar, VM form | ![Draft](images/02-ai-spec.png) **2. Draft from a description** – natural language to a validated draft |
| ![Plan](images/03-plan.png) **3. Plan + review** – counts, changes, low risk, pre-flight checklist | ![Troubleshoot](images/04-troubleshoot.png) **4. Failed validation** – diagnosis suggests a recreate |
| ![Confirm](images/04b-confirm.png) **4b. Confirmation** – destructive actions ask first | |
| ![Validation](images/05-validation-pass.png) **5. Validation passed** – running, cloud-init, guest-agent IP, port 22 | ![Promotion](images/06-promotion.png) **6. Production approval** – gates, plan, risk, acknowledgement + typed PROMOTE |
| ![History](images/07-history.png) **7. History / managed VMs** | ![Mobile](images/08-mobile.png) **8. Mobile layout** |

To regenerate: start the stack in mock mode, reset data (`docker compose down -v && docker compose up -d`) and capture the same steps as in [DEMO.md](../DEMO.md).
