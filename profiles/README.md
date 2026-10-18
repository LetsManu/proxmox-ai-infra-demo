# Project software profiles

Every folder here is an Ansible role that shows up as a **Software** checkbox in the console,
next to the built-in profiles. Add software for a project by adding a folder; no code change, no rebuild:
the backend re-reads this directory on every request (mounted read-only at `/profiles`,
see `EXTRA_PROFILE_DIRS` in `.env.example`).

```
profiles/
└── redis/
    ├── profile.yml        # label, os_family (linux|windows), description, optional port
    └── tasks/main.yml     # what to install / configure
```

`profile.yml`:

```yaml
label: Redis
os_family: linux
description: Redis server, listening on localhost
port: 6379        # optional: default port for the validation health check
```

Rules: folder name `^[a-z][a-z0-9_]{1,40}$`; built-in roles win on name clashes; roles may use
`ansible.builtin`, `ansible.windows` and `chocolatey.chocolatey` modules (installed in the image).

For one-off software you don't need a profile at all: type package names (apt for Linux,
Chocolatey for Windows) into **Extra packages** in the form.

To keep project profiles in their own repository, mount that repository's folder instead and set
`EXTRA_PROFILE_DIRS=/profiles` (several folders: `EXTRA_PROFILE_DIRS=/profiles:/other`).
