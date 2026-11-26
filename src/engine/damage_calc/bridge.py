# -*- coding: utf-8 -*-
"""Hermetic In-Process Python Bridge for Official `smogon/damage-calc` (Champions Reg M-C).

Loads `vendor/smogon_calc_champions.js` once into a thread-safe embedded JS sandbox
(`mini-racer` V8 primary, `quickjs` automatic fallback) so Coach Porygon VGC can run
batched cartridge-exact 16-roll damage calculations (~10,000+ calcs/sec) without
requiring Node.js or external network access at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional, Sequence, Tuple

VENDOR_DIR = Path(__file__).resolve().parent / "vendor"
BUNDLE_PATH = VENDOR_DIR / "smogon_calc_champions.js"
BUILD_META_PATH = VENDOR_DIR / "BUILD_META.json"

_WEATHER_NORMALIZE: Dict[str, str] = {
    "sun": "Sun",
    "sunnyday": "Sun",
    "desolateland": "Sun",
    "rain": "Rain",
    "raindance": "Rain",
    "primordialsea": "Rain",
    "sand": "Sand",
    "sandstorm": "Sand",
    "snow": "Snow",
    "snowscape": "Snow",
    "hail": "Snow",  # Legacy Showdown replay compatibility
}

_TERRAIN_NORMALIZE: Dict[str, str] = {
    "electric": "Electric",
    "electricterrain": "Electric",
    "grassy": "Grassy",
    "grassyterrain": "Grassy",
    "psychic": "Psychic",
    "psychicterrain": "Psychic",
    "misty": "Misty",
    "mistyterrain": "Misty",
}

_SPECIES_ALIASES: Dict[str, str] = {
    "Aegislash": "Aegislash-Shield",
    "Maushold-Three": "Maushold",
    "Maushold-Four": "Maushold",
    "Squawkabilly-Blue": "Squawkabilly",
    "Squawkabilly-Yellow": "Squawkabilly",
    "Squawkabilly-White": "Squawkabilly",
    "Indeedee-M": "Indeedee",
    "Meowstic-M": "Meowstic",
    "Basculegion-M": "Basculegion",
    "Palafin-Zero": "Palafin",
    "Mimikyu-Disguised": "Mimikyu",
}


def _normalize_species_for_smogon(species: str) -> str:
    """Normalize Showdown / DuckDB species strings to `@smogon/calc` Champions names."""
    clean = (species or "").replace("\u2019", "'").replace("\u2018", "'").strip()
    if clean in _SPECIES_ALIASES:
        return _SPECIES_ALIASES[clean]
    if clean.startswith("Mega "):
        return f"{clean[5:].strip()}-Mega"
    return clean


def _normalize_weather(weather: Optional[str]) -> Optional[str]:
    if not weather:
        return None
    key = "".join(ch for ch in weather.lower() if ch.isalnum())
    return _WEATHER_NORMALIZE.get(key, weather)


def _normalize_terrain(terrain: Optional[str]) -> Optional[str]:
    if not terrain:
        return None
    key = "".join(ch for ch in terrain.lower() if ch.isalnum())
    return _TERRAIN_NORMALIZE.get(key, terrain)


@dataclass(frozen=True)
class CalcPokemonSpec:
    """Champions Regulation M-C Pokémon specification using 66-SP allocations (0..32)."""

    species: str
    item: Optional[str] = None
    ability: Optional[str] = None
    ability_on: bool = False
    nature: str = "Serious"
    gender: Optional[str] = None
    level: int = 50
    sp: Dict[str, int] = field(default_factory=dict)
    boosts: Dict[str, int] = field(default_factory=dict)
    status: Optional[str] = None
    cur_hp: Optional[int] = None
    cur_hp_pct: Optional[float] = None
    allies_fainted: int = 0

    def to_payload(self, spa_boost_offset: int = 0) -> Dict[str, Any]:
        """Serialize into the JSON format expected by `smogon_calc_champions.js`."""
        sp_clean = {
            "hp": int(self.sp.get("hp", 0)),
            "atk": int(self.sp.get("atk", 0)),
            "def": int(self.sp.get("def", self.sp.get("def_", 0))),
            "spa": int(self.sp.get("spa", 0)),
            "spd": int(self.sp.get("spd", 0)),
            "spe": int(self.sp.get("spe", 0)),
        }
        boosts_clean = {
            "atk": int(self.boosts.get("atk", 0)),
            "def": int(self.boosts.get("def", 0)),
            "spa": max(-6, min(6, int(self.boosts.get("spa", 0)) + spa_boost_offset)),
            "spd": int(self.boosts.get("spd", 0)),
            "spe": int(self.boosts.get("spe", 0)),
        }
        payload: Dict[str, Any] = {
            "species": _normalize_species_for_smogon(self.species),
            "nature": self.nature or "Serious",
            "level": int(self.level or 50),
            "sp": sp_clean,
            "boosts": boosts_clean,
        }
        if self.item:
            payload["item"] = self.item
        if self.ability:
            payload["ability"] = self.ability
        if self.ability_on:
            payload["abilityOn"] = True
        if self.gender in ("M", "F", "N"):
            payload["gender"] = self.gender
        if self.status:
            payload["status"] = self.status
        if self.cur_hp is not None and self.cur_hp > 0:
            payload["curHP"] = int(self.cur_hp)
        elif self.cur_hp_pct is not None and 0.0 < self.cur_hp_pct < 100.0:
            payload["curHPPct"] = float(self.cur_hp_pct)
        if self.allies_fainted > 0:
            payload["alliesFainted"] = int(self.allies_fainted)
        return payload


@dataclass(frozen=True)
class CalcSideSpec:
    """Side-specific field conditions (Screens, Helping Hand, Friend Guard, Tailwind)."""

    is_reflect: bool = False
    is_light_screen: bool = False
    is_aurora_veil: bool = False
    is_helping_hand: bool = False
    is_friend_guard: bool = False
    is_tailwind: bool = False
    is_protected: bool = False
    is_battery: bool = False
    is_power_spot: bool = False
    is_steely_spirit: bool = False

    def to_payload(self) -> Dict[str, bool]:
        return {
            "isReflect": self.is_reflect,
            "isLightScreen": self.is_light_screen,
            "isAuroraVeil": self.is_aurora_veil,
            "isHelpingHand": self.is_helping_hand,
            "isFriendGuard": self.is_friend_guard,
            "isTailwind": self.is_tailwind,
            "isProtected": self.is_protected,
            "isBattery": self.is_battery,
            "isPowerSpot": self.is_power_spot,
            "isSteelySpirit": self.is_steely_spirit,
        }


@dataclass(frozen=True)
class CalcFieldSpec:
    """Global & side battle field conditions for Champions Doubles/Singles."""

    game_type: str = "Doubles"
    weather: Optional[str] = None
    terrain: Optional[str] = None
    is_gravity: bool = False
    is_fairy_aura: bool = False
    is_dark_aura: bool = False
    is_aura_break: bool = False
    attacker_side: CalcSideSpec = field(default_factory=CalcSideSpec)
    defender_side: CalcSideSpec = field(default_factory=CalcSideSpec)

    def to_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "gameType": self.game_type,
            "isGravity": self.is_gravity,
            "isFairyAura": self.is_fairy_aura,
            "isDarkAura": self.is_dark_aura,
            "isAuraBreak": self.is_aura_break,
            "attackerSide": self.attacker_side.to_payload(),
            "defenderSide": self.defender_side.to_payload(),
        }
        w = _normalize_weather(self.weather)
        t = _normalize_terrain(self.terrain)
        if w:
            payload["weather"] = w
        if t:
            payload["terrain"] = t
        return payload


@dataclass(frozen=True)
class CalcMoveSpec:
    """Move execution context for damage evaluation."""

    name: str
    is_crit: bool = False
    hits: Optional[int] = None
    force_single_target: bool = False
    boosts_already_include_charge_spa: bool = False
    overrides: Dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "name": self.name,
            "isCrit": self.is_crit,
            "forceSingleTarget": self.force_single_target,
        }
        if self.hits is not None and self.hits > 0:
            payload["hits"] = int(self.hits)
        if self.overrides:
            payload["overrides"] = dict(self.overrides)
        return payload


@dataclass(frozen=True)
class DamageCalcRequest:
    """Single attacker -> defender move evaluation request."""

    attacker: CalcPokemonSpec
    defender: CalcPokemonSpec
    move: CalcMoveSpec
    field: CalcFieldSpec = field(default_factory=CalcFieldSpec)

    def to_payload(self) -> Dict[str, Any]:
        # `calculateChampions` auto-adds +1 SpA (or -1 with Contrary) for Electro Shot /
        # Meteor Beam. Compensate when live replay boosts already include that +1 stage.
        spa_offset = 0
        if (
            self.move.boosts_already_include_charge_spa
            and self.move.name in ("Electro Shot", "Meteor Beam")
        ):
            spa_offset = 1 if self.attacker.ability == "Contrary" else -1
        return {
            "attacker": self.attacker.to_payload(spa_boost_offset=spa_offset),
            "defender": self.defender.to_payload(),
            "move": self.move.to_payload(),
            "field": self.field.to_payload(),
        }


@dataclass(frozen=True)
class DamageCalcResult:
    """Exact 16-roll cartridge damage output from `smogon/damage-calc` Champions."""

    ok: bool
    rolls_16: Tuple[int, ...]
    attacker_max_hp: int
    defender_max_hp: int
    attacker_stats: Dict[str, int] = field(default_factory=dict)
    defender_stats: Dict[str, int] = field(default_factory=dict)
    attacker_eff_spe: int = 0
    defender_eff_spe: int = 0
    per_hit_rolls: Optional[Tuple[Tuple[int, ...], ...]] = None
    recoil: Optional[Tuple[int, int]] = None
    drain: Optional[Tuple[int, int]] = None
    error: Optional[str] = None

    @property
    def min_damage(self) -> int:
        return self.rolls_16[0] if self.rolls_16 else 0

    @property
    def max_damage(self) -> int:
        return self.rolls_16[-1] if self.rolls_16 else 0


@dataclass(frozen=True)
class SpeedCalcRequest:
    """Single effective-speed evaluation request under Champions mechanics."""

    pokemon: CalcPokemonSpec
    field: CalcFieldSpec = field(default_factory=CalcFieldSpec)
    side: str = "attacker"

    def to_payload(self) -> Dict[str, Any]:
        return {
            "pokemon": self.pokemon.to_payload(),
            "field": self.field.to_payload(),
            "side": self.side,
        }


@dataclass(frozen=True)
class SpeedCalcResult:
    """Official Champions effective Speed and raw Level 50 stats."""

    ok: bool
    eff_spe: int
    raw_stats: Dict[str, int] = field(default_factory=dict)
    error: Optional[str] = None


class SmogonChampionsCalc:
    """Thread-safe in-process runner for the vendored `smogon/damage-calc` Champions bundle."""

    def __init__(
        self,
        bundle_path: Path = BUNDLE_PATH,
        preferred_runtime: Optional[str] = None,
    ) -> None:
        self.bundle_path = Path(bundle_path)
        if not self.bundle_path.exists():
            raise FileNotFoundError(
                f"Vendored Smogon Champions calc bundle missing at {self.bundle_path}. "
                "Run `python3 scripts/build_smogon_calc.py` to regenerate it."
            )
        self._lock = threading.Lock()
        self._runtime_name: str = ""
        self._ctx: Any = None
        self._init_runtime(preferred_runtime)

    def _init_runtime(self, preferred_runtime: Optional[str]) -> None:
        code = self.bundle_path.read_text(encoding="utf-8")
        order = (
            [preferred_runtime]
            if preferred_runtime in ("mini_racer", "quickjs")
            else ["mini_racer", "quickjs"]
        )
        errors: List[str] = []
        for rt in order:
            if rt == "mini_racer":
                try:
                    from py_mini_racer import MiniRacer

                    ctx = MiniRacer()
                    ctx.eval(code)
                    if ctx.eval("Boolean(globalThis.__COACH_PORYGON_CALC_READY__)"):
                        self._ctx = ctx
                        self._runtime_name = "mini_racer"
                        return
                except Exception as exc:
                    errors.append(f"mini_racer: {exc}")
            elif rt == "quickjs":
                try:
                    import quickjs

                    ctx = quickjs.Context()
                    ctx.eval(code)
                    if ctx.eval("Boolean(globalThis.__COACH_PORYGON_CALC_READY__)"):
                        self._ctx = ctx
                        self._runtime_name = "quickjs"
                        return
                except Exception as exc:
                    errors.append(f"quickjs: {exc}")

        raise RuntimeError(
            "Unable to initialize embedded JS runtime for Smogon Champions calc. "
            f"Install `mini-racer` or `quickjs` in your virtualenv. Details: {'; '.join(errors)}"
        )

    @property
    def runtime_name(self) -> str:
        """Active sandboxed JS runtime (`mini_racer` or `quickjs`)."""
        return self._runtime_name

    def get_build_metadata(self) -> Dict[str, Any]:
        """Return pinned upstream commit/version provenance from `BUILD_META.json`."""
        if BUILD_META_PATH.exists():
            try:
                return json.loads(BUILD_META_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"bundle_file": self.bundle_path.name}

    def _invoke_json_fn(self, fn_name: str, payload_obj: Any) -> Any:
        raw_in = json.dumps(payload_obj, separators=(",", ":"))
        with self._lock:
            if self._runtime_name == "mini_racer":
                raw_out = self._ctx.call(fn_name, raw_in)
            else:
                raw_out = self._ctx.eval(f"{fn_name}({json.dumps(raw_in)})")
        return json.loads(raw_out)

    def calculate_batch(
        self, requests: Sequence[DamageCalcRequest]
    ) -> List[DamageCalcResult]:
        """Execute a batch of Champions damage calculations in a single JS call."""
        if not requests:
            return []
        payload = [r.to_payload() for r in requests]
        rows = self._invoke_json_fn("calculateChampionsBatch", payload)
        out: List[DamageCalcResult] = []
        for row in rows:
            rolls = tuple(int(v) for v in (row.get("rolls") or [0] * 16))
            raw_phr = row.get("perHitRolls")
            per_hit = (
                tuple(tuple(int(v) for v in hit_arr) for hit_arr in raw_phr)
                if raw_phr
                else None
            )
            raw_rec = row.get("recoil")
            recoil = (
                (int(raw_rec[0]), int(raw_rec[1]))
                if isinstance(raw_rec, list) and len(raw_rec) == 2
                else None
            )
            raw_dr = row.get("drain")
            drain = (
                (int(raw_dr[0]), int(raw_dr[1]))
                if isinstance(raw_dr, list) and len(raw_dr) == 2
                else None
            )
            out.append(
                DamageCalcResult(
                    ok=bool(row.get("ok")),
                    rolls_16=rolls,
                    attacker_max_hp=int(row.get("attackerMaxHP") or 0),
                    defender_max_hp=int(row.get("defenderMaxHP") or 0),
                    attacker_stats={
                        str(k): int(v) for k, v in (row.get("attackerStats") or {}).items()
                    },
                    defender_stats={
                        str(k): int(v) for k, v in (row.get("defenderStats") or {}).items()
                    },
                    attacker_eff_spe=int(row.get("attackerEffSpe") or 0),
                    defender_eff_spe=int(row.get("defenderEffSpe") or 0),
                    per_hit_rolls=per_hit,
                    recoil=recoil,
                    drain=drain,
                    error=row.get("error"),
                )
            )
        return out

    def calculate_one(self, request: DamageCalcRequest) -> DamageCalcResult:
        """Convenience wrapper for a single damage calculation."""
        return self.calculate_batch([request])[0]

    def calculate_effective_speeds(
        self, requests: Sequence[SpeedCalcRequest]
    ) -> List[SpeedCalcResult]:
        """Compute official Champions effective Speed & L50 stats for a batch of specs."""
        if not requests:
            return []
        payload = [r.to_payload() for r in requests]
        rows = self._invoke_json_fn("calcChampionsEffectiveSpeedBatch", payload)
        return [
            SpeedCalcResult(
                ok=bool(row.get("ok")),
                eff_spe=int(row.get("effSpe") or 0),
                raw_stats={str(k): int(v) for k, v in (row.get("rawStats") or {}).items()},
                error=row.get("error"),
            )
            for row in rows
        ]


_SHARED_CALC: Optional[SmogonChampionsCalc] = None
_SHARED_LOCK = threading.Lock()


def get_champions_calc() -> SmogonChampionsCalc:
    """Return the process-wide shared `SmogonChampionsCalc` singleton."""
    global _SHARED_CALC
    if _SHARED_CALC is None:
        with _SHARED_LOCK:
            if _SHARED_CALC is None:
                _SHARED_CALC = SmogonChampionsCalc()
    return _SHARED_CALC
