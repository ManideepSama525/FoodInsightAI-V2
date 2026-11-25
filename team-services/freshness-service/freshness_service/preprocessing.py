from PIL import Image
from torchvision import transforms


IMAGE_SIZE = 224

evaluation_transform = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(IMAGE_SIZE),
    transforms.ToTensor(),
    transforms.Normalize(
        mean=(0.485, 0.456, 0.406),
        std=(0.229, 0.224, 0.225),
    ),
])


def preprocess_image(image: Image.Image):
    return evaluation_transform(image.convert("RGB"))
