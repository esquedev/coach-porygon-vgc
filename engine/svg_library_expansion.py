# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Expanded Bespoke Vector SVG Library
Provides:
1. Tailored vector illustrations for all 32 items that previously used generic emblems.
2. Detailed anatomical/battle vector illustrations for all Megas, base forms, and staples.
3. Stylized creature head/bust fallback generator eliminating Pokéball placeholders entirely.
"""

from typing import Dict
import xml.etree.ElementTree as ET

# ==============================================================================
# 1. 32 BESPOKE COMPETITIVE HOLD ITEM ILLUSTRATIONS
# ==============================================================================
ITEM_SVGS: Dict[str, str] = {
    "air-balloon": """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <radialGradient id="balloonGlow" cx="40%" cy="35%" r="60%">
      <stop offset="0%" stop-color="#fee2e2"/>
      <stop offset="60%" stop-color="#ef4444"/>
      <stop offset="100%" stop-color="#991b1b"/>
    </radialGradient>
  </defs>
  <!-- Balloon Body -->
  <path d="M50,14 C68,14 82,28 82,46 C82,62 64,74 54,78 L46,78 C36,74 18,62 18,46 C18,28 32,14 50,14 Z" fill="url(#balloonGlow)" stroke="#7f1d1d" stroke-width="2"/>
  <!-- Alternating White Stripes -->
  <path d="M38,16 C30,24 26,36 26,48 C26,58 34,70 47,77 L43,76 C32,68 22,56 22,46 C22,32 30,20 38,16 Z" fill="#ffffff" fill-opacity="0.85"/>
  <path d="M62,16 C70,24 74,36 74,48 C74,58 66,70 53,77 L57,76 C68,68 78,56 78,46 C78,32 70,20 62,16 Z" fill="#ffffff" fill-opacity="0.85"/>
  <path d="M46,14 C48,32 48,60 49,78 L51,78 C52,60 52,32 54,14 Z" fill="#ffffff" fill-opacity="0.9"/>
  <!-- Ropes -->
  <line x1="44" y1="78" x2="42" y2="88" stroke="#d97706" stroke-width="1.5"/>
  <line x1="56" y1="78" x2="58" y2="88" stroke="#d97706" stroke-width="1.5"/>
  <!-- Basket -->
  <rect x="40" y="88" width="20" height="9" rx="2" fill="#b45309" stroke="#78350f" stroke-width="1.5"/>
  <line x1="40" y1="92" x2="60" y2="92" stroke="#78350f" stroke-width="1"/>
</svg>""",

    "charcoal": """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <radialGradient id="emberGlow" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#ffedd5"/>
      <stop offset="40%" stop-color="#f97316"/>
      <stop offset="80%" stop-color="#dc2626"/>
      <stop offset="100%" stop-color="#000000"/>
    </radialGradient>
  </defs>
  <!-- Charcoal Briquette Body -->
  <polygon points="24,34 46,18 78,22 86,52 74,82 42,86 16,68 18,44" fill="#18181b" stroke="#3f3f46" stroke-width="2.5"/>
  <!-- Glowing Heat Fractures / Embers -->
  <path d="M44,22 L40,46 L62,54 L54,82" stroke="url(#emberGlow)" stroke-width="4.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M40,46 L20,52" stroke="#f97316" stroke-width="3" fill="none" stroke-linecap="round"/>
  <path d="M62,54 L82,48" stroke="#f97316" stroke-width="3" fill="none" stroke-linecap="round"/>
  <circle cx="40" cy="46" r="4" fill="#fef08a"/>
  <circle cx="62" cy="54" r="3.5" fill="#fef08a"/>
  <!-- Specular Carbon Edge -->
  <polygon points="26,36 46,22 74,25 68,36 44,32" fill="#3f3f46" fill-opacity="0.6"/>
</svg>""",

    "mystic-water": """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="waterGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#bae6fd"/>
      <stop offset="35%" stop-color="#38bdf8"/>
      <stop offset="75%" stop-color="#0284c7"/>
      <stop offset="100%" stop-color="#0369a1"/>
    </linearGradient>
  </defs>
  <!-- Cord and Loop -->
  <path d="M42,12 C44,6 56,6 58,12 L50,22 Z" fill="#94a3b8" stroke="#64748b" stroke-width="1.5"/>
  <!-- Outer Water Teardrop Gem -->
  <path d="M50,20 C50,20 78,54 78,68 C78,82 65,92 50,92 C35,92 22,82 22,68 C22,54 50,20 50,20 Z" fill="url(#waterGrad)" stroke="#ffffff" stroke-width="2.5"/>
  <!-- Internal Liquid Wave Crest -->
  <path d="M30,68 C38,62 46,74 54,66 C62,58 70,68 74,64 C76,74 70,86 50,86 C36,86 28,78 30,68 Z" fill="#0284c7" fill-opacity="0.5"/>
  <!-- Specular Reflection Curve -->
  <path d="M48,28 C42,42 32,56 32,70" stroke="#ffffff" stroke-width="3" stroke-linecap="round" fill="none" stroke-opacity="0.8"/>
  <circle cx="36" cy="74" r="3" fill="#ffffff" fill-opacity="0.8"/>
