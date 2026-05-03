# Field-Support Classifier Experiments

These experiments train BERT-family classifiers over the field-support pair
manifests generated from the 6,000-record COLA Cloud-derived public corpus.

The current dataset is weak supervision:

```text
application field value
  + candidate evidence value
  -> supports field? yes/no
```

Positive candidate values come from the same accepted public COLA application.
Negative candidate values are same-field values shuffled from other
applications in the same split. OCR evidence is attached in a later stage, so
these results prove that a text-pair arbiter can learn the support relation;
they do not prove final OCR extraction accuracy.

## Current Runs

Run outputs are intentionally gitignored under:

```text
data/work/field-support-models/
```

Commands:

```bash
.venv-gpu/bin/python experiments/field_support/train_transformer_pair_classifier.py \
  --model-id distilroberta-base \
  --run-name distilroberta-field-support-v1-e1 \
  --epochs 1 \
  --batch-size 64 \
  --eval-batch-size 128 \
  --max-length 128 \
  --device cuda \
  --false-clear-tolerance 0.005 \
  --cpu-latency-rows 512

.venv-gpu/bin/python experiments/field_support/train_transformer_pair_classifier.py \
  --model-id roberta-base \
  --run-name roberta-base-field-support-v1-e1 \
  --epochs 1 \
  --batch-size 48 \
  --eval-batch-size 96 \
  --max-length 128 \
  --device cuda \
  --false-clear-tolerance 0.005 \
  --cpu-latency-rows 512
```

Both runs used:

- `2,000` train applications
- `1,000` validation applications
- `3,000` locked holdout applications
- `31,008` train pair examples
- `15,417` validation pair examples
- `46,992` holdout pair examples
- validation-tuned threshold: `0.99`

## Results

| Model | Train Time | Holdout Accuracy | Holdout Precision | Holdout Recall | Holdout Specificity | Holdout F1 | False-Clear Rate | CPU Mean / Pair |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DistilRoBERTa | 36.5 s | 0.999915 | 0.999745 | 1.000000 | 0.999872 | 0.999872 | 0.000128 | 15.76 ms |
| RoBERTa-base | 73.7 s | 0.999851 | 0.999553 | 1.000000 | 0.999777 | 0.999777 | 0.000223 | 33.35 ms |

Interpretation:

- DistilRoBERTa is the better current candidate because it is faster and
  slightly stronger on the locked holdout in this run.
- RoBERTa-base did not justify the extra latency/capacity on this task.
- These metrics are intentionally not promoted as OCR accuracy. The next step
  is to attach docTR/PaddleOCR/OpenOCR evidence as candidate text and rerun the
  same train/validation/holdout procedure.
