# -*- coding: utf-8 -*-
"""Verification tests for Tactical HUD language separation, live JS LQRE Beta parity,
LAIC 2027 DuckDB ingestion, community emblems, Regulation M-D Base64 HTML, and SVG docs.
"""
from __future__ import annotations

from pathlib import Path
import re
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from apps.replay_coach.commentary_engine import generate_all_commentary_variants
from engine.db_registry import get_registry
from engine.solver.game_theory import solve_quantal_response
from engine.terminology import TERM_GLOSSARY, export_glossary_payload

REPO_ROOT = Path(__file__).resolve().parent.parent

VGC_FORBIDDEN_JARGON = (
    "IEDS",
    "Nash",
    "LQRE",
    "QRE",
    "CVaR",
    "Minimax",
    "U_risk",
)


def test_vgc_register_zero_academic_jargon() -> None:
    """Ensure `es_vgc` and `en_vgc` commentary & terminology labels never leak academic jargon."""
    actual = {
        "choice_pair": [1, 2],
        "desc": "Charizard Heat Wave + Rillaboom Fake Out",
        "risk_ev": 0.42,
        "cvar10": 0.15,
        "nash_pct": 18.0,
        "qre_pct": 22.0,
        "nash_regret": 0.14,
        "security_floor": -0.25,
        "worst_counter_desc": "Incineroar Fake Out + Garchomp Rock Slide",
        "strict_dominated_by": None,
        "weak_dominated_by": None,
        "flinched_hidden": False,
        "num_mc": 128,
        "ko_probs_vs_actual_opp": {"Incineroar": 45.0},
    }
    best = dict(actual, choice_pair=[3, 4], desc="Charizard Protect + Rillaboom Grassy Glide", risk_ev=0.56, nash_pct=65.0)
    variants = generate_all_commentary_variants(
        turn_number=2,
        actual_action=actual,
        top_actions=[best, actual],
        nash_value=0.56,
        ieds_summary={"t1_total": 24, "t1_strict": 8, "t1_weak": 6, "strict_rounds": 2},
        events={"crits": [], "misses": [], "flinches": []},
        field_context={"weather": "sun", "trick_room_turns": 0},
        equity_breakdown={
            "nash_pillars": {"material": 0.35, "field_tempo": 0.21, "two_turn_prime": 0.08},
            "top_drivers": [{"pillar": "material", "value": 0.35}],
        },
    )

    for key in ("es_vgc", "en_vgc"):
        block = variants[key]
        joined = " ".join(
            [block["badge"], block["headline"]]
            + [b["tag"] + " " + b["text"] for b in block["bullets"]]
        )
        for bad in VGC_FORBIDDEN_JARGON:
            assert not re.search(rf"\b{re.escape(bad)}\b", joined), (
                f"Jargon '{bad}' leaked into {key}: {joined}"
            )

    payload = export_glossary_payload()
    assert "terms" in payload and "qre_beta" in TERM_GLOSSARY
    for term_key, lang_map in TERM_GLOSSARY.items():
        for lang in ("es", "en"):
            vgc_entry = lang_map[lang]["vgc"]
            txt = f"{vgc_entry['label']} {vgc_entry['short']} {vgc_entry['desc']}"
            for bad in VGC_FORBIDDEN_JARGON:
                assert not re.search(rf"\b{re.escape(bad)}\b", txt), (
                    f"Jargon '{bad}' leaked into TERM_GLOSSARY[{term_key}][{lang}][vgc]: {txt}"
                )


def test_client_js_lqre_matches_python_across_betas() -> None:
    """Verify the browser JS `solveLogitQreClient(U, beta)` matches Python `solve_quantal_response`."""
    py_mini_racer = pytest.importorskip("py_mini_racer")
    js_src = (REPO_ROOT / "apps" / "replay_coach" / "static" / "app.js").read_text(encoding="utf-8")
    m = re.search(
        r"(function _stableSoftmax\(logits\).*?window\.__porygonSolveLogitQre = solveLogitQreClient;)",
        js_src,
        re.DOTALL,
    )
    assert m is not None, "Could not locate solveLogitQreClient in app.js"
    ctx = py_mini_racer.MiniRacer()
    ctx.eval("var window = {}; " + m.group(1))

    payoff = np.array(
        [
            [0.65, -0.20, 0.15, 0.40],
            [-0.10, 0.55, 0.30, -0.35],
            [0.25, 0.10, -0.05, 0.50],
        ],
        dtype=np.float64,
    )
    for beta in (0.5, 1.0, 4.0, 8.0, 16.0):
        py_res = solve_quantal_response(payoff, rationality_beta=beta)
        js_res = ctx.call("window.__porygonSolveLogitQre", payoff.tolist(), beta)
        p_js = np.asarray(js_res["p"], dtype=np.float64)
        q_js = np.asarray(js_res["q"], dtype=np.float64)
        assert np.max(np.abs(p_js - py_res.trainer_1_strategy)) < 1e-4, f"trainer_1 mismatch at beta={beta}"
        assert np.max(np.abs(q_js - py_res.trainer_2_strategy)) < 1e-4, f"trainer_2 mismatch at beta={beta}"
        assert abs(float(js_res["expected_value"]) - float(py_res.expected_value)) < 1e-4


def test_laic_2027_ingested_in_duckdb() -> None:
    """Verify LAIC 2027 (`LA002-m593TW3lr3apWb`) is present and queryable in DuckDB."""
    reg = get_registry()
    rows = reg.query(
        """
        SELECT tournament_id, COUNT(DISTINCT player_name) AS n_players
        FROM tournament_team_slots
        GROUP BY tournament_id
        """
    )
    by_tid = {r["tournament_id"]: int(r["n_players"]) for r in rows}
    assert len(by_tid) >= 9, f"Expected >= 9 ingested tournaments, found {len(by_tid)}"
    laic_slug = "2027_latin_america_pok_mon_vgc_international_championships"
    assert laic_slug in by_tid, "LAIC 2027 tournament missing from DuckDB"
    assert by_tid[laic_slug] >= 600


def test_community_emblems_md_scout_html_and_svgs() -> None:
    """Verify community logos, standalone Regulation M-D Base64 HTML, and all 3 native SVGs."""
    for fname in ("pokemmunity.png", "pokemex.png"):
        p = REPO_ROOT / "assets" / "community" / fname
        assert p.is_file() and p.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

    scout_html = REPO_ROOT / "reports" / "reg_md_meta_scout.html"
    assert scout_html.is_file()
    content = scout_html.read_text(encoding="utf-8")
    assert content.count("data:image/png;base64,") >= 50
    assert 'src=""' not in content
    assert "CONFIRMED M-D" in content and "RUMORED / UNCONFIRMED" in content
    assert "Pokémmunity" in content and "PokéMex" in content

    for svg_name in ("tensor_anatomy.svg", "switch_intimidate_op.svg", "architecture_pipeline.svg"):
        svg_path = REPO_ROOT / "docs" / "images" / svg_name
        assert svg_path.is_file(), f"Missing {svg_name}"
        root = ET.fromstring(svg_path.read_text(encoding="utf-8"))
        assert root.tag.endswith("svg")