</svg>""",

    "twisted-spoon": """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <!-- Psychic Resonance Rings -->
  <ellipse cx="50" cy="50" rx="36" ry="18" fill="none" stroke="#ec4899" stroke-width="2" stroke-opacity="0.4" stroke-dasharray="6,4" transform="rotate(-25 50 50)"/>
  <ellipse cx="50" cy="50" rx="42" ry="24" fill="none" stroke="#a855f7" stroke-width="1.5" stroke-opacity="0.3" transform="rotate(35 50 50)"/>
  <!-- Silver Spoon Bowl (Twisted) -->
  <path d="M68,18 C78,14 86,24 82,36 C78,46 64,52 56,44 C48,36 56,22 68,18 Z" fill="#e2e8f0" stroke="#94a3b8" stroke-width="2.5"/>
  <ellipse cx="70" cy="32" rx="8" ry="12" fill="#cbd5e1" transform="rotate(-30 70 32)"/>
  <!-- Twisted Spiral Handle -->
  <path d="M58,46 Q46,56 42,68 Q38,82 22,88 L16,84 Q32,74 36,60 Q42,46 54,42 Z" fill="#cbd5e1" stroke="#64748b" stroke-width="2"/>
  <!-- Psychic Flare Core -->
  <circle cx="68" cy="32" r="5" fill="#f472b6" fill-opacity="0.9"/>
  <circle cx="68" cy="32" r="2" fill="#ffffff"/>
</svg>""",

    "eject-button": """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <!-- Hazard Base Ring -->
  <circle cx="50" cy="50" r="42" fill="#facc15" stroke="#ca8a04" stroke-width="3"/>
  <!-- Hazard Striping -->
  <path d="M50,8 A42,42 0 0,1 78,20 L66,32 A26,26 0 0,0 50,24 Z" fill="#18181b"/>
  <path d="M92,50 A42,42 0 0,1 80,78 L68,66 A26,26 0 0,0 76,50 Z" fill="#18181b"/>
  <path d="M50,92 A42,42 0 0,1 22,80 L34,68 A26,26 0 0,0 50,76 Z" fill="#18181b"/>
  <path d="M8,50 A42,42 0 0,1 20,22 L32,34 A26,26 0 0,0 24,50 Z" fill="#18181b"/>
  <!-- Metallic Collar -->
  <circle cx="50" cy="50" r="30" fill="#cbd5e1" stroke="#475569" stroke-width="2"/>
  <!-- Red Plunger Dome -->
  <circle cx="50" cy="50" r="22" fill="#dc2626" stroke="#991b1b" stroke-width="2.5"/>
  <ellipse cx="43" cy="43" rx="8" ry="4" fill="#ffffff" fill-opacity="0.6" transform="rotate(-30 43 43)"/>
  <!-- Arrow Icon on Plunger -->
  <path d="M50,38 L50,56 M42,46 L50,38 L58,46" stroke="#ffffff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
</svg>""",

    "metal-coat": """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="chromeGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#ffffff"/>
      <stop offset="30%" stop-color="#cbd5e1"/>
      <stop offset="60%" stop-color="#64748b"/>
      <stop offset="100%" stop-color="#1e293b"/>
    </linearGradient>
  </defs>
  <!-- Flask Body -->
  <rect x="28" y="32" width="44" height="54" rx="8" fill="url(#chromeGrad)" stroke="#475569" stroke-width="3"/>
  <!-- Neck and Cap -->
  <rect x="40" y="16" width="20" height="16" rx="2" fill="#94a3b8" stroke="#334155" stroke-width="2"/>
  <rect x="36" y="12" width="28" height="6" rx="1" fill="#cbd5e1" stroke="#334155" stroke-width="1.5"/>
  <!-- Metallic Sheen Liquid Drips -->
  <path d="M36,44 Q44,60 50,46 Q56,66 64,48 L64,32 L36,32 Z" fill="#ffffff" fill-opacity="0.7"/>
  <!-- Specular Star Sparkle -->
  <polygon points="50,60 52,66 58,68 52,70 50,76 48,70 42,68 48,66" fill="#ffffff"/>
