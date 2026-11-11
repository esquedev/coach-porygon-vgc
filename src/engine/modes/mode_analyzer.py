# -*- coding: utf-8 -*-
"""Regulation M-C Team Modes & Lead Combinatorics Analyzer.

Computes exhaustive mathematical analysis of all 15 4-mon modes and 15 lead pairs
for a 6-Pokémon Regulation M-C roster.
Evaluates offensive type coverage, defensive synergy, speed control availability,
disruption tools, and Turn 1 lead initiative with strict move-grounding (zero hallucination).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import itertools
from typing import Dict, List, Optional, Set, Tuple

from engine.db_registry import VGCDataRegistry, get_registry
from engine.game_rules import NATURE_MODS, TYPE_CHART
from engine.parser.models import ParsedPokemon
from engine.parser.showdown_parser import parse_showdown_paste

ALL_TYPES: List[str] = [
    "Normal", "Fire", "Water", "Grass", "Electric", "Ice",
    "Fighting", "Poison", "Ground", "Flying", "Psychic", "Bug",
    "Rock", "Ghost", "Dragon", "Dark", "Steel", "Fairy",
]

SCREEN_MOVES: Set[str] = {"reflect", "light screen", "aurora veil"}
PIVOT_MOVES: Set[str] = {"volt switch", "parting shot", "u-turn", "flip turn", "chilly reception", "shed tail"}
PRIORITY_ATTACK_MOVES: Set[str] = {
    "fake out", "sucker punch", "extreme speed", "aqua jet", "mach punch",
    "bullet punch", "ice shard", "shadow sneak", "grassy glide", "first impression",
    "quick attack", "feint", "water shuriken", "vacuum wave",
}


@dataclass
class TeamMemberData:
    """Canonical game data and mechanical traits for a single roster member."""

    slot_index: int
    name: str
    species: str
    canonical_species: str
    item: str
    ability: str
    nature: str
    moves: List[str]
    types: List[str]
    base_stats: Dict[str, int]
    effective_stats: Dict[str, int]
    is_mega: bool = False
    mega_form: Optional[str] = None
    offensive_types: Set[str] = field(default_factory=set)

    def has_move(self, move_name: str) -> bool:
        """Returns True if this Pokémon strictly knows the given move."""
        target = move_name.strip().lower()
        return any(m.strip().lower() == target for m in self.moves)


@dataclass
class TeamMode:
    """A 4-Pokémon combination (mode/mini-core) from a 6-member team."""

    mode_id: int  # 1 to 15
    slot_indices: Tuple[int, int, int, int]
    members: List[TeamMemberData]
    name: str
    description: str


@dataclass
class LeadPair:
    """A 2-Pokémon lead combination."""

    lead_id: int  # 1 to 15
    slot_indices: Tuple[int, int]
    pokemon_1: TeamMemberData
    pokemon_2: TeamMemberData

    def get_verified_moves(self) -> Dict[str, List[str]]:
        """Returns the exact verified moves known by each lead member."""
        return {
            self.pokemon_1.species: list(self.pokemon_1.moves),
            self.pokemon_2.species: list(self.pokemon_2.moves),
        }


@dataclass
class ModeEvaluation:
    """Mathematical and tactical scores for a 4-Pokémon mode."""

    mode: TeamMode
    covered_types: List[str]
    coverage_count: int  # out of 18
    coverage_score: float  # 0.0 to 1.0
    defensive_weaknesses: Dict[str, int]  # type -> count of weak members
    defensive_resistances: Dict[str, int]  # type -> count of resisting members
    shared_weaknesses: List[Tuple[str, int]]  # [(Type, count >= 2)]
    defensive_score: float  # 0.0 to 1.0
    speed_control_tools: List[str]
    speed_control_score: float  # 0.0 to 1.0
    disruption_tools: List[str]
    disruption_score: float  # 0.0 to 1.0
    composite_score: float  # 0.0 to 100.0
    archetype_fit: str


@dataclass
class LeadEvaluation:
    """Turn 1 pressure, synergy, and initiative scores for a lead pair."""

    lead: LeadPair
    has_fake_out: bool
    has_screens: bool
    has_pivot: bool
    has_screens_or_pivot: bool
    has_scarf_or_tailwind: bool
    has_priority: bool
    combined_speed_tiers: Tuple[int, int]
    initiative_score: float  # 0.0 to 100.0
    shared_weaknesses: List[str]
    verified_tools: List[str]
    tactical_summary: str


class TeamModeAnalyzer:
    """Analyzes all 15 4-mon modes and 15 lead combinations for a team."""

    def __init__(self, registry: Optional[VGCDataRegistry] = None) -> None:
        self.registry: VGCDataRegistry = registry or get_registry()

    def parse_team_paste(self, paste_text: str) -> List[TeamMemberData]:
        """Parses a 6-Pokémon Showdown paste into canonical TeamMemberData."""
        parsed_sets = parse_showdown_paste(paste_text)
        unique_mons: List[ParsedPokemon] = []
        seen_ids: Set[int] = set()

        for p in parsed_sets.values():
            if id(p) not in seen_ids:
                seen_ids.add(id(p))
                unique_mons.append(p)

        if len(unique_mons) != 6:
            raise ValueError(f"Team paste must contain exactly 6 Pokémon; found {len(unique_mons)}.")

        members: List[TeamMemberData] = []
        for idx, mon in enumerate(unique_mons):
            item = mon.item or ""
            species = mon.species
            canonical_species = species
            is_mega = False
            mega_form = None

            # Resolve Mega Evolution via requiredItem in DuckDB pokedex
            if item:
                mega_res = self.registry.query(
                    "SELECT * FROM pokedex WHERE LOWER(requiredItem) = LOWER(?) LIMIT 1;",
                    (item.strip(),),
                )
                if mega_res:
                    canonical_species = mega_res[0].get("name", species)
                    is_mega = True
                    mega_form = canonical_species

            # Fetch pokedex info
            p_data = self.registry.get_pokemon(canonical_species) or self.registry.get_pokemon(species)
            types: List[str] = ["Normal"]
            base_stats: Dict[str, int] = {"hp": 100, "atk": 100, "def": 100, "spa": 100, "spd": 100, "spe": 100}

            if p_data:
                types = p_data.get("types", ["Normal"])
                base_stats = p_data.get("baseStats", base_stats)

            # Extract attacking move types
            offensive_types: Set[str] = set()
            for move_name in mon.moves:
                m_info = self.registry.get_move(move_name)
                if m_info:
                    cat = m_info.get("category", "")
                    bp = m_info.get("basePower", 0) or 0
                    if cat in ("Physical", "Special") and bp > 0:
                        m_type = m_info.get("type")
                        if m_type:
                            offensive_types.add(m_type)

            # Calculate Level 50 speed tier (Regulation M-C formula)
            base_spe = base_stats.get("spe", 100)
            spe_sp = mon.spread.spe if mon.spread else 0
            nature_mod = NATURE_MODS.get(mon.nature, {}).get("spe", 1.0)
            raw_spe = int((2 * base_spe + 31 + int(spe_sp // 4)) * 50 / 100) + 5
            calc_spe = int(raw_spe * nature_mod)
            if item.lower() == "choice scarf":
                calc_spe = int(calc_spe * 1.5)

            effective_stats = {
                "hp": int((2 * base_stats.get("hp", 100) + 31 + int((mon.spread.hp if mon.spread else 0) // 4)) * 50 / 100) + 60,
                "atk": int(((2 * base_stats.get("atk", 100) + 31 + int((mon.spread.atk if mon.spread else 0) // 4)) * 50 / 100 + 5) * NATURE_MODS.get(mon.nature, {}).get("atk", 1.0)),
                "def": int(((2 * base_stats.get("def", 100) + 31 + int((mon.spread.def_ if mon.spread else 0) // 4)) * 50 / 100 + 5) * NATURE_MODS.get(mon.nature, {}).get("def", 1.0)),
                "spa": int(((2 * base_stats.get("spa", 100) + 31 + int((mon.spread.spa if mon.spread else 0) // 4)) * 50 / 100 + 5) * NATURE_MODS.get(mon.nature, {}).get("spa", 1.0)),
                "spd": int(((2 * base_stats.get("spd", 100) + 31 + int((mon.spread.spd if mon.spread else 0) // 4)) * 50 / 100 + 5) * NATURE_MODS.get(mon.nature, {}).get("spd", 1.0)),
                "spe": calc_spe,
            }

            members.append(
                TeamMemberData(
                    slot_index=idx,
                    name=mon.nickname or species,
                    species=species,
                    canonical_species=canonical_species,
                    item=item,
                    ability=mon.ability or "",
                    nature=mon.nature or "Hardy",
                    moves=list(mon.moves),
                    types=types,
                    base_stats=base_stats,
                    effective_stats=effective_stats,
                    is_mega=is_mega,
                    mega_form=mega_form,
                    offensive_types=offensive_types,
                )
            )

        return members

    def generate_all_modes(self, members: List[TeamMemberData]) -> List[TeamMode]:
        """Generates all 15 4-mon mode combinations."""
        combos = list(itertools.combinations(range(6), 4))
        modes: List[TeamMode] = []

        for idx, combo in enumerate(combos, start=1):
            subset = [members[i] for i in combo]
            names = [m.species for m in subset]

            has_sun = any("charizard" in m.species.lower() for m in subset)
            has_screen = any(any(mv.lower() in SCREEN_MOVES for mv in m.moves) for m in subset)
            has_scarf = any(m.item.lower() == "choice scarf" for m in subset)
            has_defiant = any(m.ability.lower() in ("defiant", "competitive") for m in subset)

            mode_name = " + ".join(names)
            desc = "Balanced Bring-4"
            if has_sun and has_scarf:
                desc = "Sun Hyper-Offense: Sun Sweeper + Scarf Speed Control"
            elif has_screen and has_defiant:
                desc = "Screen Bulwark: Dual Screen Mitigation + Anti-Intimidate Deterrence"
            elif has_sun:
                desc = "Sun Core Setup: Weather Ball & Solar Beam Pressure"
            elif has_screen:
                desc = "Tactical Screen Control: Damage Reduction & Pivoting"

            modes.append(
                TeamMode(
                    mode_id=idx,
                    slot_indices=combo,
                    members=subset,
                    name=f"Mode {idx}: {mode_name}",
                    description=desc,
                )
            )

        return modes

    def generate_all_leads(self, members: List[TeamMemberData]) -> List[LeadPair]:
        """Generates all 15 unordered lead combinations."""
        combos = list(itertools.combinations(range(6), 2))
        leads: List[LeadPair] = []

        for idx, combo in enumerate(combos, start=1):
            leads.append(
                LeadPair(
                    lead_id=idx,
                    slot_indices=combo,
                    pokemon_1=members[combo[0]],
                    pokemon_2=members[combo[1]],
                )
            )
        return leads

    def evaluate_mode(self, mode: TeamMode) -> ModeEvaluation:
        """Evaluates offensive, defensive, speed control, and disruption indices for a mode."""
        # 1. Offensive Super-Effective Coverage
        combined_atk_types: Set[str] = set()
        for m in mode.members:
            combined_atk_types.update(m.offensive_types)

        covered_types: List[str] = []
        for def_type in ALL_TYPES:
            can_hit_super = False
            for atk_type in combined_atk_types:
                if TYPE_CHART.get(atk_type, {}).get(def_type, 1.0) >= 2.0:
                    can_hit_super = True
                    break
            if can_hit_super:
                covered_types.append(def_type)

        coverage_count = len(covered_types)
        coverage_score = coverage_count / 18.0

        # 2. Defensive Weakness & Resistance Synergy
        weaknesses: Dict[str, int] = {t: 0 for t in ALL_TYPES}
        resistances: Dict[str, int] = {t: 0 for t in ALL_TYPES}

        for m in mode.members:
            for atk_type in ALL_TYPES:
                mult = 1.0
                for def_type in m.types:
                    mult *= TYPE_CHART.get(atk_type, {}).get(def_type, 1.0)
                if mult >= 2.0:
                    weaknesses[atk_type] += 1
                elif mult <= 0.5:
                    resistances[atk_type] += 1

        shared_weaknesses = [(t, c) for t, c in weaknesses.items() if c >= 2]
        shared_weaknesses.sort(key=lambda x: x[1], reverse=True)

        total_weakness_penalty = sum(c * 1.5 for _, c in shared_weaknesses)
        total_resist_bonus = sum(resistances.values())
        raw_def_score = 0.5 + (total_resist_bonus * 0.05) - (total_weakness_penalty * 0.05)
        defensive_score = max(0.1, min(1.0, raw_def_score))

        # 3. Speed Control Tools (strictly verified moves & items)
        speed_tools: List[str] = []
        for m in mode.members:
            if m.item.lower() == "choice scarf":
                speed_tools.append(f"Choice Scarf ({m.species})")
            for move in m.moves:
                ml = move.lower()
                if ml == "nuzzle":
                    speed_tools.append(f"Nuzzle Paralysis ({m.species})")
                elif ml in ("icy wind", "electroweb"):
                    speed_tools.append(f"{move} ({m.species})")
                elif ml == "tailwind":
                    speed_tools.append(f"Tailwind ({m.species})")
                elif ml == "trick room":
                    speed_tools.append(f"Trick Room ({m.species})")
            prio_moves = [mv for mv in m.moves if mv.lower() in PRIORITY_ATTACK_MOVES]
            if prio_moves:
                speed_tools.append(f"Priority {'/'.join(prio_moves)} ({m.species})")

        speed_control_score = min(1.0, len(speed_tools) * 0.25)

        # 4. Disruption Tools (strictly decoupled and deduplicated)
        disruption_tools: List[str] = []
        for m in mode.members:
            mon_screens = [mv for mv in m.moves if mv.lower() in SCREEN_MOVES]
            if mon_screens:
                label = f"Screens {'/'.join(mon_screens)} ({m.species})"
                if label not in disruption_tools:
                    disruption_tools.append(label)
            for move in m.moves:
                ml = move.lower()
                if ml == "fake out":
                    disruption_tools.append(f"Fake Out ({m.species})")
                elif ml in PIVOT_MOVES:
                    disruption_tools.append(f"{move} Pivot ({m.species})")
                elif ml in ("spore", "yawn", "sleep powder", "will-o-wisp"):
                    disruption_tools.append(f"{move} ({m.species})")
                elif ml in ("taunt", "encore"):
                    disruption_tools.append(f"{move} ({m.species})")

        disruption_score = min(1.0, len(disruption_tools) * 0.25)

        composite_score = (
            coverage_score * 30.0 +
            defensive_score * 25.0 +
            speed_control_score * 25.0 +
            disruption_score * 20.0
        )

        archetype_fit = "General Balanced Core"
        if coverage_count >= 13 and speed_control_score >= 0.75:
            archetype_fit = "Fast Hyper-Offense: High super-effective reach & initiative"
        elif defensive_score >= 0.75 and disruption_score >= 0.5:
            archetype_fit = "Defensive Control: Strong bulk & screen/pivot mitigation"
        elif any("Nuzzle" in t for t in speed_tools) and any("Scarf" in t for t in speed_tools):
            archetype_fit = "Dual Speed Control: Hard speed manipulation & cleanup"

        return ModeEvaluation(
            mode=mode,
            covered_types=covered_types,
            coverage_count=coverage_count,
            coverage_score=coverage_score,
            defensive_weaknesses=weaknesses,
            defensive_resistances=resistances,
            shared_weaknesses=shared_weaknesses,
            defensive_score=defensive_score,
            speed_control_tools=speed_tools,
            speed_control_score=speed_control_score,
            disruption_tools=disruption_tools,
            disruption_score=disruption_score,
            composite_score=round(composite_score, 1),
            archetype_fit=archetype_fit,
        )

    def evaluate_lead(self, lead: LeadPair) -> LeadEvaluation:
        """Evaluates Turn 1 initiative, strictly decoupling Screens from Pivoting."""
        p1 = lead.pokemon_1
        p2 = lead.pokemon_2
        all_moves = [(p1.species, m) for m in p1.moves] + [(p2.species, m) for m in p2.moves]

        has_fake_out = any(m.lower() == "fake out" for _, m in all_moves)
        has_screens = any(m.lower() in SCREEN_MOVES for _, m in all_moves)
        has_pivot = any(m.lower() in PIVOT_MOVES for _, m in all_moves)
        has_screens_or_pivot = has_screens or has_pivot
        has_scarf_or_tailwind = (
            p1.item.lower() == "choice scarf"
            or p2.item.lower() == "choice scarf"
            or any(m.lower() == "tailwind" for _, m in all_moves)
        )
        has_priority = any(m.lower() in PRIORITY_ATTACK_MOVES for _, m in all_moves)

        spe1 = p1.effective_stats.get("spe", 100)
        spe2 = p2.effective_stats.get("spe", 100)
        speed_tiers = (max(spe1, spe2), min(spe1, spe2))

        shared_weaknesses: List[str] = []
        for atk_type in ALL_TYPES:
            mult1 = 1.0
            for def_type in p1.types:
                mult1 *= TYPE_CHART.get(atk_type, {}).get(def_type, 1.0)
            mult2 = 1.0
            for def_type in p2.types:
                mult2 *= TYPE_CHART.get(atk_type, {}).get(def_type, 1.0)
            if mult1 >= 2.0 and mult2 >= 2.0:
                shared_weaknesses.append(atk_type)

        # Build strictly verified tool labels from actual moves/items on p1 and p2
        verified_tools: List[str] = []
        for mon in (p1, p2):
            if mon.item.lower() == "choice scarf":
                verified_tools.append(f"Choice Scarf ({mon.species})")
            for mv in mon.moves:
                ml = mv.lower()
                if ml == "fake out":
                    verified_tools.append(f"Fake Out Flinch ({mon.species})")
                elif ml in SCREEN_MOVES:
                    verified_tools.append(f"{mv} Screen ({mon.species})")
                elif ml in PIVOT_MOVES:
                    verified_tools.append(f"{mv} Pivot ({mon.species})")
                elif ml in ("nuzzle", "icy wind", "tailwind", "trick room"):
                    verified_tools.append(f"{mv} Speed Control ({mon.species})")
                elif ml == "sucker punch":
                    verified_tools.append(f"Sucker Punch Priority ({mon.species})")

        base_init = 50.0
        if has_fake_out:
            base_init += 22.0
        if has_screens:
            base_init += 15.0
        if has_pivot:
            base_init += 10.0
        if has_scarf_or_tailwind:
            base_init += 15.0
        if speed_tiers[0] >= 170:
            base_init += 8.0
        if shared_weaknesses:
            base_init -= len(shared_weaknesses) * 12.0

        initiative_score = max(10.0, min(100.0, base_init))

        summary_points: List[str] = []
        if has_fake_out:
            summary_points.append("Turn 1 Fake Out Flinch")
        if has_screens:
            summary_points.append("Prankster Screens Mitigation")
        if has_pivot:
            pivot_names = [mv for _, mv in all_moves if mv.lower() in PIVOT_MOVES]
            summary_points.append(f"Momentum Pivot ({'/'.join(pivot_names)})")
        if has_scarf_or_tailwind:
            summary_points.append("Immediate Speed Dominance (Scarf)")
        if shared_weaknesses:
            summary_points.append(f"Shared Weakness: {', '.join(shared_weaknesses)}")

        tactical_summary = " + ".join(summary_points) if summary_points else "Standard neutral Turn 1 pressure"

        return LeadEvaluation(
            lead=lead,
            has_fake_out=has_fake_out,
            has_screens=has_screens,
            has_pivot=has_pivot,
            has_screens_or_pivot=has_screens_or_pivot,
            has_scarf_or_tailwind=has_scarf_or_tailwind,
            has_priority=has_priority,
            combined_speed_tiers=speed_tiers,
            initiative_score=round(initiative_score, 1),
            shared_weaknesses=shared_weaknesses,
            verified_tools=verified_tools,
            tactical_summary=tactical_summary,
        )

    def analyze_team(self, paste_text: str) -> Tuple[List[TeamMemberData], List[ModeEvaluation], List[LeadEvaluation]]:
        """Complete analysis of a 6-mon roster: members, all 15 modes, and all 15 leads."""
        members = self.parse_team_paste(paste_text)
        modes = self.generate_all_modes(members)
        leads = self.generate_all_leads(members)

        mode_evals = [self.evaluate_mode(m) for m in modes]
        lead_evals = [self.evaluate_lead(l) for l in leads]

        mode_evals.sort(key=lambda x: x.composite_score, reverse=True)
        lead_evals.sort(key=lambda x: x.initiative_score, reverse=True)

        return members, mode_evals, lead_evals
