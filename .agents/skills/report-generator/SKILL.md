---
name: report-generator
description: >-
  Generates publication-quality, esports-styled HTML and headless Chrome/Edge PDF visual reports
  for tournament intelligence, team rosters, match breakdowns, and Swiss scouting dossiers.
---

# Visual Report Generation & Esports Infographic Design System

Autonomous publication engine providing standardized guidelines, CSS design tokens, HTML component blueprints, and headless Chrome/Edge PDF compilation for Coach Porygon VGC.

---

## 1. Core Architectural Mandates (AI-First Generation)

1. **AI-First Visual Composition (No Rigid Python HTML Builders):**
   - The AI Agent acts directly as the **Lead Esports Graphic Designer & Data Analyst**.
   - Python code must NEVER attempt to hardcode complex visual layouts, multi-line string templates, or infographic markup. Python is strictly limited to data computation (`engine/munchstats_analyzer.py`, `engine/turn_simulator.py`) and compilation utilities (`export_pdf`).
   - The AI Agent directly generates the modern, self-contained HTML/CSS tailored dynamically to the specific tournament, opponent roster, or team audit.
2. **Self-Contained Single-File Portability:**
   - Every generated HTML report must be 100% self-contained.
   - **Zero External CDNs or Web Fonts:** Never link to external Google Fonts, unpkg, cdnjs, or Tailwind CDN scripts. Use robust system font stacks (`ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`).
   - **Zero Remote Image URLs:** All Pokémon sprites, item thumbnails, and icons must be inlined as Base64 data URIs (`data:image/png;base64,...`) sourced directly from [`assets/sprites/Reg_M-C/`](../../../assets/sprites/Reg_M-C/), [`assets/items/`](../../../assets/items/), and [`assets/icons/`](../../../assets/icons/).
3. **Dual-Presentation Modes:**
   - **Esports Infographic Mode (Primary / Digital):** High-impact competitive analytics layout for VGC esports. High information density, midnight-dark canvas, neon cyan/mint victory accents, coral/red alarms, trophy gold callouts, and modular card columns.
   - **Executive Multi-Page Dossier Mode (Print / A4):** Clean, crisp, high-contrast pages with structured chapter numbering (`01`, `02`, `03`), roadmap arrows, and strict `@page` pagination for physical tournament preparation.
4. **Deterministic File Locations & Exclusive Artifact Lock:**
   - Save all generated reports under `reports/` (or tournament-specific directories `data/munchstats/output/{slug}/`) on disk.
   - **Exclusive Artifact Lock:** NEVER copy report outputs (`.html`, `.pdf`) or create markdown showcase artifacts in the Antigravity Brain artifact directory (`<appDataDir>/brain/<conversation-id>/`) without explicit Trainer permission. Only `assets/command_center.html` is authorized for automatic artifact synchronization.

---

## 2. Design Tokens & Aesthetic Palettes

### 🎮 Preset A: Midnight Cyber Esports Infographic (Primary)
```css
:root {
  --bg-primary: #0b0e14;        /* Deep Midnight Esports Canvas */
  --bg-card: #131823;           /* Dark Slate Card Surface */
  --bg-card-subtle: #0d121c;    /* Nested Secondary Surface */
  --border-card: #1f293d;       /* Crisp Modular Divider */
  --border-highlight: #2d3b59;  /* Focused Component Border */
  
  --text-main: #ffffff;         /* High-Contrast Crisp White */
  --text-muted: #94a3b8;        /* Slate Secondary Metadata */
  --text-dim: #64748b;          /* Faint Axis & Micro-copy */
  
  --accent-mint: #00f5a0;       /* Primary Win / High-Conversion Neon */
  --accent-cyan: #00e5ff;       /* Pure Electric Telemetry Highlight */
  --accent-gold: #facc15;       /* Championship / Trophy / Rank #1 */
  --accent-coral: #ff4655;      /* Losses / Collapse Alarms / Low-Winrate */
  --accent-purple: #a855f7;     /* Psyspam & Regional Specialty */
  
  --bar-track: #1c2333;         /* Unfilled Progress Bar Background */
  --glow-mint: 0 0 16px rgba(0, 245, 160, 0.35);
  --glow-cyan: 0 0 16px rgba(0, 229, 255, 0.35);
  --card-shadow: 0 8px 32px rgba(0, 0, 0, 0.55);
}
```

### 📄 Preset B: Executive Multi-Page Editorial (Print-Ready)
```css
:root {
  --bg-primary: #f8fafc;
  --bg-card: #ffffff;
  --border-card: #e2e8f0;
  --text-main: #0f172a;
  --text-muted: #64748b;
  --accent-primary: #2563eb;    /* Deep Royal Blue */
  --accent-mint: #059669;       /* Forest Emerald */
  --accent-coral: #dc2626;      /* Crimson */
  --accent-gold: #d97706;       /* Amber Gold */
  --bar-track: #e2e8f0;
}
```

---

## 3. Core HTML/CSS Component Blueprints

### Component 1: Esports Hero Header
```html
<header class="esports-header">
  <div class="brand-left">
    <span class="partner-badge">COACH PORYGON × PLAY! POKÉMON</span>
    <h1 class="main-title">BALTIMORE REGIONAL INFOGRAPHIC</h1>
    <p class="subtitle">Regulation M-C • Masters Division • 428 Trainers</p>
  </div>
  <div class="brand-right">
    <div class="rank-trophy">
      <span class="trophy-icon">🏆</span>
      <div class="trophy-meta">
        <span class="trophy-label">CHAMPION</span>
        <span class="trophy-name">Charizard-Y Sun Offense</span>
      </div>
    </div>
  </div>
</header>
```

