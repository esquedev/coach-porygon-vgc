# -*- coding: utf-8 -*-
"""Zero-Dependency Local HTTP/SSE Server for the Coach Porygon VGC Replay Coach Studio.

Serves the 3-Step Guided Studio GUI (1. Match Setup -> 2. Live Tensor Core Pipeline Log ->
3. Synchronized Match Review Workspace), embeds the official Pokémon Showdown `replay-embed.js`
battle graphics engine inside a synchronized player frame, serves local Pokémon & item sprites
from `assets/`, manages the persistent DuckDB OTS + 66-SP database, exports team-scoped
telemetry CSVs (`data/telemetry/<team>/battles_telemetry.csv`), and streams real-time per-phase
GPU Tensor Core logs & Nash/IEDS turn audits over Server-Sent Events (SSE).
"""
from __future__ import annotations

import argparse
import copy
import csv
from datetime import datetime
import html as html_lib
import json
import mimetypes
from pathlib import Path
import re
import threading
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional, Tuple

from engine.inference.set_inferencer import OpponentSetInferencer
from engine.telemetry.extractor import (
    CSV_COLUMNS,
    TurnTelemetryRecord,
    _generate_match_id,
)
from engine.terminology import export_glossary_payload
from engine.vgc_tensor_core.state_machine import AnalysisCancelledError

from .gpu_coach_engine import GPUReplayCoachEngine, compute_match_summary
from .ots_db import OTSRosterDatabase, get_sprite_lookup, resolve_sprite_urls
from .protocol_parser import ParsedReplay, parse_showdown_replay

APP_ROOT = Path(__file__).resolve().parent
REPO_ROOT = APP_ROOT.parents[1]
STATIC_DIR = APP_ROOT / "static"
VENDOR_DIR = APP_ROOT / "vendor"
ASSETS_DIR = REPO_ROOT / "assets"
TELEMETRY_ROOT = REPO_ROOT / "data" / "telemetry"
BUG_REPORTS_DIR = REPO_ROOT / "reports" / "bug_logs"
BUG_REPORT_EMAIL = "esquedevil94@gmail.com"
SAMPLE_REPLAY_PATH = APP_ROOT / "sample_data" / "matchagotme_g1.html"


