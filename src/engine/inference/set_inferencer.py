# -*- coding: utf-8 -*-
"""Regulation M-C Opponent Set & Stat Point (66-SP) Inference Engine.

Combines regional tournament usage priors from `TournamentUsageRepository` with
live in-battle empirical telemetry (`SpeedObservation`, `DamageObservation`,
revealed moves, items, abilities, and Single-Mega-Per-Team constraints) to infer
complete, Regulation M-C legal 66-SP Pokémon sets for `trainer_2` (and any
unrevealed stats on `trainer_1`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from engine.game_rules import NATURE_MODS, TYPE_CHART
from engine.parser.models import (
    DamageObservation,
    ParsedBattle,
    ParsedPokemon,
    ParsedTeam,
    SpeedObservation,
    StatSpread,
)
from engine.sp_validator import MAX_SINGLE_STAT_SP, MAX_TOTAL_SP
from engine.stats_engine import STANDARD_IV, trunc

from .tournament_db import (
    SpeciesUsageProfile,
    TournamentUsageRepository,
    get_tournament_repository,
)


TYPE_BOOSTING_ITEMS: Dict[str, str] = {
    "Miracle Seed": "Grass",
    "Meadow Plate": "Grass",
    "Charcoal": "Fire",
    "Flame Plate": "Fire",
    "Mystic Water": "Water",
    "Splash Plate": "Water",
    "Magnet": "Electric",
    "Zap Plate": "Electric",
    "Never-Melt Ice": "Ice",
    "Icicle Plate": "Ice",
    "Black Belt": "Fighting",
    "Fist Plate": "Fighting",
    "Poison Barb": "Poison",
    "Toxic Plate": "Poison",
    "Soft Sand": "Ground",
    "Earth Plate": "Ground",
    "Sharp Beak": "Flying",
    "Sky Plate": "Flying",
    "Twisted Spoon": "Psychic",
    "Mind Plate": "Psychic",
    "Silver Powder": "Bug",
    "Insect Plate": "Bug",
    "Hard Stone": "Rock",
    "Stone Plate": "Rock",
    "Spell Tag": "Ghost",
    "Spooky Plate": "Ghost",
    "Dragon Fang": "Dragon",
    "Draco Plate": "Dragon",
    "Black Glasses": "Dark",
    "Dread Plate": "Dark",
    "Metal Coat": "Steel",
    "Iron Plate": "Steel",
    "Fairy Feather": "Fairy",
    "Pixie Plate": "Fairy",
    "Silk Scarf": "Normal",
}


@dataclass
class InferredSetCandidate:
    """A complete Regulation M-C Pokémon build candidate with posterior probability."""

    pokemon: ParsedPokemon
    level_50_stats: Dict[str, int]
    prior_weight: float = 1.0
    posterior_probability: float = 1.0
    speed_compatible: bool = True
    damage_compatible: bool = True
    notes: List[str] = field(default_factory=list)


@dataclass
class TeamInferenceReport:
    """Summary of inferred sets and candidate distributions for a trainer's team."""

    trainer_name: str
    primary_sets: Dict[str, ParsedPokemon] = field(default_factory=dict)
    candidates_by_species: Dict[str, List[InferredSetCandidate]] = field(default_factory=dict)
    speed_bounds_by_species: Dict[str, Tuple[Optional[int], Optional[int]]] = field(default_factory=dict)


def compute_level_50_stats_from_base(
    base_stats: Dict[str, int],
    spread: StatSpread,
    nature: str = "Hardy",
) -> Dict[str, int]:
    """Compute exact Level 50 stats under Regulation M-C (mandatory 31 IVs, 66-SP system)."""
    iv_half = STANDARD_IV // 2  # 15
    sp_dict = spread.to_dict()
    mods = NATURE_MODS.get(nature or "Hardy", {})

    base_hp = int(base_stats.get("hp", 80))
    hp_stat = 1 if base_hp == 1 else base_hp + int(sp_dict["hp"]) + iv_half + 60

    result: Dict[str, int] = {"hp": hp_stat}
    for stat_name in ("atk", "def", "spa", "spd", "spe"):
        raw = int(base_stats.get(stat_name, 80)) + int(sp_dict[stat_name]) + iv_half + 5
        mod = mods.get(stat_name, 1.0)
        if mod > 1.0:
            result[stat_name] = trunc(trunc(raw * 110, 16) / 100)
        elif mod < 1.0:
            result[stat_name] = trunc(trunc(raw * 90, 16) / 100)
        else:
            result[stat_name] = raw
    return result


