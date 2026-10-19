# Releases

Releases are on the GitHub releases page of the repository. Each one has an install archive
(`proxmox-ai-infra-<version>.tar.gz` with `scripts/install.sh`), its SHA-256, and from 2.1.0 on the container images on
`ghcr.io`. From 2.1.0-rc.2 on a release also has the Proxmox appliance disk
(`proxmox-ai-infra-appliance-<version>.qcow2`, [appliance.md](appliance.md)) and `import-to-proxmox.sh`.

| Version | Content | Images |
|---|---|---|
| `v2.1.0-rc.1` | Sign-in (OIDC, LDAP), roles, install/upgrade/backup scripts | `ghcr.io/letsmanu/proxmox-ai-infra-demo/{backend,frontend}:2.1.0-rc.1` |
| `v2.0.3` | Windows Server verification and fixes | none (source release, build locally) |

## Versions

- `X.Y.Z` for a release, `X.Y.Z-rc.N` for a release candidate (marked *pre-release*, no `latest` image tag).
- The version lives in `backend/app/__init__.py`, `frontend/package.json` (+ lock file) and a `## X.Y.Z – date`
  section in `CHANGELOG.md`. CI fails if they differ.
- A release candidate is tested on a real Proxmox host before the same commit, or a fixed one, becomes `X.Y.Z`.

## Making a release

1. Bump the version in the three files and write the `CHANGELOG.md` section; push to `main` and wait for green CI.
2. GitHub → **Actions → Release → Run workflow**, branch `main`, version e.g. `2.1.0-rc.2` or `2.1.0` (no `v`).
3. The workflow (`.github/workflows/release.yml`):
   1. runs the full CI on that commit,
   2. checks the version against the code and that the tag does not exist yet,
   3. builds and pushes `backend` and `frontend` to `ghcr.io/<owner>/proxmox-ai-infra-demo/…:<version>` with SBOM and
      provenance (`latest` only for a final release),
   4. builds the appliance disk from those images (`appliance/build.sh`, KVM on the runner; fails above 2 GB),
   5. creates the tag `v<version>` on exactly that commit and the GitHub release with the install archive, the
      appliance disk, `import-to-proxmox.sh`, their SHA-256 sums and the changelog section.

Pushing a tag `vX.Y.Z` yourself also starts the workflow (the tag must then point at a commit on `main`).

Repository settings this needs (once): **Settings → Actions → General → Workflow permissions: Read and write**.

### Older commits without images

`Release from tag (source only)` (`.github/workflows/release-from-tag.yml`) publishes a release with only the source
archive. GitHub refuses to let Actions create a tag on a commit whose workflow files differ from `main` (that counts as
a workflow change and needs the `workflows` permission, which the Actions token never has). For such a commit, create
the release in the GitHub UI instead: **Releases → Draft a new release → tag `vX.Y.Z`, target: the commit**. That is how
`v2.0.3` was published.

## Installing from the registry

The repository is private, so its packages are private too. On the console host either

- `docker login ghcr.io -u <github-user>` with a personal access token (classic) that has only `read:packages`, or
- make the two packages public (GitHub → your profile → **Packages** → package → **Package settings → Change
  visibility**) if the images contain nothing you need to keep private.

Without registry access: `scripts/install.sh --build` builds the images from the archive.

Check an archive before installing:

```bash
sha256sum -c proxmox-ai-infra-<version>.tar.gz.sha256
```

Inspect what an image was built from (commit, SBOM, provenance):

```bash
docker buildx imagetools inspect ghcr.io/letsmanu/proxmox-ai-infra-demo/backend:<version> --format '{{json .Provenance}}'
```

## Upgrades and rollback

- Upgrade: extract the new archive over the installation, then `scripts/upgrade.sh` (backup first, new secret files,
  list of new settings, pull, restart). Read the *Upgrading from* notes in `CHANGELOG.md` first.
- Roll back: `VERSION=<old>` in `.env`, then `scripts/restore.sh backups/<pre-upgrade backup>.tar.gz`. The database
  schema only grows (new tables/columns), so an older version still starts on a newer database, but restoring the
  pre-upgrade backup is the safe way back.
