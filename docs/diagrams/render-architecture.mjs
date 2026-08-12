#!/usr/bin/env node
/**
 * FieldClaw product architecture — same rough.js + Kalam hand style as the pitch deck.
 * Run from repo:  node --experimental-import-meta-resolve docs/diagrams/render-architecture.mjs
 * or:  cd deck && node ../docs/diagrams/render-architecture.mjs
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
const roughMod = await import(pathToFileURL(require.resolve("roughjs/bundled/rough.esm.js")).href);
const rough = roughMod.default;
const { Resvg } = await import(pathToFileURL(require.resolve("@resvg/resvg-js")).href);

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
  const { size = 22, fill = C.steel, gap = 28, anchor = "middle", weight = "400" } = opts;
  lines.forEach((line, i) => {
    text(document, svg, x, y + i * gap, line, { size, fill, anchor, weight });
  });
}

function roughBox(rc, svg, x, y, w, h, style = {}) {
  svg.appendChild(
    rc.rectangle(x, y, w, h, {
      roughness: style.roughness || 1.7,
      bowing: style.bowing || 1.4,
      stroke: style.stroke || C.stone,
      fill: style.fill || C.white,
      fillStyle: "solid",
      strokeWidth: style.strokeWidth || 2.5,
    })
  );
}

function roughArrow(rc, svg, x1, y1, x2, y2, color = C.oxide) {
  svg.appendChild(
    rc.line(x1, y1, x2, y2, { roughness: 1.6, stroke: color, strokeWidth: 2.6 })
  );
  const angle = Math.atan2(y2 - y1, x2 - x1);
  const len = 14;
  svg.appendChild(
    rc.linearPath(
      [
        [x2 + Math.cos(angle + 2.55) * len, y2 + Math.sin(angle + 2.55) * len],
        [x2, y2],
        [x2 + Math.cos(angle - 2.55) * len, y2 + Math.sin(angle - 2.55) * len],
      ],
      { roughness: 1.1, stroke: color, strokeWidth: 2.3 }
    )
  );
}

function diagram() {
  const W = 2200, H = 1180;
  const { document, svg, rc } = makeSvg(W, H);

  text(document, svg, W / 2, 52, "FieldClaw — how the pieces talk", {
    size: 36, weight: "700",
  });
  text(document, svg, W / 2, 92, "hand-drawn stack · Hermes roles · project wiki · swappable services", {
    size: 24, fill: C.steel,
  });

  // Row 1 — capture
  const caps = [
    { t: "Foreman", s: ["Telegram bot", "status · photos"], fill: C.oxideSoft, stroke: C.oxide },
    { t: "Superintendent", s: ["Telegram bot", "decisions · /init"], fill: C.oxideSoft, stroke: C.oxide },
    { t: "Project mail", s: ["inbox + PDFs", "AE / suppliers"], fill: C.oxideSoft, stroke: C.oxide },
  ];
  const cw = 320, ch = 160, cgap = 48;
  const cTotal = caps.length * cw + (caps.length - 1) * cgap;
  const cx0 = (W - cTotal) / 2;
  const cy = 130;
  caps.forEach((c, i) => {
    const x = cx0 + i * (cw + cgap);
    roughBox(rc, svg, x, cy, cw, ch, { fill: c.fill, stroke: c.stroke, strokeWidth: 3 });
    text(document, svg, x + cw / 2, cy + 55, c.t, { size: 30, weight: "700" });
    multilines(document, svg, x + cw / 2, cy + 95, c.s, { size: 22, fill: C.steel, gap: 30 });
  });

  // arrows down to Hermes band
  roughArrow(rc, svg, cx0 + cw / 2, cy + ch + 4, W / 2 - 200, 340, C.oxide);
  roughArrow(rc, svg, cx0 + cw + cgap + cw / 2, cy + ch + 4, W / 2, 340, C.oxide);
  roughArrow(rc, svg, cx0 + 2 * (cw + cgap) + cw / 2, cy + ch + 4, W / 2 + 200, 340, C.oxide);

  // Hermes multiplex band
  roughBox(rc, svg, 120, 350, W - 240, 70, {
    fill: C.yellow, stroke: C.muted, roughness: 2, strokeWidth: 2.2,
  });
  text(document, svg, W / 2, 395, "Hermes gateway (multiplex)  ·  shared FieldClaw skills  ·  separate SOUL / pairing / Mem0", {
    size: 26, weight: "700",
  });

  // Two profiles
  const py = 460;
  const pw = 720, ph = 180;
  roughBox(rc, svg, 160, py, pw, ph, { fill: C.white, stroke: C.stone, strokeWidth: 3 });
  text(document, svg, 160 + pw / 2, py + 50, "Supervisor Claw", { size: 32, weight: "700" });
  multilines(document, svg, 160 + pw / 2, py + 95, [
    "~/.hermes-fieldclaw",
    "/init · wiki · mail · cron · notify",
  ], { size: 24, gap: 32 });

  roughBox(rc, svg, W - 160 - pw, py, pw, ph, { fill: C.white, stroke: C.stone, strokeWidth: 3 });
  text(document, svg, W - 160 - pw / 2, py + 50, "Foreman Claw", { size: 32, weight: "700" });
  multilines(document, svg, W - 160 - pw / 2, py + 95, [
    "~/.hermes-fc-foreman",
    "field capture · proofs · status",
  ], { size: 24, gap: 32 });

  // Side slots: STT / TTS / Mem0
  roughBox(rc, svg, W - 280, 350, 200, 55, { fill: C.white, stroke: C.muted });
  text(document, svg, W - 180, 385, "STT / TTS", { size: 22, fill: C.steel });
  roughBox(rc, svg, W - 280, 415, 200, 55, { fill: C.white, stroke: C.muted });
  text(document, svg, W - 180, 450, "Mem0 / user", { size: 22, fill: C.steel });

  // Arrows to FieldClaw row
  roughArrow(rc, svg, 160 + pw / 2, py + ph + 6, 420, 700, C.oxide);
  roughArrow(rc, svg, W - 160 - pw / 2, py + ph + 6, W / 2, 700, C.oxide);

  // FieldClaw row
  const fy = 710;
  const boxes = [
    { t: "FieldClaw API", s: ["zones · events", "tasks · people"], fill: C.stone, dark: true, stroke: C.stone },
    { t: "Karpathy wiki", s: ["raw/ + wiki/", "index · PageIndex"], fill: C.white, stroke: C.stone },
    { t: "Web UI :8000", s: ["Ops · Maps", "PDFs · Crew"], fill: C.greenSoft, stroke: C.green },
  ];
  const bw = 480, bh = 170, bgap = 50;
  const bTotal = boxes.length * bw + (boxes.length - 1) * bgap;
  const bx0 = (W - bTotal) / 2;
  boxes.forEach((b, i) => {
    const x = bx0 + i * (bw + bgap);
    roughBox(rc, svg, x, fy, bw, bh, {
      fill: b.fill, stroke: b.stroke, strokeWidth: 3,
    });
    text(document, svg, x + bw / 2, fy + 55, b.t, {
      size: 30, weight: "700", fill: b.dark ? C.cream : C.stone,
    });
    multilines(document, svg, x + bw / 2, fy + 100, b.s, {
      size: 24, fill: b.dark ? "#A8A29E" : C.steel, gap: 32,
    });
    if (i < boxes.length - 1) {
      roughArrow(rc, svg, x + bw + 6, fy + bh / 2, x + bw + bgap - 6, fy + bh / 2, C.oxide);
    }
  });

  // Footer note
  roughBox(rc, svg, 200, 940, W - 400, 160, {
    fill: C.white, stroke: C.muted, roughness: 2, strokeWidth: 2,
  });
  text(document, svg, W / 2, 995, "Services are plugs — not the product", {
    size: 28, weight: "700",
  });
  text(document, svg, W / 2, 1045, "LLM · mail · OCR · STT/TTS · Mem0 swap via env/config · contracts stay API + wiki + skills", {
    size: 24, fill: C.steel,
  });

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
  const png = resvg.render().asPng();
  fs.writeFileSync(path.join(OUT, "fieldclaw-architecture.png"), png);

  // Lightweight Excalidraw stub pointing editors at the SVG/PNG (same as deck stubs)
  const empty = {
    type: "excalidraw",
    version: 2,
    source: "fieldclaw-docs",
    elements: [],
    appState: { viewBackgroundColor: "#FFFCF7" },
    files: {},
  };
  fs.writeFileSync(
    path.join(OUT, "fieldclaw-architecture.excalidraw"),
    JSON.stringify(empty, null, 2)
  );

  // Drop mermaid artifact from the featured set
  const mmd = path.join(OUT, "fieldclaw-architecture.mmd");
  if (fs.existsSync(mmd)) fs.unlinkSync(mmd);

  console.log("wrote", path.join(OUT, "fieldclaw-architecture.png"));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
