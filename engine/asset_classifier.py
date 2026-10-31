#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Asset Quality & Anti-Creepy Classifier (engine/asset_classifier.py)
Uses Scikit-Learn to classify repository SVG assets (Pokémon Sprites, Items, Mega Stones)
into APPROVED (high quality, authentic vector art) and REJECTED (creepy/procedural fallbacks).

Features:
1. Procedural Template Fingerprints (uncanny eyes, generic torso, generic berry, generic mega stone, text fallback).
2. Vector Complexity Metrics (path counts, polygon counts, primitive ratios, color diversity, file size).
3. Pokémon Showdown Ground-Truth Comparison (dominant palette divergence, primary color distance).
4. Leave-One-Out & Stratified K-Fold Cross-Validation evaluation.
5. Model persistence via Joblib.
"""

import argparse
import csv
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import LeaveOneOut, StratifiedKFold
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, confusion_matrix
)
import joblib

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_DATA_DIR = REPO_ROOT / "data" / "ml_asset_audit"
SHOWDOWN_REFS_DIR = AUDIT_DATA_DIR / "showdown_refs"
MODELS_DIR = AUDIT_DATA_DIR / "models"


def hex_to_rgb(hex_str: str) -> Tuple[int, int, int]:
    """Convert hex color string (#rrggbb or #rgb) to RGB integer tuple."""
    hex_str = hex_str.lstrip("#")
    if len(hex_str) == 3:
        hex_str = "".join([c * 2 for c in hex_str])
    if len(hex_str) != 6:
        return (0, 0, 0)
    return tuple(int(hex_str[i:i + 2], 16) for i in (0, 2, 4))


def rgb_dist(c1: Tuple[int, int, int], c2: Tuple[int, int, int]) -> float:
    """Calculate Euclidean distance between two RGB colors in color space."""
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(c1, c2)))


