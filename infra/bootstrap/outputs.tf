output "token_id" {
  description = "Full token ID (USER@REALM!TOKENID)."
  value       = local.token_id
}

output "token_secret" {
  description = "API token secret. Shown only via `tofu output -raw token_secret`; store it in secrets/ or .env."
  value       = split("=", proxmox_user_token.console.value)[1]
  sensitive   = true
}

output "env" {
  description = "Values to put into .env."
  value = {
    PROXMOX_USER       = var.user_id
    PROXMOX_TOKEN_ID   = var.token_name
    PROXMOX_NODE       = var.node_name
    POOL_ID            = var.pool_id
    IMAGE_STORAGE      = var.create_image_storage ? var.image_storage_id : "local"
    SNIPPETS_DATASTORE = var.create_image_storage ? var.image_storage_id : ""
    TEST_BRIDGE        = var.create_sdn ? "vtest" : var.sdn_bridge
    TEST_VLAN          = var.create_sdn ? 0 : lookup(var.vnets, "vtest", 0)
    PROD_BRIDGE        = var.create_sdn ? "vprod" : var.sdn_bridge
    PROD_VLAN          = var.create_sdn ? 0 : lookup(var.vnets, "vprod", 0)
  }
}
