from pathlib import Path
import shutil
import re

ROOT = Path(__file__).resolve().parents[1]

def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8-sig")

def write(rel, content):
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")

def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one matching section, found {count}")
    return text.replace(old, new, 1)

def backup(rel):
    path = ROOT / rel
    stamp = ".before-indian-model"
    target = path.with_name(path.name + stamp)
    if not target.exists():
        shutil.copy2(path, target)

# 1. Settings
rel = "backend/app/core/config.py"
s = read(rel)
s = replace_once(
    s,
    '    recognition_image_size: int = 224\n',
    '    recognition_image_size: int = 224\n'
    '    indian_recognition_model_path: Path = Path("artifacts/indian_food_v1/indian_food_classifier.ts")\n'
    '    indian_recognition_labels_path: Path = Path("artifacts/indian_food_v1/classes.json")\n'
    '    indian_recognition_model_version: str = "indian-food-v1"\n'
    '    indian_recognition_confidence_threshold: float = 0.65\n'
    '    indian_recognition_temperature: float = 0.583016488786505\n',
    "settings insertion",
)
s = replace_once(
    s,
    '    @field_validator("recognition_image_size")\n',
    '    @field_validator("indian_recognition_confidence_threshold")\n'
    '    @classmethod\n'
    '    def validate_indian_confidence_threshold(cls, value: float) -> float:\n'
    '        if not 0.0 <= value <= 1.0:\n'
    '            raise ValueError("INDIAN_RECOGNITION_CONFIDENCE_THRESHOLD must be between 0 and 1")\n'
    '        return value\n\n'
    '    @field_validator("indian_recognition_temperature")\n'
    '    @classmethod\n'
    '    def validate_indian_temperature(cls, value: float) -> float:\n'
    '        if not 0.05 <= value <= 20.0:\n'
    '            raise ValueError("INDIAN_RECOGNITION_TEMPERATURE must be between 0.05 and 20")\n'
    '        return value\n\n'
    '    @field_validator("recognition_image_size")\n',
    "indian validators",
)
backup(rel); write(rel, s)

# 2. Runtime temperature scaling
rel = "backend/app/services/recognition/provider.py"
s = read(rel)
s = replace_once(
    s,
    '    def __init__(self, model_path: Path) -> None:\n',
    '    def __init__(self, model_path: Path, temperature: float = 1.0) -> None:\n',
    "TorchScriptRuntime constructor",
)
s = replace_once(
    s,
    '        self._torch = torch\n        self._model = torch.jit.load(str(model_path), map_location="cpu")\n',
    '        if not 0.05 <= temperature <= 20.0:\n'
    '            raise ValueError("temperature must be between 0.05 and 20")\n'
    '        self._torch = torch\n'
    '        self._temperature = temperature\n'
    '        self._model = torch.jit.load(str(model_path), map_location="cpu")\n',
    "runtime temperature state",
)
s = replace_once(
    s,
    '            probabilities = self._torch.softmax(logits, dim=1)[0]\n',
    '            probabilities = self._torch.softmax(logits / self._temperature, dim=1)[0]\n',
    "runtime calibrated softmax",
)
s = replace_once(
    s,
    '    image_size: int,\n) -> PredictionProvider:\n',
    '    image_size: int,\n    temperature: float = 1.0,\n) -> PredictionProvider:\n',
    "provider factory signature",
)
s = replace_once(
    s,
    '        runtime = TorchScriptRuntime(model_path)\n',
    '        runtime = TorchScriptRuntime(model_path, temperature=temperature)\n',
    "provider factory runtime",
)
backup(rel); write(rel, s)

