# Research Summary

        Labels On Tap is built around a source-backed evidence chain:

        ```text
        Law / regulation / guidance / precedent
          → source-backed criterion
          → app rule
          → fixture/test
          → UI explanation
        ```

        Key decisions:

        - Runtime OCR and validation are local-first.
        - Hosted ML endpoints and VLMs are excluded from runtime.
        - The app is a preflight and reviewer-support prototype, not final agency action.
        - Raw Pass / Needs Review / Fail verdicts should feed configurable
          reviewer-policy queues before final acceptance or rejection.
        - Unknown government-warning evidence should be configurable: no human
          review is the default, and that default fails the label because the
          warning is mandatory; enabling the control routes the item to manual
          review instead.
        - Rejected/Needs Correction data is not treated as public fixture data.
        - Synthetic negative fixtures are used for controlled failure tests.
