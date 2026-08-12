#!/usr/bin/env node
/**
 * FieldClaw product architecture — rough.js + Kalam (pitch-deck style).
 * Lower bowing / roughness so boxes stay readable (not overly curved).
 * Run: cd deck && node ../docs/diagrams/render-architecture.mjs
 */
import fs from "fs";
import path from "path";
import { fileURLToPath, pathToFileURL } from "url";
import { createRequire } from "module";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = __dirname;
const DECK = path.join(__dirname, "../../deck");
const require = createRequire(path.join(DECK, "package.json"));

const { JSDOM } = await import(pathToFileURL(require.resolve("jsdom")).href);
const roughMod = await import(
  pathToFileURL(require.resolve("roughjs/bundled/rough.esm.js")).href
);
const rough = roughMod.default;
const { Resvg } = await import(
  pathToFileURL(require.resolve("@resvg/resvg-js")).href
);

const C = {
  paper: "#FFFCF7",
  stone: "#1C1917",
  steel: "#57534E",
  oxide: "#C2410C",
  oxideSoft: "#FFE8D6",
  green: "#3F6212",
  greenSoft: "#E8F5D8",
  muted: "#78716C",
  white: "#FFFFFF",
  cream: "#FAFAF9",
  yellow: "#FEF3C7",
};

const FONTS = [
  "/home/rdksupe/.local/share/fonts/handwritten/Kalam-Regular.ttf",
  "/home/rdksupe/.local/share/fonts/handwritten/Kalam-Bold.ttf",
];

function makeSvg(w, h) {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>");
  const { document } = dom.window;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  svg.setAttribute("width", String(w));
  svg.setAttribute("height", String(h));
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  const bg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  bg.setAttribute("width", "100%");
  bg.setAttribute("height", "100%");
  bg.setAttribute("fill", C.paper);
  svg.appendChild(bg);
  return { document, svg, rc: rough.svg(svg) };
}

function text(document, svg, x, y, str, opts = {}) {
  const { size = 26, fill = C.stone, anchor = "middle", weight = "400" } = opts;
  const t = document.createElementNS("http://www.w3.org/2000/svg", "text");
  t.setAttribute("x", String(x));
  t.setAttribute("y", String(y));
  t.setAttribute("text-anchor", anchor);
  t.setAttribute("font-family", "Kalam");
  t.setAttribute("font-size", String(size));
  t.setAttribute("font-weight", weight);
  t.setAttribute("fill", fill);
  t.textContent = str;
  svg.appendChild(t);
}

function multilines(document, svg, x, y, lines, opts = {}) {
  const { size = 22, fill = C.steel, gap = 28, anchor = "middle", weight = "400" } =
    opts;
  lines.forEach((line, i) => {
    text(document, svg, x, y + i * gap, line, { size, fill, anchor, weight });
  });
}

function roughBox(rc, svg, x, y, w, h, style = {}) {
  svg.appendChild(
    rc.rectangle(x, y, w, h, {
      roughness: style.roughness ?? 0.85,
      bowing: style.bowing ?? 0.35,
      stroke: style.stroke || C.stone,
      fill: style.fill || C.white,
      fillStyle: "solid",
      strokeWidth: style.strokeWidth || 2.4,
    })
  );
}

function roughArrow(rc, svg, x1, y1, x2, y2, color = C.oxide) {
  svg.appendChild(
    rc.line(x1, y1, x2, y2, {
      roughness: 0.7,
      bowing: 0.2,
      stroke: color,
      strokeWidth: 2.4,
    })
  );
  const angle = Math.atan2(y2 - y1, x2 - x1);
  const len = 13;
  svg.appendChild(
    rc.linearPath(
      [
        [x2 + Math.cos(angle + 2.55) * len, y2 + Math.sin(angle + 2.55) * len],
        [x2, y2],
        [x2 + Math.cos(angle - 2.55) * len, y2 + Math.sin(angle - 2.55) * len],
      ],
      { roughness: 0.6, bowing: 0.15, stroke: color, strokeWidth: 2.2 }
    )
  );
}