# 3. Recognition route: keep old zero-arg provider for compatibility
rel = "backend/app/api/routes/recognition.py"
s = read(rel)
s = s.replace(
    'from functools import lru_cache\n',
    'from functools import lru_cache\nfrom typing import Literal\n',
    1,
)
s = replace_once(
    s,
    '\n@router.post("/predict", response_model=RecognitionResponse)\nasync def predict_food(file: UploadFile = File(...)) -> RecognitionResponse:\n',
    '\n@lru_cache\n'
    'def get_indian_prediction_provider() -> PredictionProvider:\n'
    '    settings = get_settings()\n'
    '    return build_prediction_provider(\n'
    '        settings.indian_recognition_model_path,\n'
    '        settings.indian_recognition_labels_path,\n'
    '        settings.indian_recognition_model_version,\n'
    '        settings.indian_recognition_confidence_threshold,\n'
    '        settings.recognition_image_size,\n'
    '        settings.indian_recognition_temperature,\n'
    '    )\n'
    '\n@router.post("/predict", response_model=RecognitionResponse)\n'
    'async def predict_food(\n'
    '    file: UploadFile = File(...),\n'
    '    model: Literal["food101", "indian"] = "food101",\n'
    ') -> RecognitionResponse:\n',
    "recognition route provider and query selector",
)
s = replace_once(
    s,
    '        result = get_prediction_provider().predict(image.content)\n',
    '        provider = get_indian_prediction_provider() if model == "indian" else get_prediction_provider()\n'
    '        result = provider.predict(image.content)\n',
    "recognition route provider dispatch",
)
backup(rel); write(rel, s)

# 4. Frontend API client
rel = "frontend/src/lib/api.ts"
s = read(rel)
s = replace_once(
    s,
    '  recognize: (file: File) => {\n',
    '  recognize: (file: File, model: "food101" | "indian" = "food101") => {\n',
    "frontend recognize signature",
)
s = replace_once(
    s,
    '    return request<Recognition>("/recognition/predict", {\n',
    '    return request<Recognition>(`/recognition/predict?model=${model}`, {\n',
    "frontend recognize query",
)
backup(rel); write(rel, s)

# 5. Dashboard state, handler and UI
rel = "frontend/src/app/page.tsx"
s = read(rel)
s = replace_once(
    s,
    '  const [recognition, setRecognition] = useState<Recognition | null>(null);\n',
    '  const [recognition, setRecognition] = useState<Recognition | null>(null);\n'
    '  const [recognitionModel, setRecognitionModel] = useState<"food101" | "indian">("indian");\n',
    "recognition model state",
)
s = replace_once(
    s,
    '    try { setRecognition(await api.recognize(image)); }\n',
    '    try { setRecognition(await api.recognize(image, recognitionModel)); }\n',
    "recognition handler",
)
# Add model selector to the Food Scan upload panel after introductory paragraph.
anchor = '<div className="scan-layout"><section className="upload-panel">'
replacement = (
    '<div className="scan-layout"><section className="upload-panel">'
    '<label className="field-label" htmlFor="recognition-model">Recognition model</label>'
    '<select id="recognition-model" value={recognitionModel} '
    'onChange={e=>{setRecognitionModel(e.target.value as "food101" | "indian");setRecognition(null);}}>'
    '<option value="indian">Indian foods · 15 classes</option>'
    '<option value="food101">Food-101 · 101 classes</option>'
    '</select>'
)
s = replace_once(s, anchor, replacement, "Food Scan model selector")
backup(rel); write(rel, s)

# 6. Compose environment variables for the Indian model.
rel = "docker-compose.yml"
s = read(rel)
s = replace_once(
    s,
    '      RECOGNITION_IMAGE_SIZE: "224"\n',
    '      RECOGNITION_IMAGE_SIZE: "224"\n'
    '      INDIAN_RECOGNITION_MODEL_PATH: /app/artifacts/indian_food_v1/indian_food_classifier.ts\n'
    '      INDIAN_RECOGNITION_LABELS_PATH: /app/artifacts/indian_food_v1/classes.json\n'
    '      INDIAN_RECOGNITION_MODEL_VERSION: indian-food-v1\n'
    '      INDIAN_RECOGNITION_CONFIDENCE_THRESHOLD: "0.65"\n'
    '      INDIAN_RECOGNITION_TEMPERATURE: "0.583016488786505"\n',
    "compose insertion",
)
backup(rel); write(rel, s)

print("Indian recognition integration changes applied.")
print("Food-101 defaults remain unchanged.")
print("Indian temperature calibration is applied to logits before softmax.")
print("Backups use the suffix .before-indian-model.")
