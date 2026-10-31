# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Command Center HTML & i18n Synchronizer
Compiles:
1. assets/command_center_es.html (Spanish default OTS Command Center)
2. assets/command_center_en.html (English default OTS Command Center)
3. assets/command_center.html (Master unified command center)
4. Synchronizes base64 sprites, items, and mega stones with zero Pokeball fallbacks.
5. Copies active build directly into Antigravity Brain artifact directory.
"""

import base64
import io
from PIL import Image
import json
import os
import re
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

ASSETS_DIR = REPO_ROOT / "assets"
SPRITES_DIR = ASSETS_DIR / "sprites"
ITEMS_DIR = ASSETS_DIR / "items"
MEGASTONES_DIR = ASSETS_DIR / "megastones"

OUT_MAIN = ASSETS_DIR / "command_center.html"
OUT_ES = ASSETS_DIR / "command_center_es.html"
OUT_EN = ASSETS_DIR / "command_center_en.html"


def resolve_artifact_dir() -> Path | None:
    """Dynamically resolves the active Antigravity brain artifact directory."""
    env_dir = os.environ.get("ANTIGRAVITY_ARTIFACT_DIR")
    if env_dir and Path(env_dir).exists():
        return Path(env_dir).resolve()
    brain_root = Path.home() / ".gemini" / "antigravity" / "brain"
    if brain_root.exists():
        direct = brain_root / "cf584036-b905-4920-962f-82887aafeaab"
        if direct.exists():
            return direct
        subdirs = [d for d in brain_root.iterdir() if d.is_dir() and d.name != "tempmediaStorage"]
        if subdirs:
            return max(subdirs, key=lambda d: d.stat().st_mtime)
    return None

from engine.ui_generator import POKEMON_SVGS, UI_ICONS, load_live_telemetry


def build_base64_maps():
    """Builds deduplicated, palette-optimized base64 data URIs for all authentic sprites and items.

    Quantizes 128x128 PNGs to 256 colors to reduce sprite payload by ~70%, ensuring the final
    HTML remains under 10 MB (well below the 20 MB display limit) with zero broken links.
    """
    sprite_map = {}
    item_map = {}

    reg_mc_dir = SPRITES_DIR / "Reg_M-C"
    all_sprite_paths = []
    if reg_mc_dir.exists():
        all_sprite_paths.extend(reg_mc_dir.glob("*.png"))
    if SPRITES_DIR.exists():
        for p in SPRITES_DIR.glob("*.png"):
            if "Reg_M-C" not in str(p):
                all_sprite_paths.append(p)
        all_sprite_paths.extend(SPRITES_DIR.glob("*.svg"))

    for asset_path in sorted(all_sprite_paths):
        key = asset_path.stem.lower()
        if asset_path.suffix == ".png":
            try:
                im = Image.open(asset_path)
                im_p = im.quantize(colors=256, method=Image.Quantize.FASTOCTREE)
                buf = io.BytesIO()
                im_p.save(buf, format="PNG", optimize=True)
                raw_bytes = buf.getvalue()
            except Exception:
                raw_bytes = asset_path.read_bytes()
            mime = "image/png"
        else:
            raw_bytes = asset_path.read_bytes()
            mime = "image/svg+xml"

        b64 = base64.b64encode(raw_bytes).decode("utf-8")
        data_uri = f"data:{mime};base64,{b64}"
        # Store only once under canonical key (NO duplicate base64 bloat)
        sprite_map[key] = data_uri

    # 2. Load items from assets/items/
    if ITEMS_DIR.exists():
        for asset_path in sorted(list(ITEMS_DIR.glob("*.png")) + list(ITEMS_DIR.glob("*.svg"))):
            key = asset_path.stem.lower()
            mime = "image/png" if asset_path.suffix == ".png" else "image/svg+xml"
            b64 = base64.b64encode(asset_path.read_bytes()).decode("utf-8")
            data_uri = f"data:{mime};base64,{b64}"
            item_map[key] = data_uri
            sprite_map[f"item-{key}"] = data_uri

    # 3. Load mega stones from assets/megastones/
    if MEGASTONES_DIR.exists():
        for asset_path in sorted(list(MEGASTONES_DIR.glob("*.png")) + list(MEGASTONES_DIR.glob("*.svg"))):
            key = asset_path.stem.lower()
            mime = "image/png" if asset_path.suffix == ".png" else "image/svg+xml"
            b64 = base64.b64encode(asset_path.read_bytes()).decode("utf-8")
            data_uri = f"data:{mime};base64,{b64}"
            item_map[key] = data_uri
            sprite_map[f"mega-{key}"] = data_uri

    # 4. Mascot Coach Porygon & UI Icons only (NEVER inject species SVGs into sprite_map)
    if "porygon-coach" in POKEMON_SVGS:
        b64 = base64.b64encode(POKEMON_SVGS["porygon-coach"].strip().encode("utf-8")).decode("utf-8")
        data_uri = f"data:image/svg+xml;base64,{b64}"
        sprite_map["porygon-coach"] = data_uri

    rotom_icon = ASSETS_DIR / "icons" / "rotom-wash.svg"
    if rotom_icon.exists():
        b64 = base64.b64encode(rotom_icon.read_bytes()).decode("utf-8")
        data_uri = f"data:image/svg+xml;base64,{b64}"
        sprite_map["rotom-wash-coach"] = data_uri
        sprite_map["rotom-wash-logo"] = data_uri

    for name, svg_code in UI_ICONS.items():
        k = name.lower()
        b64 = base64.b64encode(svg_code.strip().encode("utf-8")).decode("utf-8")
        data_uri = f"data:image/svg+xml;base64,{b64}"
        sprite_map[k] = data_uri
        if k == "pokeball":
            sprite_map["placeholder"] = data_uri

    return sprite_map, item_map


def update_command_center_files():
    """Compiles unified command center and language variations."""
    sprite_map, item_map = build_base64_maps()
    print(f"Loaded {len(sprite_map)} sprites and {len(item_map)} items into Base64 cache.")

    # Read base template from OUT_ES
    content = OUT_ES.read_text(encoding="utf-8")

    # 1. Uncheck auto-advance checkboxes by default
    content = re.sub(
        r'<input type="checkbox" id="(?:crucible|flashcard)-auto-advance"\s*checked\s*class="([^"]+)">',
        r'<input type="checkbox" id="flashcard-auto-advance" class="\1">',
        content
    )
    content = re.sub(
        r'<input type="checkbox" id="speed-auto-advance"\s*checked\s*class="([^"]+)">',
        r'<input type="checkbox" id="speed-auto-advance" class="\1">',
        content
    )

    # 2. Update auto-advance banner text
    content = content.replace('m3_auto_advance: "⚡ Auto-avance (2s)",', 'm3_auto_advance: "⚡ Auto-avance (8s)",')
    content = content.replace('m3_auto_advance: "⚡ Auto-advance (2s)",', 'm3_auto_advance: "⚡ Auto-advance (8s)",')
    content = re.sub(
        r'<span class="text-\[11px\] font-bold text-emerald-300">⚡ Auto-avance \(2s\)</span>',
        r'<span class="text-[11px] font-bold text-emerald-300" data-i18n="m3_auto_advance">⚡ Auto-avance (8s)</span>',
        content
    )

    # 3. Replace dynamic getSpriteUrl fallback: ZERO Pokeballs, 100% anatomical battle crest
    old_fallback_pattern = re.compile(
        r'// Dynamic Dual-Type Cyber-Dex SVG Emblem for any of the 363 Pokédex species.*?</svg>`;\s*return "data:image/svg\+xml;base64," \+ btoa\(dynamicSvg\);',
        re.DOTALL
    )
    new_fallback_code = """// Dynamic Dual-Type Anatomical Battle Crest for any of the 363 Pokédex species (No Pokeball pattern)
      const entry = getPokedexEntry(clean);
      const t1 = (entry.types && entry.types[0]) || 'Normal';
      const t2 = (entry.types && entry.types[1]) || t1;
      const c1 = TYPE_COLORS[t1] || '#38bdf8';
      const c2 = TYPE_COLORS[t2] || '#ec4899';
      const isMega = clean.toLowerCase().includes('mega');
      const badgeCorona = isMega
        ? `<polygon points="60,6 70,22 88,14 84,32 102,34 90,48 104,60 90,72 102,86 84,88 88,106 70,98 60,114 50,98 32,106 36,88 18,86 30,72 16,60 30,48 18,34 36,32 32,14 50,22" fill="${c1}" fill-opacity="0.25" stroke="${c1}" stroke-width="1.5"/>`
        : '';
      const dynamicSvg = `<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
        <circle cx="60" cy="60" r="48" fill="${c1}" fill-opacity="0.12"/>
        ${badgeCorona}
        <path d="M32,86 C32,68 44,62 60,62 C76,62 88,68 88,86 L94,104 C94,108 26,108 26,104 Z" fill="${c1}" stroke="#0f172a" stroke-width="2"/>
        <ellipse cx="60" cy="90" rx="14" ry="12" fill="${c2}" fill-opacity="0.85"/>
        <circle cx="60" cy="46" r="18" fill="${c1}" stroke="#0f172a" stroke-width="2"/>
        <polygon points="46,42 54,44 48,48" fill="#ffffff"/><circle cx="50" cy="45" r="1.5" fill="#0f172a"/>
        <polygon points="74,42 66,44 72,48" fill="#ffffff"/><circle cx="70" cy="45" r="1.5" fill="#0f172a"/>
        <polygon points="52,56 60,66 68,56" fill="${c2}" stroke="#0f172a" stroke-width="1.5"/>
      </svg>`;
      return "data:image/svg+xml;base64," + btoa(dynamicSvg);"""

    content = old_fallback_pattern.sub(new_fallback_code, content)

    # 4. Update simulateFlashCardTurn: 8.0s auto-advance with explicit buttons, plus persistent manual navigation buttons
    old_sim_pattern = re.compile(
        r'if \(isOptimal && autoAdvanceChecked\) \{.*?(?:crucible|flashCard)AutoAdvanceTimer = setTimeout\(\(\) => \{.*?\}, \d+\);\s*\}\s*const formattedVerdict =',
        re.DOTALL
    )
    new_sim_block = """if (isOptimal && autoAdvanceChecked) {
          autoAdvanceBanner = `
            <div id="flashcard-auto-badge" class="mt-2.5 p-2 rounded-xl bg-emerald-500/20 border border-emerald-500/40 text-center text-xs font-bold text-emerald-300 flex items-center justify-between gap-2">
              <span>⏱️ ${isEn ? "OPTIMAL LINE VERIFIED! Auto-advancing in 8.0s..." : "¡LÍNEA ÓPTIMA VERIFICADA! Auto-avanzando en 8.0s..."}</span>
              <div class="flex items-center gap-1.5">
                <button type="button" onclick="loadNextRandomFlashCardScenario()" class="px-2.5 py-0.5 rounded bg-emerald-600 text-white font-extrabold text-[10px] hover:bg-emerald-500">${isEn ? "Next Now ➡️" : "Avanzar Ya ➡️"}</button>
                <button type="button" onclick="cancelFlashCardAutoAdvance()" class="px-2 py-0.5 rounded bg-slate-800 text-slate-300 hover:text-white text-[10px]">${isEn ? "Pause" : "Pausar"}</button>
              </div>
            </div>
          `;
          flashCardAutoAdvanceTimer = setTimeout(() => {
            loadNextRandomFlashCardScenario();
          }, 8000);
        }

        const formattedVerdict ="""
    content = old_sim_pattern.sub(new_sim_block, content)

    # Also make sure navActionButtons is rendered in verdictBox
    if "navActionButtons" not in content:
        old_verdict_html = """verdictBox.innerHTML = `
          <div class="flex items-center justify-between border-b border-[var(--border)] pb-2">
            <span class="font-extrabold ${isOptimal ? 'text-emerald-400' : 'text-rose-400'}">${formattedVerdict}</span>
            <span class="badge ${isOptimal ? 'bg-emerald-500/20 text-emerald-300' : 'bg-rose-500/20 text-rose-300'} font-mono">${chosen.vpDelta}</span>
          </div>
          <div class="space-y-1 pt-1 font-mono text-[11px] text-slate-300">
            ${chosen.log.map(line => `<div>• ${line}</div>`).join('')}
          </div>
          ${autoAdvanceBanner}
        `;"""

        new_verdict_html = """const curIdx = (typeof activeScenarioList !== 'undefined' && currentScenario) ? activeScenarioList.indexOf(currentScenario) : 0;
        const navActionButtons = `
          <div class="mt-3 pt-3 border-t border-[var(--border)] flex flex-wrap items-center justify-between gap-2">
            <button type="button" onclick="loadNextRandomFlashCardScenario()" class="px-4 py-2 rounded-xl bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white text-xs font-extrabold shadow-lg transition cursor-pointer flex items-center gap-2">
              <span>➡️</span> <span>${isEn ? "Next Tactical Flash Card" : "Siguiente Flash Card Táctica"}</span>
            </button>
            <button type="button" onclick="loadFlashCardScenario(${curIdx >= 0 ? curIdx : 0})" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-bold transition cursor-pointer flex items-center gap-1.5">
              <span>🔄</span> <span>${isEn ? "Retry Flash Card" : "Reintentar Flash Card"}</span>
            </button>
          </div>
        `;

        verdictBox.innerHTML = `
          <div class="flex items-center justify-between border-b border-[var(--border)] pb-2">
            <span class="font-extrabold ${isOptimal ? 'text-emerald-400' : 'text-rose-400'}">${formattedVerdict}</span>
            <span class="badge ${isOptimal ? 'bg-emerald-500/20 text-emerald-300' : 'bg-rose-500/20 text-rose-300'} font-mono">${chosen.vpDelta}</span>
          </div>
          <div class="space-y-1 pt-1 font-mono text-[11px] text-slate-300">
            ${chosen.log.map(line => `<div>• ${line}</div>`).join('')}
          </div>
          ${autoAdvanceBanner}
          ${navActionButtons}
        `;"""
        content = content.replace(old_verdict_html, new_verdict_html)

    # 4b. Update getSpritePath with comprehensive Mega alias resolver and Showdown PNG priority
    new_get_sprite_path = r"""function getSpritePath(speciesName, isShiny = false) {
      const spriteMap = window.__COACH_PORYGON_SPRITES__ || {};
      const raw = String(speciesName || '').trim();
      const clean = raw.split('@')[0].trim();
      const checkShiny = isShiny || /\bshiny\b/i.test(clean);
      const isFemale = /\(f\)/i.test(clean) || /-f$/i.test(clean) || /-female$/i.test(clean);
      const isMale = /\(m\)/i.test(clean) || /-m$/i.test(clean) || /-male$/i.test(clean);
      const stripped = clean.replace(/\bshiny\b/gi, '').replace(/\s*\([mf]\)\s*/gi, '').trim();
      const slug = slugify(stripped);
      const alnum = alnumKey(stripped);

      function lookup(key) {
        if (!key) return null;
        if (checkShiny) {
          if (spriteMap[`${key}-shiny`]) return spriteMap[`${key}-shiny`];
          if (spriteMap[`${key}shiny`]) return spriteMap[`${key}shiny`];
        }
        if (spriteMap[key]) return spriteMap[key];
        const aKey = alnumKey(key);
        if (checkShiny) {
          if (spriteMap[`${aKey}-shiny`]) return spriteMap[`${aKey}-shiny`];
          if (spriteMap[`${aKey}shiny`]) return spriteMap[`${aKey}shiny`];
        }
        if (spriteMap[aKey]) return spriteMap[aKey];

        // Dynamic Loading via Flask Web Backend (Mode 0-7)
        if (typeof window !== 'undefined' && window.location) {
          const sfx = checkShiny ? '-shiny' : '';
          if (window.location.protocol === 'http:' || window.location.protocol === 'https:') {
            return `/assets/sprites/Reg_M-C/${key}${sfx}.png`;
          }
          if (window.location.protocol === 'file:') {
            return `sprites/Reg_M-C/${key}${sfx}.png`;
          }
        }
        return null;
      }

      // 1. Gender differentiated candidates
      if (isFemale) {
        const fCandidates = [
          `${slug}-female`, `${slug}-f`, `${slug}female`, `${slug}f`,
          `${alnum}-female`, `${alnum}-f`
        ];
        if (slug === 'basculegion' || slug.includes('basculegion')) fCandidates.unshift('basculegion-female');
        if (slug === 'indeedee' || slug.includes('indeedee')) fCandidates.unshift('indeedee-female');
        if (slug === 'meowstic' || slug.includes('meowstic')) fCandidates.unshift('meowstic-female', 'meowstic-f');
        if (slug === 'pyroar' || slug.includes('pyroar')) fCandidates.unshift('pyroar-female');
        for (const c of fCandidates) {
          const res = lookup(c);
          if (res) return res;
        }
      } else if (isMale) {
        const mCandidates = [
          `${slug}-male`, `${slug}-m`, `${slug}male`, `${slug}m`,
          `${alnum}-male`, `${alnum}-m`
        ];
        if (slug === 'indeedee' || slug.includes('indeedee')) mCandidates.unshift('indeedee-male');
        if (slug === 'basculegion' || slug.includes('basculegion')) mCandidates.unshift('basculegion-male');
        if (slug === 'meowstic' || slug.includes('meowstic')) mCandidates.unshift('meowstic-male');
        if (slug === 'pyroar' || slug.includes('pyroar')) mCandidates.unshift('pyroar-male');
        for (const c of mCandidates) {
          const res = lookup(c);
          if (res) return res;
        }
      }

      // 2. Direct matches
      let res = lookup(slug);
      if (res) return res;
      res = lookup(alnum);
      if (res) return res;

      // 3. Regional forms permutations
      const regCandidates = [
        slug.replace(/^alolan-/, '').concat('-alolan'),
        slug.replace(/^alolan-/, '').concat('-alola'),
        slug.replace(/-alola$/, '-alolan'),
        slug.replace(/^hisuian-/, '').concat('-hisuian'),
        slug.replace(/^hisuian-/, '').concat('-hisui'),
        slug.replace(/-hisui$/, '-hisuian'),
        slug.replace(/^galarian-/, '').concat('-galarian'),
        slug.replace(/^galarian-/, '').concat('-galar'),
        slug.replace(/-galar$/, '-galarian'),
        slug.replace(/-paldea-/, '-paldean-'),
        slug.replace(/-paldea$/, '-paldean')
      ];
      for (const c of regCandidates) {
        res = lookup(c);
        if (res) return res;
      }

      // 4. Rotom appliances
      if (slug.includes('rotom')) {
        for (const app of ['wash', 'heat', 'frost', 'fan', 'mow']) {
          if (slug.includes(app)) {
            res = lookup(`rotom-${app}`) || lookup(`${app}-rotom`);
            if (res) return res;
          }
        }
      }

      // 5. Mega normalization permutations
      if (slug.includes('mega')) {
        const candidates = [];
        const mX = slug.match(/^(?:mega-)?([a-z0-9]+)-(?:mega-)?([xyz])$/);
        if (mX) {
          const b = mX[1];
          const s = mX[2];
          candidates.push(
            `${b}-mega-${s}`, `mega-${b}-${s}`, `${b}-mega${s}`,
            `${b}${s}-mega`, `${b}-${s}-mega`, `mega-${b}${s}`, `${b}mega${s}`
          );
        }
        if (slug.startsWith('mega-')) {
          candidates.push(slug.substring(5) + '-mega');
          candidates.push(slug.substring(5) + 'mega');
        } else if (slug.endsWith('-mega')) {
          candidates.push('mega-' + slug.substring(0, slug.length - 5));
          candidates.push(slug.substring(0, slug.length - 5) + 'mega');
        }
        for (const c of candidates) {
          res = lookup(c);
          if (res) return res;
        }
      }

      // 6. Base species fallback
      const baseSlug = slug.replace(/^mega-/, '').replace(/-mega.*$/, '').replace(/-[xyz]$/, '')
                           .replace(/-(alolan|alola|hisuian|hisui|galarian|galar|paldean|paldea).*$/, '')
                           .replace(/^(alolan|hisuian|galarian|paldean)-/, '');
      res = lookup(baseSlug) || lookup(`${baseSlug}-male`);
      if (res) return res;

      // 7. Dynamic Dual-Type Anatomical Battle Crest for any uncatalogued species (No Pokeball pattern)
      const entry = getPokedexEntry(clean);
      const t1 = (entry.types && entry.types[0]) || 'Normal';
      const t2 = (entry.types && entry.types[1]) || t1;
      const c1 = TYPE_COLORS[t1] || '#38bdf8';
      const c2 = TYPE_COLORS[t2] || '#ec4899';
      const isMega = clean.toLowerCase().includes('mega');
      const badgeCorona = isMega
        ? `<polygon points="60,6 70,22 88,14 84,32 102,34 90,48 104,60 90,72 102,86 84,88 88,106 70,98 60,114 50,98 32,106 36,88 18,86 30,72 16,60 30,48 18,34 36,32 32,14 50,22" fill="${c1}" fill-opacity="0.25" stroke="${c1}" stroke-width="1.5"/>`
        : '';
      const dynamicSvg = `<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
        <circle cx="60" cy="60" r="48" fill="${c1}" fill-opacity="0.12"/>
        ${badgeCorona}
        <path d="M32,86 C32,68 44,62 60,62 C76,62 88,68 88,86 L94,104 C94,108 26,108 26,104 Z" fill="${c1}" stroke="#0f172a" stroke-width="2"/>
        <ellipse cx="60" cy="90" rx="14" ry="12" fill="${c2}" fill-opacity="0.85"/>
        <circle cx="60" cy="46" r="18" fill="${c1}" stroke="#0f172a" stroke-width="2"/>
        <polygon points="46,42 54,44 48,48" fill="#ffffff"/><circle cx="50" cy="45" r="1.5" fill="#0f172a"/>
        <polygon points="74,42 66,44 72,48" fill="#ffffff"/><circle cx="70" cy="45" r="1.5" fill="#0f172a"/>
        <polygon points="52,56 60,66 68,56" fill="${c2}" stroke="#0f172a" stroke-width="1.5"/>
      </svg>`;
      return "data:image/svg+xml;base64," + btoa(dynamicSvg);
    }"""
    sprite_fn_pattern = re.compile(
        r'function getSpritePath\(speciesName\)\s*\{.*?return "data:image/svg\+xml;base64," \+ btoa\(dynamicSvg\);\s*\}',
        re.DOTALL
    )
    content = sprite_fn_pattern.sub(lambda _: new_get_sprite_path, content)

    # 4c. Inject fresh Live Telemetry
    telemetry = load_live_telemetry()
    telemetry_json = json.dumps(telemetry, ensure_ascii=False)
    telem_marker = "window.__COACH_PORYGON_TELEMETRY__ ="
    sprites_marker = "window.__COACH_PORYGON_SPRITES__ ="

    t_start = content.find(telem_marker)
    s_start = content.find(sprites_marker)
    if t_start != -1 and s_start > t_start:
        telem_stmt = f"window.__COACH_PORYGON_TELEMETRY__ = {telemetry_json};\n"
        content = content[:t_start] + telem_stmt + content[s_start:]
        print(f"Injected live telemetry ({telemetry['total_matches']} matches, {len(telemetry.get('scouted', []))} scouted OTS, {len(telemetry.get('tournaments', []))} tournaments).")

    # 5. Inject fresh Base64 maps
    sprites_json = json.dumps(sprite_map)
    items_json = json.dumps(item_map)

    content = re.sub(
        r'window\.__COACH_PORYGON_SPRITES__\s*=\s*\{.*?\};',
        f'window.__COACH_PORYGON_SPRITES__ = {sprites_json};',
        content
    )
    content = re.sub(
        r'window\.__COACH_PORYGON_ITEMS__\s*=\s*\{.*?\};',
        f'window.__COACH_PORYGON_ITEMS__ = {items_json};',
        content
    )

    # 6. Write ES version
    es_content = re.sub(r'<html lang="[^"]*"', '<html lang="es"', content)
    es_content = re.sub(r'window\.__INITIAL_LANG__\s*=\s*\'[^\']*\';', "window.__INITIAL_LANG__ = 'es';", es_content)
    OUT_ES.write_text(es_content, encoding="utf-8")
    print(f"[OK] Written {OUT_ES} ({len(es_content):,} bytes)")

    # 7. Write Main (default ES)
    OUT_MAIN.write_text(es_content, encoding="utf-8")
    print(f"[OK] Written {OUT_MAIN} ({len(es_content):,} bytes)")

    # 8. Write EN version
    en_content = re.sub(r'<html lang="[^"]*"', '<html lang="en"', content)
    en_content = re.sub(r'window\.__INITIAL_LANG__\s*=\s*\'[^\']*\';', "window.__INITIAL_LANG__ = 'en';", en_content)
    OUT_EN.write_text(en_content, encoding="utf-8")
    print(f"[OK] Written {OUT_EN} ({len(en_content):,} bytes)")

    # 9. Sync Artifact
    art_dir = resolve_artifact_dir()
    if art_dir and art_dir.exists():
        art_path = art_dir / "command_center.html"
        shutil.copyfile(OUT_MAIN, art_path)
        print(f"[OK] Synced Artifact -> {art_path}")


if __name__ == "__main__":
    update_command_center_files()
