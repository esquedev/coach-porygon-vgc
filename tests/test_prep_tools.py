# -*- coding: utf-8 -*-
"""Comprehensive Unit & Integration Tests for Isolated Launchers, Windows `.exe`
Packaging, Zero-AI Offline Base64 Prep Tools (`src/engine/prep_tools/`), CLI,
and Replay Coach Studio Prep Tools API.

Strictly enforces Regulation M-C invariants:
  - Mandatory 31 IVs (never 0 IV)
  - 66 total SP / 32 max SP per single stat
  - Zero Terastallization
  - Legal DuckDB Reg M-C items only (no SV-only items)
  - All 5 Weathers (Clear/Sun/Rain/Sand/Snow) & all 5 Terrains (None/Elec/Grassy/Psychic/Misty)
  - Strict `trainer_1` / `trainer_2` naming convention
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import unittest

from apps.replay_coach import launcher_entry
from apps.replay_coach.server import ReplayCoachAppState
from engine.prep_tools import (
    build_damage_matrix_html,
    build_damage_matrix_payload,
    build_speed_tiers_html,
    build_speed_tiers_payload,
    calc_champions_hp,
    calc_champions_stat,
    get_top_n_meta_snapshot,
)
from scripts import build_windows_launcher, generate_prep_tools

REPO_ROOT = Path(__file__).resolve().parents[1]
CHAR_Y_PASTE_PATH = REPO_ROOT / "data" / "teams" / "char_y_v4.txt"

ILLEGAL_SV_ITEMS = {
    "Choice Band",
    "Choice Specs",
    "Assault Vest",
    "Clear Amulet",
    "Covert Cloak",
    "Booster Energy",
}

ALT_RAIN_ZMEGA_PASTE = """
Swampert @ Swampertite
Ability: Damp
Level: 50
Adamant Nature
EVs: 32 HP / 32 Atk / 2 Spe
- Waterfall
- Earthquake
- Ice Punch
- Protect

Politoed @ Sitrus Berry
Ability: Drizzle
Level: 50
Bold Nature
EVs: 32 HP / 20 Def / 14 SpD
- Weather Ball
- Icy Wind
- Helping Hand
- Protect

Sneasler @ Grassy Seed
Ability: Unburden
Level: 50
Jolly Nature
EVs: 2 HP / 32 Atk / 32 Spe
- Close Combat
- Dire Claw
- Fake Out
- Protect

Garchomp @ Garchompite Z
Ability: Rough Skin
Level: 50
Timid Nature
EVs: 2 HP / 32 SpA / 32 Spe
- Draco Meteor
- Earth Power
- Flamethrower
- Protect

Basculegion @ Choice Scarf
Ability: Adaptability
Level: 50
Jolly Nature
EVs: 2 HP / 32 Atk / 32 Spe
- Wave Crash
- Last Respects
- Flip Turn
- Aqua Jet

