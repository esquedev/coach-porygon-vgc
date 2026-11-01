#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — SOLID Data Access & Repository Layer
Implements Repository Pattern (SRP, OCP, LSP, ISP, DIP) for persistent competitive data.

Provides:
- Data Transfer Objects (DTOs) with field validation and sanitization against CWE-1236 (Formula Injection).
- Abstract Repository Interfaces (IMatchRepository, IDiagnosticsRepository, ITeamRepository, IDamageCalcRepository).
- Robust CSV implementations (CsvMatchRepository, CsvDiagnosticsRepository, CsvTeamRepository, CsvDamageCalcRepository).
- In-memory test implementations for lightning-fast, side-effect-free unit testing.
"""

from abc import ABC, abstractmethod
import csv
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

# Safe signed number regex (e.g., "-18.0", "+2 SpA", "-1 boost")
_SAFE_SIGNED_PREFIX_RE = re.compile(r"^[+-]\d+(\.\d+)?(\s|$)")


def sanitize_csv_cell(val: Any) -> Any:
    """
    Sanitizes string inputs to prevent CSV Injection / Formula Injection (CWE-1236).
    Prepends a single quote if string starts with dangerous spreadsheet formula triggers:
    '=', '+', '-', '@', tab, or carriage return.
    """
    if val is None:
        return ""
    if not isinstance(val, str):
        return val
    if not val:
        return ""

    first_char = val[0]
    if first_char in ("=", "@", "\t", "\r"):
        return f"'{val}"
    if first_char in ("+", "-"):
        s = val.strip()
        if _SAFE_SIGNED_PREFIX_RE.match(s):
            return s
        return f"'{val}"
    return val.strip()


def get_excel_serial_timestamp(dt: Optional[datetime] = None) -> float:
    """Computes Showdown-compatible Excel serial date timestamp."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    excel_epoch = datetime(1899, 12, 30, tzinfo=timezone.utc)
    delta = dt - excel_epoch
    serial_val = delta.total_seconds() / 86400.0
    return round(serial_val, 4)


# ============================================================================
# ABSTRACT REPOSITORY INTERFACES (Interface Segregation & Dependency Inversion)
# ============================================================================

class IMatchRepository(ABC):
    """Abstract contract for match telemetry persistence."""

    @abstractmethod
    def log_match(self, match_data: Dict[str, Any]) -> Dict[str, Any]:
        """Append personal match record with Excel timestamp and sanitized cells."""
        pass

    @abstractmethod
    def get_all_matches(self) -> List[Dict[str, Any]]:
        """Retrieve all recorded match rows from disk."""
        pass

    @abstractmethod
    def get_next_id(self) -> float:
        """Compute next sequential floating-point match identifier."""
        pass


class IDiagnosticsRepository(ABC):
    """Abstract contract for playstyle mistake diagnostics persistence."""

    @abstractmethod
    def log_diagnostic(self, diag_data: Dict[str, Any]) -> Dict[str, Any]:
        """Log tactical misplay code, cognitive driver, and recovery lesson."""
        pass

    @abstractmethod
    def get_all_diagnostics(self) -> List[Dict[str, Any]]:
        """Retrieve all recorded diagnostic misplay rows."""
        pass


class ITeamRepository(ABC):
    """Abstract contract for 66-SP team roster persistence."""

    @abstractmethod
    def register_team(self, team_data: Dict[str, Any]) -> str:
        """Register a 6-mon team roster with Showdown export paste."""
        pass

    @abstractmethod
    def get_all_teams(self) -> List[Dict[str, Any]]:
        """Retrieve all registered team rosters."""
        pass

    @abstractmethod
    def get_next_team_id(self) -> str:
        """Generate next sequential team code (e.g., T01, T02)."""
        pass


class IDamageCalcRepository(ABC):
    """Abstract contract for damage calculation benchmark persistence."""

    @abstractmethod
    def log_calculation(self, calc_data: Dict[str, Any]) -> Dict[str, Any]:
        """Persist official VGC damage calculation benchmark."""
        pass

    @abstractmethod
    def get_all_calculations(self) -> List[Dict[str, Any]]:
        """Retrieve all stored damage calculation benchmarks."""
        pass


