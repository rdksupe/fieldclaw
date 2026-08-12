# FieldClaw OCI showcase host

Provisioned 2026-08-11 in **ap-hyderabad-1** (Always Free).

## SSH

```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@129.225.119.60
```

App dir on host: `/opt/fieldclaw`

## Instance

| Field | Value |
|-------|--------|
| Display name | `fieldclaw-showcase` |
| OCID | `ocid1.instance.oc1.ap-hyderabad-1.anuhsljryauwtdqcq3hgrddutsny7rvk3p6vkwgmcowt76cilrlha5j7qnhq` |
| Shape | `VM.Standard.E2.1.Micro` (1 OCPU / 1 GB) |
| Arch | x86_64 |
| State | RUNNING |
| Public IP | `129.225.119.60` |
| Private IP | `10.0.1.136` |
| Free tier | `orcl-cloud.free-tier-retained=true` |
| OS | Canonical Ubuntu 22.04 |
| Docker | 29.1.3 (installed via cloud-init) |

## Why not A1.Flex 4/24?

`VM.Standard.A1.Flex` (Ampere) returned **Out of host capacity** for 4/24, 2/12, and 1/6 in `AP-HYDERABAD-1-AD-1`. Fell back to Always Free `VM.Standard.E2.1.Micro` per plan.

To upgrade later when Ampere capacity opens:

```bash
export PATH="$HOME/bin:$PATH"
# terminate micro first (Always Free A1 needs free quota), then re-launch A1.Flex 4 OCPU / 24 GB
```

**Note:** 1 GB RAM is tight for Hermes + API + dashboard. Prefer re-trying A1 before a full stack deploy, or run a minimal API-only smoke on this Micro.

## Network

| Resource | OCID / value |
|----------|----------------|
| VCN | `ocid1.vcn.oc1.ap-hyderabad-1.amaaaaaayauwtdqaazvuj2d3i7rgjbfvfh52mjuspllppfzqkxtv6bfptutq` (`10.0.0.0/16`, `fieldclaw-vcn`) |
| IGW | `ocid1.internetgateway.oc1.ap-hyderabad-1.aaaaaaaac6f4wpmvl4sllw35jxxmxwb5xelowo56nojxuff7uuzjnty4nbpa` |
| Subnet | `ocid1.subnet.oc1.ap-hyderabad-1.aaaaaaaaor7teqveqnvr2jh4ndsxu3hdpuc43qpk7aogkiycfp5ihrojkbla` (`10.0.1.0/24`, `fieldclaw-public`) |
| Route table | `ocid1.routetable.oc1.ap-hyderabad-1.aaaaaaaagbtp4ir6m3wfylotcu4pbyymplgwq476lf5cypm64n7msyue7zda` |
| Security list | `ocid1.securitylist.oc1.ap-hyderabad-1.aaaaaaaa6wmjw655gozle4hy24mf4rswqdewps3yevm6spcfwtnhybypc2ka` |
| Open ports | TCP 22, 80, 443, 8000 |

## Memory

Personal memory uses **Mem0** (cloud Hobby). Set `MEM0_API_KEY` in Hermes `.env`.
Hermes scopes memories by Telegram user id. Project facts stay in the FieldClaw wiki.

## Tenancy

- Compartment: tenancy root `rishikirti534`
- Tenancy OCID: `ocid1.tenancy.oc1..aaaaaaaap7pnj5t7gyafo72odhnzzvt4xwrg3scfuyoxfrbdiytfttdgdmca`
- AD: `CRkV:AP-HYDERABAD-1-AD-1`
- SSH key used: `~/.ssh/id_ed25519.pub`