class ReplayCoachAppState:
    """Thread-safe container holding the warm Tensor Core engine, DuckDB OTS store, and active replay."""

    def __init__(
        self,
        preload_sample: bool = False,
        db_path: Optional[Path] = None,
        device: Optional[str] = None,
    ) -> None:
        self.lock = threading.Lock()
        self._stream_cancel_lock = threading.Lock()
        self._active_cancel_event: Optional[threading.Event] = None
        self.ots_db = OTSRosterDatabase(db_path=db_path) if db_path is not None else OTSRosterDatabase()
        self.gpu_engine = GPUReplayCoachEngine(self.ots_db, device=device)
        self.raw_replay_html: str = ""
        self.pov_trainer: str = ""
        self.t1_roster_id: Optional[str] = None
        self.t2_roster_id: Optional[str] = None
        self.t1_paste_text: str = ""
        self.t2_paste_text: str = ""
        self.replay: Optional[ParsedReplay] = None

        if preload_sample and SAMPLE_REPLAY_PATH.exists():
            self.load_sample_replay()

    def start_new_stream_cancel_event(self) -> threading.Event:
        """Cancel any previously running SSE analysis and register a fresh cancellation event."""
        with self._stream_cancel_lock:
            if self._active_cancel_event is not None:
                self._active_cancel_event.set()
            ev = threading.Event()
            self._active_cancel_event = ev
            return ev

    def cancel_active_stream(self) -> bool:
        """Signal any currently running analysis stream to abort cleanly between tiles/chunks."""
        with self._stream_cancel_lock:
            if self._active_cancel_event is not None:
                self._active_cancel_event.set()
                return True
            return False

    def list_telemetry_teams(self) -> List[str]:
        """List available team folders under `data/telemetry/`."""
        teams: List[str] = []
        if TELEMETRY_ROOT.exists():
            for d in sorted(TELEMETRY_ROOT.iterdir()):
                if d.is_dir() and not d.name.startswith("."):
                    teams.append(d.name)
        for default_team in ("char_y_v4", "char_y_v3"):
            if default_team not in teams:
                teams.append(default_team)
        return teams

    def preview_replay(
        self,
        raw_input: str,
        pov_trainer: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fast (<50ms, zero GPU) parse of a replay returning metadata, preview sprites, and auto-matched OTS IDs."""
        prelim = parse_showdown_replay(raw_input, pov_trainer=pov_trainer)
        r1 = self.ots_db.match_best_roster(prelim.trainer_1_name, prelim.trainer_1_preview)
        r2 = self.ots_db.match_best_roster(prelim.trainer_2_name, prelim.trainer_2_preview)
        return {
            "replay_id": prelim.replay_id,
            "format_name": prelim.format_name,
            "trainer_1_name": prelim.trainer_1_name,
            "trainer_2_name": prelim.trainer_2_name,
            "winner": prelim.winner,
            "num_turns": len(prelim.turns),
            "trainer_1_preview": [
                {"species": sp, **resolve_sprite_urls(sp)} for sp in prelim.trainer_1_preview
            ],
            "trainer_2_preview": [
                {"species": sp, **resolve_sprite_urls(sp)} for sp in prelim.trainer_2_preview
            ],
            "suggested_t1_roster_id": r1["roster_id"] if r1 else None,
            "suggested_t2_roster_id": r2["roster_id"] if r2 else None,
        }

    def infer_ots_from_replay(
        self,
        raw_input: str,
        side: str = "t2",
        pov_trainer: Optional[str] = None,
        use_sample: bool = False,
    ) -> Dict[str, Any]:
        """Auto-infer a full Regulation M-C 66-SP Showdown OTS paste from observed replay reveals + DuckDB usage."""
        raw_text = (raw_input or "").strip()
        if (use_sample or not raw_text) and SAMPLE_REPLAY_PATH.exists():
            if use_sample or not self.raw_replay_html:
                raw_text = SAMPLE_REPLAY_PATH.read_text(encoding="utf-8")
            else:
                raw_text = self.raw_replay_html
        if not raw_text:
            raise ValueError("Load or paste a replay first before running DuckDB Auto-Infer.")

        prelim = parse_showdown_replay(raw_text, pov_trainer=pov_trainer or self.pov_trainer or None)
        target_side = "t1" if str(side).lower() in ("t1", "trainer_1") else "t2"
        # OpponentSetInferencer infers `battle.trainer_2`, so orient POV to the opposite trainer when inferring `t1`
        infer_pov = prelim.trainer_2_name if target_side == "t1" else prelim.trainer_1_name
        target_trainer = prelim.trainer_1_name if target_side == "t1" else prelim.trainer_2_name

        oriented = parse_showdown_replay(raw_text, pov_trainer=infer_pov)
        if not oriented.turns:
            raise ValueError("Replay contains no parsed turns for OTS inference.")
        parsed_battle = copy.deepcopy(oriented.turns[-1].battle_state)
        # Merge any moves revealed on the final turn itself into trainer_2 sets
        last_snap = oriented.turns[-1]
        for slot_act in (last_snap.trainer_2_slot_a_action, last_snap.trainer_2_slot_b_action):
            if slot_act and slot_act.kind == "move" and slot_act.move_name and slot_act.actor_species:
                m_obj = parsed_battle.trainer_2.get_pokemon(slot_act.actor_species)
                if m_obj is not None and slot_act.move_name not in m_obj.moves:
                    m_obj.moves.append(slot_act.move_name)
        inferencer = OpponentSetInferencer()
        report = inferencer.infer_battle(parsed_battle)

        stat_labels = (("hp", "HP"), ("atk", "Atk"), ("def", "Def"), ("spa", "SpA"), ("spd", "SpD"), ("spe", "Spe"))
        blocks: List[str] = []
        preview_order = list(parsed_battle.trainer_2.team_preview) or list(report.primary_sets.keys())
        seen_species: set[str] = set()

        for sp in preview_order:
            mon = parsed_battle.trainer_2.get_pokemon(sp) or report.primary_sets.get(sp)
            if mon is None:
                continue
            sp_key = (mon.base_species or mon.species).split("-Mega")[0].lower()
            if sp_key in seen_species:
                continue
            seen_species.add(sp_key)

            display_sp = mon.base_species or mon.species.split("-Mega")[0]
            header = f"{display_sp} @ {mon.item}" if mon.item else display_sp
            lines = [header, f"Ability: {mon.ability or 'None'}", "Level: 50"]

            sp_dict = mon.spread.to_dict()
            ev_parts: List[str] = []
            for sk, lbl in stat_labels:
                sp_val = int(sp_dict.get(sk, 0))
                if sp_val > 0:
                    ev_val = 4 + 8 * (sp_val - 1)
                    ev_parts.append(f"{ev_val} {lbl}")
            if ev_parts:
                lines.append("EVs: " + " / ".join(ev_parts))
            lines.append(f"{mon.nature or 'Serious'} Nature")
            for mv in (mon.moves or [])[:4]:
                lines.append(f"- {mv}")
            blocks.append("\n".join(lines))

        paste_text = "\n\n".join(blocks).strip()
        validation = self.ots_db.validate_paste(paste_text) if paste_text else None
        speed_bounds_out = {
            k: [v[0], v[1]]
            for k, v in (report.speed_bounds_by_species or {}).items()
            if v and (v[0] is not None or v[1] is not None)
        }
        return {
            "ok": True,
            "side": target_side,
            "trainer_name": target_trainer,
            "inferred_count": len(blocks),
            "paste_text": paste_text,
            "validation": validation,
            "speed_bounds": speed_bounds_out,
        }

    def get_telemetry_session_summary(self, team_folder: Optional[str] = None) -> Dict[str, Any]:
        """Aggregate Bo3 / tournament session analytics from `data/telemetry/<team>/battles_telemetry.csv`."""
        teams = self.list_telemetry_teams()
        req_team = (team_folder or "").strip() or (teams[0] if teams else "char_y_v4")

        csv_paths: List[Tuple[str, Path]] = []
        if req_team.lower() == "all":
            for tf in teams:
                p = TELEMETRY_ROOT / tf / "battles_telemetry.csv"
                if p.exists() and p.stat().st_size > 0:
                    csv_paths.append((tf, p))
        else:
            clean_tf = re.sub(r"[^a-zA-Z0-9_-]", "_", req_team)
            p = TELEMETRY_ROOT / clean_tf / "battles_telemetry.csv"
            if p.exists() and p.stat().st_size > 0:
                csv_paths.append((clean_tf, p))

        matches_by_id: Dict[str, Dict[str, Any]] = {}
        badge_totals = {"optimal": 0, "good": 0, "inaccuracy": 0, "weak_dominated": 0, "strict_dominated": 0}
        mistakes_by_phase = {"lead": 0, "midgame": 0, "endgame": 0}
        lead_stats_map: Dict[str, Dict[str, int]] = {}
        total_turns = 0
        total_variance_events = 0

        def _detect_badge(comment_str: str) -> Optional[str]:
            c = comment_str or ""
            if "[?? " in c or "[??]" in c:
                return "strict_dominated"
            if "[?! " in c or "[?!]" in c:
                return "inaccuracy"
            if "[? " in c or "[?]" in c:
                return "weak_dominated"
            if "[!! " in c or "[!!]" in c:
                return "optimal"
            if "[! " in c or "[!]" in c:
                return "good"
            return None

        badge_acc_weights = {
            "optimal": 100.0,
            "good": 90.0,
            "inaccuracy": 72.0,
            "weak_dominated": 50.0,
            "strict_dominated": 20.0,
        }

        for tf_name, cpath in csv_paths:
            with open(cpath, mode="r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    mid = (row.get("match_id") or "").strip()
                    if not mid:
                        continue
                    key = f"{tf_name}:{mid}"
                    if key not in matches_by_id:
                        t1_name = (row.get("trainer_1") or "trainer_1").strip()
                        t2_name = (row.get("trainer_2") or "trainer_2").strip()
                        winner = (row.get("winner") or "Unknown").strip()
                        is_win = bool(winner and winner.lower() == t1_name.lower())
                        matches_by_id[key] = {
                            "match_id": mid,
                            "team_folder": tf_name,
                            "timestamp": (row.get("timestamp") or "").strip(),
                            "trainer_1": t1_name,
                            "trainer_2": t2_name,
                            "winner": winner,
                            "is_win": is_win,
                            "turns": 0,
                            "lead_pair": "",
                            "variance_events": 0,
                            "badge_counts": {k: 0 for k in badge_totals},
                            "_acc_scores": [],
                        }
                    m = matches_by_id[key]
                    m["turns"] += 1
                    total_turns += 1

                    try:
                        turn_num = int(float(row.get("turn") or 0))
                    except ValueError:
                        turn_num = 0

                    if turn_num == 1 and not m["lead_pair"]:
                        a1 = (row.get("trainer_1_active_1") or "").strip()
                        a2 = (row.get("trainer_1_active_2") or "").strip()
                        pair_mons = sorted([x for x in (a1, a2) if x and x != "None"])
                        if pair_mons:
                            m["lead_pair"] = " + ".join(pair_mons)

                    ve = (row.get("variance_events") or "").strip()
                    if ve and ve.lower() != "none":
                        v_cnt = len([x for x in ve.split(";") if x.strip()])
                        m["variance_events"] += v_cnt
                        total_variance_events += v_cnt

                    b_key = _detect_badge(row.get("comment") or "")
                    if b_key:
                        m["badge_counts"][b_key] += 1
                        badge_totals[b_key] += 1
                        m["_acc_scores"].append(badge_acc_weights[b_key])
                        if b_key in ("inaccuracy", "weak_dominated", "strict_dominated"):
                            if turn_num <= 1:
                                mistakes_by_phase["lead"] += 1
                            elif turn_num <= 4:
                                mistakes_by_phase["midgame"] += 1
                            else:
                                mistakes_by_phase["endgame"] += 1

        matches_list: List[Dict[str, Any]] = []
        wins = 0
        losses = 0
        all_match_accs: List[float] = []

        for m in sorted(matches_by_id.values(), key=lambda x: (x["timestamp"], x["match_id"])):
            scores = m.pop("_acc_scores")
            acc = round(sum(scores) / len(scores), 1) if scores else None
            m["accuracy_pct"] = acc
            if acc is not None:
                all_match_accs.append(acc)
            if m["is_win"]:
                wins += 1
            elif m["winner"] and m["winner"].lower() != "unknown":
                losses += 1
            if m["lead_pair"]:
                ls = lead_stats_map.setdefault(m["lead_pair"], {"games": 0, "wins": 0})
                ls["games"] += 1
                if m["is_win"]:
                    ls["wins"] += 1
            matches_list.append(m)

        total_matches = len(matches_list)
        decided = wins + losses
        win_rate_pct = round(100.0 * wins / decided, 1) if decided > 0 else 0.0
        avg_acc_pct = round(sum(all_match_accs) / len(all_match_accs), 1) if all_match_accs else None

        lead_stats = [
            {
                "lead": lead_name,
                "games": d["games"],
                "wins": d["wins"],
                "win_rate_pct": round(100.0 * d["wins"] / max(1, d["games"]), 1),
            }
            for lead_name, d in sorted(
                lead_stats_map.items(),
                key=lambda kv: (-kv[1]["games"], -kv[1]["wins"], kv[0]),
            )[:8]
        ]

        return {
            "ok": True,
            "team_folder": req_team,
            "teams": teams,
            "total_matches": total_matches,
            "wins": wins,
            "losses": losses,
            "win_rate_pct": win_rate_pct,
            "avg_accuracy_pct": avg_acc_pct,
            "total_turns": total_turns,
            "total_variance_events": total_variance_events,
            "badge_totals": badge_totals,
            "mistakes_by_phase": mistakes_by_phase,
            "lead_stats": lead_stats,
            "matches": list(reversed(matches_list)),
        }

    def load_sample_replay(self) -> Dict[str, Any]:
        """Load the bundled sample match (`treces_gc` vs. `MatchaGotMe`) with both pre-seeded OTS rosters."""
        raw = SAMPLE_REPLAY_PATH.read_text(encoding="utf-8") if SAMPLE_REPLAY_PATH.exists() else ""
        return self.load_replay(
            raw_input=raw,
            pov_trainer="treces_gc",
            t1_roster_id="treces_gc_char_y_v4",
            t2_roster_id="matchagotme_camerupt_tr",
        )

    def load_replay(
        self,
        raw_input: str,
        pov_trainer: Optional[str] = None,
        t1_roster_id: Optional[str] = None,
        t2_roster_id: Optional[str] = None,
        t1_paste_text: Optional[str] = None,
        t2_paste_text: Optional[str] = None,
        t1_save_meta: Optional[Dict[str, Any]] = None,
        t2_save_meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Parse replay, bind DuckDB or inline pasted Full OTS rosters, and store active state."""
        with self.lock:
            prelim = parse_showdown_replay(raw_input, pov_trainer=pov_trainer or self.pov_trainer or None)

            # Optional save-to-DuckDB for inline pasted OTS
            if t1_paste_text and t1_paste_text.strip() and t1_save_meta and t1_save_meta.get("save_to_db"):
                rid1 = str(t1_save_meta.get("roster_id") or f"{prelim.trainer_1_name.lower()}_ots").strip()
                rid1 = re.sub(r"[^a-zA-Z0-9_-]", "_", rid1)
                dname1 = str(t1_save_meta.get("display_name") or f"{prelim.trainer_1_name} — Full OTS").strip()
                self.ots_db.save_roster(rid1, dname1, prelim.trainer_1_name, t1_paste_text)
                t1_roster_id = rid1

            if t2_paste_text and t2_paste_text.strip() and t2_save_meta and t2_save_meta.get("save_to_db"):
                rid2 = str(t2_save_meta.get("roster_id") or f"{prelim.trainer_2_name.lower()}_ots").strip()
                rid2 = re.sub(r"[^a-zA-Z0-9_-]", "_", rid2)
                dname2 = str(t2_save_meta.get("display_name") or f"{prelim.trainer_2_name} — Full OTS").strip()
                self.ots_db.save_roster(rid2, dname2, prelim.trainer_2_name, t2_paste_text)
                t2_roster_id = rid2

            # Resolve Trainer 1 OTS (inline paste -> explicit roster_id -> auto-match)
            r1 = None
            paste1 = ""
            if t1_paste_text and t1_paste_text.strip() and not t1_roster_id:
                paste1 = t1_paste_text.strip()
                self.t1_roster_id = "inline_ots"
            else:
                r1 = (
                    self.ots_db.get_roster(t1_roster_id)
                    if t1_roster_id
                    else self.ots_db.match_best_roster(prelim.trainer_1_name, prelim.trainer_1_preview)
                )
                paste1 = r1["paste_text"] if r1 else ""
                self.t1_roster_id = r1["roster_id"] if r1 else None

            # Resolve Trainer 2 OTS (inline paste -> explicit roster_id -> auto-match)
            r2 = None
            paste2 = ""
            if t2_paste_text and t2_paste_text.strip() and not t2_roster_id:
                paste2 = t2_paste_text.strip()
                self.t2_roster_id = "inline_ots"
            else:
                r2 = (
                    self.ots_db.get_roster(t2_roster_id)
                    if t2_roster_id
                    else self.ots_db.match_best_roster(prelim.trainer_2_name, prelim.trainer_2_preview)
                )
                paste2 = r2["paste_text"] if r2 else ""
                self.t2_roster_id = r2["roster_id"] if r2 else None

            t1_sets = self.ots_db.get_parsed_sets_by_species(paste1) if paste1 else {}
            t2_sets = self.ots_db.get_parsed_sets_by_species(paste2) if paste2 else {}

            parsed = parse_showdown_replay(
                raw_input,
                pov_trainer=pov_trainer or prelim.trainer_1_name,
                trainer_1_ots_sets=t1_sets,
                trainer_2_ots_sets=t2_sets,
            )
            self.raw_replay_html = raw_input
            self.pov_trainer = parsed.trainer_1_name
            self.t1_paste_text = paste1
            self.t2_paste_text = paste2
            self.replay = parsed
            return self.get_state_summary_unlocked()

    def export_match_telemetry_csv(
        self,
        team_folder: str,
        turn_results: Dict[int, Dict[str, Any]],
        lang: str = "es",
        style: str = "vgc",
    ) -> Dict[str, Any]:
        """Export analyzed match turns + deterministic coaching comments to `data/telemetry/<team>/battles_telemetry.csv`."""
        with self.lock:
            rep = self.replay
            if rep is None:
                raise ValueError("No active replay loaded to export.")

            clean_team = re.sub(r"[^a-zA-Z0-9_-]", "_", (team_folder or "char_y_v4").strip()) or "char_y_v4"
            csv_path = TELEMETRY_ROOT / clean_team / "battles_telemetry.csv"
            csv_path.parent.mkdir(parents=True, exist_ok=True)

            match_id = _generate_match_id(rep.raw_log_text or rep.replay_id)
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            profile_key = f"{'en' if str(lang).lower().startswith('en') else 'es'}_{'scientific' if str(style).lower() == 'scientific' else 'vgc'}"

            new_records: List[TurnTelemetryRecord] = []
            for idx, snap in enumerate(rep.turns):
                t_num = snap.turn_number
                tr = turn_results.get(t_num) or turn_results.get(str(t_num)) or {}
                act = tr.get("actual_action") or {}
                com_vars = tr.get("commentary_variants") or {}
                com = com_vars.get(profile_key) or tr.get("commentary") or {}

                # Active Pokémon names at turn start
                b_t1 = snap.battle_state.trainer_1.active_slots
                b_t2 = snap.battle_state.trainer_2.active_slots
                t1_a1 = b_t1[0] if len(b_t1) > 0 and b_t1[0] else "None"
                t1_a2 = b_t1[1] if len(b_t1) > 1 and b_t1[1] else "None"
                t2_a1 = b_t2[0] if len(b_t2) > 0 and b_t2[0] else "None"
                t2_a2 = b_t2[1] if len(b_t2) > 1 and b_t2[1] else "None"

                t1_moves_str = act.get("desc") or " | ".join(
                    x.move_name or x.switch_to_species or x.kind
                    for x in (snap.trainer_1_slot_a_action, snap.trainer_1_slot_b_action)
                    if x is not None
                )
                t2_moves_str = act.get("opp_actual_desc") or " | ".join(
                    x.move_name or x.switch_to_species or x.kind
                    for x in (snap.trainer_2_slot_a_action, snap.trainer_2_slot_b_action)
                    if x is not None
                )

                # Compute turn damage differential from next snapshot HP delta
                next_snap = rep.turns[idx + 1] if idx + 1 < len(rep.turns) else None
                dmg_to_t2 = 0.0
                dmg_to_t1 = 0.0
                if next_snap is not None:
                    for sp, m_before in snap.battle_state.trainer_2.pokemon_sets.items():
                        m_after = next_snap.battle_state.trainer_2.get_pokemon(sp)
                        if m_after is not None and m_before.current_hp_pct > m_after.current_hp_pct:
                            dmg_to_t2 += round(m_before.current_hp_pct - m_after.current_hp_pct, 1)
                    for sp, m_before in snap.battle_state.trainer_1.pokemon_sets.items():
                        m_after = next_snap.battle_state.trainer_1.get_pokemon(sp)
                        if m_after is not None and m_before.current_hp_pct > m_after.current_hp_pct:
                            dmg_to_t1 += round(m_before.current_hp_pct - m_after.current_hp_pct, 1)

                faints_list = [f"{f.get('trainer')}:{f.get('species')}" for f in (snap.events.faints or [])]
                var_items: List[str] = []
                for c in snap.events.crits or []:
                    var_items.append(f"Crit on {c.get('target_species')}")
                for fl in snap.events.flinches or []:
                    var_items.append(f"Flinch on {fl.get('species')}")
                for ms in snap.events.misses or []:
                    var_items.append(f"Miss {ms.get('move')}")

                fc_items: List[str] = []
                if snap.trick_room_turns > 0:
                    fc_items.append(f"Trick Room ({snap.trick_room_turns}t)")
                if snap.trainer_1_tailwind_turns > 0:
                    fc_items.append(f"T1 Tailwind ({snap.trainer_1_tailwind_turns}t)")
                if snap.trainer_2_tailwind_turns > 0:
                    fc_items.append(f"T2 Tailwind ({snap.trainer_2_tailwind_turns}t)")

                # Build standardized AGENTS.md tagged comment
                tags: List[str] = []
                if t_num == 1:
                    tags.append("[LEAD_EVAL]")
                if snap.events.megas:
                    tags.append("[MEGA_DECISION]")
                if var_items:
                    tags.append("[VARIANCE_AUDIT]")
                tags.append("[NASH_REGRET]")

                sym = com.get("symbol", "")
                bdg = com.get("badge", "")
                hdl = com.get("headline", "")
                top_list = tr.get("top_actions") or []
                best_line = top_list[0].get("desc", "") if top_list else ""
                comment_str = " ".join(tags)
                if bdg or hdl:
                    comment_str += f" [{sym} {bdg}] {hdl}"
                if best_line and float(act.get("nash_regret", 0.0)) > 0.03:
                    comment_str += f" | Optimal: {best_line}"

                new_records.append(
                    TurnTelemetryRecord(
                        match_id=match_id,
                        timestamp=now_str,
                        turn=int(t_num),
                        trainer_1=rep.trainer_1_name,
                        trainer_2=rep.trainer_2_name,
                        trainer_1_active_1=t1_a1,
                        trainer_1_active_2=t1_a2,
                        trainer_2_active_1=t2_a1,
                        trainer_2_active_2=t2_a2,
                        trainer_1_moves=t1_moves_str,
                        trainer_2_moves=t2_moves_str,
                        damage_dealt_to_trainer_2=round(dmg_to_t2, 1),
                        damage_dealt_to_trainer_1=round(dmg_to_t1, 1),
                        faints_this_turn="; ".join(faints_list) if faints_list else "None",
                        variance_events="; ".join(var_items) if var_items else "None",
                        weather=snap.weather or "Clear",
                        terrain=snap.terrain or "None",
                        field_conditions="; ".join(fc_items) if fc_items else "None",
                        winner=rep.winner or "Unknown",
                        comment=comment_str.strip(),
                    )
                )

            # Deduplicate by match_id: replace existing rows for this match_id or append at end
            existing_rows: List[Dict[str, Any]] = []
            replaced = False
            if csv_path.exists() and csv_path.stat().st_size > 0:
                with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get("match_id") == match_id:
                            replaced = True
                            continue
                        existing_rows.append(row)

            all_rows = existing_rows + [r.to_dict() for r in new_records]
            with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
                writer.writeheader()
                writer.writerows(all_rows)

            rel_csv = (
                csv_path.relative_to(REPO_ROOT).as_posix()
                if csv_path.is_relative_to(REPO_ROOT)
                else csv_path.as_posix()
            )
            return {
                "ok": True,
                "match_id": match_id,
                "team_folder": clean_team,
                "csv_path": rel_csv,
                "turns_written": len(new_records),
                "updated_existing": replaced,
                "teams": self.list_telemetry_teams(),
            }

    def create_bug_report(
        self,
        user_message: str,
        client_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate and persist a structured Markdown bug log under `reports/bug_logs/` with a pre-filled `mailto:` link."""
        ctx = client_context or {}
        now = datetime.now()
        stamp = now.strftime("%Y%m%d_%H%M%S")
        iso_ts = now.strftime("%Y-%m-%d %H:%M:%S")

        BUG_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"bug_{stamp}.md"
        file_path = BUG_REPORTS_DIR / filename

        with self.lock:
            rep = self.replay
            rep_meta = {
                "replay_id": rep.replay_id if rep else None,
                "format": rep.format_name if rep else None,
                "trainer_1": rep.trainer_1_name if rep else None,
                "trainer_2": rep.trainer_2_name if rep else None,
                "num_turns": len(rep.turns) if rep else 0,
                "t1_roster_id": self.t1_roster_id,
                "t2_roster_id": self.t2_roster_id,
            }
            dev_name = self.gpu_engine.device_name
            dev_type = self.gpu_engine.device_type

        msg_clean = (user_message or "").strip() or "(No message provided)"
        cur_turn = ctx.get("current_turn")
        lang = ctx.get("lang", "es")
        style = ctx.get("style", "vgc")
        num_mc = ctx.get("num_mc")
        active_step = ctx.get("active_step", "setup")
        turn_snapshot = ctx.get("current_turn_summary") or {}
        recent_logs = ctx.get("recent_pipeline_logs") or []
        js_errors = ctx.get("js_errors") or []
        user_agent = ctx.get("user_agent") or "Unknown"

        lines: List[str] = [
            f"# Coach Porygon VGC — Bug Report ({iso_ts})",
            "",
            "## User Description",
            msg_clean,
            "",
            "## Environment & Session",
            f"- **Timestamp:** {iso_ts}",
            f"- **Compute Backend:** `{dev_type.upper()}` — `{dev_name}`",
            f"- **Active Step / Profile:** `{active_step}` · `{lang}_{style}` · `K={num_mc}`",
            f"- **Browser:** `{user_agent}`",
            "",
            "## Match & OTS Context",
            f"- **Replay ID:** `{rep_meta['replay_id']}` ({rep_meta['format']})",
            f"- **Matchup:** `{rep_meta['trainer_1']}` (trainer_1) vs. `{rep_meta['trainer_2']}` (trainer_2) · `{rep_meta['num_turns']}` turns",
            f"- **Selected Rosters:** `trainer_1={rep_meta['t1_roster_id']}` | `trainer_2={rep_meta['t2_roster_id']}`",
            f"- **Current Turn:** `{cur_turn}`",
        ]

        if turn_snapshot:
            lines.extend(
                [
                    "",
                    "## Active Turn Evaluation Snapshot",
                    f"- **Verdict:** `{turn_snapshot.get('symbol', '')} {turn_snapshot.get('badge', '')}`",
                    f"- **Field:** `{json.dumps(turn_snapshot.get('field', {}), ensure_ascii=False)}`",
                    f"- **Played (trainer_1):** `{turn_snapshot.get('played', '')}`",
                    f"- **Opponent (trainer_2):** `{turn_snapshot.get('opp_played', '')}`",
                    f"- **Recommended #1:** `{turn_snapshot.get('recommended', '')}`",
                    f"- **Matrix / Timelines:** `{turn_snapshot.get('matrix_shape')}` · `{turn_snapshot.get('total_timelines')}` sims",
                ]
            )

        if js_errors:
            lines.extend(["", "## Browser JS Errors"])
            for err in js_errors[-10:]:
                lines.append(f"- `{err}`")

        if recent_logs:
            lines.extend(["", "## Recent Tensor Core Pipeline Logs", "```text"])
            for lg_line in recent_logs[-25:]:
                lines.append(str(lg_line))
            lines.append("```")

        report_text = "\n".join(lines) + "\n"
        file_path.write_text(report_text, encoding="utf-8")

        rel_path = (
            file_path.relative_to(REPO_ROOT).as_posix()
            if file_path.is_relative_to(REPO_ROOT)
            else file_path.as_posix()
        )

        # Build RFC-safe mailto: URL addressed directly to esquedevil94@gmail.com
        subj_suffix = f"Turn {cur_turn}" if cur_turn else active_step
        subject = f"[Coach Porygon VGC Bug] {subj_suffix} ({stamp})"
        mail_body = report_text if len(report_text) <= 1600 else (
            report_text[:1520] + f"\n\n[Truncated for email URL — attach local file: {rel_path}]"
        )
        mailto_url = (
            f"mailto:{BUG_REPORT_EMAIL}"
            f"?subject={urllib.parse.quote(subject)}"
            f"&body={urllib.parse.quote(mail_body)}"
        )

        return {
            "ok": True,
            "filename": filename,
            "file_path": rel_path,
            "recipient": BUG_REPORT_EMAIL,
            "report_text": report_text,
            "mailto_url": mailto_url,
        }

    def get_state_summary_unlocked(self) -> Dict[str, Any]:
        """Serialize current replay metadata, matched rosters, and compute hardware info."""
        rep = self.replay
        return {
            "device": self.gpu_engine.device_name,
            "device_type": self.gpu_engine.device_type,
            "recommended_k": 128 if self.gpu_engine.device_type == "cuda" else 64,
            "has_vendor_showdown": (VENDOR_DIR / "replay-embed.js").exists(),
            "rosters": self.ots_db.list_rosters(),
            "active_t1_roster_id": self.t1_roster_id,
            "active_t2_roster_id": self.t2_roster_id,
            "t1_validation": self.ots_db.validate_paste(self.t1_paste_text) if self.t1_paste_text else None,
            "t2_validation": self.ots_db.validate_paste(self.t2_paste_text) if self.t2_paste_text else None,
            "telemetry_teams": self.list_telemetry_teams(),
            "terminology": export_glossary_payload(),
            "replay": None
            if rep is None
            else {
                "replay_id": rep.replay_id,
                "format_name": rep.format_name,
                "trainer_1_name": rep.trainer_1_name,
                "trainer_2_name": rep.trainer_2_name,
                "pov_is_right_side": rep.pov_is_right_side,
                "winner": rep.winner,
                "num_turns": len(rep.turns),
                "trainer_1_preview": [
                    {"species": sp, **resolve_sprite_urls(sp)} for sp in rep.trainer_1_preview
                ],
                "trainer_2_preview": [
                    {"species": sp, **resolve_sprite_urls(sp)} for sp in rep.trainer_2_preview
                ],
                "trainer_1_brought": rep.trainer_1_brought,
                "trainer_2_brought": rep.trainer_2_brought,
                "turn_numbers": [t.turn_number for t in rep.turns],
            },
        }

    def render_official_showdown_player_html(self) -> str:
        """Render the embedded official Pokémon Showdown replay player with postMessage turn sync."""
        rep = self.replay
        if rep is None:
            return "<!doctype html><html><body style='background:#0f172a;color:#94a3b8;font-family:sans-serif;padding:24px'>No replay loaded yet. Complete Step 1 (Match Setup) to start.</body></html>"

        escaped_log = rep.raw_log_text.replace("</script", r"<\/script")
        embed_src = (
            "/vendor/replay-embed.js"
            if (VENDOR_DIR / "replay-embed.js").exists()
            else "https://play.pokemonshowdown.com/js/replay-embed.js"
        )
        flip_js = "true" if rep.pov_is_right_side else "false"
        title_str = html_lib.escape(f"{rep.trainer_1_name} vs. {rep.trainer_2_name}")

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>{title_str} — Official Showdown Player</title>
<style>
  html, body {{
    margin: 0;
    padding: 0;
    background: #0f172a;
    color: #e2e8f0;
    font-family: Verdana, sans-serif;
    overflow-x: hidden;
  }}
  .wrapper.replay-wrapper {{
    max-width: 100% !important;
    margin: 0 auto !important;
    padding: 6px 8px 12px 8px;
  }}
  .battle-log {{
    max-height: 290px !important;
    border-radius: 6px;
  }}
  .replay-controls, .replay-controls-2 {{
    margin-top: 6px;
  }}
</style>
</head>
<body class="dark">
<div class="wrapper replay-wrapper">
  <input type="hidden" name="replayid" value="{html_lib.escape(rep.replay_id)}" />
  <div class="battle"></div>
  <div class="battle-log"></div>
  <div class="replay-controls"></div>
  <div class="replay-controls-2"></div>
  <script type="text/plain" class="battle-log-data">{escaped_log}</script>
</div>
<script src="{embed_src}"></script>
<script>
(function() {{
  const SHOULD_FLIP = {flip_js};
  let flippedOnce = false;
  let lastTurnPosted = -1;

  function notifyParentTurn(turnVal) {{
    if (typeof turnVal === 'number' && turnVal !== lastTurnPosted) {{
      lastTurnPosted = turnVal;
      window.parent.postMessage({{ type: 'TURN_CHANGED', turn: turnVal, paused: !!(window.Replays && window.Replays.battle && window.Replays.battle.paused) }}, '*');
    }}
  }}

  function wireShowdownBridge() {{
    if (!window.Replays || !window.Replays.battle) {{
      setTimeout(wireShowdownBridge, 150);
      return;
    }}
    const battle = window.Replays.battle;
    try {{ window.Replays.changeSetting('color', 'dark'); }} catch (e) {{}}
    try {{ window.Replays.changeSetting('sound', 'off'); }} catch (e) {{}}
    if (SHOULD_FLIP && !flippedOnce) {{
      flippedOnce = true;
      try {{ battle.switchViewpoint(); }} catch (e) {{}}
    }}
    battle.subscribe(function() {{
      notifyParentTurn(battle.turn);
    }});
    try {{
      battle.seekTurn(1);
      notifyParentTurn(battle.turn);
    }} catch (e) {{}}
    window.parent.postMessage({{ type: 'PLAYER_READY', turn: battle.turn }}, '*');
  }}

  window.addEventListener('message', function(ev) {{
    const msg = ev.data || {{}};
    if (!window.Replays || !window.Replays.battle) return;
    const battle = window.Replays.battle;
    if (msg.type === 'SEEK_TURN' && typeof msg.turn === 'number') {{
      try {{
        if (msg.pause !== false) battle.pause();
        battle.seekTurn(msg.turn);
        notifyParentTurn(battle.turn);
      }} catch (e) {{}}
    }} else if (msg.type === 'STEP_TURN' && typeof msg.delta === 'number') {{
      try {{
        battle.pause();
        battle.seekBy(msg.delta);
        notifyParentTurn(battle.turn);
      }} catch (e) {{}}
    }} else if (msg.type === 'SWITCH_VIEWPOINT') {{
      try {{ battle.switchViewpoint(); }} catch (e) {{}}
    }} else if (msg.type === 'TOGGLE_PLAY') {{
      try {{
        if (battle.paused) battle.play();
        else battle.pause();
      }} catch (e) {{}}
    }} else if (msg.type === 'PLAY') {{
      try {{
        if (typeof msg.turn === 'number') battle.seekTurn(msg.turn);
        if (battle.paused) battle.play();
      }} catch (e) {{}}
    }} else if (msg.type === 'PAUSE') {{
      try {{
        if (!battle.paused) battle.pause();
      }} catch (e) {{}}
    }}
  }});

  window.addEventListener('load', function() {{
    setTimeout(wireShowdownBridge, 250);
  }});
}})();
</script>
</body>
</html>
"""


def make_handler(app_state: ReplayCoachAppState):
    """Create a request handler class bound to the shared `ReplayCoachAppState`."""

    class CoachHTTPHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

        def _send_bytes(
            self,
            data: bytes,
            content_type: str,
            status: int = HTTPStatus.OK,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _send_json(self, obj: Any, status: int = HTTPStatus.OK) -> None:
            raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self._send_bytes(raw, "application/json; charset=utf-8", status=status)

        def _read_json_body(self) -> Dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            return json.loads(raw.decode("utf-8"))

        def _serve_file(self, base_dir: Path, rel_path: str) -> None:
            safe_rel = urllib.parse.unquote(rel_path).lstrip("/")
            full = (base_dir / safe_rel).resolve()
            if not str(full).startswith(str(base_dir.resolve())) or not full.is_file():
                self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
                return
            ctype, _ = mimetypes.guess_type(str(full))
            self._send_bytes(full.read_bytes(), ctype or "application/octet-stream")

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            qs = urllib.parse.parse_qs(parsed.query)

            if path == "/" or path == "/index.html":
                self._serve_file(STATIC_DIR, "index.html")
                return
            if path.startswith("/static/"):
                self._serve_file(STATIC_DIR, path[len("/static/"):])
                return
            if path.startswith("/vendor/"):
                self._serve_file(VENDOR_DIR, path[len("/vendor/"):])
                return
            if path.startswith("/assets/"):
                self._serve_file(ASSETS_DIR, path[len("/assets/"):])
                return
            if path == "/api/state":
                with app_state.lock:
                    summary = app_state.get_state_summary_unlocked()
                self._send_json(summary)
                return
            if path == "/api/rosters":
                self._send_json({"rosters": app_state.ots_db.list_rosters()})
                return
            if path == "/api/sprites":
                self._send_json(get_sprite_lookup())
                return
            if path == "/api/telemetry/teams":
                self._send_json({"teams": app_state.list_telemetry_teams()})
                return
            if path == "/api/telemetry/summary":
                try:
                    team_q = qs.get("team", [None])[0]
                    self._send_json(app_state.get_telemetry_session_summary(team_folder=team_q))
                except Exception as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            if path == "/api/replay-player":
                with app_state.lock:
                    html_doc = app_state.render_official_showdown_player_html()
                self._send_bytes(html_doc.encode("utf-8"), "text/html; charset=utf-8")
                return
            if path == "/api/analyze/turn":
                try:
                    turn_num = int(qs.get("turn", ["1"])[0])
                    num_mc = int(qs.get("num_mc", ["128"])[0])
                    force = qs.get("force", ["0"])[0] in ("1", "true", "yes")
                    two_ply = qs.get("two_ply", ["0"])[0] in ("1", "true", "yes")
                    with app_state.lock:
                        rep = app_state.replay
                    if rep is None:
                        self._send_json({"error": "No replay loaded"}, status=HTTPStatus.BAD_REQUEST)
                        return
                    result = app_state.gpu_engine.analyze_turn(
                        rep,
                        turn_number=turn_num,
                        min_prior=0.0,
                        num_mc=num_mc,
                        force_recompute=force,
                        enable_two_ply=two_ply,
                    )
                    self._send_json(result)
                except Exception as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            if path == "/api/analyze/stream":
                num_mc = int(qs.get("num_mc", ["128"])[0])
                start_turn = int(qs.get("start_turn", ["1"])[0])
                force = qs.get("force", ["0"])[0] in ("1", "true", "yes")
                two_ply = qs.get("two_ply", ["0"])[0] in ("1", "true", "yes")
                with app_state.lock:
                    rep = app_state.replay
                if rep is None:
                    self._send_json({"error": "No replay loaded"}, status=HTTPStatus.BAD_REQUEST)
                    return

                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()

                def _write_sse(event_name: str, payload_obj: Any) -> bool:
                    try:
                        msg = f"event: {event_name}\ndata: {json.dumps(payload_obj, ensure_ascii=False)}\n\n"
                        self.wfile.write(msg.encode("utf-8"))
                        self.wfile.flush()
                        return True
                    except (BrokenPipeError, ConnectionResetError):
                        return False

                all_turn_results: List[Dict[str, Any]] = []
                total_turns = len(rep.turns)
                cancel_event = app_state.start_new_stream_cancel_event()

                for idx, snap in enumerate(rep.turns, 1):
                    if snap.turn_number < start_turn:
                        continue
                    if cancel_event.is_set():
                        _write_sse("cancelled", {"turn": snap.turn_number})
                        return

                    def _on_phase_log(log_entry: Dict[str, Any], t_idx: int = idx) -> None:
                        log_entry["turn_index"] = t_idx
                        log_entry["total_turns"] = total_turns
                        if not _write_sse("log", log_entry):
                            cancel_event.set()

                    try:
                        res = app_state.gpu_engine.analyze_turn(
                            rep,
                            turn_number=snap.turn_number,
                            min_prior=0.0,
                            num_mc=num_mc,
                            force_recompute=force,
                            enable_two_ply=two_ply,
                            log_cb=_on_phase_log,
                            cancel_event=cancel_event,
                        )
                        all_turn_results.append(res)
                        if not _write_sse("turn", res):
                            cancel_event.set()
                            return
                    except AnalysisCancelledError:
                        _write_sse("cancelled", {"turn": snap.turn_number})
                        return
                    except (BrokenPipeError, ConnectionResetError):
                        cancel_event.set()
                        return
                    except Exception as exc:
                        if not _write_sse("error", {"turn": snap.turn_number, "error": str(exc)}):
                            cancel_event.set()
                            return

                summary_payload = {
                    "match_summary": compute_match_summary(all_turn_results),
                }
                _write_sse("done", summary_payload)
                return

            self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            try:
                body = self._read_json_body()
            except Exception as exc:
                self._send_json({"error": f"Invalid JSON: {exc}"}, status=HTTPStatus.BAD_REQUEST)
                return

            if path == "/api/replay/preview":
                raw_html = str(body.get("raw_input") or "")
                if body.get("use_sample") and SAMPLE_REPLAY_PATH.exists():
                    raw_html = SAMPLE_REPLAY_PATH.read_text(encoding="utf-8")
                if not raw_html.strip():
                    self._send_json({"error": "Empty replay content"}, status=HTTPStatus.BAD_REQUEST)
                    return
                try:
                    preview = app_state.preview_replay(raw_html, pov_trainer=body.get("pov_trainer"))
                    self._send_json(preview)
                except Exception as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            if path == "/api/replay/load-sample":
                try:
                    summary = app_state.load_sample_replay()
                    self._send_json(summary)
                except Exception as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            if path == "/api/replay/load":
                raw_html = str(body.get("raw_input") or "")
                if not raw_html.strip():
                    with app_state.lock:
                        raw_html = app_state.raw_replay_html
                if not raw_html.strip() and SAMPLE_REPLAY_PATH.exists():
                    raw_html = SAMPLE_REPLAY_PATH.read_text(encoding="utf-8")
                try:
                    summary = app_state.load_replay(
                        raw_input=raw_html,
                        pov_trainer=body.get("pov_trainer"),
                        t1_roster_id=body.get("t1_roster_id"),
                        t2_roster_id=body.get("t2_roster_id"),
                        t1_paste_text=body.get("t1_paste_text"),
                        t2_paste_text=body.get("t2_paste_text"),
                        t1_save_meta=body.get("t1_save_meta"),
                        t2_save_meta=body.get("t2_save_meta"),
                    )
                    self._send_json(summary)
                except Exception as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            if path == "/api/rosters/validate":
                paste_text = str(body.get("paste_text") or "")
                try:
                    self._send_json(app_state.ots_db.validate_paste(paste_text))
                except Exception as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            if path == "/api/rosters/infer-from-replay":
                try:
                    res = app_state.infer_ots_from_replay(
                        raw_input=str(body.get("raw_input") or ""),
                        side=str(body.get("side") or "t2"),
                        pov_trainer=body.get("pov_trainer"),
                        use_sample=bool(body.get("use_sample")),
                    )
                    self._send_json(res)
                except Exception as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            if path == "/api/rosters":
                try:
                    saved = app_state.ots_db.save_roster(
                        roster_id=str(body.get("roster_id") or "").strip(),
                        display_name=str(body.get("display_name") or "").strip(),
                        trainer_hint=str(body.get("trainer_hint") or "").strip(),
                        paste_text=str(body.get("paste_text") or ""),
                    )
                    self._send_json({"saved": saved, "rosters": app_state.ots_db.list_rosters()})
                except Exception as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            if path == "/api/rosters/delete":
                roster_id = str(body.get("roster_id") or "").strip()
                try:
                    deleted = app_state.ots_db.delete_roster(roster_id)
                    self._send_json({"deleted": deleted, "rosters": app_state.ots_db.list_rosters()})
                except Exception as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            if path == "/api/analyze/cancel":
                cancelled = app_state.cancel_active_stream()
                self._send_json({"ok": True, "cancelled": cancelled})
                return

            if path == "/api/bug-report":
                try:
                    res = app_state.create_bug_report(
                        user_message=str(body.get("message") or ""),
                        client_context=body.get("context") or {},
                    )
                    self._send_json(res)
                except Exception as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            if path == "/api/telemetry/export":
                try:
                    res = app_state.export_match_telemetry_csv(
                        team_folder=str(body.get("team_folder") or "char_y_v4"),
                        turn_results=body.get("turn_results") or {},
                        lang=str(body.get("lang") or "es"),
                        style=str(body.get("style") or "vgc"),
                    )
                    self._send_json(res)
                except Exception as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    return CoachHTTPHandler


def main() -> None:
    parser = argparse.ArgumentParser(description="Coach Porygon VGC — Standalone Replay Coach Studio")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765)")
    parser.add_argument(
        "--device",
        default="auto",
        choices=["auto", "cuda", "cpu"],
        help="Compute backend: auto (CUDA if available, else CPU), cuda, or cpu",
    )
    args = parser.parse_args()

    print("[Coach Porygon VGC] Initializing Tensor Core v2 & DuckDB OTS Registry...", flush=True)
    app_state = ReplayCoachAppState(preload_sample=False, device=args.device)
    print(
        f"[Coach Porygon VGC] Studio Ready on {app_state.gpu_engine.device_name} ({app_state.gpu_engine.device_type.upper()}) -> "
        f"http://{args.host}:{args.port}/",
        flush=True,
    )
    server = ThreadingHTTPServer((args.host, args.port), make_handler(app_state))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Coach Porygon VGC] Shutting down server.", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
