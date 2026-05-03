# Accessibility

Labels On Tap is designed for quick review by non-technical users and older reviewers. The sprint UI uses server-rendered HTML, native form controls, high-contrast status badges, and plain-language result text.

## Implemented Patterns

- Native buttons, links, selects, file inputs, and form labels.
- Visible Pass / Needs Review / Fail text alongside color.
- Future reviewer-policy queues must also use visible text such as Ready to
  accept, Acceptance review, Manual evidence review, Rejection review, and Ready
  to reject, not color alone.
- The future policy control board should use explicit labeled toggles for
  unknown warning review, acceptance review, and rejection review. The warning
  control must include visible helper text explaining that warning-unknown
  cases fail by default when human review is off.
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
- reviewer-policy queue names are text-readable and keyboard reachable if/when
  the queue layer is implemented,
- labels are associated with inputs,
- result detail text remains readable on mobile width,
- CSV export link is reachable without mouse-only interaction.

## Production Gap

This repository has not undergone a formal Section 508 audit. A production federal implementation would need accessibility testing with assistive technology, documented remediation, and review under the agency's accessibility process.
