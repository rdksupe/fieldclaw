# FieldClaw OCI hosts (setup only — services not started)

Provisioned in **ap-hyderabad-1** (Always Free). Two Micros in one VCN per the demo plan:

- **VM1** = public API/UI surface  
- **VM2** = Hermes with public IP for **egress only**; SSH only from VCN (jump via VM1)

A1.Flex was **Out of host capacity**; both are `VM.Standard.E2.1.Micro`.

## Hosts

| Role | Display name | Public IP | Private IP | Public ingress |
|------|--------------|-----------|------------|----------------|
| API / UI | `fieldclaw-api` | `129.225.119.60` | `10.0.1.136` | SSH 22, HTTP 80/443, API 8000 |
| Hermes | `fieldclaw-hermes` | `140.245.195.184` (egress only — do not advertise) | `10.0.1.204` | **None** (SSH from `10.0.0.0/16` only) |

| Field | API | Hermes |
|-------|-----|--------|
| OCID | `ocid1.instance.oc1.ap-hyderabad-1.anuhsljryauwtdqcq3hgrddutsny7rvk3p6vkwgmcowt76cilrlha5j7qnhq` | `ocid1.instance.oc1.ap-hyderabad-1.anuhsljryauwtdqc653t2b4mtl2gwqq5xvfkpld7jvdv2mucirp6wz7cjkwa` |
| Shape | `VM.Standard.E2.1.Micro` | same |
| OS | Ubuntu 22.04 · Docker · x86_64 | same |
| NSG | `fieldclaw-api-nsg` | `fieldclaw-hermes-nsg` |

### SSH

```bash
# API (public)
ssh -i ~/.ssh/id_ed25519 ubuntu@129.225.119.60

# Hermes (jump via API — public SSH is blocked)
ssh -i ~/.ssh/id_ed25519 -J ubuntu@129.225.119.60 ubuntu@10.0.1.204
```

App trees on both hosts:

- `/opt/fieldclaw` — FieldClaw repo
- `/opt/hermes-agent` — Hermes source

### Runtime install (done — services still not started)

| Host | Installed |
|------|-----------|
| API | `uv` + CPython 3.12, `/opt/fieldclaw/apps/api/.venv`, `apps/api/.env` (mode 600) |
| Hermes | `uv` + CPython 3.12, `/opt/hermes-agent/.venv` (`hermes` 0.17.0), `~/.hermes-fieldclaw` + `~/.hermes-fc-foreman` (`.env` + config + skills), wrappers `hermes-fieldclaw` / `hermes-fc-foreman` |

Hermes env rewrites on OCI: `FIELDCLAW_BASE_URL=http://10.0.1.136:8000`, `FIELDCLAW_KB_DIR=/opt/fieldclaw/kb`.

Role markers: `/opt/fieldclaw/HOST_ROLE.txt`  
`/etc/hosts`: `fieldclaw-api` ↔ `fieldclaw-hermes`

## Network posture (matches demo plan)

```
Internet → IGW → fieldclaw-api (public product ports)
fieldclaw-hermes ──egress──→ Internet (Telegram, AgentMail, OpenRouter, …)
fieldclaw-hermes ──private──→ fieldclaw-api:8000
Laptop ──SSH──→ api ──SSH──→ hermes (10.0.1.204)
```

Telegram uses **outbound polling** — Hermes needs **no inbound public ports**.

| Check (2026-08-12) | Result |
|--------------------|--------|
| API public SSH | OK |
| Hermes public SSH / :8642 | **Blocked** |
| SSH jump API → Hermes private | OK |
| Hermes egress HTTPS | OK |
| Private ICMP/TCP api ↔ hermes | OK |
| App processes | **Not running** |

### Shared subnet security list (`fieldclaw-public`)

VCN-only: TCP all + ICMP from `10.0.0.0/16`, MTU. **No** public 22/80/443/8000/8642.

### NSGs

| NSG | Attached to | Ingress |
|-----|-------------|---------|
| `fieldclaw-api-nsg` `ocid1.networksecuritygroup.oc1.ap-hyderabad-1.aaaaaaaao5yzujdsjsv4fols6ebsv2waqu5geu5m7kfjb2asruidnk2otyma` | API VNIC | TCP 22/80/443/8000 from `0.0.0.0/0` |
| `fieldclaw-hermes-nsg` `ocid1.networksecuritygroup.oc1.ap-hyderabad-1.aaaaaaaa7y23wl6rqwzj7br35pdkh5rkioseo4zmnnwmbm5hsnquxai24oxq` | Hermes VNIC | TCP 22 + all TCP + ICMP echo from `10.0.0.0/16` only |

### Host iptables

- **API:** VCN + NEW 22/80/443/8000 (product surface)
- **Hermes:** VCN + NEW 22 only (no public app ports)

### Core network OCIDs

| Resource | Value |
|----------|--------|
| VCN | `ocid1.vcn.oc1.ap-hyderabad-1.amaaaaaayauwtdqaazvuj2d3i7rgjbfvfh52mjuspllppfzqkxtv6bfptutq` (`10.0.0.0/16`) |
| Subnet | `ocid1.subnet.oc1.ap-hyderabad-1.aaaaaaaaor7teqveqnvr2jh4ndsxu3hdpuc43qpk7aogkiycfp5ihrojkbla` (`10.0.1.0/24`) |
| Security list | `ocid1.securitylist.oc1.ap-hyderabad-1.aaaaaaaa6wmjw655gozle4hy24mf4rswqdewps3yevm6spcfwtnhybypc2ka` |
| IGW / RT | unchanged from initial provision |

## Go-live later (do not run yet)

1. Secrets on hosts; Hermes `FIELDCLAW_BASE_URL=http://10.0.1.136:8000`
2. Start API/UI on `fieldclaw-api` only
3. Start Hermes on `fieldclaw-hermes` only (Telegram polling outbound)
4. Do **not** open Hermes to the internet for gateway/webhook ports unless a later design requires it

## Tenancy

- Compartment: tenancy root `rishikirti534`
- Tenancy OCID: `ocid1.tenancy.oc1..aaaaaaaap7pnj5t7gyafo72odhnzzvt4xwrg3scfuyoxfrbdiytfttdgdmca`
- AD: `CRkV:AP-HYDERABAD-1-AD-1`
- SSH key: `~/.ssh/id_ed25519.pub`

## Re-sync files

```bash
RSYNC_EX=(--exclude '.venv/' --exclude 'node_modules/' --exclude '__pycache__/' --exclude '.env' --exclude '.env.*' --exclude 'data/*.db')
SSH_API='ssh -i ~/.ssh/id_ed25519'
SSH_HERMES='ssh -i ~/.ssh/id_ed25519 -J ubuntu@129.225.119.60'
rsync -az --delete "${RSYNC_EX[@]}" -e "$SSH_API" ./ ubuntu@129.225.119.60:/opt/fieldclaw/
rsync -az --delete "${RSYNC_EX[@]}" -e "$SSH_HERMES" ./ ubuntu@10.0.1.204:/opt/fieldclaw/
rsync -az --delete "${RSYNC_EX[@]}" -e "$SSH_HERMES" ../hermes-agent/ ubuntu@10.0.1.204:/opt/hermes-agent/
```
