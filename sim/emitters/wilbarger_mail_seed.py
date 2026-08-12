#!/usr/bin/env python3
"""Historically-paced Wilbarger PDF seed → AgentMail inbox via Gmail SMTP.

External emitter (not Hermes). Sends public council PDFs as realistic site mail
with backdated Date headers. Skips files over SMTP_SAFE_BYTES (default 22MB).

Env (sim/.env.sim):
  SIM_SMTP_HOST/PORT/USER/PASSWORD/FROM
  HERMES_INBOX (fallback --to)
"""

from __future__ import annotations

import argparse
import os
import smtplib
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORPUS = REPO / "kb" / "samples" / "wilbarger"
# Stay under Gmail ~25MB and AgentMail base64 comfort zone
SMTP_SAFE_BYTES = 22 * 1024 * 1024


def _load_sim_env() -> None:
    env_path = REPO / "sim" / ".env.sim"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# (when ISO date, from_label, subject, body, filename)
CAMPAIGN: list[tuple[str, str, str, str, str]] = [
    (
        "2020-08-11T15:00:00+00:00",
        "City Engineering <engineering@pflugervilletx.gov>",
        "Wilbarger Creek RWWTF — design RFQ scoring & site map",
        "Team,\n\nAttached: Garver selection score matrix and project location map "
        "for the Wilbarger Creek Regional WWTF site (Gregg Lane / Weiss Lane area).\n\n"
        "— City of Pflugerville Engineering",
        "2020-8668_team-score-matrix.pdf",
    ),
    (
        "2020-08-11T15:05:00+00:00",
        "City Engineering <engineering@pflugervilletx.gov>",
        "RE: Wilbarger Creek RWWTF — site location map",
        "Follow-up attachment: location map figure for the Wilbarger site.\n",
        "2020-8668_site-location-map.pdf",
    ),
    (
        "2023-04-14T18:00:00+00:00",
        "Garver <austin@garverusa.com>",
        "WCRWWTF — CMAR recommendation (PLW Waterworks)",
        "Jeff / Brandon,\n\nRecommendation of award for CMAR preconstruction / Phase 1 "
        "to PLW Waterworks (Job P5K).\n\n— Garver",
        "2023-0388_cmar-recommendation.pdf",
    ),
    (
        "2023-11-06T16:00:00+00:00",
        "Garver <austin@garverusa.com>",
        "WCRWWTF Phase 1 — GMP #1 Letter of Recommendation",
        "Overall recommendation of award for GMP1 Early Work Packages to PLW.\n",
        "2023-1103_gmp1-letter-of-recommendation.pdf",
    ),
    (
        "2023-11-06T16:10:00+00:00",
        "PLW Preconstruction <bids@plwUS.com>",
        "WCRWWTF — Total Project Estimate (November 2023)",
        "Draft CMAR budget rollup (GMP1 + projected GMP2) for council packet.\n",
        "2023-1103_total-project-estimate-nov2023.pdf",
    ),
    (
        "2023-11-07T14:00:00+00:00",
        "PLW Preconstruction <bids@plwUS.com>",
        "WCRWWTF GMP #1 Bid Documents — Part 1 of 4 (pp. 1–120)",
        "Guaranteed Maximum Price Proposal #1 (Early Work Packages). Part 1/4.\n"
        "Full package also on Legistar file 2023-1103.\n",
        "2023-1103_gmp1-bid-documents_part1-p1-120.pdf",
    ),
    (
        "2023-11-07T14:02:00+00:00",
        "PLW Preconstruction <bids@plwUS.com>",
        "WCRWWTF GMP #1 Bid Documents — Part 2 of 4 (pp. 121–240)",
        "GMP1 Bid Documents part 2/4.\n",
        "2023-1103_gmp1-bid-documents_part2-p121-240.pdf",
    ),
    (
        "2023-11-07T14:04:00+00:00",
        "PLW Preconstruction <bids@plwUS.com>",
        "WCRWWTF GMP #1 Bid Documents — Part 3 of 4 (pp. 241–360)",
        "GMP1 Bid Documents part 3/4 (includes drawing/spec lists).\n",
        "2023-1103_gmp1-bid-documents_part3-p241-360.pdf",
    ),
    (
        "2023-11-07T14:06:00+00:00",
        "PLW Preconstruction <bids@plwUS.com>",
        "WCRWWTF GMP #1 Bid Documents — Part 4 of 4 (pp. 361–367)",
        "GMP1 Bid Documents part 4/4 (assumptions & clarifications).\n",
        "2023-1103_gmp1-bid-documents_part4-p361-367.pdf",
    ),
    (
        "2024-05-23T17:00:00+00:00",
        "Garver <austin@garverusa.com>",
        "WCRWWTF Phase 1 — GMP #2 (Balance of Plant) recommendation",
        "Overall recommendation of award for GMP2 BOP packages. Revised PLW contract "
        "total $247,671,315.93 after Amendment.\n",
        "2024-0561_gmp2-recommendation-garver.pdf",
    ),
    (
        "2024-05-24T15:00:00+00:00",
        "Kimley-Horn / STV <pflugerville@kimley-horn.com>",
        "WCRWWTF — GMP #2 Owner’s Rep recommendation letter",
        "Concurring recommendation for GMP2 Balance of Plant award.\n",
        "2024-0561_gmp2-recommendation-kimley-horn.pdf",
    ),
    (
        "2024-05-24T15:10:00+00:00",
        "PLW Preconstruction <bids@plwUS.com>",
        "WCRWWTF GMP #2 Bid Documents — Part 1 of 2 (pp. 1–89)",
        "GMP2 proposal (BOP packages). Part 1/2 — full file exceeds mail limits.\n",
        "2024-0561_gmp2-bid-documents_part1-p1-89.pdf",
    ),
    (
        "2024-05-24T15:12:00+00:00",
        "PLW Preconstruction <bids@plwUS.com>",
        "WCRWWTF GMP #2 Bid Documents — Part 2 of 2 (pp. 90–177)",
        "GMP2 Bid Documents part 2/2.\n",
        "2024-0561_gmp2-bid-documents_part2-p90-177.pdf",
    ),
    (
        "2024-07-31T12:00:00+00:00",
        "TCEQ Notices <noreply@tceq.texas.gov>",
        "TCEQ — WQ0011845005 notice (Wilbarger / Gregg Lane)",
        "Notice of receipt / intent for TPDES permit renewal WQ0011845005 "
        "(15.75 MGD, 10100 Gregg Lane).\n",
        "tceq_wq0011845005_notice.pdf",
    ),
]


