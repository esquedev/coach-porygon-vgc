Feature: Adversarial Mutation & Security Guardrails
  As a systems auditor
  I want malicious, malformed, or corrupt inputs strictly rejected across all subsystems
  So that the application is resilient against prompt injections, XML bombs, and memory exhaustion

  Scenario: Reject malformed SVG XML and injected scripts
    Given malformed or scripted SVG markup
    When asset verification runs
    Then the asset fails audit with ParseError or script detection

  Scenario: Reject illegal species and items in roster pastes
    Given a Showdown export containing banned species or items
    When validate_roster parses the paste
    Then the validation fails with clear error messages
