variable "node_name" {
  description = "Proxmox node."
  type        = string
}

variable "image_storage" {
  description = "Storage with content type 'import' for downloaded cloud images (PVE 8.4+)."
  type        = string
}

variable "template_storage" {
  description = "Storage for template disks (linked clones need the same storage as TEST_STORAGE)."
  type        = string
}

variable "bridge" {
  description = "Bridge for the template NIC (clones override it)."
  type        = string
  default     = "vmbr0"
}

variable "pool_id" {
  description = "Resource pool ('' = none)."
  type        = string
  default     = ""
}

variable "ci_user" {
  description = "Default cloud-init user baked into the templates."
  type        = string
  default     = "ops"
}

variable "default_ssh_public_key" {
  description = "Public key baked into the templates."
  type        = string
  default     = ""
}

variable "templates" {
  description = "Cloud-image templates to build, keyed by catalog key."
  type = map(object({
    vm_id     = number
    name      = string
    image_url = string
    file_name = string
  }))
  default = {}
}
