import torch
import torch.nn as nn
from torchvision.models import efficientnet_v2_s, EfficientNet_V2_S_Weights


class FreshnessModel(nn.Module):
    """EfficientNetV2-S with category-specific classification heads."""

    def __init__(
        self,
        category_names,
        label_to_idx,
        pretrained=True,
        dropout=0.30,
    ):
        super().__init__()

        self.category_names = list(category_names)
        self.category_to_idx = {
            name: index
            for index, name in enumerate(self.category_names)
        }

        if set(self.category_names) != set(label_to_idx):
            raise ValueError("Category and label mappings do not match")

        weights = (
            EfficientNet_V2_S_Weights.DEFAULT if pretrained else None
        )

        backbone = efficientnet_v2_s(weights=weights)
        self.feature_dim = backbone.classifier[1].in_features
        backbone.classifier = nn.Identity()

        self.backbone = backbone
        self.dropout = nn.Dropout(p=dropout)

        self.label_to_idx = {
            category: dict(label_to_idx[category])
            for category in self.category_names
        }

        self.idx_to_label = {
            category: {index: label for label, index in mapping.items()}
            for category, mapping in self.label_to_idx.items()
        }

        self.heads = nn.ModuleDict()

        for category_idx, category in enumerate(self.category_names):
            mapping = self.label_to_idx[category]

            if not mapping:
                raise ValueError(f"No labels for category: {category}")

            if sorted(mapping.values()) != list(range(len(mapping))):
                raise ValueError(f"Invalid label indices for {category}")

            self.heads[f"category_{category_idx}"] = nn.Linear(
                self.feature_dim,
                len(mapping),
            )

    def forward(self, images, category_indices):
        if images.ndim != 4 or category_indices.ndim != 1:
            raise ValueError("Invalid image or category tensor dimensions")

        if images.shape[0] != category_indices.shape[0]:
            raise ValueError("Image and category batch sizes differ")

        if category_indices.numel() == 0:
            raise ValueError("Empty batches are not supported")

        category_indices = category_indices.to(
            device=images.device,
            dtype=torch.long,
        )

        if (
            category_indices.min().item() < 0
            or category_indices.max().item() >= len(self.category_names)
        ):
            raise ValueError("Unknown category index")

        features = self.dropout(self.backbone(images))
        outputs = {}

        for category_idx in category_indices.unique(sorted=True).tolist():
            batch_indices = (
                category_indices == category_idx
            ).nonzero(as_tuple=False).squeeze(1)

            category_features = features.index_select(0, batch_indices)
            logits = self.heads[f"category_{category_idx}"](
                category_features
            )

            outputs[category_idx] = (batch_indices, logits)

        return outputs

    def predict_labels(self, category_idx, logits):
        if category_idx < 0 or category_idx >= len(self.category_names):
            raise ValueError("Unknown category index")

        category = self.category_names[category_idx]

        return [
            self.idx_to_label[category][index]
            for index in logits.argmax(dim=1).tolist()
        ]
