"""Source-backed rule engine exports.

Notes
-----
The public entrypoint is ``verify_label``. It turns parsed application data and
OCR evidence into rule checks, verdicts, evidence snippets, and reviewer-facing
messages.
"""

from app.services.rules.registry import verify_label

__all__ = ["verify_label"]
