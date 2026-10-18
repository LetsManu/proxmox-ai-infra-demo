locals {
  use_snippet = var.snippets_datastore_id != "" && (length(var.packages) > 0 || length(var.commands) > 0)
  is_dhcp     = var.ipv4_address == "dhcp"
}

# Optional cloud-init vendor-data with extra packages/commands.
# Uploading snippets uses SSH to the node, so it needs the provider `ssh` block
# (see docs/proxmox-setup.md). Disabled when snippets_datastore_id is empty.
resource "proxmox_virtual_environment_file" "vendor_data" {
  count        = local.use_snippet ? 1 : 0
  content_type = "snippets"
  datastore_id = var.snippets_datastore_id
  node_name    = var.node_name

  source_raw {
    file_name = "${var.name}-vendor.yaml"
    data = join("\n", [
      "#cloud-config",
      yamlencode({
        package_update = true
        packages       = distinct(concat(["qemu-guest-agent"], var.packages))
        runcmd         = concat(["systemctl enable --now qemu-guest-agent"], var.commands)
      })
    ])
  }
}

resource "proxmox_virtual_environment_vm" "this" {
  name        = var.name
  node_name   = var.node_name
  vm_id       = var.vm_id
  description = var.description
  tags        = sort(distinct(var.tags))
  on_boot     = var.start_on_boot
  started     = true

  clone {
    vm_id = var.template_id
    full  = var.full_clone
  }

  agent {
    enabled = true
    timeout = "5m"
  }

  cpu {
    cores = var.cores
    type  = "x86-64-v2-AES"
  }

  memory {
    dedicated = var.memory_mb
  }

  disk {
    datastore_id = var.datastore_id
    interface    = "scsi0"
    size         = var.disk_gb
    discard      = "on"
    iothread     = true
  }

  network_device {
    bridge  = var.bridge
    vlan_id = var.vlan_id > 0 ? var.vlan_id : null
  }

  operating_system {
    type = "l26"
  }

  serial_device {}

  initialization {
    datastore_id = var.datastore_id

    ip_config {
      ipv4 {
        address = var.ipv4_address
        gateway = local.is_dhcp ? null : var.ipv4_gateway
      }
    }

    user_account {
      username = var.ci_user
      keys     = trimspace(var.ssh_public_key) == "" ? [] : [trimspace(var.ssh_public_key)]
    }

    vendor_data_file_id = local.use_snippet ? proxmox_virtual_environment_file.vendor_data[0].id : null
  }

  lifecycle {
    precondition {
      condition     = var.vm_id >= var.vm_id_min && var.vm_id <= var.vm_id_max
      error_message = "VM ID ${var.vm_id} is outside the allowed range ${var.vm_id_min}-${var.vm_id_max} for this environment."
    }
  }
}
