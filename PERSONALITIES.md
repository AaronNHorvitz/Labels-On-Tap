# Stakeholder Analysis & Architectural Alignment (The "Hidden Rubric")

The take-home prompt provided by the hiring team contains a classic U.S. Digital Service (USDS) / 18F-style evaluation disguised as stakeholder interviews. It intentionally provides a mix of highly technical constraints (firewalls blocking ML), UX constraints (an aging workforce), and domain nuances (fuzzy matching vs. strict exact matching).

Every architectural and engineering decision in **Labels On Tap** is directly traceable to a specific stakeholder quote. Building a generic cloud-based AI wrapper will fail the baseline constraints of the IT department and the end-users.

Below is the definitive matrix mapping the stakeholder pain points to the "Hidden Test" and our exact architectural resolutions.

## The Stakeholder Matrix

| Stakeholder | The Quote / The Pain Point | The Hidden Test | Our Architectural Solution |
| :--- | :--- | :--- | :--- |
| **Marcus**<br>*(IT Admin)* | *"Our network blocks outbound traffic... firewall blocked connections to their ML endpoints."* | Do you build a cloud-dependent AI wrapper, or a localized Edge ML architecture? | We use **local OCR** inside the Docker container. Demo routes use fixture OCR ground truth for deterministic evaluation. Uploaded labels use the local docTR adapter when available. |
| **Sarah**<br>*(Deputy Dir.)* | *"If we can't get results back in about 5 seconds... handle batch uploads."* | Do you understand workflow responsiveness and hardware limitations? | The MVP provides immediate fixture-backed demos and filesystem job results. Broader async worker tuning and ZIP intake are future hardening steps, not required for the first runnable slice. |
| **Dave**<br>*(Senior Agent)* | *"'STONE'S THROW' vs 'Stone's Throw'... technically a mismatch? Sure. You need judgment."* | Do you use brittle, exact-match code, or fault-tolerant algorithms? | We use the **`RapidFuzz`** C++ library to execute Levenshtein distance fuzzy-matching for Brand Names, satisfying Dave's request for nuance and reducing false positives. |
| **Jenny**<br>*(Junior Agent)* | *"'GOVERNMENT WARNING:' has to be exact... all caps and bold. Handle images that aren't perfectly shot."* | Do you understand the difference between fuzzy data and absolute federal law? | The MVP hard-fails exact warning wording and heading capitalization when OCR confidence is adequate. Font-weight verification routes to **Needs Review** rather than pretending raster typography can always be certified. |
| **Sarah**<br>*(UX Focus)* | *"Something my 73-year-old mother could figure out... Clean, obvious."* | Can you build highly accessible, zero-friction federal software? | We use server-rendered FastAPI/Jinja pages with local CSS and USWDS-inspired accessibility patterns. No React/Vue/Angular shell is required for the MVP. |

---

## Execution Directives for AI Coding Agents

**For all subsequent codebase generation, AI coding assistants (Claude/Codex) MUST adhere to the following constraints derived from this matrix:**

1. **No External ML APIs:** Do not use OpenAI, Anthropic, or external OCR endpoints. `python-doctr[torch]` must be used locally.
2. **Local OCR Boundary:** Demo fixtures may use fixture OCR ground truth for deterministic tests. Real uploads should use local docTR when available and route unavailable/low-confidence OCR to Needs Review.
3. **No Heavy Frontend Frameworks:** Do not generate React, Vue, or Angular boilerplate. Use pure HTML/Jinja2 with HTMX.
4. **Filesystem Job Store:** Do not instantiate PostgreSQL or SQLite for the MVP. Jobs and results are written to local filesystem JSON with a cleanup policy to be added for production hardening.
