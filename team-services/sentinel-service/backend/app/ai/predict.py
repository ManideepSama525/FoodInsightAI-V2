import joblib
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

model = joblib.load(BASE_DIR / "model.pkl")
vectorizer = joblib.load(BASE_DIR / "vectorizer.pkl")


def predict_attack(payload: str):

    vector = vectorizer.transform([payload])

    prediction = model.predict(vector)[0]

    probabilities = model.predict_proba(vector)[0]

    labels = model.classes_

    confidence = round(max(probabilities) * 100, 2)

    scores = {}

    for label, probability in zip(labels, probabilities):
        scores[label] = round(probability * 100, 2)

    return {
        "prediction": prediction,
        "confidence": confidence,
        "scores": scores,
    }