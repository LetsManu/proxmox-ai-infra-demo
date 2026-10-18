terraform {
  required_version = ">= 1.6.0"

  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = ">= 0.117.0, < 1.0.0"
    }
  }

  # path supplied at init: -backend-config=path=/workspace/state/platform/terraform.tfstate
  backend "local" {}
}

# Same least-privilege token as the VM stacks (PROXMOX_VE_ENDPOINT / PROXMOX_VE_API_TOKEN).
provider "proxmox" {}
