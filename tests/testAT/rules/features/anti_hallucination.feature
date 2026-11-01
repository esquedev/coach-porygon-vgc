Feature: Regulation M-C Anti-Hallucination Guardrails
  As Head Coach Porygon
  I want all format entities, rosters, and scenario items strictly grounded in Regulation M-C
  So that competitive calculations remain 100% mathematically authentic and free of hallucinations

  Scenario: Reject non-format Paradox and Legendary species
    Given the official Regulation M-C species blacklist
    When active team rosters and flashcard scenarios are parsed
    Then zero blacklisted species must be present

  Scenario: Enforce legal item pool
    Given the Regulation M-C legal items catalog
    When all item mentions across datasets and scenarios are verified
    Then every item must exist in Regulation_MC_Items.csv

  Scenario: Reject TCG rules and terminology
    Given the TCG Contamination Guardrail
    When repository rules and engine computations are scanned
    Then zero card-game rules (prizes, energy cards, deck limits) are tolerated