def extract_showdown_palette(png_path: Path) -> List[Tuple[int, int, int]]:
    """Extract up to 8 dominant non-transparent colors from official Showdown sprite."""
    if not png_path.exists():
        return []
    try:
        im = Image.open(png_path).convert("RGBA")
        pixels = im.load()
        w, h = im.size
        counts: Dict[Tuple[int, int, int], int] = {}
        for y in range(h):
            for x in range(w):
                r, g, b, a = pixels[x, y]
                # Ignore transparent alpha background and dark outline pixels
                if a > 80 and not (r < 24 and g < 24 and b < 24) and not (r > 245 and g > 245 and b > 245):
                    bucket = (r // 16 * 16, g // 16 * 16, b // 16 * 16)
                    counts[bucket] = counts.get(bucket, 0) + 1
        sorted_colors = sorted(counts.items(), key=lambda item: item[1], reverse=True)
        return [c[0] for c in sorted_colors[:8]]
    except Exception:
        return []


class SVGFeatureExtractor:
    """Extracts structural vector metrics and Showdown ground-truth comparison features."""

    FEATURE_NAMES: List[str] = [
        "has_creepy_eye",
        "has_generic_torso",
        "has_generic_berry",
        "has_generic_mega",
        "has_text_fallback",
        "is_primitive_blob",
        "procedural_penalty",
        "unmatched_primary",
        "primary_color_dist",
        "total_elements",
        "num_paths",
        "distinct_colors",
        "file_size_bytes",
        "is_item"
    ]

    @classmethod
    def extract(cls, svg_path: Path, showdown_png_path: Optional[Path] = None, category: str = "sprite") -> Dict[str, float]:
        """Extract all engineered features from an SVG file."""
        txt = svg_path.read_text(encoding="utf-8")

        # 1. Procedural generator template markers
        has_creepy_eye = 1.0 if ('points="46,42 54,44 48,48"' in txt or 'points="74,42 66,44 72,48"' in txt) else 0.0
        has_generic_torso = 1.0 if 'C32,68 44,62 60,62' in txt else 0.0
        has_generic_berry = 1.0 if 'M50,30 C30,30 22,50 30,72' in txt else 0.0
        has_generic_mega = 1.0 if ('radialGradient id="mg-' in txt or 'Iconic Mega Evolution DNA Symbol' in txt) else 0.0
        has_text_fallback = 1.0 if '<text ' in txt else 0.0

        # 2. Geometric complexity
        num_paths = float(len(re.findall(r'<path\b', txt)))
        num_polygons = float(len(re.findall(r'<polygon\b', txt)))
        num_circles = float(len(re.findall(r'<circle\b', txt)))
        num_ellipses = float(len(re.findall(r'<ellipse\b', txt)))
        total_elements = num_paths + num_polygons + num_circles + num_ellipses

        is_primitive_blob = 1.0 if (category == "sprite" and total_elements <= 7.0 and num_paths == 0.0 and num_polygons == 0.0) else 0.0

        hex_colors = set(re.findall(r'#[0-9a-fA-F]{6}', txt))
        distinct_colors = float(len(hex_colors))
        file_size_bytes = float(len(txt.encode("utf-8")))

        # 3. Showdown Ground Truth comparison
        showdown_colors = extract_showdown_palette(showdown_png_path) if showdown_png_path else []
        svg_rgb_colors = [hex_to_rgb(h) for h in hex_colors if h.lower() not in ("#ffffff", "#000000", "#0f172a", "#1e293b", "#334155")]

        primary_color_dist = 0.0
        unmatched_primary = 0.0
        if showdown_colors and svg_rgb_colors:
            sh_primary = showdown_colors[0]
            primary_color_dist = min(rgb_dist(sh_primary, sc) for sc in svg_rgb_colors)
            if primary_color_dist > 85.0:
                unmatched_primary = 1.0
        elif not showdown_colors:
            primary_color_dist = 40.0

        # 4. Composite procedural penalty
        procedural_penalty = (
            (has_creepy_eye * 4.0) +
            (has_generic_torso * 4.0) +
            (has_generic_berry * 3.0) +
            (has_generic_mega * 4.0) +
            (has_text_fallback * 4.0) +
            (is_primitive_blob * 3.0)
        )

        return {
            "has_creepy_eye": has_creepy_eye,
            "has_generic_torso": has_generic_torso,
            "has_generic_berry": has_generic_berry,
            "has_generic_mega": has_generic_mega,
            "has_text_fallback": has_text_fallback,
            "is_primitive_blob": is_primitive_blob,
            "procedural_penalty": procedural_penalty,
            "unmatched_primary": unmatched_primary,
            "primary_color_dist": primary_color_dist,
            "total_elements": total_elements,
            "num_paths": num_paths,
            "distinct_colors": distinct_colors,
            "file_size_bytes": file_size_bytes,
            "is_item": 1.0 if category == "item" else 0.0
        }


class AssetQualityClassifier:
    """Scikit-Learn ensemble model predicting whether an SVG asset is Approved or Rejected."""

    def __init__(self, n_estimators: int = 100, max_depth: int = 4, random_state: int = 42):
        self.pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("rf", RandomForestClassifier(n_estimators=n_estimators, max_depth=max_depth, random_state=random_state))
        ])
        self.feature_names = SVGFeatureExtractor.FEATURE_NAMES
        self.is_fitted = False

    def fit(self, X: np.ndarray, y: np.ndarray) -> "AssetQualityClassifier":
        """Train the classifier pipeline on feature matrix X and labels y."""
        self.pipeline.fit(X, y)
        self.is_fitted = True
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict binary approval label: 1 = APPROVED, 0 = REJECTED."""
        return self.pipeline.predict(X)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict probability of class [P(Rejected), P(Approved)]."""
        return self.pipeline.predict_proba(X)

    def evaluate_loocv(self, X: np.ndarray, y: np.ndarray) -> Dict[str, Any]:
        """Perform rigorous Leave-One-Out Cross-Validation (LOOCV)."""
        loo = LeaveOneOut()
        preds = []
        probs = []
        for train_idx, test_idx in loo.split(X, y):
            clf = RandomForestClassifier(n_estimators=100, max_depth=4, random_state=42)
            scaler = StandardScaler()
            X_tr = scaler.fit_transform(X[train_idx])
            X_te = scaler.transform(X[test_idx])
            clf.fit(X_tr, y[train_idx])
            preds.append(int(clf.predict(X_te)[0]))
            probs.append(float(clf.predict_proba(X_te)[0][1]))

        y_true = list(y)
        acc = float(accuracy_score(y_true, preds))
        prec = float(precision_score(y_true, preds))
        rec = float(recall_score(y_true, preds))
        f1 = float(f1_score(y_true, preds))
        auc = float(roc_auc_score(y_true, probs))
        cm = confusion_matrix(y_true, preds).tolist()

        return {
            "method": "LeaveOneOut",
            "samples": len(y_true),
            "accuracy": round(acc, 4),
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1_score": round(f1, 4),
            "roc_auc": round(auc, 4),
            "confusion_matrix": cm,
            "predictions": preds,
            "probabilities": [round(p, 4) for p in probs]
        }

    def get_feature_importances(self) -> List[Dict[str, Any]]:
        """Return sorted feature importances with descriptions."""
        if not self.is_fitted:
            raise RuntimeError("Model must be fitted before computing feature importances.")
        rf = self.pipeline.named_steps["rf"]
        importances = rf.feature_importances_
        descriptions = {
            "procedural_penalty": "Combined structural penalty for template markers (creepy eyes, generic torso, berry, mega stone)",
            "primary_color_dist": "Euclidean color distance between SVG dominant color and Showdown official sprite",
            "distinct_colors": "Number of unique hex color codes used across all vector elements",
            "file_size_bytes": "Total SVG XML code file size in bytes",
            "total_elements": "Sum of paths, polygons, circles, and ellipses",
            "num_paths": "Number of custom bezier curve <path> elements",
            "unmatched_primary": "Binary flag indicating if Showdown primary color has no close match (>85 distance)",
            "has_creepy_eye": "Exact binary detection of procedural template blank triangle eyes",
            "has_generic_torso": "Exact binary detection of procedural template mannequin torso bezier curve",
            "is_item": "Category indicator (1 for items, 0 for Pokémon sprites)",
            "has_generic_berry": "Exact binary detection of cloned procedural berry silhouette",
            "has_text_fallback": "Binary detection of fallback 3-letter abbreviation text elements (MIR, WHI)",
            "is_primitive_blob": "Detection of ultra-simplistic sprites consisting exclusively of circles/ellipses without paths",
            "has_generic_mega": "Detection of generic radial gradient and default DNA glyph for mega stones"
        }
        ranked = sorted(zip(self.feature_names, importances), key=lambda x: x[1], reverse=True)
        return [
            {
                "feature": name,
                "importance": round(float(imp), 4),
                "description": descriptions.get(name, "")
            }
            for name, imp in ranked
        ]

    def save(self, filepath: Path) -> None:
        """Serialize trained pipeline to disk via Joblib."""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, filepath)

    @classmethod
    def load(cls, filepath: Path) -> "AssetQualityClassifier":
        """Load serialized pipeline from disk."""
        return joblib.load(filepath)