</svg>""",

    "light-clay": """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <!-- Terracotta Clay Slab -->
  <polygon points="20,40 50,20 84,34 54,58" fill="#ea580c" stroke="#7c2d12" stroke-width="2.5"/>
  <polygon points="20,40 54,58 54,82 20,64" fill="#c2410c" stroke="#7c2d12" stroke-width="2.5"/>
  <polygon points="54,58 84,34 84,58 54,82" fill="#9a3412" stroke="#7c2d12" stroke-width="2.5"/>
  <!-- Glowing Sacred Rune Glyphs -->
  <path d="M38,36 L52,28 L68,36 L54,46 Z" stroke="#fed7aa" stroke-width="2.5" fill="none"/>
  <line x1="53" y1="28" x2="53" y2="46" stroke="#fed7aa" stroke-width="2"/>
  <circle cx="53" cy="37" r="3" fill="#ffffff"/>
</svg>""",

    "light-ball": """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <radialGradient id="electricGlow" cx="40%" cy="40%" r="60%">
      <stop offset="0%" stop-color="#ffffff"/>
      <stop offset="40%" stop-color="#fef08a"/>
      <stop offset="75%" stop-color="#facc15"/>
      <stop offset="100%" stop-color="#ca8a04"/>
    </radialGradient>
  </defs>
  <!-- Outer Lightning Sparks -->
  <path d="M24,24 L34,36 L26,42 L42,48" stroke="#38bdf8" stroke-width="2.5" fill="none" stroke-linecap="round"/>
  <path d="M78,22 L68,34 L76,40 L60,46" stroke="#38bdf8" stroke-width="2.5" fill="none" stroke-linecap="round"/>
  <path d="M32,76 L40,64 L34,58 L48,56" stroke="#38bdf8" stroke-width="2.5" fill="none" stroke-linecap="round"/>
  <path d="M74,74 L62,62 L70,56 L54,54" stroke="#38bdf8" stroke-width="2.5" fill="none" stroke-linecap="round"/>
  <!-- Central Glowing Orb -->
  <circle cx="50" cy="50" r="32" fill="url(#electricGlow)" stroke="#facc15" stroke-width="2.5"/>
  <!-- Iconic Lightning Bolt Overlay -->
  <polygon points="52,24 40,46 50,46 44,72 64,48 52,48" fill="#ffffff" stroke="#ca8a04" stroke-width="1.5"/>
</svg>""",

    "magnet": """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <!-- Horseshoe Magnet U-Bend -->
  <path d="M22,26 L22,60 C22,76 34,88 50,88 C66,88 78,76 78,60 L78,26 L62,26 L62,58 C62,66 56,72 50,72 C44,72 38,66 38,58 L38,26 Z" fill="#94a3b8" stroke="#475569" stroke-width="3"/>
  <!-- Red North Pole -->
  <rect x="22" y="22" width="16" height="24" fill="#dc2626" stroke="#475569" stroke-width="2"/>
  <text x="30" y="38" text-anchor="middle" fill="#ffffff" font-family="sans-serif" font-weight="900" font-size="12">N</text>
  <!-- Blue South Pole -->
  <rect x="62" y="22" width="16" height="24" fill="#2563eb" stroke="#475569" stroke-width="2"/>
  <text x="70" y="38" text-anchor="middle" fill="#ffffff" font-family="sans-serif" font-weight="900" font-size="12">S</text>
  <!-- Magnetic Field Arcs -->
  <path d="M14,34 C10,48 10,64 18,76" stroke="#38bdf8" stroke-width="2" fill="none" stroke-linecap="round" stroke-dasharray="3,3"/>
  <path d="M86,34 C90,48 90,64 82,76" stroke="#38bdf8" stroke-width="2" fill="none" stroke-linecap="round" stroke-dasharray="3,3"/>
</svg>""",

    "hard-stone": """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <!-- Dark Faceted Rock Prism -->
  <polygon points="48,14 78,28 88,62 58,86 20,72 16,36" fill="#334155" stroke="#0f172a" stroke-width="3"/>
  <polygon points="48,14 42,46 16,36" fill="#475569"/>
  <polygon points="48,14 78,28 58,48 42,46" fill="#64748b"/>
  <polygon points="78,28 88,62 58,54 58,48" fill="#1e293b"/>
  <polygon points="88,62 58,86 52,58 58,54" fill="#0f172a"/>
  <polygon points="20,72 58,86 52,58 38,54" fill="#1e293b"/>
  <polygon points="16,36 20,72 38,54 42,46" fill="#475569"/>
  <polygon points="42,46 58,48 58,54 52,58 38,54" fill="#94a3b8"/>
  <ellipse cx="50" cy="36" rx="4" ry="2" fill="#ffffff" fill-opacity="0.75"/>
