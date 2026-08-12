# Wilbarger Creek RWWTF — public sample corpus

Public City of Pflugerville legislative attachments + TCEQ notice. Copied for FieldClaw demo / wiki seed. Not a substitute for full CAD plan sets (those remain on ConstructConnect / PLW bidder portals).

## Attachment size notes (AgentMail / SMTP)

| Path | Practical limit |
|------|-----------------|
| **Gmail SMTP → AgentMail** (sim emitter) | **~25 MB** total message (Gmail) |
| **AgentMail API** `attachments[].content` (base64) | Treat as **≤18–20 MB file** (base64 expands ~4/3; OSS notes **25 MB** upload) |
| **Full GMP1** `2023-1103_gmp1-bid-documents.pdf` | **33 MB** — too large; use `*_part*.pdf` |
| **Full GMP2** `2024-0561_gmp2-bid-documents.pdf` | **23 MB** — SMTP OK, API risky; prefer parts |

## Files

| File | Source |
|------|--------|
| `2023-1103_gmp1-bid-documents.pdf` (+ parts) | Legistar 2023-1103 View.ashx ID=12447926 |
| `2023-1103_total-project-estimate-nov2023.pdf` | Legistar 2023-1103 ID=12420632 |
| `2023-1103_gmp1-letter-of-recommendation.pdf` | Legistar 2023-1103 ID=12422092 |
| `2024-0561_gmp2-bid-documents.pdf` (+ parts) | Granicus `0db41123-4020-4db2-ae4b-3f414fcb7b04.pdf` |
| `2024-0561_gmp2-recommendation-*.pdf` | Legistar 2024-0561 |
| `2020-8668_*.pdf` | Legistar 2020-8668 |
| `2023-0385/0387/0388/0392/0421_*.pdf` | Granicus PSA / CMAR attachments |
| `2024-0305_interceptor-owners-rep-pssa.pdf` | Legistar 2024-0305 |
| `2011-0387_executive-summary.pdf` | Legistar 2011-0387 |
| `tceq_wq0011845005_notice.pdf` | CIRA / TCEQ notice |

## Seed via mail

```bash
# dry-run
apps/api/.venv/bin/python sim/emitters/wilbarger_mail_seed.py --mode dry-run

# SMTP → My Site AgentMail inbox (uses sim/.env.sim)
apps/api/.venv/bin/python sim/emitters/wilbarger_mail_seed.py --mode smtp \
  --to fc-my-site8506@agentmail.to
```
