output "templates" {
  description = "Built templates: key => VM ID."
  value       = { for k, t in proxmox_virtual_environment_vm.template : k => t.vm_id }
}
