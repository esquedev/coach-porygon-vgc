Feature: 45-Second Interactive Board Sparring & Reflex Flashcards
  As a competitive Trainer
  I want flashcard scenarios and Speed Duels with zero spoilers in option labels
  So that reflex conditioning strictly tests tactical decision-making under 45-second clocks

  Scenario: Zero spoiler tokens in flashcard options
    Given all flashcard scenarios in engine/scenarios_data.py
    When options are presented to the Trainer
    Then labels must never reveal correct choices or tactical hints in plain text
