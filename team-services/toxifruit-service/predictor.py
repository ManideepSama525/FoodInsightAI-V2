from io import BytesIO
from pathlib import Path

import torch
import torch.nn as nn
from PIL import Image
from torchvision import transforms
from torchvision.transforms import InterpolationMode
from torchvision.models import efficientnet_b0


MODEL_VERSION = "toxifruit-vegetable-grouped-letterbox-v2"


class Letterbox:
    def __init__(self, size=224, fill=(124, 116, 104)):
        self.size = size
        self.fill = fill

    def __call__(self, image):
        image = image.convert("RGB")
        width, height = image.size
        scale = min(self.size / width, self.size / height)

        new_width = max(1, round(width * scale))
        new_height = max(1, round(height * scale))

        image = transforms.functional.resize(
            image,
            [new_height, new_width],
            interpolation=InterpolationMode.BILINEAR,
        )

        canvas = Image.new("RGB", (self.size, self.size), self.fill)
        left = (self.size - new_width) // 2
        top = (self.size - new_height) // 2
        canvas.paste(image, (left, top))
        return canvas


class ToxiFruitPredictor:
    def __init__(self, checkpoint_path):
        self.device = torch.device("cpu")

        path = Path(checkpoint_path)
        if not path.is_file():
            raise FileNotFoundError(f"Model checkpoint not found: {path}")

        checkpoint = torch.load(
            path,
            map_location=self.device,
            weights_only=False,
        )

        self.class_names = checkpoint["class_names"]
        self.class_mapping = checkpoint["class_mapping"]

        if len(self.class_names) != 22 or len(self.class_mapping) != 22:
            raise ValueError("The combined checkpoint must contain exactly 22 classes.")

        if checkpoint.get("architecture") != "efficientnet_b0":
            raise ValueError("Unsupported model architecture.")

        if checkpoint.get("image_size") != 224:
            raise ValueError("Unexpected model input size.")

        self.fruit_classes = {
            "fresh_apple", "fresh_banana", "fresh_malta", "fresh_mango",
            "mixed_apple", "mixed_banana", "mixed_malta", "mixed_mango",
        }

        self.vegetable_classes = set(self.class_names) - self.fruit_classes

        self.fruit_mapping = {
            "Apple": "Apple",
            "Banana": "Banana",
            "Malta": "Malta",
            "Mango": "Mango",
        }

        self.condition_mapping = {
            "Fresh Apple": "fresh_control",
            "Formalin-treated Apple": "formalin_treated",
            "Fresh Banana": "fresh_control",
            "Formalin-treated Banana": "formalin_treated",
            "Fresh Malta": "fresh_control",
            "Formalin-treated Malta": "formalin_treated",
            "Fresh Mango": "fresh_control",
            "Formalin-treated Mango": "formalin_treated",
        }

        self.model = efficientnet_b0(weights=None)
        self.model.classifier[1] = nn.Linear(
            self.model.classifier[1].in_features,
            len(self.class_names),
        )
        self.model.load_state_dict(checkpoint["model_state_dict"], strict=True)
        self.model.to(self.device)
        self.model.eval()

        self.transform = transforms.Compose([
            Letterbox(224),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225],
            ),
        ])

    @torch.inference_mode()
    def predict_bytes(self, content: bytes) -> dict:
        with Image.open(BytesIO(content)) as image:
            image = image.convert("RGB")
            tensor = self.transform(image).unsqueeze(0).to(self.device)

        logits = self.model(tensor)
        probabilities = torch.softmax(logits, dim=1)[0]

        index = int(probabilities.argmax().item())
        folder_class = self.class_names[index]
        display_label = self.class_mapping[folder_class]
        is_fruit = folder_class in self.fruit_classes

        if is_fruit:
            fruit = display_label.split()[-1]
            condition = self.condition_mapping[display_label]
            category = "fruit"
        else:
            fruit = None
            condition = None
            category = "vegetable"

        return {
            "predicted_class": display_label,
            "fruit": fruit,
            "condition": condition,
            "category": category,
            "vegetable": display_label if not is_fruit else None,
            "confidence": round(float(probabilities[index].item()), 6),
            "probabilities": {
                self.class_mapping[name]: round(
                    float(probabilities[i].item()), 6
                )
                for i, name in enumerate(self.class_names)
            },
            "model": "EfficientNet-B0",
            "model_version": MODEL_VERSION,
            "interpretation": (
                "Visual screening for image patterns associated with "
                "the dataset's publisher-provided labels. This result "
                "does not chemically confirm formaldehyde, pesticide "
                "residues, or other contaminants. A fresh-control "
                "classification does not establish chemical safety."
            ),
        }
