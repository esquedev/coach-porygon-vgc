# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Complete SVG Asset Generator
Generates:
1. 80+ Mega Stones in `assets/megastones/`
2. 80+ Competitive Items & Berries in `assets/items/` (incorporating bespoke vector illustrations)
3. 363 Regulation M-C Pokémon species in `assets/sprites/` (with bespoke SVGs and anatomical battle crests)
4. Base64 map builder for Command Center injection
"""

import csv
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

REPO_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = REPO_ROOT / "assets"
SPRITES_DIR = ASSETS_DIR / "sprites"
ITEMS_DIR = ASSETS_DIR / "items"
MEGASTONES_DIR = ASSETS_DIR / "megastones"

SPRITES_DIR.mkdir(parents=True, exist_ok=True)
ITEMS_DIR.mkdir(parents=True, exist_ok=True)
MEGASTONES_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(REPO_ROOT))

# Import bespoke libraries
from engine.svg_library_expansion import ITEM_SVGS as BESPOKE_ITEMS
from engine.ui_generator import POKEMON_SVGS as BESPOKE_SPECIES

TYPE_COLORS = {
    'Fire': '#f97316', 'Water': '#38bdf8', 'Grass': '#22c55e', 'Electric': '#facc15',
    'Ice': '#67e8f9', 'Fighting': '#ef4444', 'Poison': '#a855f7', 'Ground': '#d97706',
    'Flying': '#818cf8', 'Psychic': '#ec4899', 'Bug': '#84cc16', 'Rock': '#a8a29e',
    'Ghost': '#7c3aed', 'Dragon': '#6366f1', 'Dark': '#475569', 'Steel': '#94a3b8',
    'Fairy': '#f472b6', 'Normal': '#94a3b8'
}

def slugify(s):
    """Convert species or item name into clean hyphenated slug."""
    clean = re.sub(r'\s*\([mf]\)\s*', '', str(s or ''), flags=re.I).strip().lower()
    clean = re.sub(r'[^a-z0-9]+', '-', clean)
    return clean.strip('-')

# 1. GENERATE MEGA STONES
def generate_mega_stone_svg(name, c1='#a855f7', c2='#ec4899'):
    """Generate valid standalone SVG vector for a Mega Stone."""
    slug = slugify(name)
    return f"""<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <radialGradient id="mg-{slug}" cx="35%" cy="35%" r="65%">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="0.9"/>
      <stop offset="25%" stop-color="{c1}"/>
      <stop offset="70%" stop-color="{c2}"/>
      <stop offset="100%" stop-color="#090d16"/>
    </radialGradient>
    <filter id="glow-{slug}" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="3" result="blur"/>
      <feComposite in="SourceGraphic" in2="blur" operator="over"/>
    </filter>
  </defs>
  <!-- Outer Aura Glow -->
  <circle cx="50" cy="50" r="44" fill="none" stroke="{c1}" stroke-width="2" stroke-opacity="0.5" filter="url(#glow-{slug})"/>
  <!-- Base Marble Orb -->
  <circle cx="50" cy="50" r="40" fill="url(#mg-{slug})" stroke="#ffffff" stroke-width="2" stroke-opacity="0.4"/>
  <!-- Specular Reflection -->
  <ellipse cx="38" cy="28" rx="14" ry="7" transform="rotate(-30 38 28)" fill="#ffffff" fill-opacity="0.45"/>
  <!-- Iconic Mega Evolution DNA Symbol -->
  <path d="M42,26 C48,34 52,38 58,46 C64,54 58,68 46,72 C40,64 48,52 54,46 C60,40 50,30 42,26 Z" fill="#ffffff" fill-opacity="0.85"/>
  <circle cx="50" cy="50" r="6" fill="#facc15" fill-opacity="0.9"/>
  <!-- Rim Highlight -->
  <circle cx="50" cy="50" r="39" fill="none" stroke="{c2}" stroke-width="1.5" stroke-opacity="0.6"/>
