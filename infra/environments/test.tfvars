# TEST: disposable VMs on an isolated network.
# Placement values (node, storage, bridge, VLAN) are overridden by the backend from .env.
environment  = "test"
node_name    = "pve"
datastore_id = "local-lvm"
bridge       = "vmbr0"
vlan_id      = 30

vm_id_min     = 900
vm_id_max     = 999
max_cores     = 4
max_memory_mb = 8192
max_disk_gb   = 64

full_clone    = false # linked clones are fast and cheap for disposable VMs
start_on_boot = false
base_tags     = ["disposable"]
