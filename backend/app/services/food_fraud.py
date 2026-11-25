from functools import lru_cache

import joblib
import numpy as np

from backend.app.core.config import get_settings


@lru_cache(maxsize=1)
def load_cinnamon_ftir_models() -> dict:
    model_dir = get_settings().cinnamon_ftir_model_dir

    filenames = {
        "detection": "cinnamon_adulteration_detection.joblib",
        "identification": "cinnamon_adulterant_identification.joblib",
        "regression": "cinnamon_concentration_regression.joblib",
    }

    artifacts = {}
    for task, filename in filenames.items():
        path = model_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"Required Cinnamon FTIR model is missing: {path}")
        artifacts[task] = joblib.load(path)

    feature_counts = {
        len(artifact["feature_columns"]) for artifact in artifacts.values()
    }
    if feature_counts != {2523}:
        raise RuntimeError("Cinnamon FTIR models do not share the expected 2,523 features.")

    detection_features = artifacts["detection"]["feature_columns"]
    if any(
        artifact["feature_columns"] != detection_features
        for artifact in artifacts.values()
    ):
        raise RuntimeError("Cinnamon FTIR model feature orders do not match.")

    return artifacts


def analyze_cinnamon_ftir(
    spectral_values: list[float],
    sample_id: str | None = None,
) -> dict:
    models = load_cinnamon_ftir_models()
    features = np.asarray(spectral_values, dtype=np.float64).reshape(1, -1)

    if features.shape[1] != 2523 or not np.isfinite(features).all():
        raise ValueError("Expected exactly 2,523 finite FTIR values.")

    detection_model = models["detection"]["model"]
    detection_result = str(detection_model.predict(features)[0])

    if detection_result == "Pure_Cinnamon":
        return {
            "sample_id": sample_id,
            "adulteration_status": "Pure_Cinnamon",
            "is_adulterated": False,
            "adulterant_type": None,
            "estimated_concentration_percent": 0.0,
            "validation_note": (
                "Research prototype validated using grouped cross-validation "
                "on the source dataset. Independent laboratory and instrument "
                "validation has not been performed."
            ),
        }

    if detection_result != "Adulterated":
        raise RuntimeError(f"Unexpected adulteration model output: {detection_result}")

    adulterant_model = models["identification"]["model"]
    adulterant_result = str(adulterant_model.predict(features)[0])

    if adulterant_result not in {"Peanut", "Walnut", "Wood_Dust"}:
        raise RuntimeError(f"Unexpected adulterant model output: {adulterant_result}")

    regression_model = models["regression"]["model"]
    concentration = float(regression_model.predict(features)[0])
    concentration = float(np.clip(concentration, 0.0, 24.0))

    if adulterant_result == "Peanut":
        note = (
            "Concentration estimates showed stronger grouped-validation "
            "performance for peanut adulteration."
        )
    else:
        note = (
            "Concentration estimates are less reliable for this adulterant "
            "than for peanut in grouped validation. Treat the estimate as "
            "indicative, not definitive."
        )

    return {
        "sample_id": sample_id,
        "adulteration_status": "Adulterated",
        "is_adulterated": True,
        "adulterant_type": adulterant_result,
        "estimated_concentration_percent": round(concentration, 3),
        "validation_note": (
            note
            + " Independent laboratory and instrument validation has not been performed."
        ),
    }
