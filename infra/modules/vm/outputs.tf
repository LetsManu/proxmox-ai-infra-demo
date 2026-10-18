output "vm_id" {
  description = "Proxmox VM ID."
  value       = proxmox_virtual_environment_vm.this.vm_id
}

output "name" {
  description = "VM name."
  value       = proxmox_virtual_environment_vm.this.name
}

output "ipv4_addresses" {
  description = "Non-loopback IPv4 addresses reported by the QEMU guest agent."
  value = [
    for ip in flatten(proxmox_virtual_environment_vm.this.ipv4_addresses) : ip
    if !startswith(ip, "127.")
  ]
}