# ============================================================================
# CSV REPOSITORY IMPLEMENTATIONS (Single Responsibility & Persistence Details)
# ============================================================================

class CsvMatchRepository(IMatchRepository):
    """CSV persistent storage for match telemetry (Raw_Matches.csv)."""

    HEADERS = [
        "Timestamp", "Match_ID", "Team_ID", "Opponent", "Start_Rating", "End_Rating",
        "Net_Rating", "Result", "Turns", "Enemy_Archetype", "User_Mega", "Enemy_Mega",
        "User_Lead_1", "User_Lead_2", "User_Back_1", "User_Back_2", "Enemy_Lead_1",
        "Enemy_Lead_2", "Speed_Control_Active", "First_Blood_Side", "MVP_Pokemon",
        "MVP_Move", "Misplay_Type", "Key_RNG_Event", "Core_Lesson", "Commentary"
    ]

    def __init__(self, csv_path: Optional[Path] = None):
        self.csv_path = Path(csv_path) if csv_path else (DATA_DIR / "Raw_Matches.csv")

    def _ensure_file(self):
        """Ensure target CSV file exists and write header columns if empty."""
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.csv_path.exists() or self.csv_path.stat().st_size == 0:
            with open(self.csv_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(self.HEADERS)

    def get_next_id(self) -> float:
        """Compute next sequential numeric identifier for match records."""
        self._ensure_file()
        max_id = 0.0
        with open(self.csv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if len(row) > 1 and row[1].strip():
                    try:
                        max_id = max(max_id, float(row[1]))
                    except ValueError:
                        continue
        return max_id + 1.0

    def log_match(self, match_data: Dict[str, Any]) -> Dict[str, Any]:
        """Persist match record row with Excel timestamp and sanitized cells."""
        self._ensure_file()
        record = dict(match_data)
        if "Match_ID" not in record or not record["Match_ID"]:
            record["Match_ID"] = self.get_next_id()
        if "Timestamp" not in record or not record["Timestamp"]:
            record["Timestamp"] = get_excel_serial_timestamp()

        # Sanitize and write
        row_values = [sanitize_csv_cell(record.get(col, "")) for col in self.HEADERS]
        with open(self.csv_path, "a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(row_values)

        return record

    def get_all_matches(self) -> List[Dict[str, Any]]:
        """Retrieve all recorded match rows from disk."""
        self._ensure_file()
        records = []
        with open(self.csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                records.append(dict(r))
        return records


class CsvDiagnosticsRepository(IDiagnosticsRepository):
    """CSV persistent storage for tactical diagnostics (Playstyle_Diagnostics.csv)."""

    HEADERS = [
        "Timestamp", "Match_ID", "Format_Type", "Series_Game", "Team_ID",
        "Opponent_Archetype", "Risk_Profile", "Decision_Pacing", "Mistake_Domain",
        "Mistake_Code", "Turn_Occurred", "VP_Delta_Lost", "Root_Cognitive_Trap",
        "Deterministic_Fix", "Eradication_Status"
    ]

    def __init__(self, csv_path: Optional[Path] = None):
        self.csv_path = Path(csv_path) if csv_path else (DATA_DIR / "Playstyle_Diagnostics.csv")

    def _ensure_file(self):
        """Ensure target CSV file exists and write headers if empty."""
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.csv_path.exists() or self.csv_path.stat().st_size == 0:
            with open(self.csv_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(self.HEADERS)

    def log_diagnostic(self, diag_data: Dict[str, Any]) -> Dict[str, Any]:
        """Persist tactical misplay code, cognitive driver, and recovery lesson."""
        self._ensure_file()
        record = dict(diag_data)
        if "Timestamp" not in record or not record["Timestamp"]:
            record["Timestamp"] = get_excel_serial_timestamp()

        row_values = [sanitize_csv_cell(record.get(col, "")) for col in self.HEADERS]
        with open(self.csv_path, "a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(row_values)

        return record

    def get_all_diagnostics(self) -> List[Dict[str, Any]]:
        """Retrieve all recorded diagnostic misplay rows."""
        self._ensure_file()
        records = []
        with open(self.csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                records.append(dict(r))
        return records


class CsvDamageCalcRepository(IDamageCalcRepository):
    """CSV persistent storage for damage benchmarks (Damage_Calculations.csv)."""

    HEADERS = [
        "Calc_ID", "Attacker_Species", "Attacker_Spread", "Attacker_Modifiers",
        "Move_Name", "Defender_Species", "Defender_Spread", "Defender_Modifiers",
        "Min_Dmg_Pct", "Max_Dmg_Pct", "KO_Threshold", "Damage_Rolls",
        "Strategic_Context", "Raw_Showdown_Text"
    ]

    def __init__(self, csv_path: Optional[Path] = None):
        self.csv_path = Path(csv_path) if csv_path else (DATA_DIR / "Damage_Calculations.csv")

    def _ensure_file(self):
        """Ensure target CSV file exists and write headers if empty."""
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.csv_path.exists() or self.csv_path.stat().st_size == 0:
            with open(self.csv_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(self.HEADERS)

    def log_calculation(self, calc_data: Dict[str, Any]) -> Dict[str, Any]:
        """Persist official VGC damage calculation benchmark."""
        self._ensure_file()
        record = dict(calc_data)
        row_values = [sanitize_csv_cell(record.get(col, "")) for col in self.HEADERS]
        with open(self.csv_path, "a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(row_values)
        return record

    def get_all_calculations(self) -> List[Dict[str, Any]]:
        """Retrieve all stored damage calculation benchmarks."""
        self._ensure_file()
        records = []
        with open(self.csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                records.append(dict(r))
        return records


class CsvTeamRepository(ITeamRepository):
    """CSV persistent storage for registered rosters (Teams.csv)."""

    HEADERS = [
        "Team_ID", "Team_Name", "Date_Registered", "Status",
        "Pokemon_1", "Pokemon_2", "Pokemon_3", "Pokemon_4", "Pokemon_5", "Pokemon_6",
        "Showdown_Export", "Total_Matches", "Wins", "Win_Rate"
    ]

    def __init__(self, csv_path: Optional[Path] = None):
        self.csv_path = Path(csv_path) if csv_path else (DATA_DIR / "Teams.csv")

    def _ensure_file(self):
        """Ensure target CSV file exists and write headers if empty."""
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.csv_path.exists() or self.csv_path.stat().st_size == 0:
            with open(self.csv_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(self.HEADERS)

    def get_next_team_id(self) -> str:
        """Generate next sequential team code (e.g. T01, T02)."""
        self._ensure_file()
        max_num = 0
        with open(self.csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                tid = row.get("Team_ID", "")
                m = re.match(r"^T(\d+)$", tid)
                if m:
                    max_num = max(max_num, int(m.group(1)))
        return f"T{max_num + 1:02d}"

    def register_team(self, team_data: Dict[str, Any]) -> str:
        """Register a 6-mon team roster with Showdown export paste."""
        self._ensure_file()
        team_id = team_data.get("Team_ID") or self.get_next_team_id()
        record = dict(team_data)
        record["Team_ID"] = team_id
        row_values = [sanitize_csv_cell(record.get(col, "")) for col in self.HEADERS]
        with open(self.csv_path, "a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(row_values)
        return team_id

    def get_all_teams(self) -> List[Dict[str, Any]]:
        """Retrieve all registered team rosters."""
        self._ensure_file()
        records = []
        with open(self.csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                records.append(dict(r))
        return records


# ============================================================================
# IN-MEMORY TEST IMPLEMENTATION (Liskov Substitution & Fast Unit Testing)
# ============================================================================

class InMemoryMatchRepository(IMatchRepository):
    """In-memory mock for lightning-fast, zero-I/O unit tests."""

    def __init__(self):
        self.matches: List[Dict[str, Any]] = []

    def get_next_id(self) -> float:
        """Compute next sequential numeric identifier for match records."""
        return float(len(self.matches) + 1)

    def log_match(self, match_data: Dict[str, Any]) -> Dict[str, Any]:
        """Persist match record row with Excel timestamp and sanitized cells."""
        rec = dict(match_data)
        if "Match_ID" not in rec or not rec["Match_ID"]:
            rec["Match_ID"] = self.get_next_id()
        self.matches.append(rec)
        return rec

    def get_all_matches(self) -> List[Dict[str, Any]]:
        """Retrieve all recorded match rows from disk."""
        return list(self.matches)
