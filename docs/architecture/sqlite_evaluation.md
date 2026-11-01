# Architectural Evaluation: SQLite vs. CSV/JSON Storage Layer

**Document Version:** 1.0  
**Author:** Senior Data Engineer Developer & Data Engineering QA  
**Target:** Pokémon Champions Regulation M-C Competitive Workspace  
**Status:** Approved Architectural Decision Record (ADR)

---

## 1. Context & Problem Statement
The Coach Porygon VGC coaching and turn-simulation ecosystem currently persists competitive telemetry, tournament scouting data, registered rosters, and damage benchmarks across structured CSV files (`data/*.csv`) and JSON documents (`data/*.json`).

As this repository prepares for public open-source deployment on GitHub, we evaluated whether migrating the persistence tier to an embedded relational database (SQLite 3) provides competitive or technical advantages, or if the current decoupled text-based architecture is optimal.

---

## 2. Comparative Evaluation Matrix

| Architectural Dimension | Current CSV/JSON Architecture | SQLite 3 Migration | Winner |
|---|---|---|---|
| **Git-Diffability & Public Repo Collaboration** | **Flawless**: Every match, team, and calc added appears as a clear textual diff (`+1 line`). Merge conflicts can be resolved line-by-line in GitHub PRs. | **Poor**: SQLite `.db` files are binary. Committing them creates bloated Git blobs, unmergeable binary conflicts, and prevents public audit of individual match commits. | **CSV/JSON** |
| **Agent / LLM Tool Inspection** | **Native**: AI agents, subagents, and command-line tools can inspect, grep, and parse CSV/JSON rows using standard tools (`read_file`, `grep`, `csv`). | **Indirect**: Requires invoking `sqlite3` CLI or Python connection scripts for every inspection turn. | **CSV/JSON** |
| **Data Integrity & Schema Validation** | **Previously ad-hoc**: Relied on individual script parsers. Prone to malformed rows if written incorrectly. | **Strong**: Schema enforcement, type affinity, primary keys, and foreign key constraints out of the box. | **SQLite 3** |
| **Concurrency & ACID Transactions** | File-level atomic appends. Adequate for single-user desktop coaching; unsuitable for high-write web servers. | Multi-reader, single-writer ACID transactional locking. | **SQLite 3** |
| **Zero-Configuration Developer Experience** | **Zero setup**: Clone repository and run immediately. No migrations, no database locks, no schema initialization step. | Requires database file migration and potential file lock issues on Windows OneDrive synced folders. | **CSV/JSON** |
| **Query Performance (<100k rows)** | Sub-millisecond reading with standard library `csv.DictReader` and in-memory indexing. | Sub-millisecond indexed SQL queries. | **Tie** |

---

## 3. The OneDrive File-Locking Hazard
A critical operational factor for this workspace is its deployment across cloud-synced directories (such as Microsoft OneDrive or Dropbox).
SQLite creates temporary journal and write-ahead log files (`.db-wal`, `.db-shm`) alongside the database. Cloud sync clients (specifically Microsoft OneDrive and Dropbox) aggressively scan and lock these temporary database files during sync cycles, leading to frequent `sqlite3.OperationalError: database is locked` errors during rapid battle telemetry logging.

Plain CSV appending using append mode (`open(path, 'a', newline='', encoding='utf-8')`) avoids persistent file lock handles and operates seamlessly across synced cloud directories.

---

## 4. Architectural Decision: The SOLID Repository Abstraction
Rather than tightly coupling business logic to either raw file handles or a monolithic SQLite database, we apply the **Dependency Inversion Principle (DIP)** and **Single Responsibility Principle (SRP)**:

1. **Retain CSV/JSON as the Default Storage Provider**:
   - Preserves 100% Git-diffability, public repo transparency, and seamless OneDrive synchronization.
2. **Implement an Abstract Repository Layer (`engine/repositories.py`)**:
   - Define clean, type-hinted repository interfaces:
     - `IMatchRepository`: Contract for logging and retrieving battle records (`Raw_Matches.csv`).
     - `IDiagnosticsRepository`: Contract for logging tactical mistakes and cognitive traps (`Playstyle_Diagnostics.csv`).
     - `ITeamRepository`: Contract for reading and registering 66-SP rosters (`Teams.csv`).
     - `IDamageCalcRepository`: Contract for damage benchmarks (`Damage_Calculations.csv`).
3. **Pluggable SQLite Ready (Open/Closed Principle)**:
   - The repository abstraction completely decouples business engines (`turn_simulator.py`, `telemetry.py`, `register_team.py`) from storage mechanics.
   - If a multi-tenant cloud backend is introduced in the future, a `SQLiteMatchRepository` or `PostgresMatchRepository` can be plugged in by swapping the factory provider with zero modification to coaching algorithms or damage math.

---

## 5. Verification & Recommendation
- **Verdict**: Do NOT migrate primary storage to SQLite. Maintain text-based CSV/JSON files.
- **Action**: Implement `engine/repositories.py` with typed CSV implementations, strict schema validation, safe escaping against formula injection (CWE-1236), and comprehensive unit tests.
