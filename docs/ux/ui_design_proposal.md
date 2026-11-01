# Coach Porygon VGC — UI Design & Frontend Architecture Proposal

**Document Version:** 1.0  
**Author:** Expert UX Designer  
**Audience:** Frontend Developer, Product Owner, Stakeholders  
**Status:** Approved for Implementation

---

## 1. Aesthetic Vision: "Porygon Poly-Grid Cyberpunk"
To achieve viral clout on GitHub and stand out as the most visually captivating VGC coaching tool in existence, the visual design merges competitive esports clarity with Porygon's iconic polyhedral digital identity:
- **Canvas:** Ultra-deep void navy (`#090d16`).
- **Primary Energy:** Neon Electric Cyan (`#38bdf8`) with soft drop-glow filters.
- **Secondary Accent:** Digital Polygon Magenta (`#ec4899`) representing Mega Evolution and high-stakes turning points.
- **Surface Elevation:** Translucent dark obsidian glass (`rgba(17, 24, 39, 0.85)`) with 12px blur backdrop and 1px radial gradient borders.
- **Typography:** JetBrains Mono / SFMono for damage rolls, speed tiers, and stat points; Inter / Segoe UI for clean tactical debriefs.

---

## 2. Design Tokens Architecture (CSS Custom Properties)

```css
:root {
  /* Color Palette */
  --bg-primary: #090d16;
  --bg-surface: rgba(17, 24, 39, 0.88);
  --bg-surface-elevated: rgba(30, 41, 59, 0.92);
  --border-glow: rgba(56, 189, 248, 0.25);
  --border-subtle: rgba(255, 255, 255, 0.08);

  /* Accents */
  --accent-cyan: #38bdf8;
  --accent-magenta: #ec4899;
  --accent-gold: #facc15;
  --accent-emerald: #22c55e;
  --accent-ruby: #ef4444;

  /* Typography */
  --font-sans: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;

  /* Animations & Micro-interactions */
  --ease-elastic: cubic-bezier(0.175, 0.885, 0.32, 1.275);
  --ease-smooth: cubic-bezier(0.4, 0, 0.2, 1);
  --duration-fast: 150ms;
  --duration-normal: 300ms;
}
```

---

## 3. High-Clout Micro-Interactions & Visual Effects
1. **Interactive Damage Roll Visualizer:**
   - Visual segmented HP bars highlighting guaranteed OHKO, 2HKO, and roll ranges with color gradients (Emerald -> Gold -> Ruby).
2. **Speed Tier Interactive Matrix:**
   - Active Tailwind / Weather / Mega switches instantly re-sort speed cards in real-time with smooth CSS layout transitions.
3. **Flashcards 45-Second Countdown Gauge:**
   - Circular SVG stroke-dasharray animation counting down from 45.0s to 0.0s with pulse warning under 10 seconds.
4. **Live Bilingual Switcher:**
   - Instant 1-click toggle between **English** and **Español Latinoamericano** with zero page reload.
5. **Accessibility & Reduced Motion:**
   - Full support for `@media (prefers-reduced-motion: reduce)`.
   - Distinct `:focus-visible` keyboard rings with 2px neon cyan offset.
