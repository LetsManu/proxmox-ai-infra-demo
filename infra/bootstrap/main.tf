locals {
  base_privileges = [
    "VM.Allocate", "VM.Clone", "VM.Audit", "VM.PowerMgmt",
    "VM.Config.CDROM", "VM.Config.CPU", "VM.Config.Cloudinit", "VM.Config.Disk", "VM.Config.HWType",
    "VM.Config.Memory", "VM.Config.Network", "VM.Config.Options",
    "Datastore.AllocateSpace", "Datastore.AllocateTemplate", "Datastore.Audit",
    "Pool.Audit", "SDN.Audit", "SDN.Use", "Sys.Audit",
  ]
  agent_privileges = var.pve_major >= 9 ? ["VM.GuestAgent.Audit", "VM.GuestAgent.FileRead"] : ["VM.Monitor"]

  token_id = "${var.user_id}!${var.token_name}"

  storages = concat(var.vm_storages, var.create_image_storage ? [var.image_storage_id] : [])
  acl_paths = concat(
    ["/vms", "/pool/${var.pool_id}", "/nodes/${var.node_name}", "/sdn/zones/localnetwork"],
    [for s in local.storages : "/storage/${s}"],
    var.create_sdn ? ["/sdn/zones/${var.sdn_zone}"] : [],
  )
  # every ACL path for both the user and the privilege-separated token
  grants = merge(
    { for p in local.acl_paths : "user:${p}" => { path = p, user_id = var.user_id, token_id = null } },
    { for p in local.acl_paths : "token:${p}" => { path = p, user_id = null, token_id = local.token_id } },
  )
}

# ---- Identity: least-privilege role, user (no password) and API token --------
resource "proxmox_virtual_environment_role" "automation" {
  role_id    = var.role_id
  privileges = sort(concat(local.base_privileges, local.agent_privileges))
}

resource "proxmox_virtual_environment_user" "automation" {
  user_id = var.user_id
  comment = "proxmox-ai-infra-demo automation (no password, token only)"
  enabled = true
}

resource "proxmox_user_token" "console" {
  user_id               = proxmox_virtual_environment_user.automation.user_id
  token_name            = var.token_name
  privileges_separation = true
  expiration_date       = var.token_expiration_date
  comment               = "Used by the console backend and OpenTofu"
}

# ---- Grouping ---------------------------------------------------------------
resource "proxmox_virtual_environment_pool" "infra" {
  pool_id = var.pool_id
  comment = "Templates and VMs managed by proxmox-ai-infra-demo"
}

# ---- Storage for cloud images (content 'import') and cloud-init snippets ----
resource "proxmox_storage_directory" "images" {
  count            = var.create_image_storage ? 1 : 0
  id               = var.image_storage_id
  path             = var.image_storage_path
  content          = ["import", "iso", "snippets"]
  nodes            = [var.node_name]
  create_base_path = true
}

# ---- Network: one VLAN-backed vnet per environment ---------------------------
resource "proxmox_sdn_zone_vlan" "infra" {
  count  = var.create_sdn ? 1 : 0
  id     = var.sdn_zone
  bridge = var.sdn_bridge
  nodes  = [var.node_name]
}

resource "proxmox_sdn_vnet" "env" {
  for_each = var.create_sdn ? var.vnets : {}
  id       = each.key
  zone     = proxmox_sdn_zone_vlan.infra[0].id
  tag      = each.value
  alias    = "infra-demo ${each.key}"
}

resource "proxmox_sdn_applier" "apply" {
  count      = var.create_sdn ? 1 : 0
  depends_on = [proxmox_sdn_vnet.env]
}

# ---- Permissions -------------------------------------------------------------
resource "proxmox_acl" "grant" {
  for_each  = local.grants
  path      = each.value.path
  role_id   = proxmox_virtual_environment_role.automation.role_id
  user_id   = each.value.user_id
  token_id  = each.value.token_id
  propagate = true

  depends_on = [
    proxmox_user_token.console,
    proxmox_virtual_environment_pool.infra,
    proxmox_storage_directory.images,
    proxmox_sdn_applier.apply,
  ]
}
