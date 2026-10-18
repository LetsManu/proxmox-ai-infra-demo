module "vm" {
  source   = "./modules/vm"
  for_each = var.vms

  name        = each.key
  node_name   = var.node_name
  vm_id       = each.value.vm_id
  vm_id_min   = var.vm_id_min
  vm_id_max   = var.vm_id_max
  template_id = each.value.template_id

  cores     = each.value.cores
  memory_mb = each.value.memory_mb
  disk_gb   = each.value.disk_gb

  datastore_id = var.datastore_id
  bridge       = var.bridge
  vlan_id      = var.vlan_id

  ci_user        = var.ci_user
  ssh_public_key = coalesce(each.value.ssh_public_key, var.default_ssh_public_key, " ")

  description   = each.value.description != "" ? each.value.description : "Managed by proxmox-ai-infra-demo (${var.environment})"
  tags          = concat(["managed-by-iac", var.environment], var.base_tags, each.value.tags)
  start_on_boot = var.start_on_boot
  full_clone    = var.full_clone

  snippets_datastore_id = var.snippets_datastore_id
  packages              = each.value.packages
  commands              = each.value.commands

  pool_id        = var.pool_id
  os_family      = each.value.os_family
  admin_password = each.value.os_family == "windows" ? var.windows_admin_password : ""
}

# Policy guardrails evaluated on every plan.
check "resource_limits" {
  assert {
    condition = alltrue([
      for k, v in var.vms : v.cores <= var.max_cores && v.memory_mb <= var.max_memory_mb && v.disk_gb <= var.max_disk_gb
    ])
    error_message = "One or more VMs exceed the ${var.environment} limits (${var.max_cores} vCPU / ${var.max_memory_mb} MB / ${var.max_disk_gb} GB)."
  }
}
