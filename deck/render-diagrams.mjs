#!/usr/bin/env node
/**
 * FieldClaw diagrams — rough.js + Kalam (final)
 * 01 hierarchy · 02 broken flow · 03 closed loop · 04 how-it-works · 05 architecture
 */
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { JSDOM } from "jsdom";
import rough from "roughjs/bundled/rough.esm.js";
import { Resvg } from "@resvg/resvg-js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ASSETS = path.join(__dirname, "assets");
const DIAGRAMS = path.join(__dirname, "diagrams");
const FONTS = [
  "/home/rdksupe/.local/share/fonts/handwritten/Kalam-Regular.ttf",
  "/home/rdksupe/.local/share/fonts/handwritten/Kalam-Bold.ttf",
];

const C = {
  paper: "#FFFCF7",
  stone: "#1C1917",
  steel: "#57534E",
  oxide: "#C2410C",
  oxideSoft: "#FFE8D6",
  green: "#3F6212",
  greenSoft: "#E8F5D8",
  red: "#B91C1C",
  redSoft: "#FDE8E8",
  cream: "#FAFAF9",
  muted: "#78716C",
  white: "#FFFFFF",
  yellow: "#FEF3C7",
};

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
  const { size = 20, fill = C.steel, gap = 26, anchor = "middle", weight = "400" } = opts;
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
  const len = 15;
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

function roughCurve(rc, svg, points, color = C.green, dashed = true) {
  svg.appendChild(
    rc.curve(points, {
      roughness: 1.8,
      stroke: color,
      strokeWidth: 3,
      ...(dashed ? { strokeLineDash: [12, 10] } : {}),
    })
  );
}

async function writePng(name, svgEl, outW) {
  const xml = '<?xml version="1.0" encoding="UTF-8"?>' + svgEl.outerHTML;
  fs.writeFileSync(path.join(ASSETS, `${name}.svg`), xml);
  const resvg = new Resvg(xml, {
    font: { loadSystemFonts: true, fontFiles: FONTS },
    fitTo: { mode: "width", value: outW },
  });
  fs.writeFileSync(path.join(ASSETS, `${name}.png`), resvg.render().asPng());
  console.log("wrote", name, resvg.width, "x", resvg.height);
}

/* ─── 01. Site hierarchy (verified GC chain) ─── */
function diagramHierarchy() {
  const W = 2000, H = 1000;
  const { document, svg, rc } = makeSvg(W, H);

  // PM
  roughBox(rc, svg, 700, 40, 600, 110, { fill: C.white, stroke: C.stone });
  text(document, svg, 1000, 85, "Project Manager", { size: 32, weight: "700" });
  text(document, svg, 1000, 120, "master schedule · budget · contracts · owner / A/E", {
    size: 20, fill: C.steel,
  });

  roughArrow(rc, svg, 1000, 155, 1000, 195, C.muted);
  text(document, svg, 1120, 185, "super reports to PM", { size: 18, fill: C.muted, anchor: "start" });

  // Super — hero
  roughBox(rc, svg, 620, 200, 760, 140, {
    fill: C.stone, stroke: C.stone, strokeWidth: 3,
  });
  text(document, svg, 1000, 250, "Superintendent", {
    size: 34, weight: "700", fill: C.cream,
  });
  text(document, svg, 1000, 285, "runs the day · trades · safety · quality · materials", {
    size: 20, fill: "#A8A29E",
  });
  text(document, svg, 1000, 315, "FieldClaw dashboard user", {
    size: 22, fill: "#FDBA74", weight: "700",
  });

  roughArrow(rc, svg, 1000, 345, 1000, 390, C.muted);
  text(document, svg, 1120, 380, "manages / coordinates", { size: 18, fill: C.muted, anchor: "start" });

  // Three foremen
  const fores = [
    { t: "Foreman", s: "Framing crew" },
    { t: "Foreman", s: "Electrical crew" },
    { t: "Foreman", s: "Drywall crew" },
  ];
  fores.forEach((f, i) => {
    const x = 280 + i * 520;
    roughBox(rc, svg, x, 400, 400, 120, {
      fill: i === 0 ? C.oxideSoft : C.white,
      stroke: i === 0 ? C.oxide : C.stone,
    });
    text(document, svg, x + 200, 450, f.t, { size: 28, weight: "700" });
    text(document, svg, x + 200, 485, f.s, { size: 20, fill: C.steel });
    roughArrow(rc, svg, x + 200, 525, x + 200, 570, C.muted);
  });

  // Workers row
  roughBox(rc, svg, 280, 580, 1440, 100, { fill: C.white, stroke: C.stone });
  text(document, svg, 1000, 625, "Journeymen · apprentices · laborers", {
    size: 28, weight: "700",
  });
  text(document, svg, 1000, 660, "often subcontractor crews coordinating with the GC superintendent", {
    size: 20, fill: C.steel,
  });

  // Side note
  roughBox(rc, svg, 80, 740, 1840, 180, { fill: C.yellow, stroke: C.muted, roughness: 2 });
  text(document, svg, 1000, 800, "Field questions escalate: Super → PM → Architect/Engineer", {
    size: 26, weight: "700",
  });
  text(document, svg, 1000, 845, "Formal design RFIs are not filed to material vendors", {
    size: 22, fill: C.steel,
  });
  text(document, svg, 1000, 885, "Dotted support: project engineer · safety officer · suppliers (procurement)", {
    size: 20, fill: C.muted,
  });

  return svg;
}

