# Stakeholder Alignment

The prompt's stakeholder interviews define the product constraints.

| Stakeholder | Concern | Product Response |
|---|---|---|
| Sarah Chen | Agents spend too much time doing routine field matching and need batch support. | Single, multi-panel, and batch workflows; reviewer dashboard; queue-backed processing. |
| Marcus Williams | Government networks may block hosted ML endpoints. | Local OCR/model runtime with no hosted OCR or hosted ML APIs. |
| Dave Morrison | Review needs judgment; exact string matching can be too brittle. | Fuzzy matching for human-equivalent field differences; uncertain evidence routes to review. |
| Jenny Park | Government warning text must be exact, all caps, and bold. | Strict warning text/caps rules plus conservative warning-heading boldness preflight. |
| Sarah / team | UI must be obvious for mixed technical comfort levels. | Server-rendered pages, clear buttons, result tables, evidence detail, and CSV export. |

## Design Principles

- Keep reviewers in control.
- Explain every fail/review reason.
- Treat uncertainty as `Needs Review`.
- Keep label images local at runtime.
- Optimize for batch triage, not final agency action.
