output "environment" {
  description = "Environment this state belongs to."
  value       = var.environment
}

output "vms" {
  description = "Deployed VMs with their IDs and guest-agent IPv4 addresses."
  value = {
    for k, m in module.vm : k => {
      vm_id          = m.vm_id
      ipv4_addresses = m.ipv4_addresses
    }
  }
}