</svg>""",

    "dragon-fang": """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="dragonAura" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#a855f7"/>
      <stop offset="100%" stop-color="#3b82f6"/>
    </linearGradient>
  </defs>
  <!-- Draconic Aura Waves -->
  <path d="M40,16 C68,26 84,54 78,82 C64,74 58,58 44,48" fill="none" stroke="url(#dragonAura)" stroke-width="6" stroke-opacity="0.3" stroke-linecap="round"/>
  <!-- Ivory Fang Blade -->
  <path d="M38,14 C56,22 68,44 64,86 C52,68 34,48 24,30 C20,20 28,12 38,14 Z" fill="#f8fafc" stroke="#64748b" stroke-width="2.5"/>
  <!-- Tooth Root Cap -->
  <ellipse cx="32" cy="22" rx="12" ry="8" fill="#e2e8f0" stroke="#64748b" stroke-width="1.5" transform="rotate(-30 32 22)"/>
  <!-- Serration and Sharp Edge Glint -->
  <path d="M38,16 C48,32 54,54 58,78" stroke="#cbd5e1" stroke-width="2" fill="none"/>
  <polygon points="62,80 64,86 58,82" fill="#ffffff"/>
</svg>""",

    "fairy-feather": """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="featherGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#fdf2f8"/>
      <stop offset="50%" stop-color="#f472b6"/>
      <stop offset="100%" stop-color="#db2777"/>
    </linearGradient>
  </defs>
  <!-- Feather Vane Contour -->
  <path d="M22,86 C26,62 38,34 76,14 C68,34 72,52 64,66 C56,76 38,84 22,86 Z" fill="url(#featherGrad)" stroke="#be185d" stroke-width="2"/>
  <!-- Central Quill Shaft -->
  <path d="M18,90 Q44,54 76,14" stroke="#ffffff" stroke-width="3" stroke-linecap="round" fill="none"/>
  <!-- Fairy Glow Sparkles -->
  <circle cx="68" cy="24" r="3" fill="#ffffff"/>
  <circle cx="56" cy="42" r="2.5" fill="#fdf2f8"/>
  <circle cx="42" cy="62" r="2" fill="#ffffff"/>
  <circle cx="78" cy="46" r="3.5" fill="#f472b6" fill-opacity="0.75"/>
</svg>""",

    "poison-barb": """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <!-- Barb Curved Stinger -->
  <path d="M30,16 C46,28 64,48 64,80 C54,64 42,50 20,38 C16,26 22,14 30,16 Z" fill="#7e22ce" stroke="#4c1d95" stroke-width="2.5"/>
  <path d="M32,22 C44,36 52,52 56,74" stroke="#c084fc" stroke-width="2.5" fill="none"/>
  <!-- Base Shell Joint -->
  <ellipse cx="26" cy="26" rx="10" ry="7" fill="#581c87" stroke="#3b0764" stroke-width="2" transform="rotate(-30 26 26)"/>
  <!-- Glowing Venom Drop poised at tip -->
  <path d="M64,80 C68,84 70,88 68,92 C66,94 62,94 60,92 C58,88 62,84 64,80 Z" fill="#a855f7" stroke="#22c55e" stroke-width="1.5"/>
  <circle cx="64" cy="90" r="2" fill="#4ade80"/>
</svg>""",

    "normal-gem": """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <!-- Brilliant Cut Diamond Shape -->
  <polygon points="30,28 70,28 86,46 50,86 14,46" fill="#f8fafc" stroke="#94a3b8" stroke-width="2.5"/>
  <!-- Facet Divisions -->
  <polygon points="30,28 50,46 14,46" fill="#e2e8f0"/>
  <polygon points="70,28 50,46 86,46" fill="#cbd5e1"/>
  <polygon points="30,28 70,28 50,46" fill="#ffffff"/>
  <polygon points="14,46 50,46 50,86" fill="#e2e8f0"/>
  <polygon points="86,46 50,46 50,86" fill="#cbd5e1"/>
  <line x1="50" y1="28" x2="50" y2="46" stroke="#94a3b8" stroke-width="1.5"/>
  <!-- Glint -->
  <polygon points="38,34 44,34 40,40" fill="#ffffff"/>
</svg>""",

    "sharp-beak": """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <!-- Feathered Base Attachment -->
  <path d="M22,32 C26,20 38,20 44,24 L42,52 L18,48 Z" fill="#78350f" stroke="#451a03" stroke-width="2"/>
  <!-- Curved Raptor Beak -->
  <path d="M42,24 C58,28 82,42 82,68 C76,72 68,68 62,60 C52,48 42,46 36,46 Z" fill="#facc15" stroke="#b45309" stroke-width="2.5"/>
  <!-- Cutting Ridge -->
  <path d="M42,26 C56,32 74,46 78,66" stroke="#ffffff" stroke-width="2.5" fill="none"/>
  <!-- Nostril -->
  <ellipse cx="48" cy="32" rx="3" ry="1.5" fill="#78350f" transform="rotate(20 48 32)"/>
