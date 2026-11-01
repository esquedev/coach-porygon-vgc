Feature: Application Security & Hardening (OWASP LLM01 / Top 10)
  As an application security engineer
  I want strict perimeter defenses (CORS filtering, dotfile blocking, payload caps, SSRF prevention)
  So that Coach Porygon runs securely on local networks without unauthorized data access

  Scenario: Prevent path traversal and dotfile access
    Given an HTTP request for sensitive files or dotfiles (.git, .env, trainer_profile.json)
    When ui_server handles the request
    Then a 403 Forbidden status is returned

  Scenario: Enforce payload size limits
    Given an HTTP POST request exceeding 5MB
    When ui_server processes the body
    Then a 413 Payload Too Large error is emitted
