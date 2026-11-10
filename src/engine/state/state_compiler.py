# -*- coding: utf-8 -*-
"""Regulation M-C Turn State Compiler (In-Memory DuckDB Backed).

Compiles a `ParsedBattle` (from `src/engine/parser/`) and inferred opponent sets
(from `src/engine/inference/`) into a math-ready `TurnState` (`trainer_1` and
`trainer_2` active slots, 2-slot reserve bench, pre-compiled Mega Evolution
stat transitions, and field state).

Supersedes the legacy `src/engine/stats_engine.py` by querying all species base
stats, types, abilities, and move metadata directly from the in-memory DuckDB
`VGCDataRegistry`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from engine.db_registry import VGCDataRegistry, get_registry
from engine.game_rules import NATURE_MODS, TYPE_CHART
from engine.inference.tournament_db import (
    TournamentUsageRepository,
    get_tournament_repository,
)
from engine.parser.models import (
    ParsedBattle,
    ParsedPokemon,
    ParsedTeam,
    StatSpread,
)

from .models import (
    CompiledMove,
    CompiledPokemonState,
    FieldState,
    TrainerSideState,
    TurnState,
)

# Champions requires every Pokémon to use 31 IVs. The Level 50 formula folds
# the IV contribution into its constants: 31 // 2 = 15, plus 60 for HP and 5
# for other stats.
STANDARD_IV: int = 31

CHOICE_ITEMS: Set[str] = {"Choice Band", "Choice Specs", "Choice Scarf"}


def trunc(n: float, bits: int = 0) -> int:
    """Truncate float to integer with optional bit masking."""
    res = int(n)
    if bits:
        res = res & ((1 << bits) - 1)
    return res


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


def calculate_level_50_stats(
    species: str,
    sp: Dict[str, int] | StatSpread,
    nature: str = "Hardy",
    repo: Optional[TournamentUsageRepository] = None,
) -> Tuple[int, Dict[str, int]]:
    """Calculate Champions Level 50 stats backed by in-memory DuckDB `pokedex`.

    Returns `(max_hp, other_stats)` where `other_stats` contains
    `('atk', 'def', 'spa', 'spd', 'spe')`.
    """
    active_repo = repo or get_tournament_repository()
    base_stats = active_repo.get_base_stats(species)
    spread = sp if isinstance(sp, StatSpread) else StatSpread.from_evs_or_sp(sp)
    all_stats = compute_level_50_stats_from_base(base_stats, spread, nature)
    max_hp = all_stats["hp"]
    other_stats = {k: all_stats[k] for k in ("atk", "def", "spa", "spd", "spe")}
    return max_hp, other_stats


class TurnStateCompiler:
    """Compiles `ParsedBattle` telemetry into a math-ready `TurnState`."""

    def __init__(
        self,
        repo: Optional[TournamentUsageRepository] = None,
        registry: Optional[VGCDataRegistry] = None,
    ) -> None:
        self.repo: TournamentUsageRepository = repo or get_tournament_repository()
        self.registry: VGCDataRegistry = registry or self.repo.registry
        self._species_tournament_weights: Dict[str, float] = self._load_species_weights()

    def _load_species_weights(self) -> Dict[str, float]:
        """Query total regional placement weights per species from in-memory DuckDB."""
        weights: Dict[str, float] = {}
        try:
            rows = self.registry.query(
                """
                SELECT species, SUM(weight) AS total_w
                FROM tournament_team_slots
                GROUP BY species;
                """
            )
            for r in rows:
                sp = str(r.get("species") or "").strip()
                if sp:
                    weights[sp] = float(r.get("total_w") or 0.0)
        except Exception:
            pass
        return weights

    # ------------------------------------------------------------------
    # Public Compilation Entry Point
    # ------------------------------------------------------------------

    def compile_turn_state(
        self,
        battle: ParsedBattle,
        run_inference: bool = True,
        trainer_1_bench_override: Optional[Sequence[str]] = None,
        trainer_2_bench_override: Optional[Sequence[str]] = None,
    ) -> TurnState:
        """Compile a `ParsedBattle` into a concrete `TurnState` for the next decision point.

        Args:
            battle: ParsedBattle model from `parse_showdown_chat_log`.
            run_inference: If True, runs `OpponentSetInferencer` when `trainer_2` sets
                           have unrevealed natures, spreads, or moves.
            trainer_1_bench_override: Optional explicit bench species list for `trainer_1`.
            trainer_2_bench_override: Optional explicit bench species list for `trainer_2`.

        Returns:
            Compiled `TurnState` containing `trainer_1`, `trainer_2`, and `field`.
        """
        if run_inference and (
            self._needs_inference(battle.trainer_2)
            or self._needs_inference(battle.trainer_1)
        ):
            from engine.inference.set_inferencer import OpponentSetInferencer

            inferencer = OpponentSetInferencer(repo=self.repo)
            inferencer.infer_battle(battle)

        trainer_1_side = self._compile_trainer_side(
            trainer_id="trainer_1",
            team=battle.trainer_1,
            opposing_team=battle.trainer_2,
            tailwind_active=battle.trainer_1_tailwind,
            bench_override=trainer_1_bench_override,
        )
        trainer_2_side = self._compile_trainer_side(
            trainer_id="trainer_2",
            team=battle.trainer_2,
            opposing_team=battle.trainer_1,
            tailwind_active=battle.trainer_2_tailwind,
            bench_override=trainer_2_bench_override,
        )

        field_state = FieldState(
            weather=battle.weather,
            terrain=battle.terrain,
            trick_room_active=battle.trick_room,
        )

        next_turn_num = max(1, battle.turns_played + 1) if battle.turns_played > 0 else 1
        return TurnState(
            turn_number=next_turn_num,
            trainer_1=trainer_1_side,
            trainer_2=trainer_2_side,
            field=field_state,
        )

    def _needs_inference(self, team: ParsedTeam) -> bool:
        """Check whether any Pokémon on `team` is missing a spread, nature, or moves."""
        if not team.pokemon_sets:
            return False
        for pkm in team.pokemon_sets.values():
            if not pkm.nature or pkm.spread.total_sp == 0 or len(pkm.moves) < 2:
                return True
        return False

    # ------------------------------------------------------------------
    # Side & Roster Compilation
    # ------------------------------------------------------------------

    def _compile_trainer_side(
        self,
        trainer_id: str,
        team: ParsedTeam,
        opposing_team: ParsedTeam,
        tailwind_active: bool = False,
        bench_override: Optional[Sequence[str]] = None,
    ) -> TrainerSideState:
        """Compile a `ParsedTeam` into a `TrainerSideState` with 2 active and up to 2 bench slots."""
        # Deduplicate pokemon_sets by canonical base_species / species
        unique_parsed: Dict[str, ParsedPokemon] = {}
        for key, pkm in team.pokemon_sets.items():
            canon_key = pkm.base_species or pkm.species
            if canon_key not in unique_parsed:
                unique_parsed[canon_key] = pkm

        # Ensure all team_preview species exist in unique_parsed
        for prev_sp in team.team_preview:
            pkm = team.get_pokemon(prev_sp)
            if pkm:
                canon_key = pkm.base_species or pkm.species
                if canon_key not in unique_parsed:
                    unique_parsed[canon_key] = pkm

        mega_already_used = any(p.is_mega for p in unique_parsed.values())

        compiled_map: Dict[str, CompiledPokemonState] = {}
        for canon_key, pkm in unique_parsed.items():
            compiled_map[canon_key] = self.compile_pokemon(
                pkm, trainer_mega_used=mega_already_used
            )

        # 1. Resolve Active Slots (up to 2)
        active_list: List[Optional[CompiledPokemonState]] = []
        raw_active = list(team.active_slots) if team.active_slots else list(team.leads)
        used_keys: Set[str] = set()

        for ident in raw_active:
            comp = self._lookup_compiled(ident, compiled_map)
            if comp and not comp.fainted and comp.base_species not in used_keys:
                active_list.append(comp)
                used_keys.add(comp.base_species)
            if len(active_list) == 2:
                break

        # If fewer than 2 active slots were recorded (e.g. before leads or after an unreplaced KO),
        # fill from revealed unfainted battle_roster members if available
        if len(active_list) < 2 and not team.active_slots and not team.leads:
            for ident in list(team.battle_roster) + list(team.team_preview):
                comp = self._lookup_compiled(ident, compiled_map)
                if comp and not comp.fainted and comp.base_species not in used_keys:
                    active_list.append(comp)
                    used_keys.add(comp.base_species)
                if len(active_list) == 2:
                    break

        while len(active_list) < 2:
            active_list.append(None)

        active_slots: Tuple[Optional[CompiledPokemonState], Optional[CompiledPokemonState]] = (
            active_list[0],
            active_list[1],
        )

        # 2. Resolve 4-Pokémon Battle Roster & Bench Slots (up to 2 bench Pokémon)
        # First include all brought Pokémon (active or fainted or revealed bench)
        brought_keys: List[str] = []
        for ident in team.battle_roster:
            comp = self._lookup_compiled(ident, compiled_map)
            if comp and comp.base_species not in brought_keys:
                brought_keys.append(comp.base_species)

        for act in active_slots:
            if act and act.base_species not in brought_keys:
                brought_keys.append(act.base_species)

        # Apply manual bench override if supplied
        if bench_override:
            for ident in bench_override:
                if len(brought_keys) >= 4:
                    break
                comp = self._lookup_compiled(ident, compiled_map)
                if comp and comp.base_species not in brought_keys:
                    brought_keys.append(comp.base_species)

        # If fewer than 4 Pokémon have been revealed/brought so far (common in Bo1),
        # score the unrevealed Team Preview candidates by tournament usage + matchup synergy
        if len(brought_keys) < 4:
            needed = 4 - len(brought_keys)
            unrevealed_candidates = [
                comp
                for key, comp in compiled_map.items()
                if key not in brought_keys
            ]
            scored_candidates = self._rank_unrevealed_bench_candidates(
                candidates=unrevealed_candidates,
                already_brought=[compiled_map[k] for k in brought_keys if k in compiled_map],
                opposing_team=opposing_team,
            )
            for comp in scored_candidates[:needed]:
                brought_keys.append(comp.base_species)

        bench_list: List[CompiledPokemonState] = []
        active_base_set = {a.base_species for a in active_slots if a is not None}
        for key in brought_keys[:4]:
            comp = compiled_map.get(key)
            if comp and comp.base_species not in active_base_set and not comp.fainted:
                bench_list.append(comp)

        return TrainerSideState(
            trainer_id=trainer_id,
            trainer_name=team.trainer_name,
            active_slots=active_slots,
            bench_slots=tuple(bench_list),
            full_team=compiled_map,
            mega_used=mega_already_used,
            tailwind_active=tailwind_active,
        )

    def _lookup_compiled(
        self,
        identifier: str,
        compiled_map: Dict[str, CompiledPokemonState],
    ) -> Optional[CompiledPokemonState]:
        """Find a `CompiledPokemonState` in `compiled_map` by species, base_species, or nickname."""
        if identifier in compiled_map:
            return compiled_map[identifier]
        clean = identifier.strip().lower()
        for key, comp in compiled_map.items():
            if (
                key.lower() == clean
                or comp.species.lower() == clean
                or comp.base_species.lower() == clean
                or (comp.nickname and comp.nickname.lower() == clean)
                or comp.base_species.split("-")[0].lower() == clean
            ):
                return comp
        return None

    def _rank_unrevealed_bench_candidates(
        self,
        candidates: Sequence[CompiledPokemonState],
        already_brought: Sequence[CompiledPokemonState],
        opposing_team: ParsedTeam,
    ) -> List[CompiledPokemonState]:
        """Rank unrevealed Team Preview Pokémon to complete the 4-Pokémon battle roster.

        Combines:
        1. Regional tournament usage weight from in-memory DuckDB (`tournament_team_slots`).
        2. Offensive + defensive type coverage against the opposing trainer's preview/active Pokémon.
        3. Single-Mega-Per-Team penalty if one of the already-brought Pokémon holds a Mega Stone
           or has already Mega Evolved.
        """
        already_has_mega = any(
            m.is_mega or m.can_mega_evolve for m in already_brought
        )

        # Gather opposing types
        opposing_types: List[Tuple[str, ...]] = []
        opposing_species = (
            list(opposing_team.battle_roster)
            if opposing_team.battle_roster
            else list(opposing_team.team_preview)
        )
        for opp_sp in opposing_species:
            dex_name = self.repo.resolve_species_name(opp_sp)
            dex_entry = self.repo.pokedex.get(dex_name, {})
            t_list = tuple(dex_entry.get("types") or ())
            if t_list:
                opposing_types.append(t_list)

        scored: List[Tuple[float, CompiledPokemonState]] = []
        for cand in candidates:
            # 1. Tournament usage prior (log-scaled / normalized)
            usage_w = (
                self._species_tournament_weights.get(cand.species, 0.0)
                + self._species_tournament_weights.get(cand.base_species, 0.0)
            )
            if cand.mega_target_species:
                usage_w = max(
                    usage_w,
                    self._species_tournament_weights.get(cand.mega_target_species, 0.0),
                )
            score = min(50.0, usage_w / 25.0)

            # 2. Matchup type synergy against opposing roster
            cand_types = cand.mega_types if (cand.can_mega_evolve and cand.mega_types) else cand.types
            for opp_t_tuple in opposing_types:
                # Offensive super-effective bonus
                best_off = 1.0
                for atk_t in cand_types:
                    mult = 1.0
                    for def_t in opp_t_tuple:
                        mult *= TYPE_CHART.get(atk_t, {}).get(def_t, 1.0)
                    best_off = max(best_off, mult)
                if best_off >= 2.0:
                    score += 12.0
                elif best_off < 1.0:
                    score -= 4.0

                # Defensive resistance bonus
                worst_def = 1.0
                for opp_atk_t in opp_t_tuple:
                    mult = 1.0
                    for my_def_t in cand_types:
                        mult *= TYPE_CHART.get(opp_atk_t, {}).get(my_def_t, 1.0)
                    worst_def = max(worst_def, mult)
                if worst_def <= 0.5:
                    score += 8.0
                elif worst_def >= 2.0:
                    score -= 6.0

            # 3. Single-Mega conflict penalty
            if already_has_mega and cand.can_mega_evolve:
                score -= 100.0

            scored.append((score, cand))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [pair[1] for pair in scored]

    # ------------------------------------------------------------------
    # Single Pokémon & Move Compilation
    # ------------------------------------------------------------------

    def compile_pokemon(
        self,
        pkm: ParsedPokemon,
        trainer_mega_used: bool = False,
    ) -> CompiledPokemonState:
        """Compile a `ParsedPokemon` into a `CompiledPokemonState` via in-memory DuckDB."""
        # Resolve current active species in DuckDB pokedex
        current_dex_species = self.repo.resolve_species_name(
            pkm.species,
            item=pkm.item if pkm.is_mega else None,
            is_mega=pkm.is_mega,
        )
        dex_entry = self.repo.pokedex.get(current_dex_species, {})
        forme_str = str(dex_entry.get("forme") or "")
        if "Mega" in current_dex_species or forme_str.startswith("Mega"):
            base_species = str(
                dex_entry.get("baseSpecies")
                or pkm.base_species
                or current_dex_species.split("-Mega")[0]
            )
        else:
            base_species = current_dex_species

        # Types
        raw_types = dex_entry.get("types") or ["Normal"]
        types: Tuple[str, ...] = tuple(str(t) for t in raw_types)

        # Ability
        ability = pkm.ability
        if not ability or (pkm.is_mega and current_dex_species != pkm.base_species):
            abilities_map = dex_entry.get("abilities")
            if isinstance(abilities_map, dict) and abilities_map.get("0"):
                ability = str(abilities_map["0"])
        ability = ability or "Illuminate"

        nature = pkm.nature or "Hardy"
        spread = pkm.spread

        # Compute current Level 50 stats
        # Note: HP always uses the base species' HP base stat even if Mega Evolved
        base_stats = dict(self.repo.get_base_stats(current_dex_species))
        if pkm.is_mega and base_species in self.repo.pokedex:
            base_stats["hp"] = self.repo.get_base_stats(base_species)["hp"]

        level_50_stats = compute_level_50_stats_from_base(base_stats, spread, nature)
        max_hp = level_50_stats["hp"]

        if pkm.fainted or pkm.current_hp_pct <= 0.0:
            current_hp = 0
            current_hp_pct = 0.0
            fainted = True
        else:
            current_hp_pct = min(100.0, max(0.0, float(pkm.current_hp_pct)))
            current_hp = max(1, min(max_hp, round(max_hp * (current_hp_pct / 100.0))))
            fainted = False

        # Resolve Mega Evolution capability & pre-compiled Mega stats
        item = pkm.item
        mega_stone = pkm.mega_stone
        can_mega_evolve = False
        mega_target_species: Optional[str] = None
        mega_level_50_stats: Optional[Dict[str, int]] = None
        mega_ability: Optional[str] = None
        mega_types: Optional[Tuple[str, ...]] = None

        stone_candidate = item or mega_stone
        if stone_candidate:
            target_mega = self.repo.mega_stone_to_species.get(stone_candidate)
            if target_mega:
                mega_dex = self.repo.pokedex.get(target_mega, {})
                mega_base = str(mega_dex.get("baseSpecies") or "")
                if (
                    mega_base.lower() == base_species.lower()
                    or mega_base.lower() == current_dex_species.lower()
                ):
                    mega_stone = stone_candidate
                    mega_target_species = target_mega
                    mega_base_stats = dict(self.repo.get_base_stats(target_mega))
                    mega_base_stats["hp"] = base_stats["hp"]
                    mega_level_50_stats = compute_level_50_stats_from_base(
                        mega_base_stats, spread, nature
                    )
                    mega_ab_map = mega_dex.get("abilities")
                    if isinstance(mega_ab_map, dict) and mega_ab_map.get("0"):
                        mega_ability = str(mega_ab_map["0"])
                    mega_raw_types = mega_dex.get("types")
                    if mega_raw_types:
                        mega_types = tuple(str(t) for t in mega_raw_types)
                    if not pkm.is_mega and not trainer_mega_used:
                        can_mega_evolve = True

        # Compile moves from in-memory DuckDB
        compiled_moves: List[CompiledMove] = []
        for move_name in pkm.moves:
            cm = self.compile_move(move_name)
            if cm:
                compiled_moves.append(cm)

        # Determine Choice-lock status if holding a Choice item and already executed a move while active
        locked_move: Optional[str] = None
        if (
            item in CHOICE_ITEMS
            and pkm.last_move_used
            and pkm.active_turns > 1
        ):
            locked_move = pkm.last_move_used

        active_turns = pkm.active_turns if pkm.active_turns > 0 else 1

        return CompiledPokemonState(
            species=current_dex_species if pkm.is_mega else pkm.species,
            base_species=base_species,
            nickname=pkm.nickname,
            types=types,
            item=item,
            ability=ability,
            nature=nature,
            spread=spread,
            level_50_stats=level_50_stats,
            max_hp=max_hp,
            current_hp=current_hp,
            current_hp_pct=current_hp_pct,
            fainted=fainted,
            revealed_in_battle=pkm.revealed_in_battle,
            is_mega=pkm.is_mega,
            mega_stone=mega_stone,
            can_mega_evolve=can_mega_evolve,
            mega_target_species=mega_target_species,
            mega_level_50_stats=mega_level_50_stats,
            mega_ability=mega_ability,
            mega_types=mega_types,
            moves=tuple(compiled_moves),
            boosts=dict(pkm.boosts),
            status=pkm.status,
            active_turns=active_turns,
            used_protect_last_turn=pkm.used_protect_last_turn,
            last_move_used=pkm.last_move_used,
            locked_move=locked_move,
        )

    def compile_move(self, move_name: str) -> Optional[CompiledMove]:
        """Compile a move name into a `CompiledMove` from the DuckDB `moves` view."""
        info = self.registry.get_move(move_name)
        if not info:
            info = self.repo.get_move_entry(move_name)
        if not info:
            return CompiledMove(
                id=move_name.lower().replace(" ", "").replace("-", ""),
                name=move_name,
                type="Normal",
                category="Physical",
                base_power=0,
                accuracy=100,
                priority=0,
                target="normal",
            )

        raw_acc = info.get("accuracy")
        if raw_acc is True or raw_acc is None:
            accuracy = 101  # Never-miss sentinel
        else:
            try:
                accuracy = int(raw_acc)
            except (TypeError, ValueError):
                accuracy = 100

        raw_flags = info.get("flags")
        flags = dict(raw_flags) if isinstance(raw_flags, dict) else {}

        raw_sec = info.get("secondary")
        secondary = dict(raw_sec) if isinstance(raw_sec, dict) else None

        raw_boosts = info.get("boosts")
        boosts = (
            {str(k): int(v) for k, v in raw_boosts.items() if v is not None}
            if isinstance(raw_boosts, dict)
            else None
        )

        raw_drain = info.get("drain")
        drain = (
            (int(raw_drain[0]), int(raw_drain[1]))
            if isinstance(raw_drain, (list, tuple)) and len(raw_drain) == 2
            else None
        )

        raw_recoil = info.get("recoil")
        recoil = (
            (int(raw_recoil[0]), int(raw_recoil[1]))
            if isinstance(raw_recoil, (list, tuple)) and len(raw_recoil) == 2
            else None
        )

        return CompiledMove(
            id=str(info.get("id") or move_name.lower()),
            name=str(info.get("name") or move_name),
            type=str(info.get("type") or "Normal"),
            category=str(info.get("category") or "Physical"),
            base_power=int(info.get("basePower") or 0),
            accuracy=accuracy,
            priority=int(info.get("priority") or 0),
            target=str(info.get("target") or "normal"),
            flags=flags,
            secondary=secondary,
            boosts=boosts,
            drain=drain,
            recoil=recoil,
        )

