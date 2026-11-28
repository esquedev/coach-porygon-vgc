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
import csv
from datetime import datetime
import hashlib
import html as html_lib
import io
import json
import mimetypes
from pathlib import Path
import re
import threading
import time
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Sequence, Tuple

from engine.damage_calc.bridge import get_champions_calc
from engine.inference.set_inferencer import (
    MissingOTSError,
    OpponentSetInferencer,
    SeriesSPInferenceReport,
)
from engine.prep_tools import (
    build_damage_matrix_html,
    build_speed_tiers_html,
)
from engine.solver.lead_matchup_solver import (
    LeadMatchupConfig,
    LeadMatchupSolver,
)
from engine.telemetry.extractor import (
    CSV_COLUMNS,
    TurnTelemetryRecord,
    _generate_match_id,
)
from engine.terminology import export_glossary_payload
from engine.vgc_tensor_core.state_machine import AnalysisCancelledError
from engine.vgc_tensor_core.victory_equity import EQUITY_ENGINE_VERSION

from .gpu_coach_engine import GPUReplayCoachEngine, compute_match_summary
from .ots_db import (
    DEFAULT_OPPONENT_PASTE,
    DEFAULT_TRAINER_1_PASTE,
    OTSRosterDatabase,
    canonical_mode_key,
    compute_lead_lab_matchup_hash,
    resolve_sprite_urls,
)
from .protocol_parser import (
    ParsedReplay,
    anonymize_showdown_log_text,
    assign_bo3_game_numbers,
    format_evless_ots_paste,
    format_showdown_opponent_label,
    parse_showdown_replay,
    sort_replay_entries,
)

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
        self._active_stream_coord: Optional[threading.Thread] = None
        self.ots_db = OTSRosterDatabase(db_path=db_path) if db_path is not None else OTSRosterDatabase()
        self.gpu_engine = GPUReplayCoachEngine(self.ots_db, device=device)
        self.raw_replay_html: str = ""
        self.pov_trainer: str = ""
        self.t1_roster_id: Optional[str] = None
        self.t2_roster_id: Optional[str] = None
        self.t1_paste_text: str = ""
        self.t2_paste_text: str = ""
        self.replay: Optional[ParsedReplay] = None
        # Unified Bo1/Bo3 bundle & ephemeral clamped 66-SP inference session state
        self.bo3_games: List[Dict[str, Any]] = []
        self.active_game_index: int = 0
        self.ephemeral_t2_inference: Optional[SeriesSPInferenceReport] = None
        self.ephemeral_t2_spreads: Dict[str, Dict[str, int]] = {}
        # Zero-AI Offline Base64 Prep Tools in-memory token cache
        self._prep_cache_lock = threading.Lock()
        self._prep_cache: Dict[str, Dict[str, Any]] = {}
        self._prep_cache_order: List[str] = []
        # Factored 90×90 Turn-1 Lead & Bring Lab state
        self._lead_cancel_lock = threading.Lock()
        self._lead_cancel_event: Optional[threading.Event] = None
        self._lead_jobs_lock = threading.Lock()
        self._lead_jobs: Dict[str, Dict[str, Any]] = {}
        self._lead_jobs_order: List[str] = []
        self.lead_ephemeral_t2_inference: Optional[SeriesSPInferenceReport] = None
        self.lead_ephemeral_t2_spreads: Dict[str, Dict[str, int]] = {}
        self._lead_solver: Optional[LeadMatchupSolver] = None
        # Warm SmogonChampionsCalc on the main thread so MiniRacer V8 teardown is always thread-safe
        get_champions_calc()

        if preload_sample and SAMPLE_REPLAY_PATH.exists():
            self.load_bo3_bundle(
                replays=[
                    {
                        "filename": SAMPLE_REPLAY_PATH.name,
                        "raw_input": SAMPLE_REPLAY_PATH.read_text(encoding="utf-8"),
                    }
                ],
                pov_trainer="treces_gc",
                t1_roster_id="treces_gc_char_y_v4",
                t2_roster_id="matchagotme_camerupt_tr",
            )

    def start_new_stream_cancel_event(self) -> threading.Event:
        """Cancel any previously running SSE analysis, wait for it to stop, and register a fresh event."""
        prev_coord: Optional[threading.Thread] = None
        with self._stream_cancel_lock:
            if self._active_cancel_event is not None:
                self._active_cancel_event.set()
            prev_coord = self._active_stream_coord
        if prev_coord is not None and prev_coord.is_alive():
            prev_coord.join(timeout=4.0)
        with self._stream_cancel_lock:
            ev = threading.Event()
            self._active_cancel_event = ev
            return ev

    def register_stream_coordinator(self, coord_thread: threading.Thread) -> None:
        """Track the active SSE coordinator thread so overlapping streams never run simultaneously."""
        with self._stream_cancel_lock:
            self._active_stream_coord = coord_thread

    def cancel_active_stream(self) -> bool:
        """Signal any currently running analysis stream to abort cleanly between tiles/chunks."""
        with self._stream_cancel_lock:
            if self._active_cancel_event is not None:
                self._active_cancel_event.set()
                return True
            return False

    def list_telemetry_teams(self) -> List[str]:
        """List existing team folders under `data/telemetry/`."""
        teams: List[str] = []
        if TELEMETRY_ROOT.exists():
            for d in sorted(TELEMETRY_ROOT.iterdir()):
                if d.is_dir() and not d.name.startswith("."):
                    teams.append(d.name)
        return teams

    def create_telemetry_team(self, team_folder: str) -> Dict[str, Any]:
        """Create a new local team folder under `data/telemetry/<team>/battles_telemetry.csv`."""
        raw_name = (team_folder or "").strip().lower().replace(" ", "_")
        clean_team = re.sub(r"[^a-zA-Z0-9_-]", "_", raw_name).strip("_")
        if not clean_team or clean_team == "all":
            raise ValueError("Provide a valid team folder name (letters, numbers, hyphens, or underscores).")

        csv_path = TELEMETRY_ROOT / clean_team / "battles_telemetry.csv"
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        created = False
        if not csv_path.exists() or csv_path.stat().st_size == 0:
            with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
                writer.writeheader()
            created = True

        rel_csv = (
            csv_path.relative_to(REPO_ROOT).as_posix()
            if csv_path.is_relative_to(REPO_ROOT)
            else csv_path.as_posix()
        )
        return {
            "ok": True,
            "team_folder": clean_team,
            "csv_path": rel_csv,
            "created": created,
            "teams": self.list_telemetry_teams(),
        }

    def _enrich_inference_payload(
        self,
        report: SeriesSPInferenceReport,
        override_spreads: Optional[Dict[str, Dict[str, int]]] = None,
    ) -> Dict[str, Any]:
        """Serialize a `SeriesSPInferenceReport` with local Pokémon & item sprite URLs."""
        raw = report.to_dict()
        enriched_mons: List[Dict[str, Any]] = []
        for m in raw.get("pokemon", []):
            sprites = resolve_sprite_urls(m.get("base_species") or m.get("species"), m.get("item"))
            m_copy = dict(m)
            m_copy["sprite_url"] = sprites["sprite_url"]
            m_copy["item_sprite_url"] = sprites["item_sprite_url"]
            if override_spreads:
                cand = (
                    override_spreads.get(m_copy["base_species"])
                    or override_spreads.get(m_copy["species"])
                )
                if cand:
                    m_copy["active_spread"] = dict(cand)
            if "active_spread" not in m_copy:
                m_copy["active_spread"] = dict(m_copy["default_spread"])
            enriched_mons.append(m_copy)
        paste_text = report.build_paste(override_spreads=override_spreads)
        raw["pokemon"] = enriched_mons
        raw["paste_text"] = paste_text
        raw["validation"] = self.ots_db.validate_paste(paste_text) if paste_text else None
        return raw

    def preview_bo3_bundle(
        self,
        replays: Sequence[Dict[str, Any]],
        pov_trainer: Optional[str] = None,
        use_sample: bool = False,
    ) -> Dict[str, Any]:
        """Preview 1..3 Showdown replays as a unified Bo1/Bo3 bundle, extracting `|showteam|` OTS."""
        items: List[Dict[str, str]] = []
        if use_sample and SAMPLE_REPLAY_PATH.exists():
            items.append(
                {
                    "filename": SAMPLE_REPLAY_PATH.name,
                    "raw_input": SAMPLE_REPLAY_PATH.read_text(encoding="utf-8"),
                }
            )
        else:
            for idx, entry in enumerate(list(replays or [])[:3], 1):
                raw_txt = str(entry.get("raw_input") or "").strip()
                if not raw_txt:
                    continue
                fname = str(entry.get("filename") or f"Game {idx}").strip()
                items.append({"filename": fname, "raw_input": raw_txt})

        if not items:
            raise ValueError("Provide 1 to 3 non-empty Showdown replay files.")

        items, orig_order = sort_replay_entries(items)
        game_nums = assign_bo3_game_numbers(items)

        parsed_list: List[ParsedReplay] = []
        resolved_pov = pov_trainer
        for pos, (it, g_num) in enumerate(zip(items, game_nums), 1):
            p = parse_showdown_replay(
                it["raw_input"],
                pov_trainer=resolved_pov,
                game_index=g_num,
                anonymize_opponent=True,
            )
            if pos == 1 and not resolved_pov:
                resolved_pov = p.trainer_1_name
            parsed_list.append(p)

        first = parsed_list[0]
        # Pool |showteam| EV-less OTS across all games
        t2_showteam: Dict[str, Any] = {}
        t1_showteam: Dict[str, Any] = {}
        for p in parsed_list:
            for k, v in (p.trainer_2_showteam_ots or {}).items():
                if k not in t2_showteam:
                    t2_showteam[k] = v
            for k, v in (p.trainer_1_showteam_ots or {}).items():
                if k not in t1_showteam:
                    t1_showteam[k] = v

        t2_evless_paste = format_evless_ots_paste(t2_showteam)
        t1_evless_paste = format_evless_ots_paste(t1_showteam)
        r1 = self.ots_db.match_best_roster(first.trainer_1_name, first.trainer_1_preview)
        r2 = self.ots_db.match_best_roster(first.trainer_2_name, first.trainer_2_preview)

        games_meta: List[Dict[str, Any]] = []
        with self.lock:
            self.bo3_games = []
            for it, p, g_num in zip(items, parsed_list, game_nums):
                is_win = bool(p.winner and p.winner.lower() == p.trainer_1_name.lower())
                g_rec = {
                    "game_index": g_num,
                    "wire_game_number": p.wire_game_number,
                    "filename": it["filename"],
                    "raw_input": it["raw_input"],
                    "replay_id": p.replay_id,
                    "format_name": p.format_name,
                    "winner": p.winner,
                    "is_t1_win": is_win,
                    "num_turns": len(p.turns),
                    "has_showteam": bool(p.trainer_2_showteam_ots),
                    "trainer_1_elo": p.trainer_1_elo,
                    "trainer_2_elo": p.trainer_2_elo,
                    "parsed": p,
                }
                self.bo3_games.append(g_rec)
                games_meta.append(
                    {
                        "game_index": g_num,
                        "wire_game_number": p.wire_game_number,
                        "filename": it["filename"],
                        "replay_id": p.replay_id,
                        "format_name": p.format_name,
                        "winner": p.winner,
                        "is_t1_win": is_win,
                        "num_turns": len(p.turns),
                        "has_showteam": bool(p.trainer_2_showteam_ots),
                        "trainer_1_elo": p.trainer_1_elo,
                        "trainer_2_elo": p.trainer_2_elo,
                    }
                )
            self.active_game_index = 0
            self.raw_replay_html = items[0]["raw_input"]
            self.pov_trainer = first.trainer_1_name
            self.ephemeral_t2_inference = None
            self.ephemeral_t2_spreads = {}

        return {
            "ok": True,
            "is_bo3": len(games_meta) > 1,
            "games_count": len(games_meta),
            "active_game_index": 0,
            "sorted_order": orig_order,
            "games": games_meta,
            "replay_id": first.replay_id,
            "format_name": first.format_name,
            "trainer_1_name": first.trainer_1_name,
            "trainer_2_name": first.trainer_2_name,
            "trainer_1_elo": first.trainer_1_elo,
            "trainer_2_elo": first.trainer_2_elo,
            "is_anonymized_opponent": first.is_anonymized_opponent,
            "winner": first.winner,
            "num_turns": len(first.turns),
            "trainer_1_preview": [
                {"species": sp, **resolve_sprite_urls(sp)} for sp in first.trainer_1_preview
            ],
            "trainer_2_preview": [
                {"species": sp, **resolve_sprite_urls(sp)} for sp in first.trainer_2_preview
            ],
            "suggested_t1_roster_id": r1["roster_id"] if r1 else None,
            "suggested_t2_roster_id": r2["roster_id"] if r2 else None,
            "has_showteam_ots": bool(t2_showteam),
            "trainer_2_evless_ots_paste": t2_evless_paste,
            "trainer_1_evless_ots_paste": t1_evless_paste,
        }

    def infer_bo3_opponent_sp(
        self,
        replays: Optional[Sequence[Dict[str, Any]]] = None,
        pov_trainer: Optional[str] = None,
        t1_roster_id: Optional[str] = None,
        t1_paste_text: Optional[str] = None,
        t2_ots_paste_text: Optional[str] = None,
        use_sample: bool = False,
    ) -> Dict[str, Any]:
        """Pool 1..3 replays + `trainer_1` 66-SP + `trainer_2` OTS to solve exact clamped SP bounds."""
        raw_items: List[str] = []
        if replays:
            sortable = [
                {
                    "filename": str(entry.get("filename") or f"Game {i}").strip() if isinstance(entry, dict) else f"Game {i}",
                    "raw_input": str(entry.get("raw_input") or "").strip() if isinstance(entry, dict) else str(entry or "").strip(),
                }
                for i, entry in enumerate(list(replays)[:3], 1)
            ]
            sortable = [x for x in sortable if x["raw_input"]]
            sortable, _ = sort_replay_entries(sortable)
            raw_items = [x["raw_input"] for x in sortable]
        elif use_sample and SAMPLE_REPLAY_PATH.exists():
            raw_items.append(SAMPLE_REPLAY_PATH.read_text(encoding="utf-8"))
        else:
            with self.lock:
                if self.bo3_games:
                    raw_items = [g["raw_input"] for g in self.bo3_games if g.get("raw_input")]
                elif self.raw_replay_html:
                    raw_items = [self.raw_replay_html]

        if not raw_items:
            raise ValueError("Load 1 to 3 Showdown replays first before running 66-SP inference.")

        # Resolve POV trainer & true wire Game #s
        raw_dicts = [{"filename": f"Game {i}", "raw_input": r} for i, r in enumerate(raw_items, 1)]
        g_nums_inf = assign_bo3_game_numbers(raw_dicts)
        prelim0 = parse_showdown_replay(
            raw_items[0],
            pov_trainer=pov_trainer or self.pov_trainer or None,
            game_index=g_nums_inf[0],
            anonymize_opponent=True,
        )
        resolved_pov = prelim0.trainer_1_name

        # Resolve trainer_1 exact 66-SP sets
        paste1 = (t1_paste_text or "").strip()
        if not paste1 and t1_roster_id:
            r1 = self.ots_db.get_roster(t1_roster_id)
            paste1 = r1["paste_text"] if r1 else ""
        if not paste1:
            r1_auto = self.ots_db.match_best_roster(prelim0.trainer_1_name, prelim0.trainer_1_preview)
            paste1 = r1_auto["paste_text"] if r1_auto else ""
        t1_sets = self.ots_db.get_parsed_sets_by_species(paste1) if paste1 else {}
        if not t1_sets and prelim0.trainer_1_showteam_ots:
            t1_sets = dict(prelim0.trainer_1_showteam_ots)

        # Parse all 1..N replays with trainer_1 exact sets for lossless damage/speed extraction
        parsed_replays: List[ParsedReplay] = []
        t2_showteam_pooled: Dict[str, Any] = {}
        for raw_txt, g_num in zip(raw_items, g_nums_inf):
            pr = parse_showdown_replay(
                raw_txt,
                pov_trainer=resolved_pov,
                trainer_1_ots_sets=t1_sets,
                game_index=g_num,
                anonymize_opponent=True,
            )
            parsed_replays.append(pr)
            for k, v in (pr.trainer_2_showteam_ots or {}).items():
                if k not in t2_showteam_pooled:
                    t2_showteam_pooled[k] = v

        # Resolve trainer_2 EV-less OTS (explicit paste overrides |showteam| if provided)
        t2_ots_paste = (t2_ots_paste_text or "").strip()
        if t2_ots_paste:
            t2_ots_sets = self.ots_db.get_parsed_sets_by_species(t2_ots_paste)
        else:
            t2_ots_sets = t2_showteam_pooled

        inferencer = OpponentSetInferencer()
        report = inferencer.infer_series(
            trainer_1_sets=t1_sets,
            trainer_2_ots_sets=t2_ots_sets,
            replays=parsed_replays,
            trainer_1_name=prelim0.trainer_1_name,
            trainer_2_name=prelim0.trainer_2_name,
        )

        default_spreads = {
            inf.base_species: inf.default_spread.to_dict()
            for inf in report.pokemon_inferences.values()
        }
        with self.lock:
            self.ephemeral_t2_inference = report
            self.ephemeral_t2_spreads = default_spreads

        payload = self._enrich_inference_payload(report, override_spreads=default_spreads)
        payload["ok"] = True
        payload["t1_has_66sp"] = bool(t1_sets) and all(
            m.spread.total_sp == 66 for m in t1_sets.values()
        )
        return payload

    def load_bo3_bundle(
        self,
        replays: Optional[Sequence[Dict[str, Any]]] = None,
        pov_trainer: Optional[str] = None,
        t1_roster_id: Optional[str] = None,
        t2_roster_id: Optional[str] = None,
        t1_paste_text: Optional[str] = None,
        t2_paste_text: Optional[str] = None,
        t2_user_spreads: Optional[Dict[str, Dict[str, int]]] = None,
        active_game_index: int = 0,
        t1_save_meta: Optional[Dict[str, Any]] = None,
        t2_save_meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Finalize 1..3 Bo3 replays with validated clamped 66-SP opponent spreads & load active game."""
        with self.lock:
            raw_items: List[Dict[str, str]] = []
            if replays:
                for idx, entry in enumerate(list(replays)[:3], 1):
                    rt = str(entry.get("raw_input") or "").strip() if isinstance(entry, dict) else str(entry or "").strip()
                    if rt:
                        fn = str(entry.get("filename") or f"Game {idx}").strip() if isinstance(entry, dict) else f"Game {idx}"
                        raw_items.append({"filename": fn, "raw_input": rt})
            elif self.bo3_games:
                raw_items = [
                    {"filename": g["filename"], "raw_input": g["raw_input"]}
                    for g in self.bo3_games
                    if g.get("raw_input")
                ]
            elif self.raw_replay_html:
                raw_items = [{"filename": "Game 1", "raw_input": self.raw_replay_html}]
            elif SAMPLE_REPLAY_PATH.exists():
                raw_items = [
                    {
                        "filename": SAMPLE_REPLAY_PATH.name,
                        "raw_input": SAMPLE_REPLAY_PATH.read_text(encoding="utf-8"),
                    }
                ]

            if not raw_items:
                raise ValueError("No replay files available to load.")

            raw_items, _ = sort_replay_entries(raw_items)
            game_nums = assign_bo3_game_numbers(raw_items)

            prelim0 = parse_showdown_replay(
                raw_items[0]["raw_input"],
                pov_trainer=pov_trainer or self.pov_trainer or None,
                game_index=game_nums[0],
                anonymize_opponent=True,
            )
            resolved_pov = prelim0.trainer_1_name

            # Strict backend clamp validation when user submits slider spreads for ephemeral inference!
            finalized_t2_paste = (t2_paste_text or "").strip()
            if t2_user_spreads is not None and self.ephemeral_t2_inference is not None:
                ok_sp, errs_sp = self.ephemeral_t2_inference.validate_user_spreads(t2_user_spreads)
                if not ok_sp:
                    raise ValueError(
                        "Invalid opponent 66-SP allocation (deterministic bounds cannot be overridden): "
                        + " | ".join(errs_sp)
                    )
                finalized_t2_paste = self.ephemeral_t2_inference.build_paste(
                    override_spreads=t2_user_spreads
                )
                self.ephemeral_t2_spreads = {
                    k: dict(v) for k, v in t2_user_spreads.items()
                }
                t2_roster_id = None
            elif not finalized_t2_paste and not t2_roster_id and self.ephemeral_t2_inference is not None:
                finalized_t2_paste = self.ephemeral_t2_inference.build_paste(
                    override_spreads=self.ephemeral_t2_spreads or None
                )

            # Optional explicit save to DuckDB (never auto-saved!)
            if t1_paste_text and t1_paste_text.strip() and t1_save_meta and t1_save_meta.get("save_to_db"):
                rid1 = str(t1_save_meta.get("roster_id") or f"{prelim0.trainer_1_name.lower()}_ots").strip()
                rid1 = re.sub(r"[^a-zA-Z0-9_-]", "_", rid1)
                dname1 = str(t1_save_meta.get("display_name") or f"{prelim0.trainer_1_name} — Full OTS").strip()
                self.ots_db.save_roster(
                    rid1,
                    dname1,
                    prelim0.trainer_1_name,
                    t1_paste_text,
                    team_scope="own",
                    archetype=str(t1_save_meta.get("archetype") or ""),
                    regulation=str(t1_save_meta.get("regulation") or "Reg M-C"),
                    source_type="personal",
                )
                t1_roster_id = rid1

            if finalized_t2_paste and t2_save_meta and t2_save_meta.get("save_to_db"):
                anon_lbl = format_showdown_opponent_label(prelim0.trainer_2_elo)
                slug_hash = hashlib.sha1(finalized_t2_paste.encode("utf-8")).hexdigest()[:8]
                elo_tag = f"elo{prelim0.trainer_2_elo}" if prelim0.trainer_2_elo else "unrated"
                rid2 = str(t2_save_meta.get("roster_id") or f"showdown_{elo_tag}_{slug_hash}").strip()
                rid2 = re.sub(r"[^a-zA-Z0-9_-]", "_", rid2)
                dname2 = str(t2_save_meta.get("display_name") or anon_lbl).strip()
                self.ots_db.save_roster(
                    rid2,
                    dname2,
                    anon_lbl,
                    finalized_t2_paste,
                    team_scope="rival",
                    archetype=str(t2_save_meta.get("archetype") or ""),
                    regulation=str(t2_save_meta.get("regulation") or "Reg M-C"),
                    source_type="showdown_ladder",
                    opponent_elo=prelim0.trainer_2_elo,
                )
                t2_roster_id = rid2

            # Resolve Trainer 1 paste
            paste1 = ""
            if t1_paste_text and t1_paste_text.strip() and not t1_roster_id:
                paste1 = t1_paste_text.strip()
                self.t1_roster_id = "inline_ots"
            else:
                r1 = (
                    self.ots_db.get_roster(t1_roster_id)
                    if t1_roster_id
                    else self.ots_db.match_best_roster(prelim0.trainer_1_name, prelim0.trainer_1_preview)
                )
                paste1 = r1["paste_text"] if r1 else ""
                self.t1_roster_id = r1["roster_id"] if r1 else None
                if not paste1 and prelim0.trainer_1_name.lower() == "treces_gc" and DEFAULT_TRAINER_1_PASTE.exists():
                    paste1 = DEFAULT_TRAINER_1_PASTE.read_text(encoding="utf-8")

            # Resolve Trainer 2 paste
            paste2 = ""
            if finalized_t2_paste and not t2_roster_id:
                paste2 = finalized_t2_paste
                self.t2_roster_id = "inferred_ephemeral" if self.ephemeral_t2_inference is not None else "inline_ots"
            else:
                r2 = (
                    self.ots_db.get_roster(t2_roster_id)
                    if t2_roster_id
                    else self.ots_db.match_best_roster(prelim0.trainer_2_name, prelim0.trainer_2_preview)
                )
                paste2 = r2["paste_text"] if r2 else ""
                self.t2_roster_id = r2["roster_id"] if r2 else None
                if (
                    not paste2
                    and (prelim0.raw_trainer_2_name.lower() == "matchagotme" or prelim0.trainer_2_name.lower() == "matchagotme")
                    and DEFAULT_OPPONENT_PASTE.exists()
                ):
                    paste2 = DEFAULT_OPPONENT_PASTE.read_text(encoding="utf-8")

            t1_sets = self.ots_db.get_parsed_sets_by_species(paste1) if paste1 else {}
            t2_sets = self.ots_db.get_parsed_sets_by_species(paste2) if paste2 else {}

            # Parse every game in the bundle with exact finalized sets & preserved wire Game #
            new_bo3: List[Dict[str, Any]] = []
            for it, g_num in zip(raw_items, game_nums):
                pr = parse_showdown_replay(
                    it["raw_input"],
                    pov_trainer=resolved_pov,
                    trainer_1_ots_sets=t1_sets,
                    trainer_2_ots_sets=t2_sets,
                    game_index=g_num,
                    anonymize_opponent=True,
                )
                is_win = bool(pr.winner and pr.winner.lower() == pr.trainer_1_name.lower())
                new_bo3.append(
                    {
                        "game_index": g_num,
                        "wire_game_number": pr.wire_game_number,
                        "filename": it["filename"],
                        "raw_input": it["raw_input"],
                        "replay_id": pr.replay_id,
                        "format_name": pr.format_name,
                        "winner": pr.winner,
                        "is_t1_win": is_win,
                        "num_turns": len(pr.turns),
                        "has_showteam": bool(pr.trainer_2_showteam_ots),
                        "trainer_1_elo": pr.trainer_1_elo,
                        "trainer_2_elo": pr.trainer_2_elo,
                        "parsed": pr,
                    }
                )

            self.bo3_games = new_bo3
            sel_idx = max(0, min(len(new_bo3) - 1, int(active_game_index)))
            self.active_game_index = sel_idx
            self.raw_replay_html = new_bo3[sel_idx]["raw_input"]
            self.pov_trainer = resolved_pov
            self.t1_paste_text = paste1
            self.t2_paste_text = paste2
            self.replay = new_bo3[sel_idx]["parsed"]
            return self.get_state_summary_unlocked()

    def select_bo3_game(self, game_index: int) -> Dict[str, Any]:
        """Switch active game tab (`0..N-1`) inside the currently loaded Bo3 bundle."""
        self.cancel_active_stream()
        with self.lock:
            if not self.bo3_games:
                raise ValueError("No Bo3 bundle is currently loaded.")
            idx = int(game_index)
            if idx < 0 or idx >= len(self.bo3_games):
                raise ValueError(f"Game index {idx} out of range (loaded {len(self.bo3_games)} games).")
            self.active_game_index = idx
            g = self.bo3_games[idx]
            self.raw_replay_html = g["raw_input"]
            self.replay = g["parsed"]
            return self.get_state_summary_unlocked()

    def infer_ots_from_replay(
        self,
        raw_input: str,
        side: str = "t2",
        pov_trainer: Optional[str] = None,
        use_sample: bool = False,
        t1_paste_text: Optional[str] = None,
        t2_ots_paste_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Solve exact Regulation M-C 66-SP bounds from replay telemetry + OTS (`|showteam|` or paste)."""
        raw_text = (raw_input or "").strip()
        if (use_sample or not raw_text) and SAMPLE_REPLAY_PATH.exists():
            if use_sample or not self.raw_replay_html:
                raw_text = SAMPLE_REPLAY_PATH.read_text(encoding="utf-8")
            else:
                raw_text = self.raw_replay_html
        if not raw_text:
            raise ValueError("Load or paste a replay first before running OTS 66-SP Solver.")

        prelim = parse_showdown_replay(raw_text, pov_trainer=pov_trainer or self.pov_trainer or None, game_index=1)
        target_side = "t1" if str(side).lower() in ("t1", "trainer_1") else "t2"
        infer_pov = prelim.trainer_2_name if target_side == "t1" else prelim.trainer_1_name
        target_trainer = prelim.trainer_1_name if target_side == "t1" else prelim.trainer_2_name

        # Build the exact reference sets for the opposite side + OTS for target side
        if target_side == "t2":
            res = self.infer_bo3_opponent_sp(
                replays=[{"filename": "Game 1", "raw_input": raw_text}],
                pov_trainer=infer_pov,
                t1_paste_text=t1_paste_text or self.t1_paste_text or None,
                t2_ots_paste_text=t2_ots_paste_text,
            )
            paste_text = res["paste_text"]
            validation = res["validation"]
            inferred_count = len(res.get("pokemon") or [])
            speed_bounds_out = {
                m["base_species"]: [m["bounds"]["spe"]["min_sp"], m["bounds"]["spe"]["max_sp"]]
                for m in (res.get("pokemon") or [])
                if m.get("bounds", {}).get("spe")
            }
            return {
                "ok": True,
                "side": target_side,
                "trainer_name": target_trainer,
                "inferred_count": inferred_count,
                "paste_text": paste_text,
                "validation": validation,
                "speed_bounds": speed_bounds_out,
                "inference": res,
            }

        # target_side == "t1": orient POV to trainer_2 so trainer_1 is solved symmetrically
        ref_paste = self.t2_paste_text or ""
        if not ref_paste:
            r_ref = self.ots_db.match_best_roster(prelim.trainer_2_name, prelim.trainer_2_preview)
            ref_paste = r_ref["paste_text"] if r_ref else ""
        ref_sets = self.ots_db.get_parsed_sets_by_species(ref_paste) if ref_paste else {}
        oriented = parse_showdown_replay(raw_text, pov_trainer=infer_pov, trainer_1_ots_sets=ref_sets, game_index=1)
        if not ref_sets and oriented.trainer_1_showteam_ots:
            ref_sets = dict(oriented.trainer_1_showteam_ots)
        target_ots = (
            self.ots_db.get_parsed_sets_by_species(t2_ots_paste_text)
            if t2_ots_paste_text and t2_ots_paste_text.strip()
            else oriented.trainer_2_showteam_ots
        )
        inferencer = OpponentSetInferencer()
        report = inferencer.infer_series(
            trainer_1_sets=ref_sets,
            trainer_2_ots_sets=target_ots,
            replays=[oriented],
            trainer_1_name=oriented.trainer_1_name,
            trainer_2_name=target_trainer,
        )
        enriched = self._enrich_inference_payload(report)
        return {
            "ok": True,
            "side": target_side,
            "trainer_name": target_trainer,
            "inferred_count": len(enriched["pokemon"]),
            "paste_text": enriched["paste_text"],
            "validation": enriched["validation"],
            "speed_bounds": {
                m["base_species"]: [m["bounds"]["spe"]["min_sp"], m["bounds"]["spe"]["max_sp"]]
                for m in enriched["pokemon"]
            },
            "inference": enriched,
        }

    def get_telemetry_session_summary(self, team_folder: Optional[str] = None) -> Dict[str, Any]:
        """Aggregate Bo3 / tournament session analytics from `data/telemetry/<team>/battles_telemetry.csv`."""
        teams = self.list_telemetry_teams()
        req_team = (team_folder or "").strip() or "all"

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

            clean_team = re.sub(r"[^a-zA-Z0-9_-]", "_", (team_folder or "my_team").strip()) or "my_team"
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
            "active_game_index": self.active_game_index,
            "bo3_games": [
                {
                    "game_index": g["game_index"],
                    "filename": g["filename"],
                    "replay_id": g["replay_id"],
                    "format_name": g["format_name"],
                    "winner": g["winner"],
                    "is_t1_win": g["is_t1_win"],
                    "num_turns": g["num_turns"],
                    "has_showteam": g["has_showteam"],
                }
                for g in self.bo3_games
            ],
            "ephemeral_t2_inference": (
                self._enrich_inference_payload(
                    self.ephemeral_t2_inference,
                    override_spreads=self.ephemeral_t2_spreads or None,
                )
                if self.ephemeral_t2_inference is not None
                else None
            ),
            "replay": None
            if rep is None
            else {
                "replay_id": rep.replay_id,
                "format_name": rep.format_name,
                "trainer_1_name": rep.trainer_1_name,
                "trainer_2_name": rep.trainer_2_name,
                "trainer_1_elo": rep.trainer_1_elo,
                "trainer_2_elo": rep.trainer_2_elo,
                "wire_game_number": rep.wire_game_number,
                "game_index": rep.game_index,
                "is_anonymized_opponent": rep.is_anonymized_opponent,
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

        embed_log = rep.raw_log_text
        if rep.is_anonymized_opponent and rep.raw_trainer_2_name:
            opp_wire = ("p" + "1") if rep.pov_is_right_side else ("p" + "2")
            embed_log = anonymize_showdown_log_text(
                embed_log,
                opp_wire=opp_wire,
                raw_opp_name=rep.raw_trainer_2_name,
                anon_label=rep.trainer_2_name,
            )
        escaped_log = re.sub(r"</script", r"<\/script", embed_log, flags=re.IGNORECASE)
        escaped_log = escaped_log.replace("<!--", r"<\!--")
        # Load local patched /vendor/replay-embed.js as primary so battle-animations.js (BattleScene)
        # and battle-animations-moves.js (BattleMoveAnims) are ALWAYS loaded in strict async=false order.
        primary_embed_src = (
            "/vendor/replay-embed.js"
            if (VENDOR_DIR / "replay-embed.js").exists()
            else "https://play.pokemonshowdown.com/js/replay-embed.js"
        )
        fallback_embed_src = "https://play.pokemonshowdown.com/js/replay-embed.js"
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
    background: #0b101b;
    color: #e2e8f0;
    font-family: Verdana, sans-serif;
    overflow-x: hidden;
  }}
  .wrapper.replay-wrapper {{
    position: relative !important;
    max-width: 100% !important;
    min-height: 376px !important;
    overflow: visible !important;
    margin: 0 auto !important;
    padding: 4px 6px 6px 6px !important;
  }}
  .battle-log {{
    height: 360px !important;
    max-height: 360px !important;
    border-radius: 6px;
  }}
  /* Hide Showdown's duplicate native controls — Coach Porygon provides unified controls & turn scrubber */
  .replay-controls, .replay-controls-2 {{
    display: none !important;
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
<script src="{primary_embed_src}" onerror="(function(){{var fb='{fallback_embed_src}';if(!fb)return;var s=document.createElement('script');s.async=false;s.src=fb;document.head.appendChild(s);}})();"></script>
<script>
(function() {{
  const SHOULD_FLIP = {flip_js};
  let flippedOnce = false;
  let lastTurnPosted = -1;
  let lastPausedPosted = null;
  let singleTurnTarget = null;
  let suppressTurnNotify = false;
  const pendingMessages = [];

  function postPlayerState() {{
    if (!window.Replays || !window.Replays.battle) return;
    const isPaused = !!window.Replays.battle.paused;
    if (isPaused !== lastPausedPosted) {{
      lastPausedPosted = isPaused;
      window.parent.postMessage({{ type: 'PLAYER_STATE', paused: isPaused }}, '*');
    }}
  }}

  function postIframeHeight() {{
    const wrap = document.querySelector('.wrapper.replay-wrapper');
    const battleEl = document.querySelector('.battle');
    const logEl = document.querySelector('.battle-log');
    const hWrap = wrap ? wrap.getBoundingClientRect().bottom : 0;
    const hBattle = battleEl ? battleEl.getBoundingClientRect().bottom : 0;
    const hLog = logEl ? logEl.getBoundingClientRect().bottom : 0;
    const h = Math.ceil(Math.max(376, hWrap, hBattle, hLog) + 8);
    window.parent.postMessage({{ type: 'IFRAME_HEIGHT', height: h }}, '*');
  }}

  function notifyParentTurn(turnVal) {{
    postPlayerState();
    if (suppressTurnNotify) return;
    if (typeof turnVal === 'number' && turnVal !== lastTurnPosted) {{
      lastTurnPosted = turnVal;
      window.parent.postMessage({{ type: 'TURN_CHANGED', turn: turnVal, paused: !!(window.Replays && window.Replays.battle && window.Replays.battle.paused) }}, '*');
    }}
  }}

  function handleParentCommand(msg) {{
    if (!msg || !msg.type) return;
    if (!window.Replays || !window.Replays.battle) {{
      pendingMessages.push(msg);
      return;
    }}
    const battle = window.Replays.battle;
    if (msg.type === 'SEEK_TURN' && typeof msg.turn === 'number') {{
      try {{
        suppressTurnNotify = true;
        battle.pause();
        battle.seekTurn(msg.turn);
        lastTurnPosted = msg.turn;
        suppressTurnNotify = false;
        if (msg.animate !== false) {{
          singleTurnTarget = msg.turn;
          if (battle.paused) battle.play();
        }} else {{
          singleTurnTarget = null;
        }}
        postPlayerState();
      }} catch (e) {{
        suppressTurnNotify = false;
      }}
    }} else if (msg.type === 'STEP_TURN' && typeof msg.delta === 'number') {{
      try {{
        singleTurnTarget = null;
        battle.pause();
        battle.seekBy(msg.delta);
        notifyParentTurn(battle.turn);
      }} catch (e) {{}}
    }} else if (msg.type === 'SWITCH_VIEWPOINT') {{
      try {{ battle.switchViewpoint(); }} catch (e) {{}}
    }} else if (msg.type === 'SET_SPEED' && typeof msg.speed === 'string') {{
      try {{ window.Replays.changeSetting('speed', msg.speed); }} catch (e) {{}}
    }} else if (msg.type === 'TOGGLE_PLAY') {{
      try {{
        singleTurnTarget = null;
        if (battle.paused) battle.play();
        else battle.pause();
        postPlayerState();
      }} catch (e) {{}}
    }} else if (msg.type === 'PLAY') {{
      try {{
        singleTurnTarget = null;
        if (typeof msg.turn === 'number') {{
          suppressTurnNotify = true;
          battle.seekTurn(msg.turn);
          lastTurnPosted = msg.turn;
          suppressTurnNotify = false;
        }}
        if (battle.paused) battle.play();
        postPlayerState();
      }} catch (e) {{
        suppressTurnNotify = false;
      }}
    }} else if (msg.type === 'PAUSE') {{
      try {{
        singleTurnTarget = null;
        if (!battle.paused) battle.pause();
        postPlayerState();
      }} catch (e) {{}}
    }}
  }}

  function wireShowdownBridge() {{
    if (!window.Replays || !window.Replays.battle) {{
      setTimeout(wireShowdownBridge, 120);
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
      if (singleTurnTarget !== null && (battle.turn > singleTurnTarget || battle.ended)) {{
        const completedTurn = singleTurnTarget;
        singleTurnTarget = null;
        try {{ if (!battle.paused) battle.pause(); }} catch (e) {{}}
        lastTurnPosted = completedTurn;
        postPlayerState();
        return;
      }}
      notifyParentTurn(battle.turn);
    }});
    try {{
      battle.seekTurn(1);
      notifyParentTurn(battle.turn);
    }} catch (e) {{}}
    postIframeHeight();
    if (typeof ResizeObserver !== 'undefined') {{
      const wrap = document.querySelector('.wrapper.replay-wrapper');
      if (wrap) new ResizeObserver(postIframeHeight).observe(wrap);
    }}
    window.parent.postMessage({{ type: 'PLAYER_READY', turn: battle.turn, paused: !!battle.paused }}, '*');
    while (pendingMessages.length > 0) {{
      handleParentCommand(pendingMessages.shift());
    }}
  }}

  window.addEventListener('message', function(ev) {{
    handleParentCommand(ev.data || {{}});
  }});

  window.addEventListener('load', function() {{
    setTimeout(wireShowdownBridge, 180);
  }});
}})();
</script>
</body>
</html>
"""


    def generate_prep_tool(
        self,
        kind: str = "speed_tiers",
        roster_id: Optional[str] = None,
        paste_text: Optional[str] = None,
        team_name: Optional[str] = None,
        top_n: int = 50,
        lang: str = "es",
    ) -> Dict[str, Any]:
        """Generate and cache a zero-AI standalone Base64 HTML Prep Tool report."""
        norm_kind = (kind or "speed_tiers").strip().lower()
        if norm_kind not in ("speed_tiers", "damage_matrix"):
            raise ValueError(f"Unsupported prep tool kind: '{norm_kind}'")
        norm_top_n = int(top_n) if int(top_n) in (20, 35, 50) else 50
        norm_lang = "es" if (lang or "es").lower().startswith("es") else "en"

        resolved_paste = (paste_text or "").strip()
        resolved_name = (team_name or "").strip()
        if not resolved_paste and roster_id:
            roster = self.ots_db.get_roster(str(roster_id).strip())
            if roster is None:
                raise ValueError(f"Saved DuckDB roster not found: '{roster_id}'")
            resolved_paste = str(roster.get("paste_text") or "").strip()
            if not resolved_name:
                resolved_name = str(roster.get("display_name") or roster.get("roster_id") or "My Team")

        if not resolved_paste:
            raise ValueError("Provide a saved DuckDB roster_id or a Regulation M-C 66-SP Showdown paste.")
        if not resolved_name:
            resolved_name = "My Reg M-C Team"

        cache_seed = f"{norm_kind}|{norm_top_n}|{norm_lang}|{resolved_name}|{resolved_paste}"
        token = hashlib.sha256(cache_seed.encode("utf-8")).hexdigest()[:24]

        with self._prep_cache_lock:
            existing = self._prep_cache.get(token)
            if existing is not None:
                return {
                    "ok": True,
                    "token": token,
                    "kind": existing["kind"],
                    "filename": existing["filename"],
                    "team_name": existing["team_name"],
                    "top_n": existing["top_n"],
                    "lang": existing["lang"],
                    "meta_count": existing["meta_count"],
                    "calc_count": existing["calc_count"],
                    "size_kb": existing["size_kb"],
                    "elapsed_ms": 0.0,
                    "cached": True,
                    "preview_url": f"/api/prep-tools/preview?token={token}",
                    "download_url": f"/api/prep-tools/download?token={token}",
                }

        t0 = time.perf_counter()
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", resolved_name).strip("_").lower() or "team"
        if norm_kind == "speed_tiers":
            html_doc, payload = build_speed_tiers_html(
                paste_text=resolved_paste,
                team_name=resolved_name,
                top_n=norm_top_n,
                lang=norm_lang,
            )
            filename = f"speed_tiers_{slug}_top{norm_top_n}_mobile.html"
            calc_count = 0
            meta_count = payload.total_teams
        else:
            html_doc, payload = build_damage_matrix_html(
                paste_text=resolved_paste,
                team_name=resolved_name,
                top_n=norm_top_n,
                lang=norm_lang,
            )
            filename = f"damage_calcs_{slug}_top{norm_top_n}_mobile.html"
            calc_count = payload.calc_count
            meta_count = payload.total_teams

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 1)
        html_bytes = html_doc.encode("utf-8")
        size_kb = round(len(html_bytes) / 1024.0, 1)

        entry = {
            "token": token,
            "kind": norm_kind,
            "filename": filename,
            "team_name": resolved_name,
            "top_n": norm_top_n,
            "lang": norm_lang,
            "meta_count": meta_count,
            "calc_count": calc_count,
            "size_kb": size_kb,
            "html_bytes": html_bytes,
        }
        with self._prep_cache_lock:
            self._prep_cache[token] = entry
            if token not in self._prep_cache_order:
                self._prep_cache_order.append(token)
            while len(self._prep_cache_order) > 24:
                evict = self._prep_cache_order.pop(0)
                self._prep_cache.pop(evict, None)

        return {
            "ok": True,
            "token": token,
            "kind": norm_kind,
            "filename": filename,
            "team_name": resolved_name,
            "top_n": norm_top_n,
            "lang": norm_lang,
            "meta_count": meta_count,
            "calc_count": calc_count,
            "size_kb": size_kb,
            "elapsed_ms": elapsed_ms,
            "cached": False,
            "preview_url": f"/api/prep-tools/preview?token={token}",
            "download_url": f"/api/prep-tools/download?token={token}",
        }

    def get_prep_tool_cached(self, token: str) -> Optional[Dict[str, Any]]:
        """Retrieve a previously generated offline Base64 HTML report by cache token."""
        if not token:
            return None
        with self._prep_cache_lock:
            return self._prep_cache.get(token)

    # ------------------------------------------------------------------
    # Factored 90×90 Turn-1 Lead & Bring Lab (Team-Preview Nash)
    # ------------------------------------------------------------------

    def _get_lead_solver(self) -> LeadMatchupSolver:
        """Lazily initialize the shared `LeadMatchupSolver` bound to the active compute backend."""
        with self.lock:
            if self._lead_solver is None:
                self._lead_solver = LeadMatchupSolver(
                    repo=self.gpu_engine.sc.repo,
                    device=self.gpu_engine.device_type,
                )
            return self._lead_solver

    def start_new_lead_cancel_event(self) -> threading.Event:
        """Cancel any previously running Lead Lab sweep and register a fresh cancel event."""
        with self._lead_cancel_lock:
            if self._lead_cancel_event is not None:
                self._lead_cancel_event.set()
            ev = threading.Event()
            self._lead_cancel_event = ev
            return ev

    def cancel_active_lead_stream(self) -> bool:
        """Abort any active `90 × 90` Lead Lab sweep cleanly between lead pairs/tiles."""
        with self._lead_cancel_lock:
            if self._lead_cancel_event is not None:
                self._lead_cancel_event.set()
                return True
            return False

    def infer_lead_lab_opponent(
        self,
        replays: Optional[Sequence[Dict[str, Any]]] = None,
        pov_trainer: Optional[str] = None,
        t1_roster_id: Optional[str] = None,
        t1_paste_text: Optional[str] = None,
        t2_ots_paste_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Solve exact clamped 66-SP bounds for Lead Lab Team 2 from 1–3 Bo3 scouting logs + OTS."""
        sortable_lead: List[Dict[str, str]] = []
        for idx_l, entry in enumerate(list(replays or [])[:3], 1):
            raw_txt = (
                str(entry.get("raw_input") or "").strip()
                if isinstance(entry, dict)
                else str(entry or "").strip()
            )
            fname_l = (
                str(entry.get("filename") or f"Game {idx_l}").strip()
                if isinstance(entry, dict)
                else f"Game {idx_l}"
            )
            if raw_txt:
                sortable_lead.append({"filename": fname_l, "raw_input": raw_txt})
        sortable_lead, _ = sort_replay_entries(sortable_lead)
        lead_game_nums = assign_bo3_game_numbers(sortable_lead)
        raw_items: List[str] = [x["raw_input"] for x in sortable_lead]
        if not raw_items:
            raise ValueError(
                "Upload 1 to 3 Bo3 scouting Showdown replay logs to infer clamped 66-SP bounds for an EV-less opponent OTS."
            )

        prelim0 = parse_showdown_replay(
            raw_items[0],
            pov_trainer=pov_trainer or None,
            game_index=lead_game_nums[0],
            anonymize_opponent=True,
        )
        resolved_pov = prelim0.trainer_1_name

        paste1 = (t1_paste_text or "").strip()
        if not paste1 and t1_roster_id:
            r1 = self.ots_db.get_roster(str(t1_roster_id).strip())
            paste1 = str(r1.get("paste_text") or "").strip() if r1 else ""
        if not paste1:
            r1_auto = self.ots_db.match_best_roster(prelim0.trainer_1_name, prelim0.trainer_1_preview)
            paste1 = str(r1_auto.get("paste_text") or "").strip() if r1_auto else ""
        t1_sets = self.ots_db.get_parsed_sets_by_species(paste1) if paste1 else {}
        if not t1_sets and prelim0.trainer_1_showteam_ots:
            t1_sets = dict(prelim0.trainer_1_showteam_ots)

        parsed_replays: List[ParsedReplay] = []
        t2_showteam_pooled: Dict[str, Any] = {}
        for raw_txt, g_num in zip(raw_items, lead_game_nums):
            pr = parse_showdown_replay(
                raw_txt,
                pov_trainer=resolved_pov,
                trainer_1_ots_sets=t1_sets,
                game_index=g_num,
                anonymize_opponent=True,
            )
            parsed_replays.append(pr)
            for k, v in (pr.trainer_2_showteam_ots or {}).items():
                if k not in t2_showteam_pooled:
                    t2_showteam_pooled[k] = v

        t2_ots_paste = (t2_ots_paste_text or "").strip()
        if t2_ots_paste:
            t2_ots_sets = self.ots_db.get_parsed_sets_by_species(t2_ots_paste)
        else:
            t2_ots_sets = t2_showteam_pooled

        inferencer = OpponentSetInferencer()
        report = inferencer.infer_series(
            trainer_1_sets=t1_sets,
            trainer_2_ots_sets=t2_ots_sets,
            replays=parsed_replays,
            trainer_1_name=prelim0.trainer_1_name,
            trainer_2_name=prelim0.trainer_2_name,
        )
        default_spreads = {
            inf.base_species: inf.default_spread.to_dict()
            for inf in report.pokemon_inferences.values()
        }
        with self.lock:
            self.lead_ephemeral_t2_inference = report
            self.lead_ephemeral_t2_spreads = default_spreads

        payload = self._enrich_inference_payload(report, override_spreads=default_spreads)
        payload["ok"] = True
        payload["games_pooled"] = len(parsed_replays)
        payload["trainer_1_name"] = prelim0.trainer_1_name
        payload["trainer_2_name"] = prelim0.trainer_2_name
        return payload

    def _resolve_lead_lab_inputs(
        self,
        t1_roster_id: Optional[str] = None,
        t1_paste_text: Optional[str] = None,
        t2_roster_id: Optional[str] = None,
        t2_paste_text: Optional[str] = None,
        t2_user_spreads: Optional[Dict[str, Dict[str, int]]] = None,
    ) -> Tuple[str, str, str, str]:
        """Resolve `(paste1, t1_label, paste2, t2_label)` from saved rosters, raw pastes, or Bo3 inference."""
        paste1 = (t1_paste_text or "").strip()
        t1_label = "Team 1 (trainer_1)"
        if not paste1 and t1_roster_id:
            r1 = self.ots_db.get_roster(str(t1_roster_id).strip())
            if r1 is None:
                raise ValueError(f"Saved DuckDB roster not found for trainer_1: '{t1_roster_id}'")
            paste1 = str(r1.get("paste_text") or "").strip()
            t1_label = str(r1.get("display_name") or r1.get("roster_id") or t1_label)
        if not paste1:
            raise ValueError("Select a saved DuckDB 66-SP team or paste a Full 66-SP team for trainer_1.")

        paste2 = (t2_paste_text or "").strip()
        t2_label = "Team 2 (trainer_2)"
        with self.lock:
            lead_inf = self.lead_ephemeral_t2_inference

        if t2_user_spreads is not None and lead_inf is not None:
            ok_sp, errs_sp = lead_inf.validate_user_spreads(t2_user_spreads)
            if not ok_sp:
                raise ValueError(
                    "Invalid Team 2 66-SP allocation (scouting bounds cannot be overridden): "
                    + " | ".join(errs_sp)
                )
            paste2 = lead_inf.build_paste(override_spreads=t2_user_spreads)
            t2_label = f"{lead_inf.trainer_2_name} (Inferred 66-SP)"
            with self.lock:
                self.lead_ephemeral_t2_spreads = {k: dict(v) for k, v in t2_user_spreads.items()}
        elif not paste2 and t2_roster_id:
            r2 = self.ots_db.get_roster(str(t2_roster_id).strip())
            if r2 is None:
                raise ValueError(f"Saved DuckDB roster not found for trainer_2: '{t2_roster_id}'")
            paste2 = str(r2.get("paste_text") or "").strip()
            t2_label = str(r2.get("display_name") or r2.get("roster_id") or t2_label)
        elif not paste2 and lead_inf is not None:
            with self.lock:
                sp_ov = self.lead_ephemeral_t2_spreads or None
            paste2 = lead_inf.build_paste(override_spreads=sp_ov)
            t2_label = f"{lead_inf.trainer_2_name} (Inferred 66-SP)"

        if not paste2:
            raise ValueError(
                "Select a saved 66-SP team, paste a Full 66-SP team, or solve Team 2 66-SP from 1–3 Bo3 scouting logs."
            )
        return paste1, t1_label, paste2, t2_label

    def lookup_lead_lab_vault(
        self,
        t1_roster_id: Optional[str] = None,
        t1_paste_text: Optional[str] = None,
        t2_roster_id: Optional[str] = None,
        t2_paste_text: Optional[str] = None,
        t2_user_spreads: Optional[Dict[str, Dict[str, int]]] = None,
        preset: str = "balanced",
    ) -> Dict[str, Any]:
        """Instant DuckDB Matchup Vault cache-hit lookup for the selected T1 + T2 + preset."""
        try:
            paste1, _l1, paste2, _l2 = self._resolve_lead_lab_inputs(
                t1_roster_id=t1_roster_id,
                t1_paste_text=t1_paste_text,
                t2_roster_id=t2_roster_id,
                t2_paste_text=t2_paste_text,
                t2_user_spreads=t2_user_spreads,
            )
        except Exception:
            return {"ok": True, "found": False, "current_engine_version": EQUITY_ENGINE_VERSION}

        hit = self.ots_db.lookup_lead_lab_run(
            t1_paste=paste1,
            t2_paste=paste2,
            preset=str(preset or "balanced"),
            engine_version=EQUITY_ENGINE_VERSION,
        )
        if not hit:
            return {"ok": True, "found": False, "current_engine_version": EQUITY_ENGINE_VERSION}
        return {"ok": True, "current_engine_version": EQUITY_ENGINE_VERSION, **hit}

    def load_lead_lab_vault_run(self, run_id: str) -> Dict[str, Any]:
        """Load a saved DuckDB Lead Lab matchup run and register a live `job_id` for deep Turn-1 audits."""
        saved = self.ots_db.load_lead_lab_run(run_id, current_engine_version=EQUITY_ENGINE_VERSION)
        if saved is None:
            raise ValueError(f"Saved Lead Lab Vault run not found: '{run_id}'")

        payload = dict(saved["payload"])
        # Normalize canonical + alias keys so legacy and new Vault entries restore full 15×15 × 6×6 matrices
        t1_leads = payload.get("t1_leads") or payload.get("trainer_1_leads") or []
        t2_leads = payload.get("t2_leads") or payload.get("trainer_2_leads") or []
        if not t1_leads and payload.get("heatmap_cells"):
            t1_leads = [row[0].get("lead_1", []) for row in payload["heatmap_cells"] if row and row[0]]
        if not t2_leads and payload.get("heatmap_cells") and payload["heatmap_cells"][0]:
            t2_leads = [cell.get("lead_2", []) for cell in payload["heatmap_cells"][0] if cell]
        payload["t1_leads"] = t1_leads
        payload["t2_leads"] = t2_leads
        payload["trainer_1_leads"] = t1_leads
        payload["trainer_2_leads"] = t2_leads
        payload["num_t1_modes"] = int(payload.get("num_t1_modes") or len(payload.get("modes_t1") or []) or 90)
        payload["num_t2_modes"] = int(payload.get("num_t2_modes") or len(payload.get("modes_t2") or []) or 90)
        # Reconstruct 90×90 payoff_matrix from heatmap_cells sub-matrices if absent in pre-v0.2.0 Vault rows
        if not payload.get("payoff_matrix") and payload.get("heatmap_cells"):
            hm = payload["heatmap_cells"]
            n_l1 = len(hm)
            n_l2 = len(hm[0]) if n_l1 else 0
            if n_l1 > 0 and n_l2 > 0 and hm[0][0].get("sub_matrix_6x6"):
                nb1 = len(hm[0][0]["sub_matrix_6x6"])
                nb2 = len(hm[0][0]["sub_matrix_6x6"][0]) if nb1 else 0
                mat = [[0.0] * (n_l2 * nb2) for _ in range(n_l1 * nb1)]
                for li in range(n_l1):
                    for lj in range(n_l2):
                        sub = (hm[li][lj] or {}).get("sub_matrix_6x6") or []
                        for bi in range(min(nb1, len(sub))):
                            for bj in range(min(nb2, len(sub[bi]))):
                                mat[li * nb1 + bi][lj * nb2 + bj] = round(float(sub[bi][bj]), 3)
                payload["payoff_matrix"] = mat

        sprites_map = dict(payload.get("sprites") or {})
        if not sprites_map:
            for sp in list(saved["t1_species"]) + list(saved["t2_species"]):
                sprites_map[sp] = resolve_sprite_urls(sp)

        job_id = f"vault_{saved['run_id'][:14]}"
        job_rec = {
            "job_id": job_id,
            "matchup_hash": saved["matchup_hash"],
            "t1_label": saved["t1_name"],
            "t2_label": saved["t2_name"],
            "t1_paste": saved["t1_paste"],
            "t2_paste": saved["t2_paste"],
            "config": LeadMatchupConfig.from_preset(preset=saved["preset"], device=self._get_lead_solver().device_str),
            "t1_species": saved["t1_species"],
            "t2_species": saved["t2_species"],
            "sprites": sprites_map,
            "result": payload,
        }
        with self._lead_jobs_lock:
            self._lead_jobs[job_id] = job_rec
            if job_id not in self._lead_jobs_order:
                self._lead_jobs_order.append(job_id)
                while len(self._lead_jobs_order) > 16:
                    evict = self._lead_jobs_order.pop(0)
                    self._lead_jobs.pop(evict, None)

        payload["job_id"] = job_id
        payload["sprites"] = sprites_map
        payload["t1_label"] = saved["t1_name"]
        payload["t2_label"] = saved["t2_name"]
        payload["t1_paste"] = saved["t1_paste"]
        payload["t2_paste"] = saved["t2_paste"]
        payload["vault_run_id"] = saved["run_id"]
        payload["matchup_hash"] = saved["matchup_hash"]
        payload["engine_version"] = saved["engine_version"]
        payload["is_outdated"] = saved["is_outdated"]
        payload["tags"] = saved["tags"]
        payload["created_at"] = saved["created_at"]
        payload["cached_deep_audit_keys"] = saved["cached_deep_audit_keys"]
        payload["from_vault"] = True

        return {
            "ok": True,
            "job_id": job_id,
            "run_id": saved["run_id"],
            "matchup_hash": saved["matchup_hash"],
            "preset": saved["preset"],
            "t1_name": saved["t1_name"],
            "t2_name": saved["t2_name"],
            "t1_paste": saved["t1_paste"],
            "t2_paste": saved["t2_paste"],
            "t1_species": saved["t1_species"],
            "t2_species": saved["t2_species"],
            "engine_version": saved["engine_version"],
            "is_outdated": saved["is_outdated"],
            "tags": saved["tags"],
            "created_at": saved["created_at"],
            "cached_deep_audit_keys": saved["cached_deep_audit_keys"],
            "result": payload,
        }

    def export_lead_lab_vault_run(self, run_id: str, fmt: str = "json") -> Tuple[bytes, str, str]:
        """Export the full persisted 90×90 matrix + best Turn-1 plays from DuckDB Vault as CSV or JSON."""
        loaded = self.load_lead_lab_vault_run(run_id)
        payload = loaded["result"]
        safe_slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", f"{loaded['t1_name']}_vs_{loaded['t2_name']}").strip("_")[:60]
        norm_fmt = str(fmt or "json").strip().lower()

        if norm_fmt == "csv":
            def _csv_safe(val: Any) -> str:
                s = str(val if val is not None else "")
                if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
                    return "'" + s
                return s

            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(
                [
                    "lead_1",
                    "bench_1",
                    "lead_2",
                    "bench_2",
                    "score",
                    "cvar_10",
                    "t1_best_play",
                    "t2_best_counter",
                    "t1_top3_plays",
                    "t2_top3_counters",
                ]
            )
            for row_cells in payload.get("heatmap_cells") or []:
                for cell in row_cells or []:
                    l1_str = " + ".join(cell.get("lead_1") or [])
                    l2_str = " + ".join(cell.get("lead_2") or [])
                    b1_lbls = cell.get("t1_bench_labels") or []
                    b2_lbls = cell.get("t2_bench_labels") or []
                    sub_m = cell.get("sub_matrix_6x6") or []
                    sub_cv = cell.get("sub_cvar_6x6") or []
                    sub_t1 = cell.get("sub_t1_openings") or []
                    sub_t2 = cell.get("sub_t2_openings") or []
                    sub_t1_top = cell.get("sub_t1_top_plays") or []
                    sub_t2_top = cell.get("sub_t2_top_plays") or []
                    for bi, b1_pair in enumerate(b1_lbls):
                        for bj, b2_pair in enumerate(b2_lbls):
                            sc = sub_m[bi][bj] if bi < len(sub_m) and bj < len(sub_m[bi]) else 0.0
                            cv = sub_cv[bi][bj] if bi < len(sub_cv) and bj < len(sub_cv[bi]) else 0.0
                            p1_op = sub_t1[bi][bj] if bi < len(sub_t1) and bj < len(sub_t1[bi]) else ""
                            p2_op = sub_t2[bi][bj] if bi < len(sub_t2) and bj < len(sub_t2[bi]) else ""
                            top1_list = sub_t1_top[bi][bj] if bi < len(sub_t1_top) and bj < len(sub_t1_top[bi]) else []
                            top2_list = sub_t2_top[bi][bj] if bi < len(sub_t2_top) and bj < len(sub_t2_top[bi]) else []
                            top1_fmt = " | ".join(f"{x[0]} ({x[1]}%, {x[2]:+.2f})" for x in top1_list)
                            top2_fmt = " | ".join(f"{x[0]} ({x[1]}%, {x[2]:+.2f})" for x in top2_list)
                            writer.writerow(
                                [
                                    _csv_safe(l1_str),
                                    _csv_safe(" + ".join(b1_pair)),
                                    _csv_safe(l2_str),
                                    _csv_safe(" + ".join(b2_pair)),
                                    f"{float(sc):.4f}",
                                    f"{float(cv):.4f}",
                                    _csv_safe(p1_op),
                                    _csv_safe(p2_op),
                                    _csv_safe(top1_fmt),
                                    _csv_safe(top2_fmt),
                                ]
                            )
            return (
                buf.getvalue().encode("utf-8-sig"),
                "text/csv; charset=utf-8",
                f"LeadLab_90x90_{safe_slug or 'matchup'}.csv",
            )

        export_obj = {
            "run_id": loaded["run_id"],
            "matchup_hash": loaded["matchup_hash"],
            "preset": loaded["preset"],
            "engine_version": loaded["engine_version"],
            "created_at": loaded["created_at"],
            "t1_name": loaded["t1_name"],
            "t2_name": loaded["t2_name"],
            "t1_paste": loaded["t1_paste"],
            "t2_paste": loaded["t2_paste"],
            "result": payload,
        }
        return (
            json.dumps(export_obj, indent=2, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
            f"LeadLab_90x90_{safe_slug or 'matchup'}.json",
        )

    def create_lead_lab_job(
        self,
        t1_roster_id: Optional[str] = None,
        t1_paste_text: Optional[str] = None,
        t2_roster_id: Optional[str] = None,
        t2_paste_text: Optional[str] = None,
        t2_user_spreads: Optional[Dict[str, Dict[str, int]]] = None,
        preset: str = "balanced",
        compute_mode: str = "auto",
        require_explicit_spreads: bool = True,
    ) -> Dict[str, Any]:
        """Validate both 66-SP teams and register a streamable Factored `90 × 90` Lead Lab job."""
        paste1, t1_label, paste2, t2_label = self._resolve_lead_lab_inputs(
            t1_roster_id=t1_roster_id,
            t1_paste_text=t1_paste_text,
            t2_roster_id=t2_roster_id,
            t2_paste_text=t2_paste_text,
            t2_user_spreads=t2_user_spreads,
        )

        solver = self._get_lead_solver()
        cfg = LeadMatchupConfig.from_preset(
            preset=preset,
            device=solver.device_str,
            require_explicit_spreads=require_explicit_spreads,
            compute_mode=compute_mode,
        )
        # Validate spreads & precompile pools upfront so bare EV-less OTS fails immediately with HTTP 400
        pool_t1 = solver._precompile_team_pool(
            paste1, trainer_id="trainer_1", require_explicit_spreads=cfg.require_explicit_spreads
        )
        pool_t2 = solver._precompile_team_pool(
            paste2, trainer_id="trainer_2", require_explicit_spreads=cfg.require_explicit_spreads
        )

        sprites_map: Dict[str, Dict[str, Any]] = {}
        for mon, disp in zip(pool_t1.mons, pool_t1.display_species):
            sprites_map[disp] = resolve_sprite_urls(disp, mon.item)
        for mon, disp in zip(pool_t2.mons, pool_t2.display_species):
            sprites_map[disp] = resolve_sprite_urls(disp, mon.item)

        t1_leads = [[pool_t1.display_species[a], pool_t1.display_species[b]] for (a, b) in pool_t1.leads]
        t2_leads = [[pool_t2.display_species[a], pool_t2.display_species[b]] for (a, b) in pool_t2.leads]

        matchup_hash = compute_lead_lab_matchup_hash(paste1, paste2, cfg.preset, engine_version=EQUITY_ENGINE_VERSION)
        seed_key = f"{time.time_ns()}|{cfg.preset}|{paste1[:64]}|{paste2[:64]}"
        job_id = hashlib.sha256(seed_key.encode("utf-8")).hexdigest()[:20]

        job_rec = {
            "job_id": job_id,
            "matchup_hash": matchup_hash,
            "t1_label": t1_label,
            "t2_label": t2_label,
            "t1_paste": paste1,
            "t2_paste": paste2,
            "config": cfg,
            "t1_species": list(pool_t1.display_species),
            "t2_species": list(pool_t2.display_species),
            "t1_leads": t1_leads,
            "t2_leads": t2_leads,
            "num_t1_modes": len(pool_t1.modes),
            "num_t2_modes": len(pool_t2.modes),
            "total_lead_pairs": len(t1_leads) * len(t2_leads),
            "sprites": sprites_map,
            "result": None,
        }
        with self._lead_jobs_lock:
            self._lead_jobs[job_id] = job_rec
            self._lead_jobs_order.append(job_id)
            while len(self._lead_jobs_order) > 16:
                evict = self._lead_jobs_order.pop(0)
                self._lead_jobs.pop(evict, None)

        return {
            "ok": True,
            "job_id": job_id,
            "matchup_hash": matchup_hash,
            "preset": cfg.preset,
            "compute_mode": cfg.compute_mode,
            "device": self.gpu_engine.device_name,
            "device_type": self.gpu_engine.device_type,
            "t1_label": t1_label,
            "t2_label": t2_label,
            "t1_species": job_rec["t1_species"],
            "t2_species": job_rec["t2_species"],
            "t1_leads": t1_leads,
            "t2_leads": t2_leads,
            "num_t1_modes": job_rec["num_t1_modes"],
            "num_t2_modes": job_rec["num_t2_modes"],
            "total_lead_pairs": job_rec["total_lead_pairs"],
            "sprites": sprites_map,
        }

    def get_lead_lab_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a registered Lead Lab job by `job_id`."""
        if not job_id:
            return None
        with self._lead_jobs_lock:
            return self._lead_jobs.get(job_id)

    def run_lead_lab_deep_turn1(
        self,
        job_id: str,
        mode_1_idx: int,
        mode_2_idx: int,
        num_mc: int = 128,
        force_recompute: bool = False,
        lead_1: Optional[Sequence[str]] = None,
        bench_1: Optional[Sequence[str]] = None,
        lead_2: Optional[Sequence[str]] = None,
        bench_2: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """Run (or serve cached) full unpruned Turn-1 GPU audit (`K=128`) on one exact 4v4 matchup."""
        job = self.get_lead_lab_job(job_id)
        if job is None:
            raise ValueError(f"Lead Lab session expired or not found: '{job_id}'")

        solver = self._get_lead_solver()
        # Resolve exact mode indices by species identity whenever explicit lead/bench species are supplied,
        # eliminating positional drift across Vault reloads or reordered pastes.
        resolved_m1 = int(mode_1_idx)
        resolved_m2 = int(mode_2_idx)
        pool_t1 = solver._precompile_team_pool(
            job["t1_paste"], trainer_id="trainer_1", require_explicit_spreads=False
        )
        pool_t2 = solver._precompile_team_pool(
            job["t2_paste"], trainer_id="trainer_2", require_explicit_spreads=False
        )
        if lead_1 and bench_1:
            want_k1 = canonical_mode_key(lead_1, bench_1)
            for cand in pool_t1.modes:
                if canonical_mode_key(cand.lead_species, cand.bench_species) == want_k1:
                    resolved_m1 = int(cand.mode_idx)
                    break
        if lead_2 and bench_2:
            want_k2 = canonical_mode_key(lead_2, bench_2)
            for cand in pool_t2.modes:
                if canonical_mode_key(cand.lead_species, cand.bench_species) == want_k2:
                    resolved_m2 = int(cand.mode_idx)
                    break

        m1_spec = pool_t1.modes[max(0, min(len(pool_t1.modes) - 1, resolved_m1))]
        m2_spec = pool_t2.modes[max(0, min(len(pool_t2.modes) - 1, resolved_m2))]

        m_hash = str(job.get("matchup_hash") or "")
        t1_mk = canonical_mode_key(m1_spec.lead_species, m1_spec.bench_species)
        t2_mk = canonical_mode_key(m2_spec.lead_species, m2_spec.bench_species)

        if m_hash and not force_recompute:
            cached = self.ots_db.get_cached_deep_audit(
                matchup_hash=m_hash,
                t1_mode_key=t1_mk,
                t2_mode_key=t2_mk,
                engine_version=EQUITY_ENGINE_VERSION,
                expected_lead_1=m1_spec.lead_species,
                expected_bench_1=m1_spec.bench_species,
                expected_lead_2=m2_spec.lead_species,
                expected_bench_2=m2_spec.bench_species,
            )
            if cached is not None:
                return cached

        board, m1, m2, events = solver.build_turn1_battle_state(
            trainer_1_paste=job["t1_paste"],
            trainer_2_paste=job["t2_paste"],
            mode_1_idx=resolved_m1,
            mode_2_idx=resolved_m2,
        )
        audit = self.gpu_engine.analyze_compiled_turn1(
            comp=board,
            turn0_events=events,
            num_mc=max(8, min(256, int(num_mc or 128))),
        )
        audit["mode_1"] = m1.to_dict()
        audit["mode_2"] = m2.to_dict()
        audit["sprites"] = job["sprites"]
        audit["from_vault_cache"] = False
        audit["audit_cell_key"] = f"{t1_mk}__{t2_mk}"
        if m_hash:
            try:
                self.ots_db.save_cached_deep_audit(
                    matchup_hash=m_hash,
                    t1_mode_key=t1_mk,
                    t2_mode_key=t2_mk,
                    payload=audit,
                    engine_version=EQUITY_ENGINE_VERSION,
                )
            except Exception:
                pass
        return audit

    def run_lead_lab_deep_turn1_batch(
        self,
        job_id: str,
        pairs: Sequence[Dict[str, Any]],
        num_mc: int = 128,
        force_recompute: bool = False,
    ) -> Dict[str, Any]:
        """Run (or serve cached) deep unpruned Turn-1 audits for up to 8 `(own_lead, opp_lead)` pairs."""
        clean_pairs = list(pairs or [])[:8]
        if not clean_pairs:
            raise ValueError("Provide at least one `(lead_1, bench_1, lead_2, bench_2)` pair to audit.")
        audits: List[Dict[str, Any]] = []
        cached_count = 0
        computed_count = 0
        for p in clean_pairs:
            audit = self.run_lead_lab_deep_turn1(
                job_id=job_id,
                mode_1_idx=int(p.get("mode_1_idx", 0)),
                mode_2_idx=int(p.get("mode_2_idx", 0)),
                num_mc=num_mc,
                force_recompute=force_recompute,
                lead_1=p.get("lead_1"),
                bench_1=p.get("bench_1"),
                lead_2=p.get("lead_2"),
                bench_2=p.get("bench_2"),
            )
            if audit.get("from_vault_cache"):
                cached_count += 1
            else:
                computed_count += 1
            audits.append(audit)
        return {
            "ok": True,
            "count": len(audits),
            "cached_count": cached_count,
            "computed_count": computed_count,
            "audits": audits,
        }


MAX_JSON_BODY_BYTES = 10 * 1024 * 1024  # 10 MiB hard cap against local memory DoS
_ALLOWED_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}


class _PayloadTooLargeError(ValueError):
    """Raised when an HTTP request body exceeds `MAX_JSON_BODY_BYTES`."""


def _extract_hostname(host_or_origin: str) -> str:
    """Extract normalized lowercase hostname from a `Host`, `Origin`, or `Referer` header."""
    raw = str(host_or_origin or "").strip()
    if not raw:
        return ""
    if "://" in raw:
        parsed = urllib.parse.urlparse(raw)
        return (parsed.hostname or "").lower()
    # Bare Host header (`127.0.0.1:8765`, `localhost:8765`, `[::1]:8765`)
    parsed = urllib.parse.urlparse(f"http://{raw}")
    return (parsed.hostname or "").lower()


def make_handler(app_state: ReplayCoachAppState):
    """Create a request handler class bound to the shared `ReplayCoachAppState`."""

    class CoachHTTPHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

        def _send_security_headers(self, referrer_policy: str = "no-referrer") -> None:
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "SAMEORIGIN")
            self.send_header("Referrer-Policy", referrer_policy)
            self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")

        def _is_trusted_host(self) -> bool:
            """Defend against DNS rebinding by enforcing a strict loopback Host allowlist."""
            host_hdr = self.headers.get("Host", "")
            if not host_hdr:
                return True
            return _extract_hostname(host_hdr) in _ALLOWED_LOOPBACK_HOSTS

        def _is_trusted_origin(self) -> bool:
            """Defend against cross-site localhost CSRF on state-changing POST requests."""
            fetch_site = (self.headers.get("Sec-Fetch-Site") or "").strip().lower()
            if fetch_site == "cross-site":
                return False
            origin_hdr = self.headers.get("Origin", "")
            if origin_hdr:
                return _extract_hostname(origin_hdr) in _ALLOWED_LOOPBACK_HOSTS
            referer_hdr = self.headers.get("Referer", "")
            if referer_hdr:
                return _extract_hostname(referer_hdr) in _ALLOWED_LOOPBACK_HOSTS
            return True

        def _send_bytes(
            self,
            data: bytes,
            content_type: str,
            status: int = HTTPStatus.OK,
            referrer_policy: str = "no-referrer",
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self._send_security_headers(referrer_policy=referrer_policy)
            self.end_headers()
            self.wfile.write(data)

        def _send_json(self, obj: Any, status: int = HTTPStatus.OK) -> None:
            raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self._send_bytes(raw, "application/json; charset=utf-8", status=status)

        def _read_json_body(self) -> Dict[str, Any]:
            raw_len = (self.headers.get("Content-Length") or "0").strip()
            length = int(raw_len)
            if length < 0:
                raise ValueError("Negative Content-Length")
            if length > MAX_JSON_BODY_BYTES:
                raise _PayloadTooLargeError(f"Request body exceeds {MAX_JSON_BODY_BYTES} bytes")
            raw = self.rfile.read(length) if length > 0 else b"{}"
            return json.loads(raw.decode("utf-8"))

        def _serve_file(self, base_dir: Path, rel_path: str) -> None:
            unquoted = urllib.parse.unquote(rel_path)
            if "\x00" in unquoted or "\\" in unquoted:
                self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
                return
            safe_rel = unquoted.lstrip("/")
            base_resolved = base_dir.resolve()
            full = (base_resolved / safe_rel).resolve()
            if not full.is_relative_to(base_resolved) or not full.is_file():
                self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
                return
            ctype, _ = mimetypes.guess_type(str(full))
            self._send_bytes(full.read_bytes(), ctype or "application/octet-stream")

        def do_GET(self) -> None:
            if not self._is_trusted_host():
                self._send_json({"error": "Forbidden host"}, status=HTTPStatus.FORBIDDEN)
                return
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
                scope_q = qs.get("scope", [""])[0]
                self._send_json({"rosters": app_state.ots_db.list_rosters(team_scope=scope_q or None)})
                return
            if path == "/api/rosters/search":
                try:
                    min_elo_raw = qs.get("min_elo", [""])[0].strip()
                    max_elo_raw = qs.get("max_elo", [""])[0].strip()
                    res = app_state.ots_db.search_rosters(
                        scope=qs.get("scope", [""])[0],
                        archetype=qs.get("archetype", [""])[0],
                        regulation=qs.get("regulation", [""])[0],
                        source_type=qs.get("source_type", [""])[0],
                        q=qs.get("q", [""])[0],
                        min_elo=int(min_elo_raw) if min_elo_raw.isdigit() else None,
                        max_elo=int(max_elo_raw) if max_elo_raw.isdigit() else None,
                    )
                    self._send_json(res)
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
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
                self._send_bytes(
                    html_doc.encode("utf-8"),
                    "text/html; charset=utf-8",
                    referrer_policy="strict-origin-when-cross-origin",
                )
                return
            if path == "/api/reg-md-scout":
                report_path = REPO_ROOT / "reports" / "reg_md_meta_scout.html"
                if not report_path.is_file():
                    self._send_json(
                        {"error": "Meta scout report not found. Run scripts/generate_reg_md_meta_report.py."},
                        status=HTTPStatus.NOT_FOUND,
                    )
                    return
                data = report_path.read_bytes()
                if qs.get("download", ["0"])[0] in ("1", "true", "yes"):
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header(
                        "Content-Disposition",
                        'attachment; filename="CoachPorygon_Reg_MD_Meta_Scout.html"',
                    )
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    self._send_bytes(data, "text/html; charset=utf-8")
                return
            if path == "/api/prep-tools/preview":
                token = str(qs.get("token", [""])[0]).strip()
                cached = app_state.get_prep_tool_cached(token)
                if cached is None:
                    self._send_json({"error": "Prep report expired or not found"}, status=HTTPStatus.NOT_FOUND)
                    return
                self._send_bytes(cached["html_bytes"], "text/html; charset=utf-8")
                return
            if path == "/api/prep-tools/download":
                token = str(qs.get("token", [""])[0]).strip()
                cached = app_state.get_prep_tool_cached(token)
                if cached is None:
                    self._send_json({"error": "Prep report expired or not found"}, status=HTTPStatus.NOT_FOUND)
                    return
                data = cached["html_bytes"]
                fname = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(cached["filename"]))
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
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
                import queue as _queue

                num_mc = int(qs.get("num_mc", ["128"])[0])
                start_turn = int(qs.get("start_turn", ["1"])[0])
                two_ply = qs.get("two_ply", ["0"])[0] in ("1", "true", "yes")
                compute_mode = str(qs.get("compute_mode", ["auto"])[0] or "auto").strip().lower()
                raw_skip = str(qs.get("skip_turns", [""])[0] or "").strip()
                skip_turns_list: List[int] = []
                if raw_skip:
                    for tok in raw_skip.split(","):
                        tok = tok.strip()
                        if tok.isdigit():
                            skip_turns_list.append(int(tok))

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

                total_turns = len(rep.turns)
                cancel_event = app_state.start_new_stream_cancel_event()
                sse_q: "_queue.Queue[Optional[Tuple[str, Any]]]" = _queue.Queue()
                status_lock = threading.Lock()
                active_workers: Dict[str, Dict[str, Any]] = {}
                completed_by_turn: Dict[int, Dict[str, Any]] = {}

                def _emit_worker_snapshot(extra: Optional[Dict[str, Any]] = None) -> None:
                    with status_lock:
                        snap_workers = [
                            dict(active_workers[k])
                            for k in sorted(active_workers.keys(), key=lambda x: (0 if x == "GPU" else 1, x))
                        ]
                        done_turns_sorted = sorted(completed_by_turn.keys())
                        payload: Dict[str, Any] = {
                            "active_workers": snap_workers,
                            "completed_count": len(done_turns_sorted),
                            "completed_turns": done_turns_sorted,
                            "total_turns": total_turns,
                        }
                        if extra:
                            payload.update(extra)
                    sse_q.put(("worker_progress", payload))

                def _on_plan(plan: Dict[str, Any]) -> None:
                    sse_q.put(("scheduler", plan))

                def _on_worker_start(t_num: int, w_lbl: str, hw_name: str) -> None:
                    with status_lock:
                        active_workers[w_lbl] = {
                            "worker": w_lbl,
                            "hardware_device": hw_name,
                            "turn": int(t_num),
                            "pct": 0,
                            "phase": "COMPILE",
                            "state": "running",
                        }
                    _emit_worker_snapshot({"event_kind": "start", "turn": int(t_num), "worker": w_lbl, "hardware_device": hw_name})

                def _on_log(log_entry: Dict[str, Any]) -> None:
                    # Buffer full per-turn logs inside each worker's result; stream ONLY compact
                    # non-interleaved hardware status updates while parallel workers run.
                    w_lbl = str(log_entry.get("compute_worker") or "GPU")
                    hw_dev = str(log_entry.get("hardware_device") or app_state.gpu_engine.device_name)
                    t_num = int(log_entry.get("turn") or 0)
                    ph = str(log_entry.get("phase") or "")
                    if log_entry.get("in_place") or ph in ("COMPILE", "PRUNE", "IEDS", "NASH_QRE", "VERDICT"):
                        with status_lock:
                            cur = active_workers.get(w_lbl, {})
                            pct_val = int(log_entry.get("pct")) if "pct" in log_entry else int(cur.get("pct") or 0)
                            if ph == "VERDICT":
                                pct_val = 100
                            active_workers[w_lbl] = {
                                "worker": w_lbl,
                                "hardware_device": hw_dev,
                                "turn": t_num,
                                "pct": pct_val,
                                "phase": ph,
                                "state": "done_turn" if ph == "VERDICT" else "running",
                            }
                        _emit_worker_snapshot({"event_kind": "progress", "turn": t_num, "worker": w_lbl, "hardware_device": hw_dev})

                def _on_turn(res: Dict[str, Any]) -> None:
                    t_num = int(res.get("turn") or 0)
                    w_lbl = str(res.get("compute_worker") or "GPU")
                    hw_dev = str(res.get("hardware_device") or res.get("device") or w_lbl)
                    with status_lock:
                        completed_by_turn[t_num] = res
                        active_workers[w_lbl] = {
                            "worker": w_lbl,
                            "hardware_device": hw_dev,
                            "turn": t_num,
                            "pct": 100,
                            "phase": "DONE",
                            "state": "idle",
                        }
                    _emit_worker_snapshot(
                        {
                            "event_kind": "turn_done",
                            "turn": t_num,
                            "worker": w_lbl,
                            "hardware_device": hw_dev,
                            "verdict_key": res.get("verdict_key"),
                            "elapsed_s": res.get("elapsed_s"),
                        }
                    )

                def _on_err(t_num: int, w_lbl: str, exc: Exception) -> None:
                    if isinstance(exc, AnalysisCancelledError):
                        return
                    sse_q.put(("error", {"turn": t_num, "compute_worker": w_lbl, "error": str(exc)}))

                def _coordinator() -> None:
                    try:
                        # Wait until ALL parallel workers finish and join cleanly before reconstructing
                        # the strictly ordered (Turn 1 -> Turn N) hardware-tagged log & turn payloads!
                        ordered_res, sched_stats = app_state.gpu_engine.analyze_match_parallel(
                            rep,
                            start_turn=start_turn,
                            num_mc=num_mc,
                            enable_two_ply=two_ply,
                            compute_mode=compute_mode,
                            skip_turns=skip_turns_list,
                            on_scheduler_plan=_on_plan,
                            on_worker_start=_on_worker_start,
                            on_log=_on_log,
                            on_turn=_on_turn,
                            on_error=_on_err,
                            cancel_event=cancel_event,
                        )
                        reconstructed_logs = app_state.gpu_engine.reconstruct_ordered_match_logs(
                            ordered_res,
                            sched_stats=sched_stats,
                            gpu_device_name=app_state.gpu_engine.device_name,
                        )
                        if cancel_event.is_set():
                            sse_q.put(
                                (
                                    "cancelled",
                                    {
                                        "turn": start_turn,
                                        "ordered_turns": ordered_res,
                                        "reconstructed_logs": reconstructed_logs,
                                        "scheduler_stats": sched_stats.to_dict(),
                                    },
                                )
                            )
                        else:
                            sse_q.put(
                                (
                                    "done",
                                    {
                                        "ordered_turns": ordered_res,
                                        "reconstructed_logs": reconstructed_logs,
                                        "match_summary": compute_match_summary(ordered_res),
                                        "scheduler_stats": sched_stats.to_dict(),
                                    },
                                )
                            )
                    except AnalysisCancelledError:
                        with status_lock:
                            partial_ordered = [completed_by_turn[t] for t in sorted(completed_by_turn.keys())]
                        partial_logs = app_state.gpu_engine.reconstruct_ordered_match_logs(
                            partial_ordered,
                            sched_stats=None,
                            gpu_device_name=app_state.gpu_engine.device_name,
                        )
                        sse_q.put(
                            (
                                "cancelled",
                                {
                                    "turn": start_turn,
                                    "ordered_turns": partial_ordered,
                                    "reconstructed_logs": partial_logs,
                                },
                            )
                        )
                    except Exception as exc:
                        sse_q.put(("error", {"turn": 0, "error": str(exc)}))
                    finally:
                        sse_q.put(None)

                coord_thread = threading.Thread(target=_coordinator, name="porygon-sse-coordinator", daemon=True)
                app_state.register_stream_coordinator(coord_thread)
                coord_thread.start()

                while True:
                    item = sse_q.get()
                    if item is None:
                        break
                    ev_name, ev_payload = item
                    if not _write_sse(ev_name, ev_payload):
                        cancel_event.set()
                        break
                coord_thread.join(timeout=4.0)
                return

            if path == "/api/lead-lab/stream":
                job_id = str(qs.get("job_id", [""])[0]).strip()
                job = app_state.get_lead_lab_job(job_id)
                if job is None:
                    self._send_json({"error": "Lead Lab job not found or expired"}, status=HTTPStatus.NOT_FOUND)
                    return

                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()

                def _write_lead_sse(event_name: str, payload_obj: Any) -> bool:
                    try:
                        msg = f"event: {event_name}\ndata: {json.dumps(payload_obj, ensure_ascii=False)}\n\n"
                        self.wfile.write(msg.encode("utf-8"))
                        self.wfile.flush()
                        return True
                    except (BrokenPipeError, ConnectionResetError):
                        return False

                cancel_event = app_state.start_new_lead_cancel_event()
                solver = app_state._get_lead_solver()

                def _on_cell(cell_payload: Dict[str, Any]) -> None:
                    if not _write_lead_sse("cell", cell_payload):
                        cancel_event.set()

                try:
                    result = solver.solve_90x90_matchup(
                        trainer_1_paste=job["t1_paste"],
                        trainer_2_paste=job["t2_paste"],
                        config=job["config"],
                        progress_cb=_on_cell,
                        cancel_event=cancel_event,
                    )
                    res_dict = result.to_dict()
                    res_dict["job_id"] = job_id
                    res_dict["sprites"] = job["sprites"]
                    res_dict["t1_label"] = job["t1_label"]
                    res_dict["t2_label"] = job["t2_label"]
                    res_dict["t1_species"] = job["t1_species"]
                    res_dict["t2_species"] = job["t2_species"]
                    res_dict["engine_version"] = EQUITY_ENGINE_VERSION
                    res_dict["from_vault"] = False
                    try:
                        saved_meta = app_state.ots_db.save_lead_lab_run(
                            t1_name=job["t1_label"],
                            t2_name=job["t2_label"],
                            t1_paste=job["t1_paste"],
                            t2_paste=job["t2_paste"],
                            preset=job["config"].preset,
                            result_payload=res_dict,
                            engine_version=EQUITY_ENGINE_VERSION,
                        )
                        res_dict["vault_run_id"] = saved_meta["run_id"]
                        res_dict["matchup_hash"] = saved_meta["matchup_hash"]
                        res_dict["cached_deep_audit_keys"] = saved_meta["cached_deep_audit_keys"]
                    except Exception:
                        res_dict["matchup_hash"] = job.get("matchup_hash", "")
                        res_dict["cached_deep_audit_keys"] = []
                    job["result"] = res_dict
                    _write_lead_sse("done", res_dict)
                except AnalysisCancelledError:
                    _write_lead_sse("cancelled", {"job_id": job_id})
                except (BrokenPipeError, ConnectionResetError):
                    cancel_event.set()
                except Exception as exc:
                    _write_lead_sse("error", {"job_id": job_id, "error": str(exc)})
                return

            if path == "/api/lead-lab/vault":
                try:
                    q_s = str(qs.get("q", [""])[0])
                    t1_s = str(qs.get("t1_name", [""])[0])
                    adv_s = str(qs.get("advantage", [""])[0])
                    lim_i = int(qs.get("limit", ["60"])[0] or 60)
                    res = app_state.ots_db.search_lead_lab_runs(
                        q=q_s,
                        t1_name=t1_s,
                        advantage=adv_s,
                        limit=lim_i,
                        current_engine_version=EQUITY_ENGINE_VERSION,
                    )
                    self._send_json({"ok": True, **res})
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return

            if path == "/api/lead-lab/vault/load":
                try:
                    run_id = str(qs.get("run_id", [""])[0]).strip()
                    res = app_state.load_lead_lab_vault_run(run_id)
                    self._send_json(res)
                except ValueError as exc:
                    self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.NOT_FOUND)
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return

            if path == "/api/lead-lab/vault/export":
                try:
                    run_id = str(qs.get("run_id", [""])[0]).strip()
                    fmt = str(qs.get("format", ["csv"])[0]).strip().lower()
                    data, ctype, fname = app_state.export_lead_lab_vault_run(run_id, fmt=fmt)
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "no-store")
                    self._send_security_headers()
                    self.end_headers()
                    self.wfile.write(data)
                except ValueError as exc:
                    self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.NOT_FOUND)
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return

            self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            if not self._is_trusted_host() or not self._is_trusted_origin():
                self._send_json({"error": "Forbidden cross-origin or untrusted host request"}, status=HTTPStatus.FORBIDDEN)
                return
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            try:
                body = self._read_json_body()
            except _PayloadTooLargeError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                return
            except Exception as exc:
                self._send_json({"error": f"Invalid JSON: {exc}"}, status=HTTPStatus.BAD_REQUEST)
                return

            if path == "/api/bo3/preview":
                try:
                    preview = app_state.preview_bo3_bundle(
                        replays=body.get("replays") or [],
                        pov_trainer=body.get("pov_trainer"),
                        use_sample=bool(body.get("use_sample")),
                    )
                    self._send_json(preview)
                except Exception as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            if path == "/api/bo3/infer-sp":
                try:
                    res = app_state.infer_bo3_opponent_sp(
                        replays=body.get("replays"),
                        pov_trainer=body.get("pov_trainer"),
                        t1_roster_id=body.get("t1_roster_id"),
                        t1_paste_text=body.get("t1_paste_text"),
                        t2_ots_paste_text=body.get("t2_ots_paste_text"),
                        use_sample=bool(body.get("use_sample")),
                    )
                    self._send_json(res)
                except MissingOTSError as exc:
                    self._send_json(
                        {"ok": False, "missing_ots": True, "error": str(exc)},
                        status=HTTPStatus.UNPROCESSABLE_ENTITY,
                    )
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            if path == "/api/bo3/load":
                try:
                    summary = app_state.load_bo3_bundle(
                        replays=body.get("replays"),
                        pov_trainer=body.get("pov_trainer"),
                        t1_roster_id=body.get("t1_roster_id"),
                        t2_roster_id=body.get("t2_roster_id"),
                        t1_paste_text=body.get("t1_paste_text"),
                        t2_paste_text=body.get("t2_paste_text"),
                        t2_user_spreads=body.get("t2_user_spreads"),
                        active_game_index=int(body.get("active_game_index", 0) or 0),
                        t1_save_meta=body.get("t1_save_meta"),
                        t2_save_meta=body.get("t2_save_meta"),
                    )
                    self._send_json(summary)
                except Exception as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            if path == "/api/bo3/select-game":
                try:
                    summary = app_state.select_bo3_game(int(body.get("game_index", 0)))
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
                        t1_paste_text=body.get("t1_paste_text"),
                        t2_ots_paste_text=body.get("t2_ots_paste_text"),
                    )
                    self._send_json(res)
                except MissingOTSError as exc:
                    self._send_json(
                        {"ok": False, "missing_ots": True, "error": str(exc)},
                        status=HTTPStatus.UNPROCESSABLE_ENTITY,
                    )
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            if path == "/api/rosters":
                try:
                    saved = app_state.ots_db.save_roster(
                        roster_id=str(body.get("roster_id") or "").strip(),
                        display_name=str(body.get("display_name") or "").strip(),
                        trainer_hint=str(body.get("trainer_hint") or "").strip(),
                        paste_text=str(body.get("paste_text") or ""),
                        team_scope=str(body.get("team_scope") or "own"),
                        archetype=str(body.get("archetype") or ""),
                        regulation=str(body.get("regulation") or "Reg M-C"),
                        source_type=str(body.get("source_type") or ""),
                        opponent_elo=body.get("opponent_elo"),
                        notes=str(body.get("notes") or ""),
                    )
                    self._send_json({"ok": True, "saved": saved, "rosters": app_state.ots_db.list_rosters()})
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            if path == "/api/rosters/update-meta":
                try:
                    rid = str(body.get("roster_id") or "").strip()
                    updated = app_state.ots_db.update_roster_meta(
                        roster_id=rid,
                        display_name=body.get("display_name"),
                        team_scope=body.get("team_scope"),
                        archetype=body.get("archetype"),
                        regulation=body.get("regulation"),
                        opponent_elo=body.get("opponent_elo"),
                        notes=body.get("notes"),
                    )
                    if updated is None:
                        self._send_json({"ok": False, "error": f"Roster not found: {rid}"}, status=HTTPStatus.NOT_FOUND)
                        return
                    self._send_json({"ok": True, "updated": updated, "rosters": app_state.ots_db.list_rosters()})
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
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

            if path == "/api/prep-tools/generate":
                try:
                    res = app_state.generate_prep_tool(
                        kind=str(body.get("kind") or "speed_tiers"),
                        roster_id=body.get("roster_id"),
                        paste_text=body.get("paste_text"),
                        team_name=body.get("team_name"),
                        top_n=int(body.get("top_n") or 50),
                        lang=str(body.get("lang") or "es"),
                    )
                    self._send_json(res)
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            if path == "/api/lead-lab/infer-opponent":
                try:
                    res = app_state.infer_lead_lab_opponent(
                        replays=body.get("replays") or [],
                        pov_trainer=body.get("pov_trainer"),
                        t1_roster_id=body.get("t1_roster_id"),
                        t1_paste_text=body.get("t1_paste_text"),
                        t2_ots_paste_text=body.get("t2_ots_paste_text"),
                    )
                    self._send_json(res)
                except MissingOTSError as exc:
                    self._send_json(
                        {"ok": False, "missing_ots": True, "error": str(exc)},
                        status=HTTPStatus.UNPROCESSABLE_ENTITY,
                    )
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            if path == "/api/lead-lab/start":
                try:
                    res = app_state.create_lead_lab_job(
                        t1_roster_id=body.get("t1_roster_id"),
                        t1_paste_text=body.get("t1_paste_text"),
                        t2_roster_id=body.get("t2_roster_id"),
                        t2_paste_text=body.get("t2_paste_text"),
                        t2_user_spreads=body.get("t2_user_spreads"),
                        preset=str(body.get("preset") or "balanced"),
                        compute_mode=str(body.get("compute_mode") or "auto"),
                    )
                    self._send_json(res)
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            if path == "/api/lead-lab/cancel":
                cancelled = app_state.cancel_active_lead_stream()
                self._send_json({"ok": True, "cancelled": cancelled})
                return

            if path == "/api/lead-lab/lookup":
                try:
                    res = app_state.lookup_lead_lab_vault(
                        t1_roster_id=body.get("t1_roster_id"),
                        t1_paste_text=body.get("t1_paste_text"),
                        t2_roster_id=body.get("t2_roster_id"),
                        t2_paste_text=body.get("t2_paste_text"),
                        t2_user_spreads=body.get("t2_user_spreads"),
                        preset=str(body.get("preset") or "balanced"),
                    )
                    self._send_json(res)
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            if path == "/api/lead-lab/vault/tag":
                try:
                    run_id = str(body.get("run_id") or "").strip()
                    tags = str(body.get("tags") or "")
                    updated = app_state.ots_db.update_lead_lab_tags(run_id, tags)
                    self._send_json({"ok": updated, "run_id": run_id, "tags": tags.strip()[:240]})
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            if path == "/api/lead-lab/vault/delete":
                try:
                    run_id = str(body.get("run_id") or "").strip()
                    deleted = app_state.ots_db.delete_lead_lab_run(run_id)
                    self._send_json({"ok": deleted, "deleted": deleted, "run_id": run_id})
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            if path == "/api/lead-lab/deep-turn1":
                try:
                    res = app_state.run_lead_lab_deep_turn1(
                        job_id=str(body.get("job_id") or "").strip(),
                        mode_1_idx=int(body.get("mode_1_idx", 0)),
                        mode_2_idx=int(body.get("mode_2_idx", 0)),
                        num_mc=int(body.get("num_mc") or 128),
                        force_recompute=bool(body.get("force_recompute", False)),
                        lead_1=body.get("lead_1"),
                        bench_1=body.get("bench_1"),
                        lead_2=body.get("lead_2"),
                        bench_2=body.get("bench_2"),
                    )
                    self._send_json(res)
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            if path == "/api/lead-lab/deep-turn1-batch":
                try:
                    res = app_state.run_lead_lab_deep_turn1_batch(
                        job_id=str(body.get("job_id") or "").strip(),
                        pairs=body.get("pairs") or [],
                        num_mc=int(body.get("num_mc") or 128),
                        force_recompute=bool(body.get("force_recompute", False)),
                    )
                    self._send_json(res)
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            if path == "/api/telemetry/create-team":
                try:
                    res = app_state.create_telemetry_team(
                        team_folder=str(body.get("team_folder") or ""),
                    )
                    self._send_json(res)
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            if path == "/api/telemetry/export":
                try:
                    res = app_state.export_match_telemetry_csv(
                        team_folder=str(body.get("team_folder") or "my_team"),
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
