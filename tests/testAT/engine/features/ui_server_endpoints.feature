Feature: Coach Porygon UI Server HTTP API
  As a local client or dashboard widget
  I want reliable REST endpoints (/api/ping, /api/telemetry, /sprites/<name>)
  So that frontend interactions dynamically reflect real-time telemetry and assets

  Scenario: Retrieve live telemetry via REST API
    Given a running ui_server Flask test client
    When a GET request is sent to /api/telemetry
    Then HTTP 200 OK is returned with valid JSON telemetry data