def apply_stat_stage(stat_value: int, stage: int) -> int:
    """Apply standard Pokémon stat stage multiplier (-6..+6) to a Level 50 stat."""
    clamped = max(-6, min(6, int(stage)))
    if clamped >= 0:
        return (stat_value * (2 + clamped)) // 2
    return (stat_value * 2) // (2 - clamped)


def compute_effective_speed(
    base_spe_stat: int,
    spe_stage: int = 0,
    tailwind_active: bool = False,
    status: Optional[str] = None,
    ability: Optional[str] = None,
    item: Optional[str] = None,
    weather: Optional[str] = None,
    terrain: Optional[str] = None,
) -> int:
    """Compute effective in-battle Speed after stage boosts, Tailwind, items, and abilities."""
    eff = apply_stat_stage(base_spe_stat, spe_stage)

    if item == "Choice Scarf":
        eff = (eff * 3) // 2
    elif item == "Iron Ball":
        eff = eff // 2

    if (
        (ability == "Chlorophyll" and weather == "Sun")
        or (ability == "Swift Swim" and weather == "Rain")
        or (ability == "Sand Rush" and weather == "Sand")
        or (ability == "Slush Rush" and weather == "Snow")
        or (ability == "Surge Surfer" and terrain == "Electric")
    ):
        eff *= 2

    if tailwind_active:
        eff *= 2

    if status == "par" and ability != "Quick Feet":
        eff //= 2

    return eff


