# Validation Rules

        The validation engine separates rules into:

        1. Strict deterministic compliance checks.
        2. Fuzzy application-vs-label matching.
        3. Numeric/unit normalization.
        4. Image and upload preflight checks.
        5. Risk-based Needs Review heuristics.

        These rules produce raw triage verdicts: Pass, Needs Review, or Fail.
        A separate reviewer-policy layer should map those raw verdicts into
        workflow queues such as Ready to accept, Acceptance review, Manual
        evidence review, Rejection review, or Ready to reject. This keeps rule
        evidence separate from final agency action.

        See:

        ```text
        research/legal-corpus/matrices/source-backed-criteria.json
        ```
