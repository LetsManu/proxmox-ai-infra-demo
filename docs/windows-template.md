# Windows template (provided once)

Linux templates are built automatically by the platform stack from official cloud images. Microsoft publishes no
freely redistributable cloud image, so the Windows Server template is created **once** by a person. After that,
everything is automated: the console clones it, sets the Administrator password through cloudbase-init, and
Ansible installs the selected software over WinRM.

Expected result: a Proxmox template with VMID `TEMPLATE_WINDOWS_2022_ID` (default `9002`) that

- boots with VirtIO drivers (SCSI + network) and the **QEMU guest agent** running,
- runs **cloudbase-init** on first boot (reads the Proxmox cloud-init drive),
- exposes **WinRM over HTTPS (5986)** for Ansible,
- is **sysprepped** (generalized).

## Steps

1. Upload the Windows Server 2022 ISO (evaluation or your licensed media) and the
   [VirtIO driver ISO](https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/stable-virtio/) to an ISO storage.
2. Create the VM (once):
   ```bash
   qm create 9002 --name tmpl-windows-2022 --memory 4096 --cores 2 --cpu x86-64-v2-AES --machine q35 \
     --ostype win11 --bios ovmf --efidisk0 local-lvm:1,efitype=4m,pre-enrolled-keys=1 \
     --scsihw virtio-scsi-single --scsi0 local-lvm:40,discard=on,iothread=1 \
     --net0 virtio,bridge=vmbr0 --agent enabled=1 \
     --ide2 local:iso/<windows-server-2022>.iso,media=cdrom --ide0 local:iso/virtio-win.iso,media=cdrom \
     --pool infra-demo
   ```
3. Install Windows; load the `vioscsi` driver from the VirtIO ISO when the installer asks for a disk.
4. In Windows (PowerShell as Administrator):
   ```powershell
   # VirtIO drivers + QEMU guest agent (D: = the VirtIO ISO; check the letter with Get-Volume)
   Start-Process msiexec -Wait -ArgumentList '/i D:\virtio-win-gt-x64.msi /qn'
   Start-Process msiexec -Wait -ArgumentList '/i D:\guest-agent\qemu-ga-x86_64.msi /qn'

   # cloudbase-init (sets hostname, Administrator password, network from the cloud-init drive)
   Invoke-WebRequest https://cloudbase.it/downloads/CloudbaseInitSetup_Stable_x64.msi -OutFile C:\cbi.msi
   Start-Process msiexec -Wait -ArgumentList '/i C:\cbi.msi /qn LOGGINGSERIALPORTNAME=COM1 USERNAME=Administrator'

   # WinRM over HTTPS for Ansible: only open the port here. Do not create a certificate in the template:
   # it would be copied into every clone with the same private key. cloudbase-init's ConfigWinRMListenerPlugin
   # (on by default) creates a new self-signed certificate and the HTTPS listener on each clone's first boot.
   New-NetFirewallRule -Name winrm-https -DisplayName 'WinRM HTTPS' -Protocol TCP -LocalPort 5986 -Action Allow
   ```
   Windows Server also enables an unencrypted HTTP listener (5985). Save this one line as
   `C:\Program Files\Cloudbase Solutions\Cloudbase-Init\LocalScripts\winrm-no-http.ps1`; cloudbase-init runs it as
   SYSTEM after the HTTPS listener is configured:
   ```powershell
   Get-ChildItem WSMan:\localhost\Listener | Where-Object { $_.Keys -contains 'Transport=HTTP' } | Remove-Item -Recurse -Force
   ```
   The certificate is self-signed, so Ansible does not validate it (`group_vars/windows.yml`); use a CA-issued
   certificate (e.g. AD CS auto-enrollment) in production and set `ansible_winrm_server_cert_validation: validate`.
   In `C:\Program Files\Cloudbase Solutions\Cloudbase-Init\conf\cloudbase-init.conf` and `cloudbase-init-unattend.conf`
   set `metadata_services=cloudbaseinit.metadata.services.configdrive.ConfigDriveService` and keep
   `inject_user_password=true` so the password from Proxmox (cloud-init `cipassword`) is applied.
   Keep the default `plugins` list: it contains `ConfigWinRMListenerPlugin` (HTTPS listener) and `LocalScriptsPlugin`.
5. Generalize and shut down with cloudbase-init's unattend file:
   ```powershell
   cd 'C:\Program Files\Cloudbase Solutions\Cloudbase-Init\conf'
   C:\Windows\System32\Sysprep\sysprep.exe /generalize /oobe /shutdown /unattend:Unattend.xml
   ```
6. Back on the node: `qm set 9002 --delete ide2,ide0 && qm set 9002 --ide2 local-lvm:cloudinit && qm template 9002`.

The **Platform** page then shows `9002 (Windows Server 2022)` as present.

## Console configuration

- `TEMPLATE_WINDOWS_2022_ID=9002`
- `WINDOWS_ADMIN_PASSWORD` (12+ characters, ideally via `secrets/windows_admin_password`): OpenTofu passes it to
  cloudbase-init as the Administrator password, Ansible uses it for WinRM. It is never written to disk by the console
  and is masked in job logs.
- Windows computer names are limited to 15 characters; the API rejects longer names.

## Verification

The whole Windows path was run once on **2026-10-18** with Windows Server 2022 (evaluation ISO, Server Core) on a VM
built like this template: q35, OVMF, `x86-64-v2-AES` CPU flags, VirtIO SCSI disk, virtio-net, guest agent channel,
`ostype win11`. The steps above were followed; the clone was a linked clone with a cloud-init drive in Proxmox's
`configdrive2` layout (`openstack/latest/meta_data.json` with `admin_pass`, attached as `ide2`).

| Step | Result |
|---|---|
| Template: VirtIO drivers, guest agent, cloudbase-init, sysprep | OK; the clone boots from VirtIO SCSI after sysprep |
| Guest agent on the clone (`network-get-interfaces`, `get-osinfo`) as parsed by the console | IPv4 of the NIC; loopback, IPv6 and link-local skipped; `Windows Server 2022 Standard Evaluation` |
| cloudbase-init reads the config drive | hostname, Administrator password (`admin_pass`), new WinRM HTTPS certificate per clone |
| `site.yml` through the console's `configure_vm` (profiles `iis`, `windows_tools`, package `jq`) | `failed=0` |
| `tests.yml` through the console's test runner: security baseline, profile checks, AI-style checks of every Windows type, negative controls | all expected results |

Found and fixed during the run (see CHANGELOG 2.0.3): link-local addresses taken as the guest IP; the guest agent
answering minutes before cloudbase-init has set the password (validation now waits for WinRM 5986); the WinRM
certificate made in the template and shared by every clone; the 5985 listener; check results lost for all-digit check
ids; the cloud-init format now set explicitly to `configdrive2`.

Not covered by that run, check these on your Proxmox host:

- It ran under QEMU without KVM, outside Proxmox. Proxmox API calls (clone, cloud-init drive creation, start) were not
  exercised; the OpenTofu module's request is covered by `tofu test` in `infra/modules/vm` (mocked provider).
- The guest reached the console through port forwarding, so checks from the console against ports measure the
  forwarding, not your VLAN firewall.
- Timing: emulation is far slower than KVM. Measured there: guest agent answering about 6.5 minutes before the
  password was set. On Proxmox the gaps are shorter; the order (agent first) is expected to stay.

## Licensing

You need a valid Windows Server license for every VM you run. Evaluation media expires after 180 days.
