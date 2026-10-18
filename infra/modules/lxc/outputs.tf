output "vm_id" {
  description = "Container ID."
  value       = proxmox_virtual_environment_container.this.vm_id
}

output "ipv4_addresses" {
  description = "IPv4 addresses of the container."
  value       = [for k, v in proxmox_virtual_environment_container.this.ipv4 : v if k != "lo"]
}
