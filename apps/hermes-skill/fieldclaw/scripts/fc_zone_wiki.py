#!/usr/bin/env python3
"""Write proper wiki zone pages for imported zones and refresh index."""
import os, json

KB = '/home/rdksupe/building_shit/buildsync/kb/projects/2d32661e-cf1d-422f-9f46-461417af3e28/wiki'

zones = [
    ("Influent Lift Station", "ILS", "Influent pumping / ILS electrical", "#1e3a5f"),
    ("Headworks", "HW", "Screening / grit removal", "#0f766e"),
    ("Aeration Basins", "AB", "Biological treatment (A2O)", "#0369a1"),
    ("Blower Facility", "BLR", "Aeration blowers / controls", "#4338ca"),
    ("RAS/WAS Pump Station", "RAS", "Return / waste activated sludge", "#7c3aed"),
    ("UV Disinfection", "UV", "UV treatment / effluent", "#ca8a04"),
    ("Biosolids Handling", "BIO", "Centrifuge / polymer / solids building", "#b45309"),
    ("Ops & Laboratory", "OPS", "Operations / lab building", "#15803d"),
    ("Maintenance Building", "MNT", "Maintenance / storage", "#57534e"),
    ("Main Plant Electrical", "ELE", "Switchgear / generator yard", "#991b1b"),
    ("Laydown / Site Logistics", "LAY", "Trailers / laydown / temp power", "#78716c"),
]

os.makedirs(f"{KB}/zones", exist_ok=True)

# Remove stale OCR-noise zone stubs
for stale in ("zone-1.md", "zone-3.md", "zone-outside.md", "zone-pavement.md", "zone-with.md"):
    p = f"{KB}/zones/{stale}"
    if os.path.exists(p):
        os.remove(p)
        print("removed stale:", stale)

created = []
for name, code, use, color in zones:
    slug = code.lower()
    body = f"""# {name} ({code})

**Zone status:** grey / 0% — not yet started.
**Source:** `sitemap.geojson` (rev A — Wilbarger Creek Regional WWTF site layout).
**Use:** {use}
"""
    with open(f"{KB}/zones/{slug}.md", "w") as f:
        f.write(body)
    created.append(slug)
    print("wrote zones/%s.md" % slug)

# Refresh index.md
lines = ["# FieldClaw Wiki Index\n", "Folder-organized site knowledge base (markdown-wiki).\n",
         "\nProject `fc_demo1` (2d32661e-cf1d-422f-9f46-461417af3e28) — Wilbarger Creek Regional WWTF (Pflugerville, TX).\n",
         "\n## ops/\n",
         "- [[ops/log]] — site log (status/field reports)\n",
         "- [[ops/agents]] — agent pairing notes\n",
         "\n## zones/ (sitemap rev A)\n"]
for name, code, use, color in zones:
    lines.append(f"- [[zones/{code.lower()}]] — {name} ({code}) — {use}\n")
lines += ["\n## sources/\n",
          "- [[sources/source-tceq-wq0011845005-notice]] — TCEQ WQ permit renewal notice\n",
          "- [[sources/source-2024-0561-gmp2-bid-documents-part1-p1-89]] — GMP2 bid docs part1\n",
          "- [[sources/source-2024-0561-gmp2-bid-documents-part2-p90-177]] — GMP2 bid docs part2\n",
          "- [[sources/source-2024-0561-gmp2-recommendation-garver]] — Garver GMP2 recommendation\n",
          "- [[sources/source-2024-0561-gmp2-recommendation-kimley-horn]] — Kimley-Horn GMP2 recommendation\n",
          "- [[sources/source-2023-1103-gmp1-bid-documents-part4-p361-367]] — GMP1 bid docs part4\n",
          "\n## pos/ · rfis/ · people/ · media/ · maps/ · pageindex/\n",
          "Empty pending site flow — seed only from real site traffic.\n"]

with open(f"{KB}/index.md", "w") as f:
    f.write("".join(lines))
print("\nindex.md refreshed")