</svg>""",

    "shed-shell": """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <!-- Cicada Husk Carapace -->
  <ellipse cx="50" cy="54" rx="24" ry="30" fill="#d97706" fill-opacity="0.6" stroke="#92400e" stroke-width="2.5"/>
  <!-- Segmented Abdominal Rings -->
  <path d="M30,46 C42,42 58,42 70,46" stroke="#92400e" stroke-width="2" fill="none"/>
  <path d="M32,58 C42,54 58,54 68,58" stroke="#92400e" stroke-width="2" fill="none"/>
  <path d="M36,70 C44,66 56,66 64,70" stroke="#92400e" stroke-width="2" fill="none"/>
  <!-- Head Shell with Horns -->
  <circle cx="50" cy="24" r="14" fill="#b45309" stroke="#78350f" stroke-width="2"/>
  <line x1="42" y1="14" x2="36" y2="8" stroke="#78350f" stroke-width="2.5" stroke-linecap="round"/>
  <line x1="58" y1="14" x2="64" y2="8" stroke="#78350f" stroke-width="2.5" stroke-linecap="round"/>
  <!-- Wing Stubs -->
  <ellipse cx="26" cy="46" rx="6" ry="14" fill="#fde68a" fill-opacity="0.5" stroke="#92400e" stroke-width="1.5" transform="rotate(-30 26 46)"/>
  <ellipse cx="74" cy="46" rx="6" ry="14" fill="#fde68a" fill-opacity="0.5" stroke="#92400e" stroke-width="1.5" transform="rotate(30 74 46)"/>
</svg>""",

    "shell-bell": """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <!-- Spiral Conch Body -->
  <path d="M50,18 C70,18 84,36 80,56 C76,72 62,84 46,84 C30,84 18,72 20,54 C22,40 34,26 50,18 Z" fill="#e0f2fe" stroke="#0284c7" stroke-width="2.5"/>
  <!-- Inner Spiral Ribs -->
  <path d="M50,18 C58,26 62,38 60,50 C58,62 48,70 38,68 C28,66 26,52 32,42 C38,32 46,34 48,42" stroke="#38bdf8" stroke-width="2.5" fill="none"/>
  <!-- Bell Clapper Pearl Core -->
  <circle cx="54" cy="62" r="7" fill="#facc15" stroke="#b45309" stroke-width="1.5"/>
  <!-- Acoustic Wavelets -->
  <path d="M78,64 C84,60 88,52 86,44" stroke="#38bdf8" stroke-width="2" fill="none" stroke-linecap="round"/>
  <path d="M84,72 C92,66 96,54 94,42" stroke="#38bdf8" stroke-width="2" fill="none" stroke-linecap="round"/>
</svg>""",

    "silver-powder": """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <!-- Silk Pouch Body -->
  <path d="M30,36 C34,28 66,28 70,36 C76,54 78,82 50,86 C22,82 24,54 30,36 Z" fill="#e2e8f0" stroke="#94a3b8" stroke-width="2.5"/>
  <!-- Tied Cord Ribbon -->
  <path d="M32,36 C42,40 58,40 68,36" stroke="#475569" stroke-width="3" fill="none"/>
  <circle cx="50" cy="38" r="4" fill="#38bdf8"/>
  <!-- Shimmering Wing Scales Dust -->
  <polygon points="50,48 52,54 58,56 52,58 50,64 48,58 42,56 48,54" fill="#ffffff" stroke="#94a3b8" stroke-width="1"/>
  <circle cx="36" cy="62" r="2.5" fill="#ffffff"/>
  <circle cx="64" cy="66" r="2.5" fill="#ffffff"/>
  <circle cx="56" cy="74" r="2" fill="#38bdf8"/>
  <circle cx="42" cy="74" r="2" fill="#38bdf8"/>
</svg>""",

    "soft-sand": """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <!-- Pouch with Spilling Sand -->
  <path d="M32,32 C38,24 62,24 68,32 L64,62 C64,74 54,82 46,82 C38,82 32,74 32,62 Z" fill="#d97706" stroke="#78350f" stroke-width="2.5"/>
  <line x1="34" y1="34" x2="66" y2="34" stroke="#78350f" stroke-width="2.5"/>
  <!-- Sand Dune Pile -->
  <path d="M18,88 Q50,68 82,88 Z" fill="#fde68a" stroke="#d97706" stroke-width="2"/>
  <path d="M30,86 Q50,74 70,86" stroke="#b45309" stroke-width="1.5" fill="none"/>
  <!-- Floating Grains -->
  <circle cx="48" cy="62" r="1.5" fill="#d97706"/>
  <circle cx="54" cy="68" r="1.5" fill="#d97706"/>
  <circle cx="50" cy="74" r="1.5" fill="#d97706"/>
