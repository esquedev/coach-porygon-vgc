Feature: Frontend HTML Integrity & Responsive Layout
  As a web user
  I want Command Center builds to be well-formed UTF-8 HTML with complete i18n tags
  So that rendering is responsive across desktop, tablet, and mobile browsers

  Scenario: Viewport and character encoding integrity
    Given the compiled Command Center HTML files
    When the HTML document is validated
    Then it must declare UTF-8 encoding and responsive viewport meta tags