</svg>"""

# 2. GENERATE COMPETITIVE ITEMS & BERRIES
def generate_item_svg(name, category="item"):
    """Generate valid standalone SVG vector for a competitive hold item."""
    slug = slugify(name)
    n_lower = name.lower()

    # Priority 1: Check bespoke custom items
    if slug in BESPOKE_ITEMS:
        return BESPOKE_ITEMS[slug].strip()
    if slug.replace("-", "") in BESPOKE_ITEMS:
        return BESPOKE_ITEMS[slug.replace("-", "")].strip()

    # Priority 2: Specific competitive item categories
    if "scarf" in n_lower:
        # Choice Scarf - Blue striped ribbon
        return """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <path d="M22,35 C32,22 68,22 78,35 C84,43 76,55 68,52 C58,48 42,48 32,52 C24,55 16,43 22,35 Z" fill="#2563eb" stroke="#60a5fa" stroke-width="3"/>
  <path d="M60,48 L72,82 L52,86 L46,50 Z" fill="#1d4ed8" stroke="#3b82f6" stroke-width="2"/>
  <line x1="28" y1="32" x2="36" y2="48" stroke="#ffffff" stroke-width="3"/>
  <line x1="46" y1="30" x2="52" y2="46" stroke="#ffffff" stroke-width="3"/>
  <line x1="64" y1="34" x2="68" y2="50" stroke="#ffffff" stroke-width="3"/>
  <line x1="58" y1="56" x2="68" y2="80" stroke="#ffffff" stroke-width="3"/>
</svg>"""
    elif "band" in n_lower or "belt" in n_lower:
        # Choice Band / Focus Band / Black Belt
        c = "#dc2626" if "choice" in n_lower else "#1e293b" if "black" in n_lower else "#f59e0b"
        return f"""<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <rect x="18" y="36" width="64" height="18" rx="4" fill="{c}" stroke="#ffffff" stroke-width="2.5"/>
  <path d="M44,48 L32,78 L44,82 L52,50 Z" fill="{c}" stroke="#ffffff" stroke-width="2"/>
  <path d="M56,48 L68,78 L56,82 L48,50 Z" fill="{c}" stroke="#ffffff" stroke-width="2"/>
  <circle cx="50" cy="45" r="7" fill="#facc15" stroke="#ffffff" stroke-width="2"/>
</svg>"""
    elif "specs" in n_lower or "glasses" in n_lower:
        # Choice Specs / Black Glasses
        c = "#f59e0b" if "choice" in n_lower else "#334155"
        return f"""<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <circle cx="32" cy="50" r="18" fill="none" stroke="{c}" stroke-width="4"/>
  <circle cx="68" cy="50" r="18" fill="none" stroke="{c}" stroke-width="4"/>
  <path d="M50,50 L50,44" stroke="{c}" stroke-width="4"/>
  <ellipse cx="30" cy="46" rx="6" ry="3" fill="#ffffff" fill-opacity="0.6"/>
  <ellipse cx="66" cy="46" rx="6" ry="3" fill="#ffffff" fill-opacity="0.6"/>
</svg>"""
    elif "berry" in n_lower:
        # Competitive Berry
        c = "#f97316" if "sitrus" in n_lower else "#ef4444" if "lum" in n_lower else "#eab308" if "iapapa" in n_lower else "#84cc16"
        return f"""<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <path d="M50,30 C30,30 22,50 30,72 C36,88 64,88 70,72 C78,50 70,30 50,30 Z" fill="{c}" stroke="#ffffff" stroke-width="2.5"/>
  <path d="M50,30 Q46,14 36,16" stroke="#15803d" stroke-width="4" stroke-linecap="round" fill="none"/>
  <circle cx="42" cy="48" r="4" fill="#ffffff" fill-opacity="0.4"/>
</svg>"""
    elif "sash" in n_lower:
        # Focus Sash
        return """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <path d="M20,50 C35,25 65,75 80,50" stroke="#f8fafc" stroke-width="12" stroke-linecap="round" fill="none"/>
  <path d="M20,50 C35,25 65,75 80,50" stroke="#dc2626" stroke-width="6" stroke-linecap="round" fill="none"/>
</svg>"""
    elif "orb" in n_lower:
        # Life Orb / Toxic Orb / Flame Orb
        c = "#ec4899" if "life" in n_lower else "#a855f7" if "toxic" in n_lower else "#ea580c"
        return f"""<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <circle cx="50" cy="50" r="32" fill="{c}" stroke="#ffffff" stroke-width="3"/>
  <ellipse cx="40" cy="38" rx="10" ry="5" transform="rotate(-30 40 38)" fill="#ffffff" fill-opacity="0.6"/>
</svg>"""
    elif "vest" in n_lower:
        # Assault Vest
        return """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <path d="M26,30 L38,20 L62,20 L74,30 L68,76 L32,76 Z" fill="#475569" stroke="#94a3b8" stroke-width="3"/>
  <path d="M42,20 C42,32 58,32 58,20 Z" fill="#0f172a"/>
  <line x1="50" y1="36" x2="50" y2="76" stroke="#94a3b8" stroke-width="2"/>
