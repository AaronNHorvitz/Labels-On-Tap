# Accessibility

Labels On Tap is designed for quick review by non-technical users and older reviewers. The sprint UI uses server-rendered HTML, native form controls, high-contrast status badges, and plain-language result text.

## Implemented Patterns

- Native buttons, links, selects, file inputs, and form labels.
- Visible Pass / Needs Review / Fail text alongside color.
- Large demo actions on the home page.
- Linear page structure: demo/upload, results, detail.
- Server-rendered pages that work without a frontend build step.
- Local CSS and vendored HTMX, with no CDN dependency.
- Result detail pages that expose expected values, observed values, source refs, and reviewer actions.

## Submission Check

Before final submission, manually verify:

- keyboard tab order reaches demo buttons, upload fields, result links, and CSV export,
- focus outlines are visible,
- status meaning is not color-only,
- labels are associated with inputs,
- result detail text remains readable on mobile width,
- CSV export link is reachable without mouse-only interaction.

## Production Gap

This repository has not undergone a formal Section 508 audit. A production federal implementation would need accessibility testing with assistive technology, documented remediation, and review under the agency's accessibility process.