/* ─── 02. Broken information flow (from DIRECTION_V2) ─── */
function diagramBroken() {
  const W = 2100, H = 1000;
  const { document, svg, rc } = makeSvg(W, H);

  const steps = [
    { t: "Worker", s: "“almost out of rebar”", fill: C.oxideSoft, stroke: C.oxide },
    { t: "Crew lead", s: "half a day left", fill: C.white, stroke: C.stone },
    { t: "Foreman", s: "Zone C · end of day", fill: C.white, stroke: C.stone },
    { t: "Super", s: "which PO? how much?", fill: C.white, stroke: C.stone },
    { t: "PM", s: "checks PO · calls supplier", fill: C.white, stroke: C.stone },
  ];
  const bw = 300, bh = 150, gap = 70;
  const total = steps.length * bw + (steps.length - 1) * gap;
  const x0 = (W - total) / 2;
  const y = 80;

  steps.forEach((st, i) => {
    const x = x0 + i * (bw + gap);
    roughBox(rc, svg, x, y, bw, bh, {
      fill: st.fill, stroke: st.stroke, strokeWidth: 2.4,
    });
    text(document, svg, x + bw / 2, y + 60, st.t, { size: 30, weight: "700" });
    text(document, svg, x + bw / 2, y + 100, st.s, { size: 20, fill: C.steel });
    if (i < steps.length - 1) {
      roughArrow(rc, svg, x + bw + 6, y + bh / 2, x + bw + gap - 6, y + bh / 2, C.muted);
      text(document, svg, x + bw + gap / 2, y + bh / 2 - 28, "+hrs", {
        size: 20, fill: C.oxide, weight: "700",
      });
    }
  });

  // Supplier branch from PM
  roughArrow(rc, svg, x0 + 4 * (bw + gap) + bw / 2, y + bh + 8, x0 + 4 * (bw + gap) + bw / 2, 320, C.muted);
  roughBox(rc, svg, x0 + 4 * (bw + gap) - 40, 330, bw + 80, 100, {
    fill: C.white, stroke: C.steel,
  });
  text(document, svg, x0 + 4 * (bw + gap) + bw / 2, 375, "Supplier", { size: 26, weight: "700" });
  text(document, svg, x0 + 4 * (bw + gap) + bw / 2, 408, "“delayed — Monday”", { size: 20, fill: C.steel });

  // Failure sticky
  roughBox(rc, svg, 280, 500, 1540, 160, {
    fill: C.redSoft, stroke: C.red, strokeWidth: 3,
  });
  text(document, svg, W / 2, 560, "Who tells the foreman? Does the schedule shift?", {
    size: 30, fill: C.red, weight: "700",
  });
  text(document, svg, W / 2, 610, "The field learns when the truck doesn’t show", {
    size: 24, fill: C.steel,
  });

  roughBox(rc, svg, 650, 720, 800, 110, {
    fill: C.stone, stroke: C.stone,
  });
  text(document, svg, W / 2, 770, "Total latency: 1–2 days", {
    size: 34, fill: C.cream, weight: "700",
  });
  text(document, svg, W / 2, 805, "illustrative site relay — not a cited study figure", {
    size: 18, fill: "#A8A29E",
  });

  return svg;
}

