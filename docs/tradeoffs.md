# Trade-Offs

The root `TRADEOFFS.md` is the canonical trade-off summary for submission.

Short version:

- Local OCR/model execution avoids hosted ML dependencies.
- Deterministic rules decide compliance; models only support evidence.
- DistilRoBERTa field support is optional and not a legal authority.
- Warning-heading boldness uses a conservative low-latency model.
- Batch jobs use a local filesystem-backed durable queue for the MVP.
- ZIP upload is supported only for manifest-backed image batches with guardrails.
- Reviewer dashboard exists, but auth/admin/roles are future production work.
- Graph scorer and CNN-inclusive typography ensembles are documented future
  promotion candidates, not hidden runtime claims.
