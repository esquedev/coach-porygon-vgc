Feature: End-to-End Telemetry CLI Pipeline
  As a coach running command-line telemetry
  I want python -m engine.telemetry to accept match payloads and display help
  So that scripting and batch replay imports execute deterministically

  Scenario: CLI help and argument parsing
    Given the engine.telemetry CLI executable
    When invoked with --help
    Then usage options and argument descriptions are displayed cleanly