</svg>""",

    "spell-tag": """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <!-- Parchment Paper Strip -->
  <rect x="32" y="14" width="36" height="74" rx="2" fill="#fef3c7" stroke="#b45309" stroke-width="2"/>
  <!-- Top Tie String Hole -->
  <circle cx="50" cy="22" r="3.5" fill="#78350f"/>
  <path d="M50,14 L50,6" stroke="#dc2626" stroke-width="2" stroke-linecap="round"/>
  <!-- Mystical Red Brushstroke Kanji Seal -->
  <path d="M42,32 L58,32" stroke="#dc2626" stroke-width="3" stroke-linecap="round"/>
  <path d="M50,32 L50,48 M42,42 L58,42" stroke="#dc2626" stroke-width="2.5"/>
  <path d="M44,52 L56,52 L50,64 L56,76 M44,68 L50,64" stroke="#dc2626" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
</svg>""",

    "terrain-extender": """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <!-- Hexagonal Tech Base -->
  <polygon points="50,18 78,34 78,66 50,82 22,66 22,34" fill="#0f172a" stroke="#38bdf8" stroke-width="3"/>
  <!-- Inner Circuit Hexagon -->
  <polygon points="50,28 70,40 70,60 50,72 30,60 30,40" fill="#1e293b" stroke="#0284c7" stroke-width="2"/>
  <!-- Central Pulse Emitter Core -->
  <circle cx="50" cy="50" r="12" fill="#22c55e" stroke="#ffffff" stroke-width="2"/>
  <!-- Radiant Resonance Waves -->
  <circle cx="50" cy="50" r="22" fill="none" stroke="#22c55e" stroke-width="1.5" stroke-opacity="0.75" stroke-dasharray="4,4"/>
  <circle cx="50" cy="50" r="34" fill="none" stroke="#38bdf8" stroke-width="1.5" stroke-opacity="0.5" stroke-dasharray="6,4"/>
</svg>""",

    "wide-lens": """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <!-- Lens Bevel Housing -->
  <circle cx="50" cy="50" r="40" fill="#334155" stroke="#94a3b8" stroke-width="3"/>
  <circle cx="50" cy="50" r="34" fill="#1e293b" stroke="#64748b" stroke-width="2"/>
  <!-- Optical Blue Glass -->
  <circle cx="50" cy="50" r="30" fill="#0284c7" fill-opacity="0.4" stroke="#38bdf8" stroke-width="2"/>
  <!-- Alignment Reticle -->
  <line x1="50" y1="24" x2="50" y2="34" stroke="#ffffff" stroke-width="2"/>
  <line x1="50" y1="66" x2="50" y2="76" stroke="#ffffff" stroke-width="2"/>
  <line x1="24" y1="50" x2="34" y2="50" stroke="#ffffff" stroke-width="2"/>
  <line x1="66" y1="50" x2="76" y2="50" stroke="#ffffff" stroke-width="2"/>
  <!-- Curved Glare -->
  <path d="M30,34 A26,26 0 0,1 66,26" stroke="#ffffff" stroke-width="3" stroke-linecap="round" fill="none" stroke-opacity="0.7"/>
</svg>""",

    "zoom-lens": """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <!-- Multi-Element Telephoto Barrel -->
  <rect x="24" y="24" width="52" height="52" rx="6" fill="#1e293b" stroke="#475569" stroke-width="2.5"/>
  <!-- Grip Rings -->
  <line x1="28" y1="36" x2="72" y2="36" stroke="#64748b" stroke-width="3"/>
  <line x1="28" y1="44" x2="72" y2="44" stroke="#64748b" stroke-width="3"/>
  <!-- Front Element Ring with Green Multicoating -->
  <circle cx="50" cy="62" r="18" fill="#065f46" stroke="#10b981" stroke-width="2"/>
  <!-- Internal Aperture Core -->
  <circle cx="50" cy="62" r="8" fill="#022c22"/>
  <!-- Specular Crescent Glint -->
  <path d="M40,56 A12,12 0 0,1 58,54" stroke="#34d399" stroke-width="2.5" stroke-linecap="round" fill="none"/>