def build_message(to: str, smtp_from: str, when: datetime, subject: str, body: str, path: Path) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = when.strftime("%a, %d %b %Y %H:%M:%S %z")
    msg["X-FieldClaw-Seed"] = "wilbarger-public-corpus"
    msg.set_content(body)
    data = path.read_bytes()
    msg.add_attachment(data, maintype="application", subtype="pdf", filename=path.name)
    return msg


def main() -> None:
    _load_sim_env()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=("dry-run", "smtp"), default="dry-run")
    ap.add_argument("--to", default=os.environ.get("WILBARGER_SEED_TO") or "fc-my-site8506@agentmail.to")
    ap.add_argument("--pause", type=float, default=2.0, help="seconds between SMTP sends")
    ap.add_argument("--max-bytes", type=int, default=SMTP_SAFE_BYTES)
    ap.add_argument("--limit", type=int, default=0, help="send only first N planned messages (0=all)")
    ap.add_argument("--skip", type=int, default=0, help="skip first N planned messages")
    args = ap.parse_args()

    smtp_from = os.environ.get("SIM_SMTP_FROM") or os.environ.get("SMTP_FROM") or ""
    planned: list[tuple] = []
    for when_s, from_label, subject, body, fname in CAMPAIGN:
        path = CORPUS / fname
        if not path.exists():
            print(f"MISSING {fname}")
            continue
        size = path.stat().st_size
        if size > args.max_bytes:
            print(f"SKIP oversize {fname} ({size/1e6:.1f}MB > {args.max_bytes/1e6:.0f}MB)")
            continue
        when = datetime.fromisoformat(when_s)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        planned.append((when, from_label, subject, body, path, size))

    if args.skip and args.skip > 0:
        planned = planned[args.skip :]
    if args.limit and args.limit > 0:
        planned = planned[: args.limit]
    print(f"to={args.to} mode={args.mode} count={len(planned)}", flush=True)
    for when, from_label, subject, body, path, size in planned:
        print(f"  {when.date()}  {size/1e6:5.1f}MB  {path.name}", flush=True)
        print(f"           {subject[:70]}", flush=True)

    if args.mode == "dry-run":
        return

    host = os.environ.get("SIM_SMTP_HOST") or os.environ.get("SMTP_HOST") or "smtp.gmail.com"
    port = int(os.environ.get("SIM_SMTP_PORT") or os.environ.get("SMTP_PORT") or "587")
    user = os.environ.get("SIM_SMTP_USER") or os.environ.get("SMTP_USER") or ""
    password = os.environ.get("SIM_SMTP_PASSWORD") or os.environ.get("SMTP_PASSWORD") or ""
    if not (user and password and smtp_from):
        raise SystemExit("Need SIM_SMTP_USER/PASSWORD/FROM in sim/.env.sim")

    print(f"connecting {host}:{port}…", flush=True)
    with smtplib.SMTP(host, port, timeout=120) as s:
        s.ehlo()
        s.starttls()
        s.login(user, password)
        print("login ok", flush=True)
        for when, from_label, subject, body, path, size in planned:
            # Gmail rewrites From; keep persona in body header line
            text = f"(From: {from_label})\n\n{body}"
            print(f"sending {path.name} ({size/1e6:.1f}MB)…", flush=True)
            t0 = time.time()
            msg = build_message(args.to, smtp_from, when, subject, text, path)
            s.send_message(msg)
            elapsed = round(time.time() - t0, 2)
            print(f"SENT {path.name} ({size/1e6:.1f}MB) in {elapsed}s", flush=True)
            time.sleep(args.pause)
    print("done", flush=True)


if __name__ == "__main__":
    main()
