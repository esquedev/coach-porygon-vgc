Feature: Bilingual Localization Parity (EN/ES)
  As a bilingual competitive VGC player
  I want Coach Porygon's Command Center and reflexes to support English and Mexican Spanish
  So that all analysis, tactical feedback, and UI tags have complete symmetry

  Scenario: Validate dictionary completeness and symmetry
    Given the English and Spanish translation dictionaries
    When dictionary keys are cross-referenced
    Then both dictionaries must have identical key coverage with non-empty values

  Scenario: Canonical Trainer terminology
    Given the canonical persona terminology rule
    When English and Spanish texts are checked
    Then Trainer and Entrenador must be used consistently without aviation or mecha jargon
