# Product Requirements

## Problem

TTB label reviewers spend substantial time comparing COLA application fields
against label artwork. Many checks are routine matching tasks: brand name,
class/type, alcohol content, net contents, country of origin for imports, and
the mandatory government health warning.

The prototype should reduce routine review burden without removing human
judgment.

## Goals

- Provide a working web prototype at `https://www.labelsontap.ai`.
- Compare COLA-style application fields to OCR evidence from label images.
- Return `Pass`, `Needs Review`, or `Fail` with clear reasons.
- Support single-label, multi-panel, and batch workflows.
- Show reviewer queues for high-volume batches.
- Keep OCR/model execution local at runtime.
- Document assumptions, measurements, and trade-offs.

## Users

- Senior compliance agents who need judgment and clear evidence.
- Junior compliance agents who benefit from checklist automation.
- Managers who need batch triage across hundreds of applications.
- IT stakeholders who need a local-first, deployable prototype.

## In Scope

- Single-label upload.
- Multi-panel upload for one application.
- Manifest-backed batch upload with loose images or ZIP.
- Photo OCR intake demo.
- Public COLA side-by-side demo when local data is present.
- Reviewer dashboard.
- CSV export.
- Upload preflight and basic hardening.
- Deterministic source-backed rules.
- Optional field-support model evidence.
- Warning-heading boldness preflight.

## Out of Scope For Submission

- Authentication, roles, and admin portal.
- Final agency action.
- Direct private COLAs Online integration.
- Hosted OCR/ML APIs.
- Full legal rule coverage for every alcohol category.
- Production audit logging and retention.
- Production malware scanning.

## Success Criteria

- Public URL is reachable.
- Demo scenarios run without external data.
- Manual upload works.
- Batch upload works.
- ZIP upload works.
- Reviewer dashboard shows queue distribution.
- CSV export contains evidence and reviewer fields.
- Test suite passes.
- README explains setup, deployment, model results, and limitations.