</svg>"""
    elif "goggles" in n_lower:
        # Safety Goggles
        return """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <rect x="18" y="36" width="28" height="24" rx="6" fill="#0284c7" stroke="#ffffff" stroke-width="3"/>
  <rect x="54" y="36" width="28" height="24" rx="6" fill="#0284c7" stroke="#ffffff" stroke-width="3"/>
  <line x1="46" y1="48" x2="54" y2="48" stroke="#ffffff" stroke-width="4"/>
</svg>"""
    elif "helmet" in n_lower:
        # Rocky Helmet
        return """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <path d="M22,60 C22,35 78,35 78,60 L78,66 L22,66 Z" fill="#ea580c" stroke="#ffffff" stroke-width="3"/>
  <polygon points="50,22 42,35 58,35" fill="#facc15" stroke="#ffffff" stroke-width="2"/>
  <polygon points="32,32 26,44 38,44" fill="#facc15" stroke="#ffffff" stroke-width="2"/>
  <polygon points="68,32 62,44 74,44" fill="#facc15" stroke="#ffffff" stroke-width="2"/>
</svg>"""
    elif "dice" in n_lower:
        # Loaded Dice
        return """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <rect x="25" y="25" width="50" height="50" rx="10" fill="#f8fafc" stroke="#0f172a" stroke-width="4"/>
  <circle cx="40" cy="40" r="4" fill="#ef4444"/>
  <circle cx="60" cy="40" r="4" fill="#ef4444"/>
  <circle cx="50" cy="50" r="4" fill="#ef4444"/>
  <circle cx="40" cy="60" r="4" fill="#ef4444"/>
  <circle cx="60" cy="60" r="4" fill="#ef4444"/>
</svg>"""
    elif "booster" in n_lower:
        # Booster Energy Capsule
        return """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <rect x="34" y="20" width="32" height="60" rx="16" fill="#06b6d4" stroke="#ffffff" stroke-width="3"/>
  <line x1="34" y1="50" x2="66" y2="50" stroke="#ffffff" stroke-width="3"/>
</svg>"""
    elif "rock" in n_lower:
        # Damp Rock / Heat Rock / Icy Rock / Smooth Rock
        c = "#0284c7" if "damp" in n_lower else "#ea580c" if "heat" in n_lower else "#38bdf8"
        return f"""<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <polygon points="45,18 76,26 84,62 55,82 22,68 18,34" fill="{c}" stroke="#ffffff" stroke-width="3"/>
  <line x1="45" y1="18" x2="55" y2="82" stroke="#ffffff" stroke-width="2" stroke-opacity="0.5"/>
  <line x1="76" y1="26" x2="22" y2="68" stroke="#ffffff" stroke-width="2" stroke-opacity="0.5"/>
</svg>"""
    else:
        # Fallback: Sleek Competitive Battle Crystal Capsule (No plain generic emblem)
        initials = re.sub(r'[^a-zA-Z]', '', name)[:3].upper()
        return f"""<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="ic-{slug}" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#38bdf8"/>
      <stop offset="100%" stop-color="#6366f1"/>
    </linearGradient>
  </defs>
  <polygon points="50,14 80,30 80,70 50,86 20,70 20,30" fill="#0f172a" stroke="url(#ic-{slug})" stroke-width="3"/>
  <polygon points="50,22 72,34 72,66 50,78 28,66 28,34" fill="url(#ic-{slug})" fill-opacity="0.25"/>
  <circle cx="50" cy="50" r="16" fill="#0f172a" stroke="#facc15" stroke-width="2"/>
  <text x="50" y="55" text-anchor="middle" fill="#f8fafc" font-family="sans-serif" font-weight="900" font-size="11">{initials}</text>
