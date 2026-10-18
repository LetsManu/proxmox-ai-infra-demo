# Downloads each official cloud image to the node and turns it into a
# cloud-init template. Everything the VM stacks clone from is created here.

resource "proxmox_download_file" "image" {
  for_each = var.templates

  node_name    = var.node_name
  datastore_id = var.image_storage
  content_type = "import"
  url          = each.value.image_url
  file_name    = each.value.file_name
  overwrite    = false
}

resource "proxmox_virtual_environment_vm" "template" {
  for_each = var.templates

  name        = each.value.name
  node_name   = var.node_name
  vm_id       = each.value.vm_id
  pool_id     = var.pool_id == "" ? null : var.pool_id
  description = "Cloud-init template built from ${each.value.image_url}"
  tags        = ["managed-by-iac", "template"]
  template    = true
  started     = false
  on_boot     = false

  agent {
    enabled = true
  }

  cpu {
    cores = 2
    type  = "x86-64-v2-AES"
  }

  memory {
    dedicated = 2048
  }

  disk {
    datastore_id = var.template_storage
    interface    = "scsi0"
    import_from  = proxmox_download_file.image[each.key].id
    discard      = "on"
    iothread     = true
  }

  network_device {
    bridge = var.bridge
  }

  operating_system {
    type = "l26"
  }

  serial_device {}

  vga {
    type = "serial0"
  }

  initialization {
    datastore_id = var.template_storage

    ip_config {
      ipv4 {
        address = "dhcp"
      }
    }

    user_account {
      username = var.ci_user
      keys     = trimspace(var.default_ssh_public_key) == "" ? [] : [trimspace(var.default_ssh_public_key)]
    }
  }

  lifecycle {
    # a template is immutable: rebuilding means a new ID (see docs/cloud-images.md)
    ignore_changes = [description]
  }
}

# LXC templates (vztmpl) for containers in the VM stacks.
resource "proxmox_download_file" "ct" {
  for_each = var.ct_templates

  node_name    = var.node_name
  datastore_id = var.ct_storage
  content_type = "vztmpl"
  url          = each.value.url
  file_name    = each.value.file_name
  overwrite    = false
}