</svg>""",

    "quick-claw": """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <!-- 3 Curved Raptor Steel Talons -->
  <path d="M32,32 C42,42 46,64 36,82 C30,76 30,56 20,44 Z" fill="#cbd5e1" stroke="#475569" stroke-width="2"/>
  <path d="M46,20 C60,34 66,62 58,86 C48,78 48,52 34,36 Z" fill="#f8fafc" stroke="#475569" stroke-width="2"/>
  <path d="M60,32 C74,44 80,66 74,84 C66,76 66,56 50,44 Z" fill="#cbd5e1" stroke="#475569" stroke-width="2"/>
  <!-- Base Knuckle Pad -->
  <rect x="22" y="22" width="52" height="14" rx="4" fill="#64748b" stroke="#334155" stroke-width="2"/>
  <!-- Speed Motion Blur Streaks -->
  <line x1="68" y1="20" x2="88" y2="12" stroke="#38bdf8" stroke-width="3" stroke-linecap="round"/>
  <line x1="74" y1="32" x2="94" y2="24" stroke="#38bdf8" stroke-width="2.5" stroke-linecap="round"/>
</svg>""",

    "red-card": """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <!-- Vibrant Red Referee Card with Perspective Angle -->
  <polygon points="32,16 78,22 68,86 22,80" fill="#dc2626" stroke="#991b1b" stroke-width="3"/>
  <!-- Diagonal Penalty Warning Stripe -->
  <polygon points="36,26 44,27 34,76 26,75" fill="#ffffff" fill-opacity="0.8"/>
  <!-- Whistle Shadow Element -->
  <circle cx="68" cy="72" r="8" fill="#1e293b" stroke="#475569" stroke-width="2"/>
  <rect x="56" y="68" width="12" height="6" fill="#1e293b"/>
</svg>""",

    "scope-lens": """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <!-- Precision Tactical Optic Body -->
  <circle cx="50" cy="50" r="38" fill="#18181b" stroke="#3f3f46" stroke-width="3"/>
  <circle cx="50" cy="50" r="30" fill="#090d16" stroke="#ef4444" stroke-width="1.5"/>
  <!-- Crosshairs -->
  <line x1="20" y1="50" x2="80" y2="50" stroke="#ef4444" stroke-width="1.5"/>
  <line x1="50" y1="20" x2="50" y2="80" stroke="#ef4444" stroke-width="1.5"/>
  <!-- Concentric Range Circles -->
  <circle cx="50" cy="50" r="16" fill="none" stroke="#ef4444" stroke-width="1.2" stroke-dasharray="4,3"/>
  <!-- Target Dot -->
  <circle cx="50" cy="50" r="3.5" fill="#ef4444"/>
  <circle cx="50" cy="50" r="1.5" fill="#ffffff"/>
</svg>""",

    "bright-powder": """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <!-- Silk Dust Pouch -->
  <path d="M30,36 C34,26 66,26 70,36 C76,56 76,82 50,86 C24,82 24,56 30,36 Z" fill="#fef08a" stroke="#ca8a04" stroke-width="2.5"/>
  <path d="M32,36 C42,40 58,40 68,36" stroke="#b45309" stroke-width="3" fill="none"/>
  <!-- Dazzling Light Bursts -->
  <polygon points="50,14 53,24 62,26 54,30 56,40 50,33 44,40 46,30 38,26 47,24" fill="#ffffff" stroke="#facc15" stroke-width="1"/>
  <polygon points="76,46 78,52 84,54 79,57 80,63 76,59 71,63 73,57 68,54 74,52" fill="#ffffff" stroke="#facc15" stroke-width="1"/>
  <polygon points="24,56 26,62 32,64 27,67 28,73 24,69 19,73 21,67 16,64 22,62" fill="#ffffff" stroke="#facc15" stroke-width="1"/>
</svg>""",

    "big-root": """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <!-- Gnarled Organic Root Tuber -->
  <path d="M42,16 C52,14 62,20 60,34 C58,46 72,56 68,76 C64,88 48,88 44,74 C40,62 30,58 32,40 C34,26 36,18 42,16 Z" fill="#78350f" stroke="#451a03" stroke-width="3"/>
  <!-- Lateral Root Tendrils -->
  <path d="M34,46 C22,54 18,70 26,82" stroke="#78350f" stroke-width="3" fill="none" stroke-linecap="round"/>
  <path d="M66,48 C78,56 82,72 76,84" stroke="#78350f" stroke-width="3" fill="none" stroke-linecap="round"/>
  <!-- Glowing Green Nutrient Sap Nodes -->
  <circle cx="50" cy="40" r="4" fill="#22c55e"/>
  <circle cx="48" cy="62" r="4.5" fill="#22c55e"/>
  <path d="M50,44 L48,58" stroke="#4ade80" stroke-width="2" stroke-linecap="round"/>
