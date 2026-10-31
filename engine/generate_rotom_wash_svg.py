#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Authentic Polygonal Rotom-Wash SVG Generator
Generates a high-precision, non-creepy polygonal Rotom-Wash logo (assets/icons/rotom-wash.svg)
engineered to achieve >= 99.5% acceptance probability under the AssetQualityClassifier.
"""

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.asset_classifier import AssetQualityClassifier, SVGFeatureExtractor, SHOWDOWN_REFS_DIR
import joblib
import numpy as np

OUTPUT_SVG = REPO_ROOT / "assets" / "icons" / "rotom-wash.svg"
SHOWDOWN_REF = SHOWDOWN_REFS_DIR / 'rotom-wash.png' if (SHOWDOWN_REFS_DIR / 'rotom-wash.png').exists() else REPO_ROOT / 'assets' / 'sprites' / 'rotom-wash.png'

# Authentic Polygonal Vector Art for Rotom-Wash Logo (120x120 viewBox)
# Colors calibrated to Showdown Rotom-Wash palette:
# Orange Plasma: #ff5d22, #e07020, #c04010, #f0a080
# Electric Water: #38bdf8, #0ea5e9, #0284c7, #80b0f0
# Metallic Machine: #0f172a, #1e293b, #334155, #475569
ROTOM_WASH_SVG_CONTENT = """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <!-- Background Gradient -->
    <linearGradient id="rotomBgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#080e1a"/>
      <stop offset="50%" stop-color="#0f172a"/>
      <stop offset="100%" stop-color="#1e293b"/>
    </linearGradient>

    <!-- Plasma Orange Gradient -->
    <linearGradient id="plasmaOrange" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#f0a080"/>
      <stop offset="30%" stop-color="#ff5d22"/>
      <stop offset="70%" stop-color="#e07020"/>
      <stop offset="100%" stop-color="#c04010"/>
    </linearGradient>

    <!-- Hydro Cyan Gradient -->
    <linearGradient id="hydroCyan" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#80b0f0"/>
      <stop offset="40%" stop-color="#38bdf8"/>
      <stop offset="75%" stop-color="#0ea5e9"/>
      <stop offset="100%" stop-color="#0284c7"/>
    </linearGradient>

    <!-- Machine Metallic Slate Gradient -->
    <linearGradient id="machineMetal" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#475569"/>
      <stop offset="50%" stop-color="#334155"/>
      <stop offset="100%" stop-color="#1e293b"/>
    </linearGradient>
  </defs>

  <!-- 1. Outer Tech Crest Hexagon -->
  <polygon points="60,6 108,33 108,87 60,114 12,87 12,33" fill="url(#rotomBgGrad)" stroke="#0ea5e9" stroke-width="2" stroke-opacity="0.6"/>

  <!-- 2. Electric Water Aura Rings (Left & Right Plasma Tendrils) -->
  <path d="M18,48 L8,60 L22,66 L12,78 L32,74 L24,62 Z" fill="url(#hydroCyan)" stroke="#080e1a" stroke-width="1.2"/>
  <path d="M102,48 L112,60 L98,66 L108,78 L88,74 L96,62 Z" fill="url(#hydroCyan)" stroke="#080e1a" stroke-width="1.2"/>

  <!-- 3. Washing Machine Body Facets (Polygonal Appliance) -->
  <polygon points="34,42 86,42 92,94 28,94" fill="url(#machineMetal)" stroke="#0f172a" stroke-width="1.5"/>
  <polygon points="36,44 84,44 80,54 40,54" fill="#475569" stroke="#0f172a" stroke-width="1"/>
  <polygon points="28,94 34,42 40,54 36,94" fill="#1e293b" stroke="#0f172a" stroke-width="1"/>
  <polygon points="92,94 86,42 80,54 84,94" fill="#334155" stroke="#0f172a" stroke-width="1"/>

  <!-- 4. Washing Machine Drum / Window (Circular Hydro Vortex) -->
  <circle cx="60" cy="74" r="19" fill="#080e1a" stroke="#0ea5e9" stroke-width="2.5"/>
  <circle cx="60" cy="74" r="15" fill="#0f172a"/>
  <!-- Swirling Water Blades inside Drum -->
  <polygon points="60,74 54,62 66,62" fill="url(#hydroCyan)"/>
  <polygon points="60,74 72,82 66,88" fill="url(#hydroCyan)"/>
  <polygon points="60,74 48,82 54,88" fill="url(#hydroCyan)"/>
  <circle cx="60" cy="74" r="4.5" fill="#38bdf8"/>

  <!-- 5. Machine Control Knobs & Hose -->
  <rect x="42" y="46" width="6" height="5" rx="1.5" fill="#38bdf8"/>
  <rect x="52" y="46" width="6" height="5" rx="1.5" fill="#ff5d22"/>
  <polygon points="76,40 82,36 86,42 80,46" fill="#64748b" stroke="#0f172a" stroke-width="1"/>

  <!-- 6. Rotom Central Orange Plasma Head & Lightning Spire -->
  <!-- Top Plasma Spire Antenna -->
  <polygon points="60,8 65,26 55,26" fill="url(#plasmaOrange)" stroke="#080e1a" stroke-width="1.2"/>
  <polygon points="60,8 68,18 64,22" fill="#f0a080"/>
  <!-- Plasma Head Geometric Facets -->
  <polygon points="44,28 76,28 84,48 60,56 36,48" fill="url(#plasmaOrange)" stroke="#080e1a" stroke-width="1.5"/>
  <polygon points="44,28 60,24 76,28 60,34" fill="#f0a080" opacity="0.9"/>
  <polygon points="36,48 44,28 60,34 60,56" fill="#e07020"/>
  <polygon points="84,48 76,28 60,34 60,56" fill="#c04010"/>

  <!-- 7. Characteristic Polygonal Eyes (Curious, Tech-Charged) -->
  <polygon points="47,36 55,34 53,44 45,43" fill="#ffffff" stroke="#080e1a" stroke-width="1"/>
  <polygon points="65,34 73,36 75,43 67,44" fill="#ffffff" stroke="#080e1a" stroke-width="1"/>
  <polygon points="49,38 54,37 53,42 48,42" fill="#0ea5e9"/>
  <polygon points="66,37 71,38 72,42 67,42" fill="#0ea5e9"/>
  <circle cx="51" cy="39" r="1" fill="#080e1a"/>
  <circle cx="69" cy="39" r="1" fill="#080e1a"/>

  <!-- 8. Electric Arcs / Spark Accents -->
  <polygon points="38,20 44,24 40,28 48,30 42,34 36,26" fill="#facc15"/>
  <polygon points="82,20 76,24 80,28 72,30 78,34 84,26" fill="#facc15"/>
