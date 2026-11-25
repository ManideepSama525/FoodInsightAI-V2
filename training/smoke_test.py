import time
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Subset
from torchvision import datasets, transforms, models
from torchvision.models import EfficientNet_V2_S_Weights

assert torch.cuda.is_available(), "CUDA unavailable"

device = torch.device("cuda")
torch.cuda.reset_peak_memory_stats()

transform = transforms.Compose([
    transforms.Resize(256),
    transforms.RandomResizedCrop(224, scale=(0.75, 1.0)),
    transforms.RandomHorizontalFlip(),
    transforms.ToTensor(),
    transforms.Normalize(
        mean=(0.485, 0.456, 0.406),
        std=(0.229, 0.224, 0.225),
    ),
])

print("Loading Food-101 subset...", flush=True)
dataset = datasets.Food101(
    root="/workspace/data/food101",
    split="train",
    download=False,
    transform=transform,
)
subset = Subset(dataset, list(range(32)))
loader = DataLoader(subset, batch_size=4, shuffle=True, num_workers=0)

print("Loading pretrained EfficientNetV2-S...", flush=True)
model = models.efficientnet_v2_s(
    weights=EfficientNet_V2_S_Weights.DEFAULT
)
model.classifier[1] = nn.Linear(model.classifier[1].in_features, 101)
model = model.to(device)

optimizer = torch.optim.AdamW(model.parameters(), lr=0.0001)
criterion = nn.CrossEntropyLoss()
scaler = torch.amp.GradScaler("cuda")

model.train()
start = time.time()

for step, (images, labels) in enumerate(loader):
    if step == 2:
        break

    images = images.to(device)
    labels = labels.to(device)
    optimizer.zero_grad(set_to_none=True)

    with torch.autocast("cuda", dtype=torch.float16):
        logits = model(images)
        loss = criterion(logits, labels)

    scaler.scale(loss).backward()
    scaler.step(optimizer)
    scaler.update()

    print(
        f"Batch {step + 1}/2 | loss={loss.item():.4f} | "
        f"elapsed={time.time() - start:.1f}s",
        flush=True,
    )

print("\nSMOKE TEST PASSED")
print("GPU:", torch.cuda.get_device_name(0))
print("Peak allocated VRAM GB:",
      round(torch.cuda.max_memory_allocated() / 1024**3, 2))
print("Peak reserved VRAM GB:",
      round(torch.cuda.max_memory_reserved() / 1024**3, 2))
print("Elapsed seconds:", round(time.time() - start, 2))
