Feature: Showdown Raster Asset Inventory & Manifest Integrity
  As Head Coach Porygon
  I want all 561 curated Regulation M-C species, items, and megastones verified
  So that every UI rendering and PDF report loads authentic graphics with zero broken sprites

  Scenario: Verify complete PNG coverage against manifest
    Given the curated assets inventory in assets/sprites/Reg_M-C
    When verify_png_inventory audits the directory
    Then exactly 561 valid assets must match cryptographic SHA-256 digests
