# Screenshots

Captured from mock mode (`LIVE_MODE=false`) with a headless browser walking through the full workflow. All IPs are RFC 5737 documentation addresses.

| | |
|---|---|
| ![Dashboard](images/01-dashboard.png) **1. Dashboard** – environment selector, VM form, mode/Proxmox/AI status | ![AI spec](images/02-ai-spec.png) **2. AI VM spec** – natural language to a validated draft |
| ![Plan](images/03-plan.png) **3. Plan + AI review** – counts, plan output, risk LOW, pre-flight checks | ![Troubleshoot](images/04-troubleshoot.png) **4. Failed validation** – AI troubleshooting suggests a recreate |
| ![Validation](images/05-validation-pass.png) **5. Validation PASS** – running, cloud-init, guest-agent IP, port 22 | ![Promotion](images/06-promotion.png) **6. Production approval** – plan, AI risk, checkbox + typed PROMOTE |
| ![History](images/07-history.png) **7. History / managed VMs** | ![Mobile](images/08-mobile.png) **8. Mobile layout** |

To regenerate: start the stack in mock mode, reset data (`docker compose down -v && docker compose up -d`) and capture the same steps as in [DEMO.md](../DEMO.md).
