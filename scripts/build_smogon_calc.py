#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dev-only upstream compiler for Coach Porygon VGC's vendored Smogon Champions Damage Calc.

Compiles upstream `smogon/damage-calc` (`calc/src/mechanics/champions.ts` + Gen 0
Champions data) into a single, self-contained, tree-shaken offline JavaScript bundle:
    src/engine/damage_calc/vendor/smogon_calc_champions.js

End users NEVER need to run this script or install Node.js/esbuild — Python executes
the committed bundle strictly in-process inside a hermetic V8/QuickJS sandbox
(`src/engine/damage_calc/bridge.py`).

Usage:
    python3 scripts/build_smogon_calc.py
    python3 scripts/build_smogon_calc.py --source-dir /tmp/smogon-damage-calc-src
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess

REPO_ROOT = Path(__file__).resolve().parent.parent
VENDOR_DIR = REPO_ROOT / "src" / "engine" / "damage_calc" / "vendor"
UPSTREAM_REPO = "https://github.com/smogon/damage-calc.git"

BRIDGE_ENTRYPOINT_TS = r"""
// Tree-shaken Champions-only entrypoint for Coach Porygon VGC.
// Imports ONLY calculateChampions + Gen 0 (Pokémon Champions) data so esbuild
// strips Gen 1..9 legacy battle mechanics out of the offline bundle.
import {Generations} from './calc/src/data';
import {Field} from './calc/src/field';
import {Move} from './calc/src/move';
import {Pokemon} from './calc/src/pokemon';
import {calculateChampions} from './calc/src/mechanics/champions';
import {getFinalSpeed} from './calc/src/mechanics/util';

const GEN_CHAMPIONS = Generations.get(0);

interface CalcPokemonInput {
  species: string;
  item?: string | null;
  ability?: string | null;
  abilityOn?: boolean;
  nature?: string | null;
  gender?: 'M' | 'F' | 'N' | null;
  level?: number;
  sp?: {hp?: number; atk?: number; def?: number; spa?: number; spd?: number; spe?: number};
  boosts?: {atk?: number; def?: number; spa?: number; spd?: number; spe?: number};
  status?: string | null;
  curHP?: number | null;
  curHPPct?: number | null;
  alliesFainted?: number;
}

interface CalcSideInput {
  isReflect?: boolean;
  isLightScreen?: boolean;
  isAuroraVeil?: boolean;
  isHelpingHand?: boolean;
  isFriendGuard?: boolean;
  isTailwind?: boolean;
  isProtected?: boolean;
  isBattery?: boolean;
  isPowerSpot?: boolean;
  isSteelySpirit?: boolean;
}

interface CalcFieldInput {
  gameType?: 'Singles' | 'Doubles';
  weather?: string | null;
  terrain?: string | null;
  isGravity?: boolean;
  isFairyAura?: boolean;
  isDarkAura?: boolean;
  isAuraBreak?: boolean;
  attackerSide?: CalcSideInput;
  defenderSide?: CalcSideInput;
}

interface CalcMoveInput {
  name: string;
  isCrit?: boolean;
  hits?: number;
  forceSingleTarget?: boolean;
  overrides?: Record<string, any>;
}

interface CalcRequest {
  attacker: CalcPokemonInput;
  defender: CalcPokemonInput;
  move: CalcMoveInput;
  field?: CalcFieldInput;
}

function buildPokemon(spec: CalcPokemonInput): Pokemon {
  const sp = spec.sp || {};
  const opts: Record<string, any> = {
    level: spec.level || 50,
    nature: spec.nature || 'Serious',
    evs: {
      hp: sp.hp || 0,
      atk: sp.atk || 0,
      def: sp.def || 0,
      spa: sp.spa || 0,
      spd: sp.spd || 0,
      spe: sp.spe || 0,
    },
    boosts: spec.boosts || {},
  };
  if (spec.item) opts.item = spec.item;
  if (spec.ability) opts.ability = spec.ability;
  if (spec.abilityOn) opts.abilityOn = true;
  if (spec.gender) opts.gender = spec.gender;
  if (spec.status) opts.status = spec.status;
  if (typeof spec.alliesFainted === 'number') opts.alliesFainted = spec.alliesFainted;
  const mon = new Pokemon(GEN_CHAMPIONS, spec.species, opts);
  if (typeof spec.curHP === 'number' && spec.curHP > 0) {
    mon.originalCurHP = Math.min(mon.rawStats.hp, Math.max(1, Math.floor(spec.curHP)));
  } else if (typeof spec.curHPPct === 'number' && spec.curHPPct > 0 && spec.curHPPct < 100) {
    mon.originalCurHP = Math.max(1, Math.round((mon.rawStats.hp * spec.curHPPct) / 100));
  }
  return mon;
}

function buildField(f?: CalcFieldInput): Field {
  const cfg = f || {};
  const opts: Record<string, any> = {
    gameType: cfg.gameType || 'Doubles',
    isGravity: !!cfg.isGravity,
    isFairyAura: !!cfg.isFairyAura,
    isDarkAura: !!cfg.isDarkAura,
    isAuraBreak: !!cfg.isAuraBreak,
    attackerSide: cfg.attackerSide || {},
    defenderSide: cfg.defenderSide || {},
  };
  if (cfg.weather) opts.weather = cfg.weather;
  if (cfg.terrain) opts.terrain = cfg.terrain;
  return new Field(opts);
}

function normalizeRolls(dmg: any): {rolls: number[]; perHitRolls: number[][] | null} {
  if (typeof dmg === 'number') {
    const arr = new Array(16).fill(dmg);
    return {rolls: arr, perHitRolls: null};
  }
  if (Array.isArray(dmg) && dmg.length > 0) {
    if (Array.isArray(dmg[0])) {
      // Multi-hit / Parental Bond array of roll arrays -> sum element-wise for min/max & keep per-hit
      const perHit = dmg as number[][];
      const summed = new Array(16).fill(0);
      for (const hitArr of perHit) {
        for (let i = 0; i < 16; i++) {
          summed[i] += hitArr[Math.min(i, hitArr.length - 1)] || 0;
        }
      }
      return {rolls: summed, perHitRolls: perHit};
    }
    const nums = dmg as number[];
    if (nums.length === 16) {
      return {rolls: nums, perHitRolls: null};
    }
    const out = new Array(16).fill(nums[0] || 0);
    for (let i = 0; i < Math.min(16, nums.length); i++) out[i] = nums[i];
    return {rolls: out, perHitRolls: null};
  }
  return {rolls: new Array(16).fill(0), perHitRolls: null};
}

function calculateChampionsBatch(requestsJson: string): string {
  const reqs: CalcRequest[] = JSON.parse(requestsJson);
  const results = new Array(reqs.length);
  for (let idx = 0; idx < reqs.length; idx++) {
    const r = reqs[idx];
    try {
      const attacker = buildPokemon(r.attacker);
      const defender = buildPokemon(r.defender);
      const field = buildField(r.field);
      const mvOpts: Record<string, any> = {
        ability: attacker.ability,
        item: attacker.item,
        isCrit: !!r.move.isCrit,
      };
      if (typeof r.move.hits === 'number' && r.move.hits > 0) {
        mvOpts.hits = r.move.hits;
      }
      const overrides: Record<string, any> = Object.assign({}, r.move.overrides || {});
      if (r.move.forceSingleTarget) {
        // Disables Doubles 0.75x spread penalty while preserving Doubles Reflect/Light Screen (2732/4096)
        overrides.target = 'normal';
      }
      if (Object.keys(overrides).length > 0) {
        mvOpts.overrides = overrides;
      }
      const move = new Move(GEN_CHAMPIONS, r.move.name, mvOpts);
      const res = calculateChampions(GEN_CHAMPIONS, attacker, defender, move, field);
      const {rolls, perHitRolls} = normalizeRolls(res.damage);
      results[idx] = {
        ok: true,
        rolls,
        perHitRolls,
        attackerMaxHP: res.attacker.maxHP(),
        defenderMaxHP: res.defender.maxHP(),
        attackerStats: res.attacker.rawStats,
        defenderStats: res.defender.rawStats,
        attackerEffSpe: res.attacker.stats.spe,
        defenderEffSpe: res.defender.stats.spe,
        recoil: move.recoil || null,
        drain: move.drain || null,
      };
    } catch (err: any) {
      results[idx] = {
        ok: false,
        error: String(err && err.message ? err.message : err),
        rolls: new Array(16).fill(0),
        perHitRolls: null,
        attackerMaxHP: 0,
        defenderMaxHP: 0,
      };
    }
  }
  return JSON.stringify(results);
}

function calcChampionsEffectiveSpeedBatch(requestsJson: string): string {
  const reqs: Array<{pokemon: CalcPokemonInput; field?: CalcFieldInput; side?: 'attacker' | 'defender'}> = JSON.parse(requestsJson);
  const out = new Array(reqs.length);
  for (let i = 0; i < reqs.length; i++) {
    const r = reqs[i];
    try {
      const mon = buildPokemon(r.pokemon);
      const field = buildField(r.field);
      const side = r.side === 'defender' ? field.defenderSide : field.attackerSide;
      const effSpe = getFinalSpeed(GEN_CHAMPIONS, mon, field, side);
      out[i] = {
        ok: true,
        rawStats: mon.rawStats,
        effSpe,
      };
    } catch (err: any) {
      out[i] = {ok: false, error: String(err && err.message ? err.message : err), effSpe: 0};
    }
  }
  return JSON.stringify(out);
}

(globalThis as any).calculateChampionsBatch = calculateChampionsBatch;
(globalThis as any).calcChampionsEffectiveSpeedBatch = calcChampionsEffectiveSpeedBatch;
(globalThis as any).__COACH_PORYGON_CALC_READY__ = true;
"""