/* ─── 03. Closed loop ─── */
function diagramLoop() {
  const W = 2000, H = 900;
  const { document, svg, rc } = makeSvg(W, H);

  roughBox(rc, svg, 280, 50, 1440, 90, { fill: C.yellow, stroke: C.muted, roughness: 2 });
  text(document, svg, W / 2, 95, "“Rebar short, Zone C” → PO-9905 ETA Thursday → reply on his phone", {
    size: 24, fill: C.stone,
  });
  text(document, svg, W / 2, 125, "human decision stays in the loop", {
    size: 18, fill: C.oxide, weight: "700",
  });

  const nodes = [
    { t: "Foreman", s: "voice + photo", fill: C.oxideSoft, stroke: C.oxide },
    { t: "FieldClaw", s: "structure + triage", fill: C.stone, stroke: C.stone, dark: true },
    { t: "Superintendent", s: "ops picture", fill: C.white, stroke: C.stone },
    { t: "Decision", s: "reply to crew", fill: C.greenSoft, stroke: C.green },
  ];
  const bw = 340, bh = 160, gap = 90;
  const total = nodes.length * bw + (nodes.length - 1) * gap;
  const x0 = (W - total) / 2;
  const y = 220;

  nodes.forEach((n, i) => {
    const x = x0 + i * (bw + gap);
    roughBox(rc, svg, x, y, bw, bh, {
      stroke: n.stroke, fill: n.fill, strokeWidth: 2.8,
    });
    text(document, svg, x + bw / 2, y + 70, n.t, {
      size: 30, weight: "700", fill: n.dark ? C.cream : C.stone,
    });
    text(document, svg, x + bw / 2, y + 110, n.s, {
      size: 22, fill: n.dark ? "#A8A29E" : C.steel,
    });
    if (i < nodes.length - 1) {
      roughArrow(rc, svg, x + bw + 8, y + bh / 2, x + bw + gap - 8, y + bh / 2, C.oxide);
    }
  });

  roughCurve(
    rc, svg,
    [
      [x0 + total - bw / 2, y + bh + 10],
      [x0 + total - bw / 2, y + 220],
      [W / 2, y + 260],
      [x0 + bw / 2, y + 220],
      [x0 + bw / 2, y + bh + 10],
    ],
    C.green
  );
  text(document, svg, W / 2, y + 310, "answer returns to the person who asked", {
    size: 26, fill: C.green, weight: "700",
  });

  return svg;
}

/* ─── 04. How it moves with FieldClaw (DIRECTION_V2) ─── */
function diagramHow() {
  const W = 2100, H = 920;
  const { document, svg, rc } = makeSvg(W, H);

  // Vertical story matching DIRECTION_V2 "How It Moves With BuildSync"
  const steps = [
    {
      t: "1 · Capture",
      s: ['Foreman Telegram voice: "Rebar running low at Zone C, got maybe half a day"'],
      fill: C.oxideSoft, stroke: C.oxide,
    },
    {
      t: "2 · Structure",
      s: ["FieldClaw transcribes → extracts: shortage · rebar · Zone C · high urgency"],
      fill: C.white, stroke: C.stone,
    },
    {
      t: "3 · Context",
      s: ["Cross-references PO → 200 bundles on order from Acme Steel · ETA Thursday"],
      fill: C.white, stroke: C.stone,
    },
    {
      t: "4 · Ops picture",
      s: ['Gantt "Structural Framing — Zone C" → at-risk · Super dashboard: alert + impact'],
      fill: C.greenSoft, stroke: C.green,
    },
    {
      t: "5 · Answer back",
      s: ['Telegram to foreman: "Logged. PO #9905 on file. ETA Thursday." · Crew unblocked'],
      fill: C.greenSoft, stroke: C.green,
    },
  ];

  const bw = 1780, bh = 105, gap = 18;
  const x0 = (W - bw) / 2;
  let y = 55;

  steps.forEach((st, i) => {
    roughBox(rc, svg, x0, y, bw, bh, {
      fill: st.fill, stroke: st.stroke, strokeWidth: 2.8,
    });
    text(document, svg, x0 + 36, y + 42, st.t, {
      size: 28, weight: "700", fill: C.stone, anchor: "start",
    });
    text(document, svg, x0 + 36, y + 78, st.s[0], {
      size: 24, fill: C.steel, anchor: "start",
    });
    if (i < steps.length - 1) {
      roughArrow(rc, svg, W / 2, y + bh + 2, W / 2, y + bh + gap - 2, C.oxide);
    }
    y += bh + gap;
  });

  // Latency banner — illustrative, matches V2 contrast to broken path
  roughBox(rc, svg, x0, y + 8, bw, 95, { fill: C.stone, stroke: C.stone });
  text(document, svg, W / 2, y + 48, "Same hierarchy. Shorter path. One shared picture.", {
    size: 32, fill: C.cream, weight: "700",
  });
  text(document, svg, W / 2, y + 82, "The person who reported the shortage gets the ETA — before work stalls.", {
    size: 24, fill: "#A8A29E",
  });

  return svg;
}

