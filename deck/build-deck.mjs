#!/usr/bin/env node
/**
 * FieldClaw — Kaya AI Hackathon 2026 Stage 1 (FINAL)
 * Formwork · rough.js diagrams · McKinsey-led problem · DIRECTION_V2 flows
 */
import pptxgen from "pptxgenjs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const A = path.join(__dirname, "assets");

const C = {
  stone: "1C1917",
  paper: "FBFAF7",
  steel: "57534E",
  line: "D6D3D1",
  oxide: "C2410C",
  green: "3F6212",
  amber: "B45309",
  cream: "FAFAF9",
  muted: "A8A29E",
  white: "FFFFFF",
};

const H = "IBM Plex Sans";
const B = "IBM Plex Sans";

function leftRail(slide, pres, color = C.oxide) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.14, h: 5.625,
    fill: { color }, line: { color },
  });
}

function sectionLabel(slide, text, y = 0.32) {
  slide.addText(text, {
    x: 0.55, y, w: 8.8, h: 0.28,
    fontSize: 12, fontFace: B, color: C.oxide, bold: true,
    charSpacing: 2.5, margin: 0,
  });
}

function title(slide, text, y = 0.58, opts = {}) {
  slide.addText(text, {
    x: 0.55, y, w: opts.w || 9.1, h: opts.h || 0.65,
    fontSize: opts.size || 24, fontFace: H, color: C.stone, bold: true, margin: 0,
    valign: "top",
  });
}

function body(slide, text, y, opts = {}) {
  slide.addText(text, {
    x: 0.55, y, w: opts.w || 8.9, h: opts.h || 0.5,
    fontSize: opts.size || 15, fontFace: B, color: opts.color || C.steel,
    margin: 0, ...opts.extra,
  });
}

function diagramImage(slide, file, opts = {}) {
  const maxX = opts.x ?? 0.3;
  const maxY = opts.y ?? 1.15;
  const maxW = opts.w ?? 9.4;
  const maxH = opts.h ?? 4.3;
  const aspect = opts.aspect ?? 2000 / 1000;
  let w = maxW;
  let h = w / aspect;
  if (h > maxH) {
    h = maxH;
    w = h * aspect;
  }
  const x = maxX + (maxW - w) / 2;
  const y = maxY + (maxH - h) / 2;
  slide.addImage({ path: file, x, y, w, h });
}

