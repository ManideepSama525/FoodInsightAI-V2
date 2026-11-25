# Food classifier training handoff

Phase 4 delivers the inference contract and preprocessing adapter. It does **not** train a model or claim accuracy. Model training remains a project task and requires a legally usable, labelled food-image dataset.

## Dataset layout

Keep source datasets outside Git. A simple layout is:

```text
datasets/food/
  images/
    dosa/
    idli/
    biryani/
  splits/
    train.csv
    validation.csv
    test.csv
```

Each split CSV must contain `image_path,label`. Paths should be relative to the dataset root. Avoid placing near-duplicate images or images from the same capture session in different splits. Preserve dataset license and source metadata.

## Training requirements

1. Freeze a class taxonomy and document ambiguous/mixed-food rules.
2. Deduplicate images and split by source/subject/session before augmentation.
3. Establish a simple baseline, then evaluate transfer learning.
4. Use training-only augmentation; keep validation/test preprocessing deterministic.
5. Report per-class precision, recall, F1, macro-F1, top-1/top-5 accuracy, confusion matrix, and class support.
6. Calibrate confidence on validation data and select the review threshold based on error costs.
7. Export the selected model as TorchScript and write `artifacts/classes.json` in output-index order.
8. Record dataset provenance, license, class mapping, preprocessing, seed, hyperparameters, metrics, and model version.

## Inference contract

The exported model must accept a batch tensor shaped `[N, 3, 224, 224]` with RGB values normalized using ImageNet mean `[0.485, 0.456, 0.406]` and standard deviation `[0.229, 0.224, 0.225]`. It must return logits shaped `[N, number_of_classes]`.

Install training/inference extras with `pip install -e ".[vision]"`. Keep model weights and datasets out of Git; use an artifact store or local ignored `artifacts/` directory.