Armarouge @ Focus Sash
Ability: Flash Fire
Level: 50
Modest Nature
EVs: 2 HP / 32 SpA / 32 Spe
- Expanding Force
- Heat Wave
- Armor Cannon
- Protect
""".strip()


class TestPrepToolsAndLaunchers(unittest.TestCase):
    """End-to-end verification of zero-AI Prep Tools, Reg M-C legality, and launchers."""

    def test_01_meta_snapshot_legal_reg_mc_items_and_66sp_profiles(self) -> None:
        """DuckDB Top-50 snapshot enforces legal Reg M-C items, 31 IVs, and <= 66 SP bulk spreads."""
        snap = get_top_n_meta_snapshot(top_n=50)
        self.assertGreater(snap.total_teams, 5000)
        self.assertEqual(len(snap.entries), 50)

        species_names = {e.species for e in snap.entries}
        self.assertIn("Rillaboom", species_names)
        self.assertIn("Raichu-Mega-Y", species_names)
        self.assertIn("Garchomp-Mega-Z", species_names)
        self.assertIn("Floette-Mega", species_names)

        for entry in snap.entries:
            # Strict Anti-Hallucination check: zero illegal SV items
            self.assertNotIn(entry.top_item, ILLEGAL_SV_ITEMS)
            self.assertNotIn(entry.default_item, ILLEGAL_SV_ITEMS)
            for item_row in entry.top_items:
                self.assertNotIn(item_row["name"], ILLEGAL_SV_ITEMS)

            # Strict 31-IV Level 50 speed formulas (no 0 IV leakage!)
            b_spe = entry.base_stats["spe"]
            self.assertEqual(entry.speeds["minus0"], calc_champions_stat(b_spe, 0, 0.9))
            self.assertEqual(entry.speeds["neu0"], calc_champions_stat(b_spe, 0, 1.0))
            self.assertEqual(entry.speeds["neu32"], calc_champions_stat(b_spe, 32, 1.0))
            self.assertEqual(entry.speeds["plus32"], calc_champions_stat(b_spe, 32, 1.1))

            # Strict <= 66 SP & <= 32 single-stat invariant on all 7 legal bulk profiles
            self.assertEqual(
                set(entry.profiles.keys()),
                {"min0", "hp32", "bal", "balDef", "balSpd", "maxDef", "maxSpd"},
            )
            for prof in entry.profiles.values():
                self.assertGreaterEqual(prof.hp_sp, 0)
                self.assertLessEqual(prof.hp_sp, 32)
                self.assertGreaterEqual(prof.def_sp, 0)
                self.assertLessEqual(prof.def_sp, 32)
                self.assertGreaterEqual(prof.spd_sp, 0)
                self.assertLessEqual(prof.spd_sp, 32)
                self.assertLessEqual(prof.hp_sp + prof.def_sp + prof.spd_sp, 66)
                self.assertEqual(prof.hp, calc_champions_hp(entry.base_stats["hp"], prof.hp_sp))

        # Verify Grassy Seed detection on Volcarona / Sneasler
        by_sp = {e.species: e for e in snap.entries}
        self.assertEqual(by_sp["Volcarona"].terrain_seed, "Grassy Seed")
        self.assertEqual(by_sp["Volcarona"].terrain_seed_terrain, "grassy")
        self.assertEqual(by_sp["Volcarona"].terrain_seed_stat, "def")

    def test_02_speed_tiers_dynamic_any_team_no_hardcoding(self) -> None:
        """Speed Tiers adapts dynamically to any Reg M-C team (Sun vs. Rain/Unburden/Z-Mega)."""
        # Team A: char_y_v4 (Sun Chlorophyll + Charizard-Mega-Y + Raichu-Mega-X)
        char_paste = CHAR_Y_PASTE_PATH.read_text(encoding="utf-8")
        p_char = build_speed_tiers_payload(char_paste, team_name="char_y_v4", top_n=50)
        mod_keys_a = [b["key"] for b in p_char.data["teamModButtons"]]
        self.assertEqual(mod_keys_a, ["sun"])
        self.assertIn("Venusaur", p_char.data["teamModButtons"][0]["holders"])

        by_sp_a = {m["species"]: m for m in p_char.data["trainer1Team"]}
        self.assertIn("Charizard-Mega-Y", by_sp_a)
        self.assertIn("Raichu-Mega-X", by_sp_a)
        self.assertEqual(by_sp_a["Raichu-Mega-X"]["mega"]["speed"], 178)
        self.assertEqual(by_sp_a["Garchomp"]["base"]["speed"], 169)
        self.assertEqual(by_sp_a["Charizard-Mega-Y"]["mega"]["speed"], 141)
        self.assertEqual(by_sp_a["Venusaur"]["base"]["speed"], 132)

        # Team B: Custom Rain + Unburden + Garchomp-Mega-Z + Choice Scarf Basculegion
        p_rain = build_speed_tiers_payload(ALT_RAIN_ZMEGA_PASTE, team_name="Rain Z-Chomp", top_n=35)
        mod_keys_b = {b["key"] for b in p_rain.data["teamModButtons"]}
        self.assertIn("rain", mod_keys_b)
        self.assertIn("unburden", mod_keys_b)
        self.assertNotIn("sun", mod_keys_b)

        by_sp_b = {m["species"]: m for m in p_rain.data["trainer1Team"]}
        self.assertIn("Garchomp-Mega-Z", by_sp_b)
        self.assertEqual(by_sp_b["Garchomp-Mega-Z"]["mega"]["baseSpe"], 151)
        self.assertEqual(by_sp_b["Garchomp-Mega-Z"]["mega"]["speed"], 223)
        self.assertEqual(by_sp_b["Garchomp-Mega-Z"]["base"]["speed"], 169)
        self.assertTrue(by_sp_b["Basculegion"]["hasScarf"])
        self.assertEqual(by_sp_b["Basculegion"]["base"]["rawSpeed"], 143)
        self.assertEqual(by_sp_b["Basculegion"]["base"]["speed"], 214)

    def test_03_damage_matrix_all_5_weathers_5_terrains_and_seeds_exact(self) -> None:
        """Pre-computed SmogonChampionsCalc LUT captures Snow, Sand, Misty, Grassy Seed, and Spread/Single."""
        char_paste = CHAR_Y_PASTE_PATH.read_text(encoding="utf-8")
        payload = build_damage_matrix_payload(char_paste, team_name="char_y_v4", top_n=50)
        self.assertGreater(payload.calc_count, 5000)
        self.assertGreater(payload.unique_roll_arrays, 100)

        data = payload.data
        pool = data["rollPool"]
        lut = data["calcLut"]
        def_idx_by_sp = {d["species"]: i for i, d in enumerate(data["defenders"])}

        def _get_rolls(fm_key: str, sp: str, prof: str, env_key: str) -> list[int]:
            entry = lut[fm_key][def_idx_by_sp[sp]][prof]
            if isinstance(entry, int):
                return pool[entry]
            rid = entry.get(env_key, entry["_"])
            return pool[rid]

        # 1. Snow 1.5x Def on Ice types (Garchomp Rock Slide vs Froslass-Mega)
        rs_clear = _get_rolls("base:garchomp_2_rockslide", "Froslass-Mega", "min0", "none|none|0|0")
        rs_snow = _get_rolls("base:garchomp_2_rockslide", "Froslass-Mega", "min0", "snow|none|0|0")
        self.assertGreater(rs_clear[0], 0)
        self.assertLess(rs_snow[15], rs_clear[0])

        # 2. Sand 1.5x SpD on Rock types (Charizard-Mega-Y Heat Wave vs Tyranitar-Mega)
        hw_clear = _get_rolls("mega:charizard_0_heatwave", "Tyranitar-Mega", "min0", "none|none|0|0")
        hw_sand = _get_rolls("mega:charizard_0_heatwave", "Tyranitar-Mega", "min0", "sand|none|0|0")
        self.assertGreater(hw_clear[0], 0)
        self.assertLess(hw_sand[15], hw_clear[0])

        # 3. Weather Ball in Snow (Pelipper Weather Ball -> 100 BP Ice 4x vs Garchomp)
        wb_clear = _get_rolls("base:pelipper_4_weatherball", "Garchomp", "min0", "none|none|0|0")
        wb_snow = _get_rolls("base:pelipper_4_weatherball", "Garchomp", "min0", "snow|none|0|0")
        self.assertGreater(wb_snow[0], wb_clear[15] * 4)

        # 4. Misty Terrain 0.5x Dragon on grounded Rillaboom (Garchomp Dragon Claw)
        dc_none = _get_rolls("base:garchomp_2_dragonclaw", "Rillaboom", "min0", "none|none|0|0")
        dc_misty = _get_rolls("base:garchomp_2_dragonclaw", "Rillaboom", "min0", "none|misty|0|0")
        self.assertGreater(dc_none[0], 0)
        self.assertLess(dc_misty[15], dc_none[0] * 0.65)

        # 5. Grassy Seed +1 Def on Sneasler (Garchomp Dragon Claw in Grassy Terrain)
        dc_sneasler_no_seed = _get_rolls("base:garchomp_2_dragonclaw", "Sneasler", "min0", "none|grassy|0|0")
        dc_sneasler_seed = _get_rolls("base:garchomp_2_dragonclaw", "Sneasler", "min0", "none|grassy|0|1")
        self.assertGreater(dc_sneasler_no_seed[0], dc_sneasler_seed[15])

        # 6. Spread (0.75x) vs Single-Target (1.0x) on Heat Wave
        hw_spread = _get_rolls("mega:charizard_0_heatwave", "Rillaboom", "min0", "none|none|0|0")
        hw_single = _get_rolls("mega:charizard_0_heatwave", "Rillaboom", "min0", "none|none|1|0")
        self.assertGreater(hw_single[0], hw_spread[15])

    def test_04_offline_html_rendering_self_contained_and_syntax_valid(self) -> None:
        """Both offline HTML reports have zero CDN refs, embedded Base64 sprites, zero Tera, valid JS."""
        char_paste = CHAR_Y_PASTE_PATH.read_text(encoding="utf-8")
        speed_html, _ = build_speed_tiers_html(char_paste, team_name="char_y_v4", top_n=20, lang="es")
        dmg_html, _ = build_damage_matrix_html(char_paste, team_name="char_y_v4", top_n=20, lang="en")

        esbuild_bin = Path("/tmp/esbuild-bin/package/bin/esbuild")
        for label, doc in (("speed_es", speed_html), ("damage_en", dmg_html)):
            lower = doc.lower()
            self.assertNotIn("<script src=", lower, msg=f"External script in {label}")
            self.assertNotIn("<link ", lower, msg=f"External link in {label}")
            self.assertNotIn("terastalliz", lower, msg=f"Forbidden Tera reference in {label}")
            self.assertIn("data:image/png;base64,", doc, msg=f"Missing Base64 sprites in {label}")

            m = re.search(r"<script>(.*)</script>", doc, re.S)
            self.assertIsNotNone(m, msg=f"Missing inline script in {label}")
            js_src = m.group(1)  # type: ignore[union-attr]
            if esbuild_bin.is_file():
                with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as tf:
                    tf.write(js_src)
                    tmp_js = Path(tf.name)
                try:
                    proc = subprocess.run(
                        [str(esbuild_bin), str(tmp_js), "--bundle=false", "--outfile=/dev/null"],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(proc.returncode, 0, msg=f"esbuild JS error in {label}: {proc.stderr}")
                finally:
                    tmp_js.unlink(missing_ok=True)

    def test_05_cli_generate_prep_tools_end_to_end(self) -> None:
        """Headless CLI writes both standalone Base64 HTML reports cleanly."""
        with tempfile.TemporaryDirectory() as td:
            rc = generate_prep_tools.main(
                [
                    "--team",
                    str(CHAR_Y_PASTE_PATH),
                    "--name",
                    "LAIC Test",
                    "--top-n",
                    "20",
                    "--lang",
                    "es",
                    "--out-dir",
                    td,
                ]
            )
            self.assertEqual(rc, 0)
            out_dir = Path(td)
            speed_file = out_dir / "speed_tiers_laic_test_top20_mobile.html"
            dmg_file = out_dir / "damage_calcs_laic_test_top20_mobile.html"
            self.assertTrue(speed_file.is_file())
            self.assertTrue(dmg_file.is_file())
            self.assertGreater(speed_file.stat().st_size, 100_000)
            self.assertGreater(dmg_file.stat().st_size, 100_000)

    def test_06_launchers_and_windows_exe_builder_validation(self) -> None:
        """Isolated .venv bash/bat launchers, launcher_entry.py, icon builder, and GH workflow are valid."""
        sh_path = REPO_ROOT / "start_replay_coach.sh"
        bat_path = REPO_ROOT / "start_replay_coach.bat"
        wf_path = REPO_ROOT / ".github" / "workflows" / "build-windows-launcher.yml"

        self.assertTrue(sh_path.is_file())
        self.assertTrue(os.access(sh_path, os.X_OK), msg="start_replay_coach.sh must be executable")
        bash_chk = subprocess.run(["bash", "-n", str(sh_path)], capture_output=True, text=True, check=False)
        self.assertEqual(bash_chk.returncode, 0, msg=f"bash -n failed: {bash_chk.stderr}")

        sh_txt = sh_path.read_text(encoding="utf-8")
        self.assertIn('source ".venv/bin/activate"', sh_txt)
        self.assertIn("py_mini_racer", sh_txt)
        self.assertIn(".requirements.sha256", sh_txt)

        bat_txt = bat_path.read_text(encoding="utf-8")
        self.assertIn(r'call ".venv\Scripts\activate.bat"', bat_txt)
        self.assertIn("py_mini_racer", bat_txt)
        self.assertIn(".requirements.sha256", bat_txt)

        self.assertTrue(wf_path.is_file())
        self.assertIn("windows-latest", wf_path.read_text(encoding="utf-8"))

        # Test launcher_entry pure helpers
        found_root = launcher_entry.find_repo_root(REPO_ROOT)
        self.assertEqual(found_root, REPO_ROOT)
        req_hash = launcher_entry.compute_requirements_hash(REPO_ROOT / "requirements.txt")
        self.assertEqual(len(req_hash), 64)
        parsed_args = launcher_entry.build_arg_parser().parse_args(["--port", "9100", "--no-browser"])
        self.assertEqual(parsed_args.port, 9100)
        self.assertTrue(parsed_args.no_browser)

        # Test pure-stdlib ICO generation
        with tempfile.TemporaryDirectory() as td:
            ico_file = build_windows_launcher.generate_coach_icon(Path(td) / "test.ico")
            raw = ico_file.read_bytes()
            reserved, ico_type, count = struct.unpack("<HHH", raw[:6])
            self.assertEqual((reserved, ico_type, count), (0, 1, 4))

    def test_07_studio_prep_tools_api_and_caching(self) -> None:
        """ReplayCoachAppState.generate_prep_tool serves live & cached offline Base64 HTMLs."""
        with tempfile.TemporaryDirectory() as td:
            app_state = ReplayCoachAppState(
                preload_sample=False,
                db_path=Path(td) / "ots_test.duckdb",
                device="cpu",
            )
            try:
                res1 = app_state.generate_prep_tool(
                    kind="speed_tiers",
                    roster_id="treces_gc_char_y_v4",
                    top_n=20,
                    lang="es",
                )
                self.assertTrue(res1["ok"])
                self.assertFalse(res1["cached"])
                self.assertGreater(res1["size_kb"], 100.0)
                cached_doc = app_state.get_prep_tool_cached(res1["token"])
                self.assertIsNotNone(cached_doc)
                assert cached_doc is not None
                self.assertIn(b"data:image/png;base64,", cached_doc["html_bytes"])

                # Second identical call hits in-memory cache immediately
                res2 = app_state.generate_prep_tool(
                    kind="speed_tiers",
                    roster_id="treces_gc_char_y_v4",
                    top_n=20,
                    lang="es",
                )
                self.assertTrue(res2["cached"])
                self.assertEqual(res2["token"], res1["token"])

                # Inline custom 66-SP paste Damage Matrix generation
                res3 = app_state.generate_prep_tool(
                    kind="damage_matrix",
                    paste_text=ALT_RAIN_ZMEGA_PASTE,
                    team_name="Rain Z-Chomp",
                    top_n=20,
                    lang="en",
                )
                self.assertTrue(res3["ok"])
                self.assertGreater(res3["calc_count"], 1000)
                cached_dmg = app_state.get_prep_tool_cached(res3["token"])
                self.assertIsNotNone(cached_dmg)
                assert cached_dmg is not None
                self.assertIn(b"Garchomp-Mega-Z", cached_dmg["html_bytes"])
            finally:
                app_state.ots_db.conn.close()


if __name__ == "__main__":
    unittest.main()