</svg>"""

# 3. GENERATE DUAL-TYPE ANATOMICAL BATTLE CREST FOR ALL SPECIES (NO POKEBALL PATTERN)
def generate_species_svg(name, t1="Normal", t2=None):
    """Generate dual-type anatomical creature battle crest SVG for a Pokémon species."""
    c1 = TYPE_COLORS.get(t1, '#94a3b8')
    c2 = TYPE_COLORS.get(t2, c1) if t2 else c1
    is_mega = "mega" in name.lower()

    if t1 in ['Fire', 'Dragon']:
        head_horns = f"""
          <polygon points="46,34 32,10 44,28" fill="{c1}" stroke="#0f172a" stroke-width="1.5"/>
          <polygon points="74,34 88,10 76,28" fill="{c1}" stroke="#0f172a" stroke-width="1.5"/>
          <polygon points="54,28 60,14 66,28" fill="{c2}"/>
        """
        muzzle = f"""
          <polygon points="48,54 72,54 68,70 52,70" fill="{c2}" stroke="#0f172a" stroke-width="1.5"/>
          <ellipse cx="60" cy="62" rx="4" ry="2" fill="#0f172a"/>
        """
    elif t1 in ['Water', 'Ice']:
        head_horns = f"""
          <polygon points="42,32 20,20 34,36" fill="{c2}" stroke="#0f172a" stroke-width="1.5"/>
          <polygon points="78,32 100,20 86,36" fill="{c2}" stroke="#0f172a" stroke-width="1.5"/>
          <path d="M50,26 C60,12 60,12 70,26 Z" fill="{c1}"/>
        """
        muzzle = f"""
          <ellipse cx="60" cy="62" rx="12" ry="7" fill="{c2}" stroke="#0f172a" stroke-width="1.5"/>
          <circle cx="60" cy="60" r="2" fill="#0f172a"/>
        """
    elif t1 in ['Grass', 'Bug']:
        head_horns = f"""
          <path d="M46,32 Q26,8 18,18" stroke="{c1}" stroke-width="3" stroke-linecap="round" fill="none"/>
          <path d="M74,32 Q94,8 102,18" stroke="{c1}" stroke-width="3" stroke-linecap="round" fill="none"/>
          <ellipse cx="60" cy="24" rx="8" ry="4" fill="{c2}"/>
        """
        muzzle = f"""
          <polygon points="50,56 60,68 70,56" fill="{c2}" stroke="#0f172a" stroke-width="1.5"/>
        """
    elif t1 in ['Electric']:
        head_horns = f"""
          <polygon points="46,34 24,14 38,24 28,34" fill="{c1}" stroke="#ca8a04" stroke-width="1.5"/>
          <polygon points="74,34 96,14 82,24 92,34" fill="{c1}" stroke="#ca8a04" stroke-width="1.5"/>
        """
        muzzle = f"""
          <ellipse cx="60" cy="60" rx="10" ry="6" fill="{c2}"/>
          <circle cx="44" cy="56" r="4" fill="#ef4444"/><circle cx="76" cy="56" r="4" fill="#ef4444"/>
        """
    elif t1 in ['Ghost', 'Dark', 'Psychic']:
        head_horns = f"""
          <path d="M46,32 C34,14 26,20 32,36" fill="{c1}" stroke="#0f172a" stroke-width="1.5"/>
          <path d="M74,32 C86,14 94,20 88,36" fill="{c1}" stroke="#0f172a" stroke-width="1.5"/>
          <circle cx="60" cy="28" r="4" fill="#facc15"/>
        """
        muzzle = f"""
          <ellipse cx="60" cy="62" rx="8" ry="5" fill="{c2}"/>
        """
    elif t1 in ['Fighting', 'Steel', 'Rock', 'Ground']:
        head_horns = f"""
          <polygon points="44,30 52,14 60,30" fill="{c1}" stroke="#0f172a" stroke-width="1.5"/>
          <polygon points="60,30 68,14 76,30" fill="{c1}" stroke="#0f172a" stroke-width="1.5"/>
          <polygon points="34,36 20,44 32,50" fill="{c2}"/><polygon points="86,36 100,44 88,50" fill="{c2}"/>
        """
        muzzle = f"""
          <rect x="48" y="56" width="24" height="12" rx="3" fill="{c2}" stroke="#0f172a" stroke-width="1.5"/>
        """
    else:
        # Avian / Feline / Normal
        head_horns = f"""
          <polygon points="44,34 30,16 46,26" fill="{c1}" stroke="#0f172a" stroke-width="1.5"/>
          <polygon points="76,34 90,16 74,26" fill="{c1}" stroke="#0f172a" stroke-width="1.5"/>
        """
        muzzle = """
          <polygon points="54,56 60,66 66,56" fill="#facc15" stroke="#ca8a04" stroke-width="1.5"/>
        """

    badge_corona = ""
    if is_mega:
        badge_corona = f"""<polygon points="60,6 70,22 88,14 84,32 102,34 90,48 104,60 90,72 102,86 84,88 88,106 70,98 60,114 50,98 32,106 36,88 18,86 30,72 16,60 30,48 18,34 36,32 32,14 50,22" fill="{c1}" fill-opacity="0.25" stroke="{c1}" stroke-width="1.5"/>"""

    return f"""<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Elemental Battle Crest Backdrop -->
  <circle cx="60" cy="60" r="48" fill="{c1}" fill-opacity="0.12"/>
  {badge_corona}
  <!-- Anatomical Creature Torso & Shoulders -->
  <path d="M32,86 C32,68 44,62 60,62 C76,62 88,68 88,86 L94,104 C94,108 26,108 26,104 Z" fill="{c1}" stroke="#0f172a" stroke-width="2"/>
  <ellipse cx="60" cy="90" rx="14" ry="12" fill="{c2}" fill-opacity="0.85"/>
  <!-- Head Horns / Ears / Feathers -->
  {head_horns}
  <!-- Creature Head Contour -->
  <circle cx="60" cy="46" r="18" fill="{c1}" stroke="#0f172a" stroke-width="2"/>
  <!-- Focused Battle Eyes -->
  <polygon points="46,42 54,44 48,48" fill="#ffffff"/><circle cx="50" cy="45" r="1.5" fill="#0f172a"/>
  <polygon points="74,42 66,44 72,48" fill="#ffffff"/><circle cx="70" cy="45" r="1.5" fill="#0f172a"/>
  <!-- Muzzle / Beak / Jaw -->
  {muzzle}
