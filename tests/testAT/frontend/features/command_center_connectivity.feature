Feature: Command Center Dashboard Portability & Connectivity
  As a competitive Trainer
  I want command_center.html to function 100% offline via file:/// protocol
  With embedded Base64 sprites and live Flask API polling when online

  Scenario: Offline portability and Base64 sprites
    Given assets/command_center.html
    When opened locally without internet access
    Then all core sprites render via Base64 data URIs with zero external requests
