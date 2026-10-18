variable "name" {
  description = "Hostname of the container."
  type        = string
}

variable "node_name" {
  description = "Proxmox node."
  type        = string
}

variable "vm_id" {
  description = "Container ID."
  type        = number
}

variable "vm_id_min" {
  description = "Lowest ID allowed in this environment."
  type        = number
}

variable "vm_id_max" {
  description = "Highest ID allowed in this environment."
  type        = number
}

variable "template_file_id" {
  description = "CT template volume, e.g. local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst."
  type        = string
}

variable "os_type" {
  description = "Container OS type (debian, ubuntu)."
  type        = string
  default     = "debian"
}

variable "cores" {
  description = "CPU cores."
  type        = number
}

variable "memory_mb" {
  description = "Memory in MB."
  type        = number
}

variable "disk_gb" {
  description = "Root disk size in GB."
  type        = number
}

variable "datastore_id" {
  description = "Storage for the root disk."
  type        = string
}

variable "bridge" {
  description = "Network bridge or SDN vnet."
  type        = string
}

variable "vlan_id" {
  description = "VLAN tag (0 = untagged)."
  type        = number
  default     = 0
}

variable "ssh_public_key" {
  description = "Public key for root (Ansible)."
  type        = string
  default     = ""
}

variable "nesting" {
  description = "Allow nested containers (needed for Docker)."
  type        = bool
  default     = true
}

variable "description" {
  description = "Description shown in Proxmox."
  type        = string
  default     = ""
}

variable "tags" {
  description = "Proxmox tags."
  type        = list(string)
  default     = []
}

variable "start_on_boot" {
  description = "Start with the node."
  type        = bool
  default     = false
}

variable "pool_id" {
  description = "Resource pool ('' = none)."
  type        = string
  default     = ""
}
