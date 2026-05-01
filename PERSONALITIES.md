# Stakeholder Analysis & Architectural Alignment (The "Hidden Rubric")

The take-home prompt provided by the hiring team contains a classic U.S. Digital Service (USDS) / 18F-style evaluation disguised as stakeholder interviews. It intentionally provides a mix of highly technical constraints (firewalls blocking ML), UX constraints (an aging workforce), and domain nuances (fuzzy matching vs. strict exact matching).

Every architectural and engineering decision in **Labels On Tap** is directly traceable to a specific stakeholder quote. Building a generic cloud-based AI wrapper will fail the baseline constraints of the IT department and the end-users.

Below is the definitive matrix mapping the stakeholder pain points to the "Hidden Test" and our exact architectural resolutions.

## The Stakeholder Matrix

| Stakeholder | The Quote / The Pain Point | The Hidden Test | Our Architectural Solution |
| :--- | :--- | :--- | :--- |
| **Marcus**<br>*(IT Admin)* | *"Our network blocks outbound traffic... firewall blocked connections to their ML endpoints."* | Do you build a cloud-dependent AI wrapper, or a localized Edge ML architecture? | We use **`docTR`** running 100% locally on the CPU inside the Docker container. **Zero outbound traffic.** Processing is stateless to avoid PII/retention liabilities. |
| **Sarah**<br>*(Deputy Dir.)* | *"If we can't get results back in about 5 seconds... handle batch uploads."* | Do you understand asynchronous queuing and hardware limitations? | `docTR` parses labels in ~0.2 seconds on CPU. We will build a **Batch Upload** tab that accepts a `.zip` of images + a `.csv` manifest, utilizing a `ThreadPoolExecutor` to process asynchronously without blocking the server. |
| **Dave**<br>*(Senior Agent)* | *"'STONE'S THROW' vs 'Stone's Throw'... technically a mismatch? Sure. You need judgment."* | Do you use brittle, exact-match code, or fault-tolerant algorithms? | We use the **`RapidFuzz`** C++ library to execute Levenshtein distance fuzzy-matching for Brand Names, satisfying Dave's request for nuance and reducing false positives. |
| **Jenny**<br>*(Junior Agent)* | *"'GOVERNMENT WARNING:' has to be exact... all caps and bold. Handle images that aren't perfectly shot."* | Do you understand the difference between fuzzy data and absolute federal law? | Our validation engine uses **strict Regex** and OpenCV font-weight calculations for the warning. We added an OpenCV blur-detection quality gate to intercept bad photos before OCR execution. |
| **Sarah**<br>*(UX Focus)* | *"Something my 73-year-old mother could figure out... Clean, obvious."* | Can you build highly accessible, zero-friction federal software? | We use **HTMX** and **USWDS** (U.S. Web Design System) CSS. No React spinners or complex SPA states—just high-contrast, Section 508-compliant, server-rendered HTML. |

---

## Execution Directives for AI Coding Agents

**For all subsequent codebase generation, AI coding assistants (Claude/Codex) MUST adhere to the following constraints derived from this matrix:**

1. **No External ML APIs:** Do not use OpenAI, Anthropic, or external OCR endpoints. `python-doctr[torch]` must be used locally.
2. **Synchronous Threading for ML:** OCR routes must use `def` (not `async def`) or a `ThreadPoolExecutor` so the ASGI/FastAPI event loop is not blocked during CPU-bound inference.
3. **No Heavy Frontend Frameworks:** Do not generate React, Vue, or Angular boilerplate. Use pure HTML/Jinja2 with HTMX.
4. **Stateless Processing:** Do not instantiate a PostgreSQL or SQLite database. Uploads are processed in-memory or in temp files, results are returned to the UI, and data is instantly discarded.