async function build() {
  const pres = new pptxgen();
  pres.defineLayout({ name: "LAYOUT_16x9", width: 10, height: 5.625 });
  pres.layout = "LAYOUT_16x9";
  pres.author = "FieldClaw";
  pres.title = "FieldClaw — Field Intelligence Layer";
  pres.subject = "Kaya AI Hackathon 2026 · Open Innovation · Stage 1";

  // ═══════════════════════════════════════════════════════════
  // 1 · COVER
  // ═══════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    s.background = { color: C.stone };
    leftRail(s, pres);

    s.addText("FIELDCLAW", {
      x: 0.7, y: 1.35, w: 8.5, h: 0.7,
      fontSize: 46, fontFace: H, color: C.cream, bold: true, margin: 0,
    });
    s.addText("Field intelligence layer for construction execution", {
      x: 0.7, y: 2.2, w: 8.5, h: 0.45,
      fontSize: 20, fontFace: B, color: C.muted, margin: 0,
    });

    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.7, y: 2.9, w: 1.2, h: 0.04, fill: { color: C.oxide },
    });

    s.addText("Rishi Divyakirti  ·  Harshit Tomar", {
      x: 0.7, y: 3.25, w: 8.5, h: 0.3,
      fontSize: 15, fontFace: B, color: C.cream, margin: 0,
    });
    s.addText("IIT Kanpur  ·  4th Year Undergraduate", {
      x: 0.7, y: 3.6, w: 8.5, h: 0.28,
      fontSize: 13, fontFace: B, color: C.muted, margin: 0,
    });
    s.addText("Kaya AI Hackathon 2026  ·  Open Innovation  ·  Stage 1", {
      x: 0.7, y: 4.9, w: 8.5, h: 0.28,
      fontSize: 12, fontFace: B, color: C.steel, margin: 0,
    });
  }

  // ═══════════════════════════════════════════════════════════
  // 2 · PROBLEM — McKinsey leads
  // ═══════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    s.background = { color: C.paper };
    leftRail(s, pres);
    sectionLabel(s, "PROBLEM");
    title(s, "Different versions of the truth on the same site", 0.52, {
      size: 24, h: 0.55,
    });
    body(s,
      "McKinsey: the area supervisor, project manager, planner, and owner often disagree on what is going on because they do not get the right information in time — or the same information.",
      1.12, { h: 0.62, size: 15 }
    );

    const mckUrl =
      "https://www.mckinsey.com/capabilities/operations/our-insights/the-construction-productivity-imperative";
    s.addImage({
      path: path.join(A, "mckinsey-favicon.png"),
      x: 0.55, y: 1.78, w: 0.22, h: 0.22,
      hyperlink: { url: mckUrl, tooltip: "McKinsey — The construction productivity imperative" },
    });
    s.addText(
      [
        {
          text: "mckinsey.com — The construction productivity imperative (2015)",
          options: {
            hyperlink: { url: mckUrl, tooltip: mckUrl },
            color: C.steel,
            underline: true,
          },
        },
      ],
      {
        x: 0.84, y: 1.78, w: 8.5, h: 0.24,
        fontSize: 11, fontFace: B, margin: 0, valign: "middle",
      }
    );

    const stats = [
      {
        n: "98%",
        l: "of megaprojects overrun cost by more than 30% — when the site picture is late or split",
        src: "McKinsey, 2015",
        url: mckUrl,
      },
      {
        n: "Relay",
        l: "Field asks → phone chain → lost record. Crew learns when work already stalled.",
        src: "Mechanism — next slide",
        url: null,
      },
      {
        n: "48%",
        l: "of U.S. rework from poor project data and miscommunication ($31.3B)",
        src: "PlanGrid + FMI, 2018",
        url: "https://www.autodesk.com/blogs/construction/construction-disconnected-fmi-report/",
      },
    ];
    stats.forEach((st, i) => {
      const x = 0.55 + i * 3.1;
      s.addShape(pres.shapes.RECTANGLE, {
        x, y: 2.15, w: 2.95, h: 2.65,
        fill: { color: C.white }, line: { color: C.line, width: 1 },
      });
      s.addShape(pres.shapes.RECTANGLE, {
        x, y: 2.15, w: 2.95, h: 0.08, fill: { color: C.oxide },
      });
      s.addText(st.n, {
        x: x + 0.2, y: 2.38, w: 2.55, h: 0.55,
        fontSize: st.n.length > 3 ? 28 : 34, fontFace: H, color: C.oxide, bold: true, margin: 0,
      });
      s.addText(st.l, {
        x: x + 0.2, y: 3.1, w: 2.55, h: 1.1,
        fontSize: 13, fontFace: B, color: C.stone, margin: 0,
      });
      if (st.url) {
        s.addText(
          [{ text: st.src, options: { hyperlink: { url: st.url }, color: C.muted, underline: true } }],
          {
            x: x + 0.2, y: 4.4, w: 2.55, h: 0.28,
            fontSize: 11, fontFace: B, margin: 0,
          }
        );
      } else {
        s.addText(st.src, {
          x: x + 0.2, y: 4.4, w: 2.55, h: 0.28,
          fontSize: 11, fontFace: B, color: C.muted, margin: 0,
        });
      }
    });
    s.addNotes(
      "McKinsey (Changali, Mohammad, van Nieuwland), The construction productivity imperative, July 2015: https://www.mckinsey.com/capabilities/operations/our-insights/the-construction-productivity-imperative\nLocal PDF: research/mckinsey-productivity/The_construction_productivity_imperative.pdf\nPlanGrid+FMI 2018: https://www.autodesk.com/blogs/construction/construction-disconnected-fmi-report/"
    );
  }

  // ═══════════════════════════════════════════════════════════
  // 3 · HIERARCHY
  // ═══════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    s.background = { color: C.paper };
    leftRail(s, pres);
    sectionLabel(s, "WHO");
    title(s, "The site hierarchy FieldClaw plugs into");
    diagramImage(s, path.join(A, "01-hierarchy.png"), { aspect: 2000 / 1000 });
  }

  // ═══════════════════════════════════════════════════════════
  // 4 · BROKEN FLOW
  // ═══════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    s.background = { color: C.paper };
    leftRail(s, pres);
    sectionLabel(s, "PROBLEM");
    title(s, "How information moves today");
    diagramImage(s, path.join(A, "02-broken-latency.png"), { aspect: 2100 / 1000 });
  }

  // ═══════════════════════════════════════════════════════════
  // 5 · SOLUTION — lead into product flow (DIRECTION_V2)
  // ═══════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    s.background = { color: C.paper };
    leftRail(s, pres);
    sectionLabel(s, "SOLUTION");
    title(s, "Skip the relay. Keep the decision human.", 0.55, {
      size: 26, h: 0.6,
    });

    s.addText(
      [
        {
          text: "A phone call still fails when the foreman lacks the PO, the drawing, or the authority. The record dies when someone hangs up. The crew learns the answer when work has already stalled.",
          options: { breakLine: true },
        },
        { text: "", options: { breakLine: true } },
        {
          text: "FieldClaw replaces that relay. Foremen report by voice from the site. The report is structured, matched to read-side PO context, and landed in one ops picture for the superintendent. Judgment stays with the super — the lost record and the phone chain do not.",
          options: { breakLine: true },
        },
        { text: "", options: { breakLine: true } },
        {
          text: "Voice → structure → schedule flag → human decision → answer back to the field. Next: how that path runs.",
        },
      ],
      {
        x: 0.7, y: 1.5, w: 8.6, h: 3.6,
        fontSize: 17, fontFace: B, color: C.steel, margin: 0, valign: "top",
        paraSpaceAfter: 12,
      }
    );
  }

  // ═══════════════════════════════════════════════════════════
  // 6 · PRODUCT — how info moves (DIRECTION_V2)
  // ═══════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    s.background = { color: C.paper };
    leftRail(s, pres);
    sectionLabel(s, "PRODUCT");
    title(s, "How information moves with FieldClaw", 0.52, { size: 22, h: 0.42 });
    diagramImage(s, path.join(A, "04-how-it-works.png"), {
      aspect: 2100 / 920, x: 0.1, y: 0.92, w: 9.8, h: 4.6,
    });
  }

  // ═══════════════════════════════════════════════════════════
  // 7 · USE CASES — on-ground realities (DIRECTION_V2)
  // ═══════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    s.background = { color: C.paper };
    leftRail(s, pres);
    sectionLabel(s, "USE CASES");
    title(s, "On-ground realities FieldClaw handles", 0.52, {
      size: 22, h: 0.4,
    });
    body(s, "What foremen and crew report that tools today still miss.", 0.95, {
      h: 0.28, size: 13,
    });

    const cases = [
      { t: "Daily progress", b: "Zone updates → Gantt shift · ahead/behind flags" },
      { t: "Material shortages", b: "Voice shortage → PO match or super flag" },
      { t: "Quality issues", b: "Observation + location · rework → schedule impact" },
      { t: "Safety / near misses", b: "Severity tag · compliance record · notify if critical" },
      { t: "Weather & site", b: "Outdoor delay · re-sequence · claims log" },
      { t: "Equipment down", b: "Cascade blocked tasks · impact for the super" },
      { t: "Trade conflicts", b: "Clash logged · both crews see it · re-sequence" },
      { t: "Inspections", b: "Sign-off unlocks next phase · PM notified" },
      { t: "Field questions", b: "Voice → super / PM path · answer logged on task" },
      { t: "Crew & labor", b: "Understaffed flag · resource gap on the schedule" },
    ];

    cases.forEach((c, i) => {
      const col = i % 5;
      const row = Math.floor(i / 5);
      const x = 0.45 + col * 1.88;
      const y = 1.4 + row * 1.9;
      s.addShape(pres.shapes.RECTANGLE, {
        x, y, w: 1.78, h: 1.7,
        fill: { color: C.white }, line: { color: C.line, width: 1 },
      });
      s.addShape(pres.shapes.RECTANGLE, {
        x, y, w: 1.78, h: 0.07, fill: { color: C.oxide },
      });
      s.addText(c.t, {
        x: x + 0.1, y: y + 0.25, w: 1.58, h: 0.55,
        fontSize: 13, fontFace: H, color: C.stone, bold: true, margin: 0, valign: "top",
      });
      s.addText(c.b, {
        x: x + 0.1, y: y + 0.85, w: 1.58, h: 0.7,
        fontSize: 12, fontFace: B, color: C.steel, margin: 0, valign: "top",
      });
    });
  }

  // ═══════════════════════════════════════════════════════════
  // 8 · ARCHITECTURE (HOW) — before WITH KAYA
  // ═══════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    s.background = { color: C.paper };
    leftRail(s, pres);
    sectionLabel(s, "HOW");
    title(s, "Proposed architecture, Stage 1", 0.52, { size: 22, h: 0.42 });
    diagramImage(s, path.join(A, "05-architecture.png"), {
      aspect: 2100 / 880, x: 0.1, y: 0.92, w: 9.8, h: 4.6,
    });
  }

  // ═══════════════════════════════════════════════════════════
  // 9 · WITH KAYA
  // ═══════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    s.background = { color: C.paper };
    leftRail(s, pres);
    sectionLabel(s, "WITH KAYA");
    title(s, "Kaya covers the PO. FieldClaw covers the site.");

    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.55, y: 1.35, w: 4.35, h: 3.5,
      fill: { color: C.white }, line: { color: C.line, width: 1 },
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.55, y: 1.35, w: 4.35, h: 0.08, fill: { color: C.steel },
    });
    s.addText("KAYA", {
      x: 0.85, y: 1.7, w: 3.8, h: 0.3,
      fontSize: 13, fontFace: B, color: C.steel, bold: true, charSpacing: 2, margin: 0,
    });
    s.addText("What was ordered", {
      x: 0.85, y: 2.15, w: 3.8, h: 0.45,
      fontSize: 22, fontFace: H, color: C.stone, bold: true, margin: 0,
    });
    s.addText(
      "Procurement and supply-chain intelligence.\nOffice to suppliers.\nPOs, lead times, vendor workflows.",
      {
        x: 0.85, y: 2.85, w: 3.8, h: 1.5,
        fontSize: 15, fontFace: B, color: C.steel, margin: 0,
      }
    );

    s.addShape(pres.shapes.RECTANGLE, {
      x: 5.1, y: 1.35, w: 4.35, h: 3.5,
      fill: { color: C.stone },
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x: 5.1, y: 1.35, w: 4.35, h: 0.08, fill: { color: C.oxide },
    });
    s.addText("FIELDCLAW", {
      x: 5.4, y: 1.7, w: 3.8, h: 0.3,
      fontSize: 13, fontFace: B, color: C.oxide, bold: true, charSpacing: 2, margin: 0,
    });
    s.addText("What is happening", {
      x: 5.4, y: 2.15, w: 3.8, h: 0.45,
      fontSize: 22, fontFace: H, color: C.cream, bold: true, margin: 0,
    });
    s.addText(
      "Execution-layer field intelligence.\nField to superintendent to field.\nVoice, photos, ops picture, answers back.",
      {
        x: 5.4, y: 2.85, w: 3.8, h: 1.5,
        fontSize: 15, fontFace: B, color: C.muted, margin: 0,
      }
    );
  }

  // ═══════════════════════════════════════════════════════════
  // 10 · CLOSE
  // ═══════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    s.background = { color: C.stone };
    leftRail(s, pres);

    s.addText("Thank you :)", {
      x: 0.7, y: 2.0, w: 8.5, h: 0.7,
      fontSize: 42, fontFace: H, color: C.cream, bold: true, margin: 0,
    });
    s.addText("Excited to build.", {
      x: 0.7, y: 2.85, w: 8.5, h: 0.45,
      fontSize: 22, fontFace: B, color: C.muted, margin: 0,
    });
  }

  const out = path.join(__dirname, "FieldClaw_Pitch_Deck.pptx");
  await pres.writeFile({ fileName: out });
  console.log("wrote", out);
}

build().catch((e) => {
  console.error(e);
  process.exit(1);
});
