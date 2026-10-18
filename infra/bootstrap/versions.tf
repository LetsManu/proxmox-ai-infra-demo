terraform {
  required_version = ">= 1.6.0"

  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = ">= 0.117.0, < 1.0.0"
    }
  }

  # Own state, kept next to this stack (gitignored). Contains the token secret: protect it.
  backend "local" {
    path = "terraform.tfstate"
  }
}

# ADMIN credentials, from the environment of the person running scripts/bootstrap.sh only:
#   PROXMOX_VE_ENDPOINT = https://<proxmox-host>:8006/
#   PROXMOX_VE_USERNAME = root@pam   and   PROXMOX_VE_PASSWORD = ...
#   (or PROXMOX_VE_API_TOKEN = root@pam!bootstrap=... with privilege separation off)
# The web console never runs this stack and never sees these credentials.
provider "proxmox" {}
