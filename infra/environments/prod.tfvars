# PRODUCTION: stable VMs. Applied only after TEST validation + explicit human approval.
environment  = "prod"
node_name    = "pve"
datastore_id = "local-lvm"
bridge       = "vmbr0"
vlan_id      = 10

vm_id_min     = 100
vm_id_max     = 299
max_cores     = 8
max_memory_mb = 16384
max_disk_gb   = 128

full_clone    = true # independent of the template
start_on_boot = true
base_tags     = ["production"]