/* ─── 05. Architecture ─── */
function diagramArch() {
  const W = 2100, H = 880;
  const { document, svg, rc } = makeSvg(W, H);

  text(document, svg, W / 2, 48, "field-ops path · read-side PO context · no buy-side agent", {
    size: 32, fill: C.steel,
  });

  const stages = [
    { t: "Capture", s: ["Telegram", "voice + photo"], fill: C.oxideSoft, stroke: C.oxide },
    { t: "Gateway", s: ["project", "session route"], fill: C.white, stroke: C.stone },
    { t: "Skills", s: ["transcribe", "log · RFI draft"], fill: C.white, stroke: C.stone },
    { t: "Tools", s: ["progress", "shortage notify"], fill: C.white, stroke: C.stone },
    { t: "Dashboard", s: ["Gantt · feed", "alerts · SSE"], fill: C.stone, stroke: C.stone, dark: true },
    { t: "Human gate", s: ["super / PM", "reply to crew"], fill: C.greenSoft, stroke: C.green },
  ];
  const bw = 290, bh = 250, gap = 35;
  const total = stages.length * bw + (stages.length - 1) * gap;
  const x0 = (W - total) / 2;
  const y = 90;

  stages.forEach((st, i) => {
    const x = x0 + i * (bw + gap);
    roughBox(rc, svg, x, y, bw, bh, {
      stroke: st.stroke, fill: st.fill, strokeWidth: 3,
    });
    text(document, svg, x + bw / 2, y + 65, st.t, {
      size: 36, weight: "700", fill: st.dark ? C.cream : C.stone,
    });
    multilines(document, svg, x + bw / 2, y + 125, st.s, {
      size: 26, fill: st.dark ? "#A8A29E" : C.steel, gap: 38,
    });
    if (i < stages.length - 1) {
      roughArrow(rc, svg, x + bw + 4, y + bh / 2, x + bw + gap - 4, y + bh / 2, C.oxide);
    }
  });

  const memX = x0 + 2 * (bw + gap);
  roughBox(rc, svg, memX, y + bh + 70, bw * 2 + gap, 160, {
    stroke: C.muted, fill: C.white, roughness: 2,
  });
  text(document, svg, memX + (bw * 2 + gap) / 2, y + bh + 130, "Memory", {
    size: 34, weight: "700",
  });
  text(document, svg, memX + (bw * 2 + gap) / 2, y + bh + 185, "site context · project context", {
    size: 28, fill: C.steel,
  });
  svg.appendChild(
    rc.line(memX + (bw * 2 + gap) / 2, y + bh + 70, memX + (bw * 2 + gap) / 2, y + bh + 8, {
      roughness: 1.5, stroke: C.muted, strokeWidth: 2.5, strokeLineDash: [8, 8],
    })
  );

  const mx = x0 + 4 * (bw + gap) - 20;
  roughBox(rc, svg, mx, y + bh + 70, bw * 2 + gap + 40, 320, {
    stroke: C.stone, fill: C.stone,
  });
  text(document, svg, mx + (bw * 2 + gap + 40) / 2, y + bh + 130, "Model slots", {
    size: 34, weight: "700", fill: C.cream,
  });
  ["Whisper STT", "Tool-calling LLM", "VLM on photos", "RAG drawings / specs"].forEach((s, i) => {
    text(document, svg, mx + 50, y + bh + 190 + i * 45, "•  " + s, {
      size: 28, fill: "#FDBA74", anchor: "start",
    });
  });

  return svg;
}

function writeExcalidrawStubs() {
  fs.mkdirSync(DIAGRAMS, { recursive: true });
  const empty = {
    type: "excalidraw",
    version: 2,
    source: "fieldclaw-deck",
    elements: [],
    appState: { viewBackgroundColor: "#FFFCF7" },
    files: {},
  };
  ["01-hierarchy", "02-broken-latency", "03-closed-loop", "04-how-it-works", "05-architecture"].forEach((n) => {
    fs.writeFileSync(path.join(DIAGRAMS, `${n}.excalidraw`), JSON.stringify(empty, null, 2));
  });
}

async function main() {
  fs.mkdirSync(ASSETS, { recursive: true });
  await writePng("01-hierarchy", diagramHierarchy(), 2400);
  await writePng("02-broken-latency", diagramBroken(), 2400);
  await writePng("03-closed-loop", diagramLoop(), 2400);
  await writePng("04-how-it-works", diagramHow(), 2400);
  await writePng("05-architecture", diagramArch(), 2400);
  writeExcalidrawStubs();
  console.log("diagrams ready");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
