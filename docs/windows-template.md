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
   # VirtIO drivers + QEMU guest agent
   Start-Process msiexec -Wait -ArgumentList '/i D:\virtio-win-gt-x64.msi /qn'
   Start-Process msiexec -Wait -ArgumentList '/i D:\guest-agent\qemu-ga-x86_64.msi /qn'

   # cloudbase-init (sets hostname, Administrator password, network from the cloud-init drive)
   Invoke-WebRequest https://cloudbase.it/downloads/CloudbaseInitSetup_Stable_x64.msi -OutFile C:\cbi.msi
   Start-Process msiexec -Wait -ArgumentList '/i C:\cbi.msi /qn LOGGINGSERIALPORTNAME=COM1 USERNAME=Administrator'

   # WinRM over HTTPS for Ansible (self-signed; pin a CA certificate in production)
   $cert = New-SelfSignedCertificate -DnsName $env:COMPUTERNAME -CertStoreLocation Cert:\LocalMachine\My
   winrm create winrm/config/Listener?Address=*+Transport=HTTPS "@{Hostname=`"$env:COMPUTERNAME`";CertificateThumbprint=`"$($cert.Thumbprint)`"}"
   New-NetFirewallRule -Name winrm-https -DisplayName 'WinRM HTTPS' -Protocol TCP -LocalPort 5986 -Action Allow
   ```
   In `C:\Program Files\Cloudbase Solutions\Cloudbase-Init\conf\cloudbase-init.conf` and `cloudbase-init-unattend.conf`
   set `metadata_services=cloudbaseinit.metadata.services.configdrive.ConfigDriveService` and keep
   `inject_user_password=true` so the password from Proxmox (cloud-init `cipassword`) is applied.
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

## Licensing

You need a valid Windows Server license for every VM you run. Evaluation media expires after 180 days.
