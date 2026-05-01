# Security and Privacy

Public prototype upload controls:

- extension allowlist for `.jpg`, `.jpeg`, and `.png`,
- path-component rejection,
- double-extension rejection,
- upload size limit,
- JPG/PNG magic-byte validation,
- Pillow decode validation after signature check,
- randomized server-side stored filenames,
- original upload filename preserved as metadata only,
- no ZIP upload in the sprint MVP,
- no hosted OCR or hosted ML endpoints,
- local filesystem job storage for prototype review.

Remaining prototype hardening items:

- old-job cleanup command or retention task,
- friendlier upload-error UI,
- production authentication and role-based access control,
- formal audit logging,
- records retention and destruction policy,
- vulnerability scanning and SBOM generation.

This is a prototype and does not implement production federal identity, audit logging, or records retention.
