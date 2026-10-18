# Plan-only checks of what the module asks Proxmox for. The provider is mocked,
# so no Proxmox API is called: run with `tofu test` in infra/modules/vm.
mock_provider "proxmox" {}

variables {
  name         = "win-app"
  node_name    = "pve"
  vm_id        = 950
  vm_id_min    = 900
  vm_id_max    = 999
  template_id  = 9002
  datastore_id = "local-lvm"
  os_family    = "windows"
  # test-only placeholder, never a real password
  admin_password = "placeholder-not-real-1"
}

run "windows_vm_uses_config_drive_and_administrator" {
  command = plan

  assert {
    condition     = proxmox_virtual_environment_vm.this.operating_system[0].type == "win11"
    error_message = "Windows VMs must use ostype win11."
  }
  assert {
    condition     = proxmox_virtual_environment_vm.this.initialization[0].type == "configdrive2"
    error_message = "cloudbase-init needs the configdrive2 cloud-init format."
  }
  assert {
    condition     = proxmox_virtual_environment_vm.this.initialization[0].user_account[0].username == "Administrator"
    error_message = "cloudbase-init sets the Administrator password."
  }
  assert {
    condition     = length(proxmox_virtual_environment_vm.this.initialization[0].user_account[0].keys) == 0
    error_message = "Windows VMs get no SSH keys."
  }
  assert {
    condition     = proxmox_virtual_environment_vm.this.disk[0].interface == "scsi0"
    error_message = "The template disk is expected on scsi0 (VirtIO SCSI)."
  }
  assert {
    condition     = length(proxmox_virtual_environment_file.vendor_data) == 0
    error_message = "Windows VMs get no Linux vendor-data snippet."
  }
}

run "windows_vm_needs_a_long_password" {
  command = plan

  variables {
    admin_password = "short"
  }

  expect_failures = [proxmox_virtual_environment_vm.this]
}

run "vm_id_outside_the_environment_range_is_refused" {
  command = plan

  variables {
    vm_id = 150
  }

  expect_failures = [proxmox_virtual_environment_vm.this]
}

run "linux_vm_keeps_the_proxmox_default_format" {
  command = plan

  variables {
    os_family      = "linux"
    admin_password = ""
    ssh_public_key = "ssh-ed25519 AAAAplaceholder test@example"
  }

  assert {
    condition     = proxmox_virtual_environment_vm.this.operating_system[0].type == "l26"
    error_message = "Linux VMs must use ostype l26."
  }
  assert {
    condition     = proxmox_virtual_environment_vm.this.initialization[0].user_account[0].password == null
    error_message = "Linux VMs get no password."
  }
}