</svg>"""

# ==================== PROCESS DATASETS ====================

def run_generation():
    """Executes full SVG asset generation across megastones, items, and Pokemon species."""
    # A. Read Regulation_MC_Items.csv
    items_seen = set()
    megastones_seen = set()

    with open(REPO_ROOT / 'data' / 'Regulation_MC_Items.csv', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader, None)  # Skip CSV header
        for row in reader:
            if not row: continue
            if len(row) > 0 and row[0].strip():
                items_seen.add(row[0].strip())
            if len(row) > 3 and row[3].strip():
                items_seen.add(row[3].strip())
            if len(row) > 6 and row[6].strip():
                megastones_seen.add(row[6].strip())

    print(f"Extracted {len(items_seen)} unique hold items/berries and {len(megastones_seen)} unique mega stones.")

    # Write Item SVGs (Overwriting all to guarantee no generic fallbacks)
    for it in items_seen:
        slug = slugify(it)
        svg_content = generate_item_svg(it).strip()
        ET.fromstring(svg_content)  # Validate XML
        (ITEMS_DIR / f"{slug}.svg").write_text(svg_content, encoding='utf-8')

    # Write Mega Stone SVGs
    for ms in megastones_seen:
        slug = slugify(ms)
        svg_content = generate_mega_stone_svg(ms).strip()
        ET.fromstring(svg_content)
        (MEGASTONES_DIR / f"{slug}.svg").write_text(svg_content, encoding='utf-8')

    print(f"Generated {len(items_seen)} items in {ITEMS_DIR} and {len(megastones_seen)} mega stones in {MEGASTONES_DIR}.")

    # B. Read MC_Available_Pokemon.csv
    species_list = []
    with open(REPO_ROOT / 'data' / 'MC_Available_Pokemon.csv', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader, None)  # Skip CSV header
        for row in reader:
            if not row or not row[0].strip(): continue
            raw_name = row[0].strip()
            t1 = row[1].strip() if len(row) > 1 and row[1].strip() else 'Normal'
            t2 = row[2].strip() if len(row) > 2 and row[2].strip() else None

            canonical = raw_name
            if canonical.startswith("Mega "):
                canonical = canonical.replace("Mega ", "") + "-Mega"

            species_list.append((canonical, t1, t2))

    print(f"Read {len(species_list)} species from MC_Available_Pokemon.csv.")

    # Write Species SVGs: Use bespoke if exists, else anatomical battle crest
    # OVERWRITE all existing to eradicate old Pokeball patterns
    bespoke_slug_map = {slugify(k): v for k, v in BESPOKE_SPECIES.items()}
    bespoke_count = 0
    anatomical_count = 0

    for sp_name, t1, t2 in species_list:
        slug = slugify(sp_name)
        if slug in bespoke_slug_map:
            svg_content = bespoke_slug_map[slug].strip()
            bespoke_count += 1
        elif slug.replace("-mega", "") in bespoke_slug_map and not slug.endswith("-mega"):
            svg_content = bespoke_slug_map[slug.replace("-mega", "")].strip()
            bespoke_count += 1
        else:
            svg_content = generate_species_svg(sp_name, t1, t2).strip()
            anatomical_count += 1

        ET.fromstring(svg_content)
        svg_file = SPRITES_DIR / f"{slug}.svg"
        svg_file.write_text(svg_content, encoding='utf-8')

        # Also write Title-Case filename
        title_name = "-".join(part.capitalize() for part in slug.split("-"))
        (SPRITES_DIR / f"{title_name}.svg").write_text(svg_content, encoding='utf-8')

    print(f"Written {bespoke_count} bespoke and {anatomical_count} anatomical SVGs to {SPRITES_DIR}.")
    print(f"Total sprite files in directory: {len(list(SPRITES_DIR.glob('*.svg')))}")

if __name__ == "__main__":
    run_generation()