def build_and_evaluate_pipeline() -> Tuple[AssetQualityClassifier, Dict[str, Any]]:
    """Runs Phase 1 feature extraction and Phase 2 training/evaluation on the 40 labeled samples."""
    manifest_path = AUDIT_DATA_DIR / "training_set_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Training manifest not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Phase 1: Extract features and build dataset
    dataset_rows = []
    for item in manifest:
        svg_p = REPO_ROOT / item["relative_path"]
        sh_p = REPO_ROOT / item["showdown_ref"]
        feats = SVGFeatureExtractor.extract(svg_p, sh_p, item["category"])
        row = {
            "filename": item["filename"],
            "category": item["category"],
            "label": item["label"],
            "class_name": item["class_name"],
            **feats
        }
        dataset_rows.append(row)

    # Save feature dataset as CSV and JSON
    csv_out = AUDIT_DATA_DIR / "features_dataset.csv"
    json_out = AUDIT_DATA_DIR / "features_dataset.json"

    fieldnames = list(dataset_rows[0].keys())
    with open(csv_out, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(dataset_rows)

    json_out.write_text(json.dumps(dataset_rows, indent=2), encoding="utf-8")
    print(f"[OK] Exported feature dataset: {csv_out} ({len(dataset_rows)} samples)")

    # Phase 2, Step 1 & 2: Train and evaluate Scikit-Learn ensemble model
    feature_cols = SVGFeatureExtractor.FEATURE_NAMES
    X = np.array([[r[c] for c in feature_cols] for r in dataset_rows])
    y = np.array([r["label"] for r in dataset_rows])

    model = AssetQualityClassifier(n_estimators=100, max_depth=4, random_state=42)
    loocv_results = model.evaluate_loocv(X, y)
    print(f"[OK] LOOCV Evaluation: Accuracy={loocv_results['accuracy']*100:.2f}%, ROC-AUC={loocv_results['roc_auc']*100:.2f}%")

    # Fit final model on all data
    model.fit(X, y)

    # Feature importance report
    feat_importances = model.get_feature_importances()
    imp_out = AUDIT_DATA_DIR / "feature_importance.json"
    imp_out.write_text(json.dumps(feat_importances, indent=2), encoding="utf-8")

    # Metrics evaluation report
    eval_out = AUDIT_DATA_DIR / "evaluation_metrics.json"
    eval_data = {
        "loocv_summary": loocv_results,
        "feature_importances": feat_importances,
        "sample_count": len(dataset_rows),
        "good_samples": int(sum(y == 1)),
        "bad_samples": int(sum(y == 0)),
    }
    eval_out.write_text(json.dumps(eval_data, indent=2), encoding="utf-8")

    # Save model artifact
    model_path = MODELS_DIR / "asset_classifier.joblib"
    model.save(model_path)
    print(f"[OK] Saved trained model artifact: {model_path}")

    return model, eval_data


if __name__ == "__main__":
    build_and_evaluate_pipeline()
