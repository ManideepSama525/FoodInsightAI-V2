# Food recognition API

## Endpoint

`POST /api/v1/recognition/predict`

Send one JPEG, PNG, or WEBP file as multipart form data under the field `file`.

A successful high-confidence response contains `status: "recognized"` and `predicted_food`. A low-confidence response uses `status: "needs_review"`, leaves `predicted_food` null, and provides ranked candidates for user confirmation. Confidence is a model score, not a calibrated probability unless calibration is performed during model evaluation.

If model artifacts or the optional inference runtime are missing, the endpoint returns HTTP 503. It never fabricates a food prediction.

## Model artifacts

- `artifacts/food_classifier.ts`: TorchScript model returning one logit per class.
- `artifacts/classes.json`: JSON array of class labels in the exact output-index order, or `{"classes": [...]}`.
- Configure paths and thresholds through the `RECOGNITION_*` environment variables.
- The inference adapter uses ImageNet mean/std normalization and a 224x224 RGB center-fit image by default. Training must use the same preprocessing.

Install optional runtime dependencies with `pip install -e ".[vision]"`.
