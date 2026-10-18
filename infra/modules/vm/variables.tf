variable "name" {
  description = "VM name (also used as hostname by cloud-init)."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,40}[a-z0-9]$", var.name))
    error_message = "Name must be lowercase letters, digits and hyphens (3-42 chars)."
  }
}

variable "node_name" {
  description = "Proxmox node that hosts the VM."
  type        = string
}

variable "vm_id" {
  description = "Proxmox VM ID."
  type        = number
}

variable "vm_id_min" {
  description = "Lowest VM ID allowed in this environment."
  type        = number
}

variable "vm_id_max" {
  description = "Highest VM ID allowed in this environment."
  type        = number
}

variable "template_id" {
  description = "VM ID of the cloud-init template to clone."
  type        = number
}

variable "cores" {
  description = "Number of vCPU cores."
  type        = number
  default     = 2
}

variable "memory_mb" {
  description = "Memory in MB."
  type        = number
  default     = 4096
}

variable "disk_gb" {
  description = "Root disk size in GB (can only grow)."
  type        = number
  default     = 32
}

variable "datastore_id" {
  description = "Storage pool for the VM disk and cloud-init drive."
  type        = string
}

variable "bridge" {
  description = "Network bridge."
  type        = string
  default     = "vmbr0"
}

variable "vlan_id" {
  description = "VLAN tag (0 = untagged)."
  type        = number
  default     = 0
}

variable "ipv4_address" {
  description = "\"dhcp\" or a CIDR address such as 192.0.2.10/24."
  type        = string
  default     = "dhcp"
}

variable "ipv4_gateway" {
  description = "Gateway for a static address (ignored for DHCP)."
  type        = string
  default     = null
}

variable "ci_user" {
  description = "Cloud-init default user."
  type        = string
  default     = "ops"
}

variable "ssh_public_key" {
  description = "OpenSSH public key for the cloud-init user."
  type        = string
  default     = ""
}

variable "description" {
  description = "Proxmox VM description (notes)."
  type        = string
  default     = ""
}

variable "tags" {
  description = "Proxmox tags."
  type        = list(string)
  default     = []
}

variable "start_on_boot" {
  description = "Start the VM when the Proxmox node boots."
  type        = bool
  default     = false
}

variable "full_clone" {
  description = "Full clone (independent disk) instead of a linked clone."
  type        = bool
  default     = true
}

variable "snippets_datastore_id" {
  description = "Datastore with 'snippets' content. Empty disables the package/command vendor-data snippet."
  type        = string
  default     = ""
}

variable "packages" {
  description = "Extra packages installed by cloud-init (requires snippets_datastore_id)."
  type        = list(string)
  default     = []
}

variable "commands" {
  description = "Commands run once by cloud-init (requires snippets_datastore_id)."
  type        = list(string)
  default     = []
}