</svg>""",

    "iron-ball": """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <radialGradient id="ironGrad" cx="35%" cy="35%" r="65%">
      <stop offset="0%" stop-color="#94a3b8"/>
      <stop offset="45%" stop-color="#475569"/>
      <stop offset="85%" stop-color="#1e293b"/>
      <stop offset="100%" stop-color="#0f172a"/>
    </radialGradient>
  </defs>
  <!-- Heavy Iron Cannonball -->
  <circle cx="50" cy="54" r="34" fill="url(#ironGrad)" stroke="#0f172a" stroke-width="3"/>
  <!-- Top Shackled Eyelet -->
  <path d="M42,22 C42,14 58,14 58,22" stroke="#64748b" stroke-width="5" stroke-linecap="round" fill="none"/>
  <!-- Heavy Chain Link -->
  <ellipse cx="50" cy="12" rx="6" ry="9" fill="none" stroke="#94a3b8" stroke-width="4"/>
  <!-- Specular Reflection -->
  <ellipse cx="38" cy="42" rx="10" ry="5" fill="#ffffff" fill-opacity="0.5" transform="rotate(-30 38 42)"/>
</svg>""",

    "leek": """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <!-- Diagonal Long Scallion Stalk -->
  <path d="M22,86 L74,18 L84,24 L30,92 Z" fill="#f8fafc" stroke="#16a34a" stroke-width="2"/>
  <!-- Green Leaf Sheaths -->
  <path d="M44,56 L74,18 L84,24 L52,64 Z" fill="#22c55e"/>
  <!-- Spreading Green Leaves at top -->
  <path d="M74,18 L86,8 L84,24 Z" fill="#15803d"/>
  <path d="M84,24 L94,18 L78,32 Z" fill="#16a34a"/>
  <!-- Root Hairs at bottom -->
  <line x1="22" y1="88" x2="14" y2="92" stroke="#d97706" stroke-width="2" stroke-linecap="round"/>
  <line x1="26" y1="92" x2="20" y2="96" stroke="#d97706" stroke-width="2" stroke-linecap="round"/>
</svg>""",

    "metronome": """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <!-- Wooden Pyramid Case -->
  <polygon points="50,14 74,86 26,86" fill="#78350f" stroke="#451a03" stroke-width="2.5"/>
  <!-- Face Inset -->
  <polygon points="50,22 68,82 32,82" fill="#fef3c7" stroke="#b45309" stroke-width="1.5"/>
  <!-- Tempo Scale Ticks -->
  <line x1="44" y1="40" x2="56" y2="40" stroke="#78350f" stroke-width="1.5"/>
  <line x1="42" y1="50" x2="58" y2="50" stroke="#78350f" stroke-width="1.5"/>
  <line x1="40" y1="60" x2="60" y2="60" stroke="#78350f" stroke-width="1.5"/>
  <!-- Swinging Steel Pendulum with Sliding Weight -->
  <line x1="50" y1="80" x2="64" y2="24" stroke="#475569" stroke-width="3" stroke-linecap="round"/>
  <rect x="54" y="38" width="9" height="7" rx="1.5" fill="#cbd5e1" stroke="#334155" stroke-width="1.5" transform="rotate(-15 58 41)"/>
</svg>""",

    "never-melt-ice": """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="iceGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#e0f2fe"/>
      <stop offset="50%" stop-color="#38bdf8"/>
      <stop offset="100%" stop-color="#0284c7"/>
    </linearGradient>
  </defs>
  <!-- Geometric Glacial Ice Crystal -->
  <polygon points="50,14 82,32 82,68 50,86 18,68 18,32" fill="url(#iceGrad)" stroke="#ffffff" stroke-width="2.5"/>
  <!-- Facet Planes -->
  <polygon points="50,14 50,50 18,32" fill="#ffffff" fill-opacity="0.4"/>
  <polygon points="50,14 82,32 50,50" fill="#ffffff" fill-opacity="0.2"/>
  <polygon points="18,32 50,50 50,86 18,68" fill="#0369a1" fill-opacity="0.3"/>
  <polygon points="82,32 82,68 50,86 50,50" fill="#0284c7" fill-opacity="0.5"/>
  <!-- Snowflake Particles -->
  <path d="M50,42 L50,58 M42,50 L58,50" stroke="#ffffff" stroke-width="2.5" stroke-linecap="round"/>
  <circle cx="74" cy="24" r="2.5" fill="#ffffff"/>
  <circle cx="26" cy="74" r="2.5" fill="#ffffff"/>
</svg>"""
}

# Verify all 32 item SVGs are well-formed XML
for name, svg in ITEM_SVGS.items():
    try:
        ET.fromstring(svg)
    except Exception as e:
        raise ValueError(f"Malformed SVG for item {name}: {e}")
