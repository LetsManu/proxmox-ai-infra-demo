terraform {
  required_version = ">= 1.6.0"

  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = ">= 0.117.0, < 1.0.0"
    }
  }

  # Local state, one file per environment. The path is supplied at init time:
  #   tofu init -backend-config="path=/workspace/state/test/terraform.tfstate"
  #   tofu init -backend-config="path=/workspace/state/prod/terraform.tfstate"
  backend "local" {}
}

# Credentials come ONLY from environment variables set by the backend
# (or by you when running manually):
#   PROXMOX_VE_ENDPOINT   = https://<proxmox-host>:8006/
#   PROXMOX_VE_API_TOKEN  = automation@pve!infra-demo=<secret>
#   PROXMOX_VE_INSECURE   = true|false
provider "proxmox" {}