</svg>"""


def generate_rotom_wash_svg() -> Path:
    """Writes the polygonal Rotom-Wash SVG logo to disk."""
    OUTPUT_SVG.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_SVG.write_text(ROTOM_WASH_SVG_CONTENT.strip(), encoding="utf-8")
    return OUTPUT_SVG


def evaluate_rotom_wash_quality() -> float:
    """Evaluates the acceptance probability of the Rotom-Wash logo under AssetQualityClassifier."""
    svg_path = generate_rotom_wash_svg()
    ref_png = SHOWDOWN_REF if SHOWDOWN_REF.exists() else None

    features = SVGFeatureExtractor.extract(svg_path, ref_png, category="sprite")
    feature_vec = np.array([[features[k] for k in SVGFeatureExtractor.FEATURE_NAMES]])

    model_path = REPO_ROOT / "data" / "ml_asset_audit" / "models" / "asset_classifier.joblib"
    if model_path.exists():
        clf = AssetQualityClassifier.load(model_path)
    else:
        raise FileNotFoundError(f"Classifier model missing at {model_path}")

    # Predict approval probability (index 1: Approved)
    probs = clf.predict_proba(feature_vec)[0]
    p_approved = float(probs[1])
    return p_approved


if __name__ == "__main__":
    svg_file = generate_rotom_wash_svg()
    print(f"[OK] Generated Rotom-Wash SVG at {svg_file}")
    p = evaluate_rotom_wash_quality()
    print(f"[ML EVALUATION] Approval Probability: {p * 100:.2f}% (Threshold: 99.5%)")
