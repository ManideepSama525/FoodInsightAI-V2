from io import BytesIO
from PIL import Image

from backend.app.services.recognition.preprocessing import prepare_image
from backend.app.services.recognition.provider import RawPrediction, RecognitionService

class FakeRuntime:
    def __init__(self, predictions):
        self.predictions = predictions

    def predict(self, image, top_k):
        assert image.mode == "RGB"
        assert image.size == (224, 224)
        return self.predictions[:top_k]

def make_image():
    buffer = BytesIO()
    Image.new("RGB", (640, 480), "red").save(buffer, format="JPEG")
    return buffer.getvalue()

def test_preprocessing_converts_to_square_rgb():
    prepared = prepare_image(make_image())
    assert prepared.image.mode == "RGB"
    assert prepared.image.size == (224, 224)
    assert (prepared.original_width, prepared.original_height) == (640, 480)

def test_high_confidence_prediction_is_returned():
    service = RecognitionService(FakeRuntime([RawPrediction(0, 0.91)]), ["idli"], "test-v1")
    result = service.predict(make_image())
    assert result.predicted_food == "idli"
    assert result.needs_review is False

def test_low_confidence_requires_user_review():
    service = RecognitionService(FakeRuntime([RawPrediction(0, 0.42)]), ["dosa"], "test-v1", 0.65)
    result = service.predict(make_image())
    assert result.predicted_food is None
    assert result.needs_review is True
    assert result.message is not None

def test_invalid_class_index_is_ignored():
    service = RecognitionService(FakeRuntime([RawPrediction(9, 0.99)]), ["rice"], "test-v1")
    result = service.predict(make_image())
    assert result.predicted_food is None
    assert result.needs_review is True
