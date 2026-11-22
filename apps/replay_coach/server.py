# -*- coding: utf-8 -*-
"""Zero-Dependency Local HTTP/SSE Server for the Coach Porygon VGC Replay Coach MVP.

Serves the standalone GUI, embeds the official Pokémon Showdown `replay-embed.js`
battle graphics engine inside a synchronized player frame, manages the persistent
DuckDB OTS + EVs/SPs database, and streams live GPU Tensor Core Nash/IEDS turn
audits over Server-Sent Events (SSE).
"""
from __future__ import annotations

import argparse
import html as html_lib
import json
import mimetypes
import threading
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

from .gpu_coach_engine import GPUReplayCoachEngine
from .ots_db import OTSRosterDatabase
from .protocol_parser import ParsedReplay, parse_showdown_replay

APP_ROOT = Path(__file__).resolve().parent
STATIC_DIR = APP_ROOT / "static"
VENDOR_DIR = APP_ROOT / "vendor"
SAMPLE_REPLAY_PATH = APP_ROOT / "sample_data" / "matchagotme_g1.html"


class ReplayCoachAppState:
    """Thread-safe container holding the warm GPU engine, DuckDB OTS store, and active replay."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.ots_db = OTSRosterDatabase()
        self.gpu_engine = GPUReplayCoachEngine(self.ots_db)
        self.raw_replay_html: str = ""
        self.pov_trainer: str = "treces_gc"
        self.t1_roster_id: Optional[str] = None
        self.t2_roster_id: Optional[str] = None
        self.replay: Optional[ParsedReplay] = None

        if SAMPLE_REPLAY_PATH.exists():
            self.load_replay(
                raw_input=SAMPLE_REPLAY_PATH.read_text(encoding="utf-8"),
                pov_trainer="treces_gc",
            )

    def load_replay(
        self,
        raw_input: str,
        pov_trainer: Optional[str] = None,
        t1_roster_id: Optional[str] = None,
        t2_roster_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Parse replay, auto-match (or bind explicit) DuckDB OTS rosters, and store active state."""
        with self.lock:
            prelim = parse_showdown_replay(raw_input, pov_trainer=pov_trainer or self.pov_trainer)
            r1 = (
                self.ots_db.get_roster(t1_roster_id)
                if t1_roster_id
                else self.ots_db.match_best_roster(prelim.trainer_1_name, prelim.trainer_1_preview)
            )
            r2 = (
                self.ots_db.get_roster(t2_roster_id)
                if t2_roster_id
                else self.ots_db.match_best_roster(prelim.trainer_2_name, prelim.trainer_2_preview)
            )
            t1_sets = self.ots_db.get_parsed_sets_by_species(r1["paste_text"]) if r1 else {}
            t2_sets = self.ots_db.get_parsed_sets_by_species(r2["paste_text"]) if r2 else {}

            parsed = parse_showdown_replay(
                raw_input,
                pov_trainer=pov_trainer or prelim.trainer_1_name,
                trainer_1_ots_sets=t1_sets,
                trainer_2_ots_sets=t2_sets,
            )
            self.raw_replay_html = raw_input
            self.pov_trainer = parsed.trainer_1_name
            self.t1_roster_id = r1["roster_id"] if r1 else None
            self.t2_roster_id = r2["roster_id"] if r2 else None
            self.replay = parsed
            return self.get_state_summary_unlocked()

    def get_state_summary_unlocked(self) -> Dict[str, Any]:
        """Serialize current replay metadata, matched rosters, and GPU hardware info."""
        rep = self.replay
        return {
            "device": self.gpu_engine.device_name,
            "has_vendor_showdown": (VENDOR_DIR / "replay-embed.js").exists(),
            "rosters": self.ots_db.list_rosters(),
            "active_t1_roster_id": self.t1_roster_id,
            "active_t2_roster_id": self.t2_roster_id,
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
                "trainer_1_preview": rep.trainer_1_preview,
                "trainer_2_preview": rep.trainer_2_preview,
                "trainer_1_brought": rep.trainer_1_brought,
                "trainer_2_brought": rep.trainer_2_brought,
                "turn_numbers": [t.turn_number for t in rep.turns],
            },
        }

    def render_official_showdown_player_html(self) -> str:
        """Render the embedded official Pokémon Showdown replay player with postMessage turn sync."""
        rep = self.replay
        if rep is None:
            return "<!doctype html><html><body style='background:#111;color:#ccc;font-family:sans-serif;padding:24px'>No replay loaded.</body></html>"

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
      window.parent.postMessage({{ type: 'TURN_CHANGED', turn: turnVal }}, '*');
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
    // Jump to Turn 1 cleanly on initial load so both leads are immediately visible
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
        battle.pause();
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
            # Keep server stdout concise
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
            safe_rel = rel_path.lstrip("/")
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
            if path == "/api/state":
                with app_state.lock:
                    summary = app_state.get_state_summary_unlocked()
                self._send_json(summary)
                return
            if path == "/api/rosters":
                self._send_json({"rosters": app_state.ots_db.list_rosters()})
                return
            if path == "/api/replay-player":
                with app_state.lock:
                    html_doc = app_state.render_official_showdown_player_html()
                self._send_bytes(html_doc.encode("utf-8"), "text/html; charset=utf-8")
                return
            if path == "/api/analyze/turn":
                try:
                    turn_num = int(qs.get("turn", ["1"])[0])
                    min_prior = float(qs.get("min_prior", ["0.55"])[0])
                    num_mc = int(qs.get("num_mc", ["128"])[0])
                    force = qs.get("force", ["0"])[0] in ("1", "true", "yes")
                    with app_state.lock:
                        rep = app_state.replay
                    if rep is None:
                        self._send_json({"error": "No replay loaded"}, status=HTTPStatus.BAD_REQUEST)
                        return
                    result = app_state.gpu_engine.analyze_turn(
                        rep,
                        turn_number=turn_num,
                        min_prior=min_prior,
                        num_mc=num_mc,
                        force_recompute=force,
                    )
                    self._send_json(result)
                except Exception as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            if path == "/api/analyze/stream":
                min_prior = float(qs.get("min_prior", ["0.55"])[0])
                num_mc = int(qs.get("num_mc", ["128"])[0])
                force = qs.get("force", ["0"])[0] in ("1", "true", "yes")
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

                for snap in rep.turns:
                    try:
                        res = app_state.gpu_engine.analyze_turn(
                            rep,
                            turn_number=snap.turn_number,
                            min_prior=min_prior,
                            num_mc=num_mc,
                            force_recompute=force,
                        )
                        msg = f"event: turn\ndata: {json.dumps(res, ensure_ascii=False)}\n\n"
                        self.wfile.write(msg.encode("utf-8"))
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        return
                    except Exception as exc:
                        err = f"event: error\ndata: {json.dumps({'turn': snap.turn_number, 'error': str(exc)})}\n\n"
                        self.wfile.write(err.encode("utf-8"))
                        self.wfile.flush()
                try:
                    self.wfile.write(b"event: done\ndata: {}\n\n")
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
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

            if path == "/api/replay/load":
                raw_html = str(body.get("raw_input") or "")
                if not raw_html.strip():
                    with app_state.lock:
                        raw_html = app_state.raw_replay_html
                try:
                    summary = app_state.load_replay(
                        raw_input=raw_html,
                        pov_trainer=body.get("pov_trainer"),
                        t1_roster_id=body.get("t1_roster_id"),
                        t2_roster_id=body.get("t2_roster_id"),
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

            if path == "/api/rosters":
                try:
                    saved = app_state.ots_db.save_roster(
                        roster_id=str(body.get("roster_id") or "").strip(),
                        display_name=str(body.get("display_name") or "").strip(),
                        trainer_hint=str(body.get("trainer_hint") or "").strip(),
                        paste_text=str(body.get("paste_text") or ""),
                    )
                    # Re-bind active replay so updated spreads take effect immediately
                    with app_state.lock:
                        raw_cur = app_state.raw_replay_html
                        pov_cur = app_state.pov_trainer
                        r1_cur = app_state.t1_roster_id
                        r2_cur = app_state.t2_roster_id
                    if raw_cur:
                        app_state.load_replay(raw_cur, pov_cur, r1_cur, r2_cur)
                    self._send_json({"saved": saved, "rosters": app_state.ots_db.list_rosters()})
                except Exception as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    return CoachHTTPHandler


def main() -> None:
    parser = argparse.ArgumentParser(description="Coach Porygon VGC — Standalone Replay Coach GUI")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765)")
    args = parser.parse_args()

    print("[Coach Porygon VGC] Initializing GPU Tensor Core & DuckDB OTS Registry...", flush=True)
    app_state = ReplayCoachAppState()
    print(
        f"[Coach Porygon VGC] Ready on {app_state.gpu_engine.device_name} -> "
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
