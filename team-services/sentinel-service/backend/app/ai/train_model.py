import joblib
import pandas as pd

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split

print("Loading dataset...")

df = pd.read_csv("dataset.csv")

X = df["payload"]
y = df["label"]

print(f"Samples: {len(df)}")

# Split dataset
X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42,
    stratify=y,
)

# TF-IDF
vectorizer = TfidfVectorizer(
    lowercase=True,
    ngram_range=(1, 2),
)

X_train_vec = vectorizer.fit_transform(X_train)
X_test_vec = vectorizer.transform(X_test)

# Train
print("Training AI model...")

model = LogisticRegression(
    max_iter=1000,
    class_weight="balanced",
)

model.fit(X_train_vec, y_train)

# Evaluate
predictions = model.predict(X_test_vec)

accuracy = accuracy_score(y_test, predictions)

print("\n" + "=" * 60)
print(f"Accuracy : {accuracy * 100:.2f}%")
print("=" * 60)

print(classification_report(y_test, predictions))

# Save
joblib.dump(model, "model.pkl")
joblib.dump(vectorizer, "vectorizer.pkl")

print("=" * 60)
print("Model saved successfully.")
print("=" * 60)