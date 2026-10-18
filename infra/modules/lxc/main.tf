# One unprivileged LXC container from a downloaded CT template (vztmpl).
# Ansible reaches it over SSH as root with key auth only (password login is disabled
# by the linux_base role); nesting is on so the container can run Docker.

resource "proxmox_virtual_environment_container" "this" {
  node_name     = var.node_name
  vm_id         = var.vm_id
  description   = var.description
  tags          = sort(distinct(var.tags))
  start_on_boot = var.start_on_boot
  started       = true
  unprivileged  = true
  pool_id       = var.pool_id == "" ? null : var.pool_id

  operating_system {
    template_file_id = var.template_file_id
    type             = var.os_type
  }

  cpu {
    cores = var.cores
  }

  memory {
    dedicated = var.memory_mb
    swap      = 512
  }

  disk {
    datastore_id = var.datastore_id
    size         = var.disk_gb
  }

  features {
    nesting = var.nesting
  }

  network_interface {
    name    = "eth0"
    bridge  = var.bridge
    vlan_id = var.vlan_id > 0 ? var.vlan_id : null
  }

  initialization {
    hostname = var.name

    ip_config {
      ipv4 {
        address = "dhcp"
      }
    }

    user_account {
      keys = trimspace(var.ssh_public_key) == "" ? [] : [trimspace(var.ssh_public_key)]
    }
  }

  wait_for_ip {
    ipv4 = true
  }

  lifecycle {
    precondition {
      condition     = var.vm_id >= var.vm_id_min && var.vm_id <= var.vm_id_max
      error_message = "Container ID ${var.vm_id} is outside the allowed range ${var.vm_id_min}-${var.vm_id_max} for this environment."
    }
  }
}
