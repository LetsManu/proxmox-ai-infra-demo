locals {
  windows = var.os_family == "windows"
  # Linux: always ship a vendor-data snippet when a snippet store exists, so the
  # QEMU guest agent is installed even if the image lacks it.
  use_snippet = !local.windows && var.snippets_datastore_id != ""
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
  pool_id     = var.pool_id == "" ? null : var.pool_id

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
    type = local.windows ? "win11" : "l26"
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
      username = local.windows ? "Administrator" : var.ci_user
      keys     = local.windows || trimspace(var.ssh_public_key) == "" ? [] : [trimspace(var.ssh_public_key)]
      password = local.windows ? var.admin_password : null
    }

    vendor_data_file_id = local.use_snippet ? proxmox_virtual_environment_file.vendor_data[0].id : null
  }

  lifecycle {
    precondition {
      condition     = var.vm_id >= var.vm_id_min && var.vm_id <= var.vm_id_max
      error_message = "VM ID ${var.vm_id} is outside the allowed range ${var.vm_id_min}-${var.vm_id_max} for this environment."
    }
    precondition {
      condition     = !local.windows || length(var.admin_password) >= 12
      error_message = "Windows VMs need WINDOWS_ADMIN_PASSWORD (12+ characters) for cloudbase-init and Ansible."
    }
  }
}
