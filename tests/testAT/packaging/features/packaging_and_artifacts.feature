Feature: Build Packaging & Exclusive Artifact Lock (Rule 11)
  As a release automation engineer
  I want pyproject.toml PEP 517/621 compliance, GitHub CI workflows, and Rule 11 enforced
  So that releases are reproducible and only command_center.html is synced automatically

  Scenario: PEP 621 metadata compliance
    Given pyproject.toml
    When build tools inspect configuration
    Then setuptools.build_meta backend and valid metadata are verified

  Scenario: Exclusive Artifact Lock Guardrail
    Given report generation and PDF export tooling
    When export_pdf runs without explicit user authorization
    Then sync_to_artifact defaults strictly to False