function diagram() {
  const W = 2100,
    H = 1120;
  const { document, svg, rc } = makeSvg(W, H);

  text(document, svg, W / 2, 48, "FieldClaw — how the pieces talk", {
    size: 34,
    weight: "700",
  });

  // Capture row
  const caps = [
    { t: "Foreman", s: ["Telegram", "status · photos"] },
    { t: "Superintendent", s: ["Telegram", "decisions · /init"] },
    { t: "Project mail", s: ["inbox + PDFs", "AE / suppliers"] },
  ];
  const cw = 340,
    ch = 140,
    cgap = 40;
  const cTotal = caps.length * cw + (caps.length - 1) * cgap;
  const cx0 = (W - cTotal) / 2;
  const cy = 90;
  caps.forEach((c, i) => {
    const x = cx0 + i * (cw + cgap);
    roughBox(rc, svg, x, cy, cw, ch, {
      fill: C.oxideSoft,
      stroke: C.oxide,
      strokeWidth: 2.6,
    });
    text(document, svg, x + cw / 2, cy + 48, c.t, { size: 28, weight: "700" });
    multilines(document, svg, x + cw / 2, cy + 85, c.s, {
      size: 20,
      fill: C.steel,
      gap: 26,
    });
  });

  // Vertical arrows into Hermes
  const midY = cy + ch;
  roughArrow(rc, svg, cx0 + cw / 2, midY + 6, cx0 + cw / 2, 280, C.oxide);
  roughArrow(
    rc,
    svg,
    cx0 + cw + cgap + cw / 2,
    midY + 6,
    cx0 + cw + cgap + cw / 2,
    280,
    C.oxide
  );
  roughArrow(
    rc,
    svg,
    cx0 + 2 * (cw + cgap) + cw / 2,
    midY + 6,
    cx0 + 2 * (cw + cgap) + cw / 2,
    280,
    C.oxide
  );

  // Hermes band
  roughBox(rc, svg, 100, 290, W - 200, 64, {
    fill: C.yellow,
    stroke: C.muted,
    strokeWidth: 2.2,
  });
  text(
    document,
    svg,
    W / 2,
    330,
    "Hermes gateway · shared skills · separate SOUL / pairing / Mem0",
    { size: 24, weight: "700" }
  );

  // Profiles
  const py = 390;
  const pw = 700,
    ph = 150;
  roughBox(rc, svg, 140, py, pw, ph, { fill: C.white, stroke: C.stone });
  text(document, svg, 140 + pw / 2, py + 48, "Supervisor Claw", {
    size: 28,
    weight: "700",
  });
  multilines(
    document,
    svg,
    140 + pw / 2,
    py + 85,
    ["~/.hermes-fieldclaw", "/init · wiki · mail · cron · notify"],
    { size: 20, gap: 28 }
  );

  roughBox(rc, svg, W - 140 - pw, py, pw, ph, { fill: C.white, stroke: C.stone });
  text(document, svg, W - 140 - pw / 2, py + 48, "Foreman Claw", {
    size: 28,
    weight: "700",
  });
  multilines(
    document,
    svg,
    W - 140 - pw / 2,
    py + 85,
    ["~/.hermes-fc-foreman", "field capture · proofs · status"],
    { size: 20, gap: 28 }
  );

  // Side column — speech / memory (clear of other boxes)
  const sx = W - 210;
  roughBox(rc, svg, sx, 290, 160, 50, { fill: C.white, stroke: C.muted });
  text(document, svg, sx + 80, 322, "STT / TTS", { size: 18, fill: C.steel });
  roughBox(rc, svg, sx, 350, 160, 50, { fill: C.white, stroke: C.muted });
  text(document, svg, sx + 80, 382, "Mem0", { size: 18, fill: C.steel });

  // Down to FieldClaw
  roughArrow(rc, svg, 140 + pw / 2, py + ph + 6, 380, 600, C.oxide);
  roughArrow(rc, svg, W - 140 - pw / 2, py + ph + 6, W / 2 + 100, 600, C.oxide);

  // FieldClaw row
  const fy = 610;
  const boxes = [
    {
      t: "FieldClaw API",
      s: ["zones · events", "tasks · people"],
      fill: C.stone,
      dark: true,
      stroke: C.stone,
    },
    {
      t: "Karpathy wiki",
      s: ["raw/ + wiki/", "index · PageIndex"],
      fill: C.white,
      stroke: C.stone,
    },
    {
      t: "Web UI :8000",
      s: ["Ops · Maps", "PDFs · Crew"],
      fill: C.greenSoft,
      stroke: C.green,
    },
  ];
  const bw = 460,
    bh = 150,
    bgap = 40;
  const bTotal = boxes.length * bw + (boxes.length - 1) * bgap;
  const bx0 = (W - bTotal) / 2;
  boxes.forEach((b, i) => {
    const x = bx0 + i * (bw + bgap);
    roughBox(rc, svg, x, fy, bw, bh, {
      fill: b.fill,
      stroke: b.stroke,
      strokeWidth: 2.6,
    });
    text(document, svg, x + bw / 2, fy + 50, b.t, {
      size: 26,
      weight: "700",
      fill: b.dark ? C.cream : C.stone,
    });
    multilines(document, svg, x + bw / 2, fy + 90, b.s, {
      size: 20,
      fill: b.dark ? "#A8A29E" : C.steel,
      gap: 28,
    });
    if (i < boxes.length - 1) {
      roughArrow(
        rc,
        svg,
        x + bw + 4,
        fy + bh / 2,
        x + bw + bgap - 4,
        fy + bh / 2,
        C.oxide
      );
    }
  });

  // Footer
  roughBox(rc, svg, 180, 820, W - 360, 220, {
    fill: C.white,
    stroke: C.muted,
    strokeWidth: 2.2,
  });
  text(document, svg, W / 2, 880, "Services are plugs — not the product", {
    size: 26,
    weight: "700",
  });
  multilines(
    document,
    svg,
    W / 2,
    930,
    [
      "LLM · mail · OCR · STT/TTS · Mem0 — swap in .env / Hermes config",
      "Keep the API shape, the wiki layout, and the FieldClaw skills",
      "Standard Hermes features (gateway, pairing, cron, tools) still apply",
    ],
    { size: 20, fill: C.steel, gap: 30 }
  );

  return svg;
}

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const svgEl = diagram();
  const xml = '<?xml version="1.0" encoding="UTF-8"?>' + svgEl.outerHTML;
  fs.writeFileSync(path.join(OUT, "fieldclaw-architecture.svg"), xml);

  const resvg = new Resvg(xml, {
    font: { loadSystemFonts: true, fontFiles: FONTS },
    fitTo: { mode: "width", value: 2400 },
  });
  fs.writeFileSync(
    path.join(OUT, "fieldclaw-architecture.png"),
    resvg.render().asPng()
  );

  console.log("wrote", path.join(OUT, "fieldclaw-architecture.png"));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