class OpponentSetInferencer:
    """Infers complete Regulation M-C Pokémon sets and 66-SP spreads for battle teams."""

    def __init__(self, repo: Optional[TournamentUsageRepository] = None) -> None:
        self.repo = repo or get_tournament_repository()

    # ------------------------------------------------------------------
    # Public Entry Points
    # ------------------------------------------------------------------

    def infer_battle(self, battle: ParsedBattle) -> TeamInferenceReport:
        """Infer complete 66-SP sets for trainer_2 (and fill any missing trainer_1 stats).

        Mutates `battle.trainer_2.pokemon_sets` in-place with the highest-posterior
        inferred sets and returns a detailed `TeamInferenceReport`.
        """
        # 1. Canonicalize & ensure trainer_1 has valid 66-SP spreads if partial
        self._canonicalize_team_megas(battle.trainer_1)
        for sp_key, mon in list(battle.trainer_1.pokemon_sets.items()):
            if mon.spread.total_sp == 0:
                self._populate_single_pokemon(mon, allow_mega=True, require_mega=mon.is_mega)

        # 2. Check if trainer_2 has already committed their Mega Evolution or Mega Stone
        self._canonicalize_team_megas(battle.trainer_2)
        committed_mega_mon: Optional[str] = None
        for mon in battle.trainer_2.pokemon_sets.values():
            if mon.is_mega or (mon.item and mon.item in self.repo.mega_stone_to_species):
                committed_mega_mon = mon.base_species or mon.species
                break

        # 3. Ensure all 6 preview species exist in trainer_2.pokemon_sets
        for preview_sp in battle.trainer_2.team_preview:
            if not battle.trainer_2.get_pokemon(preview_sp):
                battle.trainer_2.pokemon_sets[preview_sp] = ParsedPokemon(
                    species=preview_sp,
                    base_species=preview_sp.split("-Mega")[0],
                )

        # Deduplicate references (since nickname and species may point to the same ParsedPokemon)
        unique_mons: List[ParsedPokemon] = []
        seen_ids: Set[int] = set()
        for mon in battle.trainer_2.pokemon_sets.values():
            if id(mon) not in seen_ids:
                seen_ids.add(id(mon))
                unique_mons.append(mon)

        # 4. Populate each trainer_2 Pokémon's item, ability, nature, and 4 moves
        for mon in unique_mons:
            base_id = mon.base_species or mon.species.split("-Mega")[0]
            if committed_mega_mon:
                is_this_mega = base_id.lower() == committed_mega_mon.lower()
                allow_mega = is_this_mega
                require_mega = mon.is_mega or is_this_mega
            else:
                allow_mega = mon.item is None or (mon.item in self.repo.mega_stone_to_species)
                require_mega = mon.is_mega

            self._populate_single_pokemon(
                mon,
                allow_mega=allow_mega,
                require_mega=require_mega,
                battle=battle,
            )

        # 5. Compute empirical Speed bounds on trainer_2 from battle.speed_observations
        speed_bounds = self._extract_empirical_speed_bounds(battle)

        # 6. Generate & score 66-SP spread candidates for each trainer_2 Pokémon
        report = TeamInferenceReport(
            trainer_name=battle.trainer_2.trainer_name,
            speed_bounds_by_species=speed_bounds,
        )

        for mon in unique_mons:
            key = mon.base_species or mon.species
            bounds = speed_bounds.get(key) or speed_bounds.get(mon.species) or (None, None)
            candidates = self._build_and_score_sp_candidates(mon, bounds, battle)
            report.candidates_by_species[mon.species] = candidates
            if candidates:
                best = candidates[0]
                mon.spread = best.pokemon.spread
            report.primary_sets[mon.species] = mon

        return report

    # ------------------------------------------------------------------
    # Step 1: Canonical Mega & Set Completion
    # ------------------------------------------------------------------

    def _canonicalize_team_megas(self, team: ParsedTeam) -> None:
        """Resolve 'Mega <Name>' strings or Mega Stone items to canonical Pokédex names."""
        seen: Set[int] = set()
        for mon in team.pokemon_sets.values():
            if id(mon) in seen:
                continue
            seen.add(id(mon))
            if not mon.base_species:
                if mon.species.startswith("Mega "):
                    mon.base_species = mon.species[len("Mega ") :].strip()
                else:
                    mon.base_species = mon.species.split("-Mega")[0]

            stone = mon.mega_stone or (
                mon.item if (mon.item and mon.item in self.repo.mega_stone_to_species) else None
            )
            if mon.is_mega or stone:
                resolved = self.repo.resolve_species_name(
                    mon.base_species or mon.species,
                    item=stone,
                    is_mega=mon.is_mega or bool(stone),
                )
                if mon.is_mega and "-Mega" in resolved:
                    mon.species = resolved
                    dex = self.repo.get_pokedex_entry(resolved)
                    mega_ab = dex.get("abilities", {}).get("0")
                    if mega_ab:
                        mon.ability = mega_ab
                    req_stone = dex.get("requiredItem")
                    if req_stone and not mon.item:
                        mon.item = req_stone
                        mon.mega_stone = req_stone

    def _populate_single_pokemon(
        self,
        mon: ParsedPokemon,
        allow_mega: bool = True,
        require_mega: bool = False,
        battle: Optional[ParsedBattle] = None,
    ) -> None:
        """Fill missing item, ability, nature, and moves from tournament usage."""
        # Normalize any already-known moves
        mon.moves = [self.repo.canonical_move_name(m) for m in mon.moves if m]
        revealed_moves = list(mon.moves)

        profile = self.repo.query_species_profile(
            species=mon.base_species or mon.species,
            revealed_moves=revealed_moves,
            revealed_item=mon.item,
            revealed_ability=mon.ability,
            allow_mega=allow_mega,
            require_mega=require_mega,
        )

        # Check mechanical item exclusions from revealed moves
        has_status_move = any(
            self.repo.get_move_entry(m).get("category") == "Status" for m in revealed_moves
        )
        used_multiple_moves = len(revealed_moves) >= 2 and (battle is not None and not battle.is_bo3)

        # 1. Infer Item
        if not mon.item:
            for cand_item in profile.items.keys():
                if not allow_mega and cand_item in self.repo.mega_stone_to_species:
                    continue
                if has_status_move and cand_item == "Assault Vest":
                    continue
                if used_multiple_moves and cand_item in ("Choice Band", "Choice Specs", "Choice Scarf"):
                    continue
                # Respect Item Clause on the team if battle is provided
                if battle and any(
                    other.item == cand_item
                    for other in battle.trainer_2.pokemon_sets.values()
                    if other is not mon
                ):
                    continue
                mon.item = cand_item
                if cand_item in self.repo.mega_stone_to_species:
                    mon.mega_stone = cand_item
                break
            if not mon.item:
                mon.item = "Sitrus Berry"

        # Update species if inferred item is a Mega Stone and Mega is required
        if mon.item in self.repo.mega_stone_to_species:
            mon.mega_stone = mon.item
            if mon.is_mega:
                mon.species = self.repo.mega_stone_to_species[mon.item]

        # 2. Infer Ability
        dex_entry = self.repo.get_pokedex_entry(mon.species, item=mon.item, is_mega=mon.is_mega)
        dex_abilities = list(dex_entry.get("abilities", {}).values())
        if not mon.ability:
            if mon.is_mega and dex_abilities:
                mon.ability = dex_abilities[0]
            elif profile.abilities:
                mon.ability = next(iter(profile.abilities.keys()))
            elif dex_abilities:
                mon.ability = dex_abilities[0]
            else:
                mon.ability = "Illuminate"

        # 3. Infer Nature
        if not mon.nature:
            if profile.natures:
                mon.nature = next(iter(profile.natures.keys()))
            else:
                base_stats = self.repo.get_base_stats(mon.species, item=mon.item, is_mega=mon.is_mega)
                if base_stats["atk"] >= base_stats["spa"]:
                    mon.nature = "Jolly" if base_stats["spe"] >= 95 else "Adamant"
                else:
                    mon.nature = "Timid" if base_stats["spe"] >= 95 else "Modest"

        # 4. Infer Moves up to 4
        if len(mon.moves) < 4:
            for cand_move in profile.moves.keys():
                if len(mon.moves) >= 4:
                    break
                if cand_move not in mon.moves:
                    mon.moves.append(cand_move)

        # Fallback if tournament archive had < 4 moves for a rare species
        if len(mon.moves) < 4:
            fallback_moves = ["Protect", "Tera Blast", "Helping Hand", "Substitute"]
            sp_id = (mon.base_species or mon.species).lower().replace("-", "").replace(" ", "")
            learnset_pool = sorted(self.repo.learnsets.get(sp_id, set()))
            for lm in learnset_pool + fallback_moves:
                if len(mon.moves) >= 4:
                    break
                if lm not in mon.moves:
                    mon.moves.append(lm)

    # ------------------------------------------------------------------
    # Step 2: Empirical Speed & Damage Telemetry Extraction
    # ------------------------------------------------------------------

    def _get_trainer_1_effective_speed(
        self,
        battle: ParsedBattle,
        mon_identifier: str,
        obs: SpeedObservation,
    ) -> Optional[int]:
        """Calculate exact effective Speed of a trainer_1 Pokémon during an observation."""
        pkm = battle.trainer_1.get_pokemon(mon_identifier)
        if not pkm:
            return None
        base_stats = self.repo.get_base_stats(pkm.species, item=pkm.item, is_mega=pkm.is_mega)
        l50 = compute_level_50_stats_from_base(base_stats, pkm.spread, pkm.nature or "Hardy")
        is_faster = obs.faster_mon == mon_identifier
        tw = obs.tailwind_active_faster if is_faster else obs.tailwind_active_slower
        return compute_effective_speed(
            base_spe_stat=l50["spe"],
            spe_stage=pkm.boosts.get("spe", 0),
            tailwind_active=tw,
            status=pkm.status,
            ability=pkm.ability,
            item=pkm.item,
            weather=obs.weather,
            terrain=obs.terrain,
        )

    def _extract_empirical_speed_bounds(
        self,
        battle: ParsedBattle,
    ) -> Dict[str, Tuple[Optional[int], Optional[int]]]:
        """Compute (min_eff_spe, max_eff_spe) bounds for trainer_2 Pokémon from SpeedObservations."""
        bounds: Dict[str, Tuple[Optional[int], Optional[int]]] = {}

        def update_bound(sp_name: str, low: Optional[int], high: Optional[int]) -> None:
            cur_low, cur_high = bounds.get(sp_name, (None, None))
            new_low = max(cur_low, low) if (cur_low is not None and low is not None) else (low if low is not None else cur_low)
            new_high = min(cur_high, high) if (cur_high is not None and high is not None) else (high if high is not None else cur_high)
            if new_low is not None and new_high is not None and new_low > new_high:
                # Keep the tighter direct observation if conflicting boosts occurred across turns
                new_low = min(new_low, new_high)
            bounds[sp_name] = (new_low, new_high)

        for obs in battle.speed_observations:
            f_mon_t1 = battle.trainer_1.get_pokemon(obs.faster_mon)
            s_mon_t1 = battle.trainer_1.get_pokemon(obs.slower_mon)
            f_mon_t2 = battle.trainer_2.get_pokemon(obs.faster_mon)
            s_mon_t2 = battle.trainer_2.get_pokemon(obs.slower_mon)

            # Case A: trainer_1 moved before trainer_2 in the same priority bracket
            if f_mon_t1 and s_mon_t2:
                t1_spe = self._get_trainer_1_effective_speed(battle, obs.faster_mon, obs)
                if t1_spe is not None:
                    key = s_mon_t2.base_species or s_mon_t2.species
                    if obs.trick_room_active:
                        update_bound(key, t1_spe, None)
                        update_bound(s_mon_t2.species, t1_spe, None)
                    else:
                        update_bound(key, None, t1_spe)
                        update_bound(s_mon_t2.species, None, t1_spe)

            # Case B: trainer_2 moved before trainer_1 in the same priority bracket
            elif f_mon_t2 and s_mon_t1:
                t1_spe = self._get_trainer_1_effective_speed(battle, obs.slower_mon, obs)
                if t1_spe is not None:
                    key = f_mon_t2.base_species or f_mon_t2.species
                    if obs.trick_room_active:
                        update_bound(key, None, t1_spe)
                        update_bound(f_mon_t2.species, None, t1_spe)
                    else:
                        update_bound(key, t1_spe, None)
                        update_bound(f_mon_t2.species, t1_spe, None)

        return bounds

    # ------------------------------------------------------------------
    # Step 3: 66-SP Candidate Generation & Scoring
    # ------------------------------------------------------------------

    def _build_and_score_sp_candidates(
        self,
        mon: ParsedPokemon,
        speed_bounds: Tuple[Optional[int], Optional[int]],
        battle: ParsedBattle,
    ) -> List[InferredSetCandidate]:
        """Generate Regulation M-C 66-SP candidate spreads and rank by posterior likelihood."""
        base_stats = self.repo.get_base_stats(mon.species, item=mon.item, is_mega=mon.is_mega)
        nature = mon.nature or "Hardy"

        # Determine primary offensive axis from moves and base stats
        phys_moves = sum(
            1 for m in mon.moves if self.repo.get_move_entry(m).get("category") == "Physical"
        )
        spec_moves = sum(
            1 for m in mon.moves if self.repo.get_move_entry(m).get("category") == "Special"
        )
        is_physical = (phys_moves > spec_moves) or (
            phys_moves == spec_moves and base_stats["atk"] >= base_stats["spa"]
        )
        off_key = "atk" if is_physical else "spa"

        # Determine whether the Pokémon is a slow/Trick Room build or speed-oriented
        is_slow_nature = nature in ("Brave", "Quiet", "Relaxed", "Sassy")
        is_support_nature = nature in ("Bold", "Impish", "Calm", "Careful")
        is_fast_nature = nature in ("Jolly", "Timid", "Hasty", "Naive")

        raw_archetypes: List[Tuple[str, Dict[str, int], float]] = []
        if is_slow_nature:
            raw_archetypes.append(
                ("Trick Room Max Bulk/Offense", {"hp": 32, off_key: 32, "spd": 2, "spe": 0}, 1.5)
            )
            raw_archetypes.append(
                ("Bulky Tank", {"hp": 32, off_key: 18, "def": 8, "spd": 8, "spe": 0}, 1.1)
            )
        elif is_support_nature:
            raw_archetypes.append(
                ("Max Bulk Support", {"hp": 32, "def": 18, "spd": 16, "spe": 0}, 1.5)
            )
            raw_archetypes.append(
                ("Balanced Support", {"hp": 32, off_key: 12, "def": 12, "spd": 10, "spe": 0}, 1.2)
            )
        elif is_fast_nature:
            raw_archetypes.append(
                ("Max Speed Sweeper", {"hp": 2, off_key: 32, "spe": 32}, 1.6)
            )
            raw_archetypes.append(
                ("Fast Bulky Attacker", {"hp": 14, off_key: 28, "spe": 24}, 1.3)
            )
            raw_archetypes.append(
                ("Mid-Speed Bulky", {"hp": 24, off_key: 26, "spe": 16}, 1.0)
            )
        else:
            # Adamant / Modest / neutral
            raw_archetypes.append(
                ("Bulky Attacker", {"hp": 32, off_key: 32, "spe": 2}, 1.5)
            )
            raw_archetypes.append(
                ("Speed-Creep Attacker", {"hp": 18, off_key: 32, "spe": 16}, 1.35)
            )
            raw_archetypes.append(
                ("Max Offense Max Speed", {"hp": 2, off_key: 32, "spe": 32}, 1.2)
            )

        # If empirical speed bounds exist, also synthesize a speed-tuned 66-SP spread
        min_spe, max_spe = speed_bounds
        if min_spe is not None or max_spe is not None:
            for target_spe_sp in range(0, MAX_SINGLE_STAT_SP + 1, 2):
                rem = MAX_TOTAL_SP - target_spe_sp
                off_sp = min(MAX_SINGLE_STAT_SP, rem)
                hp_sp = min(MAX_SINGLE_STAT_SP, rem - off_sp)
                def_sp = max(0, rem - off_sp - hp_sp)
                test_spread = StatSpread(
                    hp=hp_sp,
                    atk=off_sp if off_key == "atk" else 0,
                    def_=def_sp,
                    spa=off_sp if off_key == "spa" else 0,
                    spd=0,
                    spe=target_spe_sp,
                )
                l50 = compute_level_50_stats_from_base(base_stats, test_spread, nature)
                eff_spe = compute_effective_speed(
                    l50["spe"],
                    ability=mon.ability,
                    item=mon.item,
                )
                ok_low = min_spe is None or eff_spe >= min_spe
                ok_high = max_spe is None or eff_spe <= max_spe
                if ok_low and ok_high:
                    raw_archetypes.append(
                        (
                            f"Empirical Speed-Tuned ({target_spe_sp} Spe SP)",
                            test_spread.to_dict(),
                            1.8,
                        )
                    )
                    break

        candidates: List[InferredSetCandidate] = []
        seen_spreads: Set[Tuple[int, int, int, int, int, int]] = set()

        for label, sp_dict, prior_w in raw_archetypes:
            spread = StatSpread.from_dict(sp_dict)
            if spread.total_sp != MAX_TOTAL_SP:
                continue
            sig = (spread.hp, spread.atk, spread.def_, spread.spa, spread.spd, spread.spe)
            if sig in seen_spreads:
                continue
            seen_spreads.add(sig)

            l50 = compute_level_50_stats_from_base(base_stats, spread, nature)
            eff_spe = compute_effective_speed(l50["spe"], ability=mon.ability, item=mon.item)

            spe_ok = True
            if min_spe is not None and eff_spe < min_spe:
                spe_ok = False
            if max_spe is not None and eff_spe > max_spe:
                spe_ok = False

            dmg_ok, dmg_score = self._evaluate_damage_compatibility(mon, l50, battle)

            weight = prior_w
            if spe_ok:
                weight *= 2.0
            else:
                weight *= 0.15
            weight *= dmg_score

            cand_mon = ParsedPokemon(
                species=mon.species,
                base_species=mon.base_species,
                nickname=mon.nickname,
                item=mon.item,
                ability=mon.ability,
                nature=nature,
                level=50,
                gender=mon.gender,
                spread=spread,
                ivs=dict(mon.ivs),
                moves=list(mon.moves),
                is_mega=mon.is_mega,
                mega_stone=mon.mega_stone,
                current_hp_pct=mon.current_hp_pct,
                fainted=mon.fainted,
                revealed_in_battle=mon.revealed_in_battle,
                boosts=dict(mon.boosts),
                status=mon.status,
            )

            candidates.append(
                InferredSetCandidate(
                    pokemon=cand_mon,
                    level_50_stats=l50,
                    prior_weight=prior_w,
                    posterior_probability=weight,
                    speed_compatible=spe_ok,
                    damage_compatible=dmg_ok,
                    notes=[label],
                )
            )

        # Normalize posterior probabilities
        total_post = sum(c.posterior_probability for c in candidates) or 1.0
        for c in candidates:
            c.posterior_probability = round(c.posterior_probability / total_post, 4)

        candidates.sort(key=lambda c: -c.posterior_probability)
        return candidates

    def _evaluate_damage_compatibility(
        self,
        mon: ParsedPokemon,
        l50_stats: Dict[str, int],
        battle: ParsedBattle,
    ) -> Tuple[bool, float]:
        """Score how well `l50_stats` explain observed DamageObservations involving `mon`."""
        score = 1.0
        all_compatible = True
        mon_names = {
            n.lower()
            for n in (mon.species, mon.base_species, mon.nickname or "")
            if n
        }

        for obs in battle.damage_observations:
            # Check when this Pokémon is the DEFENDER taking damage from trainer_1
            if obs.defender.lower() in mon_names:
                atk_mon = battle.trainer_1.get_pokemon(obs.attacker)
                if atk_mon:
                    atk_base = self.repo.get_base_stats(
                        atk_mon.species, item=atk_mon.item, is_mega=atk_mon.is_mega
                    )
                    atk_l50 = compute_level_50_stats_from_base(
                        atk_base, atk_mon.spread, atk_mon.nature or "Hardy"
                    )
                    min_pct, max_pct = self._estimate_damage_pct_range(
                        attacker=atk_mon,
                        attacker_stats=atk_l50,
                        defender=mon,
                        defender_stats=l50_stats,
                        obs=obs,
                    )
                    if max_pct > 0:
                        if min_pct - 8.0 <= obs.damage_pct <= max_pct + 8.0:
                            score *= 1.5
                        else:
                            all_compatible = False
                            score *= 0.6

            # Check when this Pokémon is the ATTACKER dealing damage to trainer_1
            elif obs.attacker.lower() in mon_names:
                def_mon = battle.trainer_1.get_pokemon(obs.defender)
                if def_mon:
                    def_base = self.repo.get_base_stats(
                        def_mon.species, item=def_mon.item, is_mega=def_mon.is_mega
                    )
                    def_l50 = compute_level_50_stats_from_base(
                        def_base, def_mon.spread, def_mon.nature or "Hardy"
                    )
                    min_pct, max_pct = self._estimate_damage_pct_range(
                        attacker=mon,
                        attacker_stats=l50_stats,
                        defender=def_mon,
                        defender_stats=def_l50,
                        obs=obs,
                    )
                    if max_pct > 0:
                        if min_pct - 8.0 <= obs.damage_pct <= max_pct + 8.0:
                            score *= 1.5
                        else:
                            all_compatible = False
                            score *= 0.6

        return all_compatible, score

    def _estimate_damage_pct_range(
        self,
        attacker: ParsedPokemon,
        attacker_stats: Dict[str, int],
        defender: ParsedPokemon,
        defender_stats: Dict[str, int],
        obs: DamageObservation,
    ) -> Tuple[float, float]:
        """Estimate Level 50 [min_pct, max_pct] damage range for a single hit."""
        move_entry = self.repo.get_move_entry(obs.move)
        bp = int(move_entry.get("basePower", 0) or 0)
        cat = move_entry.get("category", "Status")
        if bp <= 0 or cat == "Status":
            return (0.0, 0.0)

        move_type = move_entry.get("type", "Normal")
        is_phys = cat == "Physical"
        atk_key = "atk" if is_phys else "spa"
        def_key = "def" if is_phys else "spd"

        atk_val = apply_stat_stage(
            attacker_stats[atk_key], obs.attacker_boosts.get(atk_key, 0)
        )
        def_val = apply_stat_stage(
            defender_stats[def_key], obs.defender_boosts.get(def_key, 0)
        )

        # Ability modifiers (Huge Power / Pure Power)
        if is_phys and attacker.ability in ("Huge Power", "Pure Power"):
            atk_val *= 2

        # Item stat modifiers
        if is_phys and attacker.item == "Choice Band":
            atk_val = (atk_val * 3) // 2
        elif not is_phys and attacker.item == "Choice Specs":
            atk_val = (atk_val * 3) // 2
        if not is_phys and defender.item == "Assault Vest":
            def_val = (def_val * 3) // 2

        base_dmg = ((22 * bp * atk_val) // max(1, def_val)) // 50 + 2

        # Spread move modifier (0.75x in Doubles)
        target_type = move_entry.get("target", "normal")
        if target_type in ("allAdjacentFoes", "allAdjacent"):
            base_dmg = (base_dmg * 3) // 4

        # Weather modifier
        if obs.weather == "Sun":
            if move_type == "Fire":
                base_dmg = (base_dmg * 3) // 2
            elif move_type == "Water":
                base_dmg //= 2
        elif obs.weather == "Rain":
            if move_type == "Water":
                base_dmg = (base_dmg * 3) // 2
            elif move_type == "Fire":
                base_dmg //= 2

        # Terrain modifier (1.3x in Gen 9)
        if (
            (obs.terrain == "Grassy" and move_type == "Grass")
            or (obs.terrain == "Electric" and move_type == "Electric")
            or (obs.terrain == "Psychic" and move_type == "Psychic")
        ):
            base_dmg = (base_dmg * 13) // 10

        # STAB
        atk_dex = self.repo.get_pokedex_entry(
            attacker.species, item=attacker.item, is_mega=attacker.is_mega
        )
        atk_types = atk_dex.get("types", [])
        stab_mult = 1.0
        if move_type in atk_types:
            stab_mult = 2.0 if attacker.ability == "Adaptability" else 1.5

        # Type effectiveness
        def_dex = self.repo.get_pokedex_entry(
            defender.species, item=defender.item, is_mega=defender.is_mega
        )
        def_types = def_dex.get("types", [])
        type_mult = 1.0
        for dt in def_types:
            type_mult *= TYPE_CHART.get(move_type, {}).get(dt, 1.0)

        # Item damage boost (Life Orb, Miracle Seed, etc.)
        item_mult = 1.0
        if attacker.item == "Life Orb":
            item_mult = 1.3
        elif attacker.item and TYPE_BOOSTING_ITEMS.get(attacker.item) == move_type:
            item_mult = 1.2

        min_roll = int(base_dmg * 0.85) * stab_mult * type_mult * item_mult
        max_roll = int(base_dmg * 1.00) * stab_mult * type_mult * item_mult

        max_hp = max(1, defender_stats["hp"])
        return (
            round((min_roll / max_hp) * 100.0, 1),
            round((max_roll / max_hp) * 100.0, 1),
        )