def find_esbuild(explicit_path: str | None) -> Path:
    """Locate standalone esbuild binary."""
    candidates: list[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path))
    which_esbuild = shutil.which("esbuild")
    if which_esbuild:
        candidates.append(Path(which_esbuild))
    candidates.extend(
        [
            Path("/tmp/esbuild-bin/package/bin/esbuild"),
            REPO_ROOT / "node_modules" / ".bin" / "esbuild",
        ]
    )
    for cand in candidates:
        if cand.exists() and cand.is_file():
            return cand
    raise FileNotFoundError(
        "esbuild binary not found. Pass --esbuild /path/to/esbuild or install esbuild."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile tree-shaken Champions-only offline bundle from smogon/damage-calc."
    )
    parser.add_argument(
        "--source-dir",
        type=str,
        default="/tmp/smogon-damage-calc-src",
        help="Path to local smogon/damage-calc checkout (cloned automatically if missing).",
    )
    parser.add_argument(
        "--esbuild",
        type=str,
        default=None,
        help="Path to esbuild binary (auto-detected from PATH or /tmp/esbuild-bin).",
    )
    args = parser.parse_args()

    src_dir = Path(args.source_dir)
    if not (src_dir / "calc" / "src" / "mechanics" / "champions.ts").exists():
        print(f"[build_smogon_calc] Cloning {UPSTREAM_REPO} into {src_dir}...")
        subprocess.run(
            ["git", "clone", "--depth", "1", UPSTREAM_REPO, str(src_dir)],
            check=True,
        )

    esbuild_bin = find_esbuild(args.esbuild)
    VENDOR_DIR.mkdir(parents=True, exist_ok=True)
    out_bundle = VENDOR_DIR / "smogon_calc_champions.js"

    # Write temporary entrypoint inside src_dir so relative imports resolve natively
    entry_file = src_dir / "_coach_porygon_champions_entry.ts"
    try:
        entry_file.write_text(BRIDGE_ENTRYPOINT_TS, encoding="utf-8")
        cmd = [
            str(esbuild_bin),
            str(entry_file),
            "--bundle",
            "--minify",
            "--format=iife",
            "--target=es2020",
            f"--outfile={out_bundle}",
        ]
        print("[build_smogon_calc] Running:", " ".join(cmd))
        subprocess.run(cmd, check=True)
    finally:
        if entry_file.exists():
            entry_file.unlink()

    # Copy upstream MIT license
    upstream_license = src_dir / "LICENSE"
    if upstream_license.exists():
        shutil.copy2(upstream_license, VENDOR_DIR / "LICENSE.smogon-damage-calc")

    # Record provenance metadata
    commit_sha = "unknown"
    try:
        commit_sha = subprocess.check_output(
            ["git", "-C", str(src_dir), "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception:
        pass

    pkg_version = "unknown"
    pkg_json = src_dir / "calc" / "package.json"
    if pkg_json.exists():
        try:
            pkg_version = str(json.loads(pkg_json.read_text(encoding="utf-8")).get("version", "unknown"))
        except Exception:
            pass

    meta = {
        "upstream_repo": UPSTREAM_REPO,
        "upstream_commit": commit_sha,
        "calc_version": pkg_version,
        "bundle_file": out_bundle.name,
        "bundle_bytes": out_bundle.stat().st_size,
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (VENDOR_DIR / "BUILD_META.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"[build_smogon_calc] Done! Bundle: {out_bundle} ({out_bundle.stat().st_size / 1024:.1f} KB), "
        f"commit={commit_sha[:12]}, version={pkg_version}"
    )


if __name__ == "__main__":
    main()
