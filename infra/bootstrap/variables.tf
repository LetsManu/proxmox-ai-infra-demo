variable "node_name" {
  description = "Proxmox node."
  type        = string
  default     = "pve"
}

variable "pve_major" {
  description = "Proxmox VE major version (8 or 9); selects guest-agent privileges."
  type        = number
  default     = 8

  validation {
    condition     = contains([8, 9], var.pve_major)
    error_message = "pve_major must be 8 or 9."
  }
}

variable "user_id" {
  description = "Automation user."
  type        = string
  default     = "automation@pve"
}

variable "token_name" {
  description = "API token name (TOKEN_ID)."
  type        = string
  default     = "infra-demo"
}

variable "token_expiration_date" {
  description = "Optional RFC 3339 expiry for the token, e.g. 2026-12-31T00:00:00Z."
  type        = string
  default     = null
}

variable "role_id" {
  description = "Custom role."
  type        = string
  default     = "InfraDemo"
}

variable "pool_id" {
  description = "Resource pool for templates and managed VMs."
  type        = string
  default     = "infra-demo"
}

variable "vm_storages" {
  description = "Existing storage pools the console may allocate VM disks on (TEST_STORAGE, PROD_STORAGE, TEMPLATE_STORAGE)."
  type        = list(string)
  default     = ["local-lvm"]
}

variable "create_image_storage" {
  description = "Create a directory storage for cloud images (content 'import') and cloud-init snippets."
  type        = bool
  default     = true
}

variable "image_storage_id" {
  description = "ID of the image/snippet directory storage."
  type        = string
  default     = "infra-demo"
}

variable "image_storage_path" {
  description = "Path of the image/snippet directory storage on the node."
  type        = string
  default     = "/var/lib/infra-demo"
}

variable "create_sdn" {
  description = "Create an SDN VLAN zone with one vnet per environment."
  type        = bool
  default     = true
}

variable "sdn_zone" {
  description = "SDN zone ID (max 8 chars)."
  type        = string
  default     = "infrazn"
}

variable "sdn_bridge" {
  description = "VLAN-aware bridge the SDN zone uses."
  type        = string
  default     = "vmbr0"
}

variable "vnets" {
  description = "One vnet per environment: name => VLAN tag."
  type        = map(number)
  default = {
    vtest = 30
    vprod = 10
  }
}