### Component 2: High-Density Metric Strip (KPIs)
```html
<div class="kpi-strip">
  <div class="kpi-card">
    <span class="kpi-label">TOTAL MASTERS</span>
    <span class="kpi-value text-cyan">428</span>
    <span class="kpi-sub">Day 1 Field</span>
  </div>
  <div class="kpi-card">
    <span class="kpi-label">DAY 2 CUT</span>
    <span class="kpi-value text-mint">64</span>
    <span class="kpi-sub">14.95% Cut Rate</span>
  </div>
  <div class="kpi-card">
    <span class="kpi-label">TOP CUT PODIUM</span>
    <span class="kpi-value text-gold">8</span>
    <span class="kpi-sub">Bo3 Single Elimination</span>
  </div>
  <div class="kpi-card">
    <span class="kpi-label">LETHAL CORE</span>
    <span class="kpi-value text-mint">83.3%</span>
    <span class="kpi-sub">Zard-Y + Salamence</span>
  </div>
</div>
```

### Component 3: Species Showcase with Element Avatar Ring
```html
<div class="species-row">
  <div class="species-avatar-container">
    <div class="avatar-ring ring-fire">
      <img src="data:image/png;base64,..." alt="Charizard-Mega-Y" class="sprite-avatar" />
    </div>
  </div>
  <div class="species-meta">
    <div class="species-name-row">
      <span class="species-name">Charizard-Mega-Y</span>
      <span class="badge-role">CHAMPION</span>
    </div>
    <div class="species-stats-row">
      <span>D1: <strong>112 (26.2%)</strong></span>
      <span>•</span>
      <span>D2: <strong>32 (50.0%)</strong></span>
      <span>•</span>
      <span>Top Cut: <strong class="text-mint">6 (75.0%)</strong></span>
    </div>
  </div>
  <div class="species-conversion">
    <span class="conv-pct text-mint">18.75%</span>
    <span class="conv-label">D2 → CUT</span>
  </div>
</div>
```

### Component 4: Stacked Winrate Tendency Bar
```html
<div class="tendency-bar-group">
  <div class="tendency-label-row">
    <span class="category-name">Sun Hyper Offense</span>
    <span class="tendency-stat text-mint">71.4% Winrate</span>
    <span class="placement-pill pill-gold">1st Place</span>
  </div>
  <div class="progress-track">
    <div class="progress-fill fill-mint" style="width: 71.4%;"></div>
  </div>
</div>
```

### Component 5: Swiss Rounds / Metagame Tenure Gantt Chart
```html
<div class="gantt-chart-container">
  <h3 class="card-title">Top Cut Archetype Evolution Across Rounds</h3>
  <div class="gantt-axis">
    <span>Swiss R1-4</span>
    <span>Swiss R5-7</span>
    <span>Swiss R8-9</span>
    <span>Top 8</span>
    <span>Finals</span>
  </div>
  <div class="gantt-row">
    <span class="gantt-label">Charizard Sun</span>
    <div class="gantt-track">
      <div class="gantt-bar bar-mint" style="left: 0%; width: 100%;">Champion</div>
    </div>
  </div>
  <div class="gantt-row">
    <span class="gantt-label">Rain Archaludon</span>
    <div class="gantt-track">
      <div class="gantt-bar bar-cyan" style="left: 0%; width: 80%;">Top 4</div>
    </div>
  </div>
  <div class="gantt-row">
    <span class="gantt-label">Psyspam Balance</span>
    <div class="gantt-track">
      <div class="gantt-bar bar-purple" style="left: 0%; width: 60%;">Top 8</div>
    </div>
  </div>
</div>
```

---

## 4. Headless Chrome/Edge PDF Compilation Protocol

To compile pixel-perfect, vector-sharp PDFs without ugly page breaks or header headers:

### 1. In CSS (`@page` and print media):
```css
@page {
  size: A4 portrait;
  margin: 10mm 10mm 12mm 10mm;
}

@media print {
  body {
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
  }
  .no-break {
    page-break-inside: avoid !important;
    break-inside: avoid !important;
  }
  .page-break {
    page-break-after: always !important;
    break-after: page !important;
  }
}
```

### 2. Execution via Python (`engine/pdf_exporter.py`):
```python
from engine.pdf_exporter import export_pdf

# 1. Compile full HTML string with embedded Base64 sprites
html_content = generate_my_report_html(data)

# 2. Export directly to PDF using installed Chrome/Edge
res = export_pdf(html_content, "reports/my_report.pdf", theme="porygon")
print(f"Generated PDF: {res['pdf_path']} ({res['size_bytes']} bytes)")
```

### 3. Direct Shell Command (if invoked manually):
```bash
chrome.exe --headless=new --disable-gpu --no-sandbox --no-pdf-header-footer --print-to-pdf="reports/output.pdf" "reports/output.html"
```

---

## 5. Agent Verification Checklist Before Delivery

- [ ] **Zero External Network Assets:** Confirmed zero `<link href="http...">` or `<script src="http...">` tags.
- [ ] **Zero Pokeball Leaks:** All sprites validated through `get_species_sprite()` (curated PNGs from `assets/sprites/Reg_M-C/`).
- [ ] **Dual Deliverable:** Both `.html` and `.pdf` files written to `reports/` or `data/munchstats/output/{slug}/`.
- [ ] **Exclusive Artifact Lock Enforced:** Verified report outputs remain strictly in `reports/` on disk and are NOT copied to the Antigravity Artifact directory without explicit Trainer permission.
- [ ] **WCAG Contrast Compliance:** All text readable against `#0B0E14` or `#131823` card backgrounds.
