# Public COLA ETL Runbook

This runbook describes the local-only ETL path for turning public TTB Public COLA Registry records into curated Labels On Tap fixtures.

The deployed app must not scrape the registry at runtime. ETL work happens locally under `data/work/`, then a small set of reviewed fixtures can be exported into `data/fixtures/public-cola/`.

## Data Flow

```text
TTB public registry search CSV
  -> local SQLite registry index
  -> public printable Form 5100.31 HTML by TTB ID
  -> parsed application JSON + attachment metadata
  -> downloaded public label images
  -> curated fixture export
```

When TTBOnline.gov is unavailable, the COLA Cloud sample pack can be imported
as a development-only fallback corpus:

```text
COLA Cloud sample pack ZIP
  -> local SQLite registry index
  -> parsed application JSON
  -> CloudFront label image download
  -> local PNG conversion
  -> local OCR evaluation
```

This fallback is for local development and OCR measurement only. The deployed
application must not depend on COLA Cloud or any hosted data API at runtime.
COLA Cloud's OCR fields are third-party silver labels, not Labels On Tap ground
truth.

## Local Workspace

Bulk ETL artifacts are gitignored:

```text
data/work/
  public-cola/
    raw/
      search-results/
      forms/
      images/
    parsed/
      applications/
      ocr/
    registry.sqlite
```

Curated official fixtures can be committed only after review:

```text
data/fixtures/public-cola/
  <ttb_id>/
    source.html
    application.json
    labels/
    expected.json
    provenance.json
```

## Commands

Initialize the workspace and SQLite database:

```bash
python scripts/init_public_cola_workspace.py
```

Import a CSV downloaded from the registry search page:

```bash
python scripts/import_public_cola_search_results.py path/to/search-results.csv --copy-raw
```

Fetch a few public printable forms slowly:

```bash
python scripts/fetch_public_cola_forms.py --missing-only --limit 5 --delay 3 --jitter 1
```

Or fetch a known TTB ID:

```bash
python scripts/fetch_public_cola_forms.py --ttb-id 03235001000005 --delay 3 --jitter 1
```

If the local machine cannot validate the TTB certificate chain, keep the run local and add `--insecure` for the ETL fetch only:

```bash
python scripts/fetch_public_cola_forms.py --ttb-id 03235001000005 --delay 3 --jitter 1 --insecure
```

Parse saved form HTML into structured JSON and attachment metadata:

```bash
python scripts/parse_public_cola_forms.py --limit 5
```

Download parsed public label image attachments slowly:

```bash
python scripts/download_public_cola_images.py --limit 10 --delay 2 --jitter 1
```

The attachment downloader validates every response with Pillow before accepting
it as an OCR-ready image. This is important because the public attachment
endpoint can return an HTML error page with HTTP 200 when an image cannot be
rendered. Invalid responses are marked pending in SQLite instead of being saved
as successful label images.

Audit locally downloaded attachments before OCR:

```bash
python scripts/audit_public_cola_images.py
```

If the audit finds invalid rows, clear those SQLite paths so the downloader can
retry them later:

```bash
python scripts/audit_public_cola_images.py --mark-invalid
```

When the TTB image endpoint works in a browser but not through automated HTTP,
export a browser-download manifest:

```bash
python scripts/export_public_cola_attachment_links.py \
  --ttb-id 25337001000464 \
  --output data/work/public-cola/sampling/manual-attachment-links.csv
```

Open the parent form first, then download each attachment link in the same
browser session. After the image files are saved locally, import and validate
them:

```bash
python scripts/import_manual_public_cola_images.py ~/Downloads \
  --ttb-id 25337001000464 \
  --recursive
```

For ambiguous or renamed browser downloads, create a CSV with
`ttb_id,panel_order,path` and import it explicitly:

```bash
python scripts/import_manual_public_cola_images.py ~/Downloads \
  --manifest data/work/public-cola/sampling/manual-image-map.csv
```

Import the COLA Cloud sample pack when TTBOnline.gov is down:

```bash
python scripts/import_colacloud_sample_pack.py \
  ~/Downloads/cola-sample-pack-v1.zip \
  --limit 100 \
  --download-images \
  --image-limit 250
```

The importer reads `cola.csv` and `cola_image.csv`, creates parsed application
JSON files, downloads CloudFront WebP label images, validates them with Pillow,
converts them to PNG, and records the image paths in the local SQLite index.
All artifacts remain under gitignored `data/work/public-cola/`.

Evaluate OCR field matching against downloaded public COLA records:

```bash
python scripts/evaluate_public_cola_ocr.py --limit 25 --run-name pilot-25
```

If the host shell does not have docTR installed, run the evaluator through the
app container and bind-mount the gitignored work directory:

```bash
docker compose run --rm \
  -v "$PWD/data/work:/app/data/work" \
  app python scripts/evaluate_public_cola_ocr.py --limit 25 --run-name pilot-25
```

Podman equivalent for Fedora/Kinoite-style local development:

```bash
podman run --rm \
  -v "$PWD/data/work:/app/data/work:Z" \
  -v "$PWD/data/work/model-cache:/root/.cache:Z" \
  labels-on-tap-app:local \
  python scripts/evaluate_public_cola_ocr.py --limit 25 --run-name pilot-25
```

The evaluator does not contact the public registry. It reads parsed
applications and validated downloaded label images from `data/work/public-cola/`,
runs or reuses local OCR, and writes outputs under:

```text
data/work/public-cola/parsed/ocr/
  panels/<ttb_id>/*.json
  evaluations/<run-name>/
    summary.json
    applications.json
    application_results.csv
    field_results.csv
```

Each COLA application is treated as one evidence bundle that may contain many
label panels. The evaluator OCRs each panel separately, preserves panel-level
evidence, aggregates OCR text across panels, and compares application fields
against the full label-artwork bundle.

Do not treat an OCR run as valid until `audit_public_cola_images.py` reports
readable image files. Parsed forms and attachment metadata are still valuable,
but field-level OCR metrics require real raster label panels.

Export a reviewed public record into a committed fixture folder:

```bash
python scripts/export_public_cola_fixtures.py --ttb-id 03235001000005
```

## Politeness Controls

Network-touching commands default to delays between requests. Keep those delays on unless doing a single known TTB ID.

Recommended first pass:

```text
forms: 3 seconds + up to 1 second jitter
images: 2 seconds + up to 0.75 second jitter
limits: 5 to 25 records while developing
```

This is enough for fixture curation without hammering the public registry.

## Parser Contract

The parser extracts:

- `ttb_id`
- plant/basic permit
- source of product
- serial number
- product type
- brand name
- fanciful name
- applicant name/address
- formula ID
- net contents
- alcohol content
- special wording/translations
- application type
- status
- class/type description
- every public label attachment URL with panel order, filename, image type, dimensions, and alt text

## OCR Evaluation Contract

Accepted public COLAs are used as positive ground truth for field matching, not
as proof of every legal-compliance rule. The evaluation asks a narrower question:

```text
Given accepted public application data and its accepted label artwork,
can local OCR recover enough label text to confirm the application fields?
```

The first evaluation fields are:

- brand name,
- fanciful name when present,
- class/type,
- alcohol content,
- net contents,
- country of origin for imported records when registry origin data is available,
- applicant/producer/bottler text when visible.

Synthetic negative fixtures remain necessary for mismatch and Needs Correction
coverage because confidential rejected applications are not public.

The first parser target is the public printable Form 5100.31 HTML exposed by:

```text
https://ttbonline.gov/colasonline/viewColaDetails.do?action=publicFormDisplay&ttbid=<TTB_ID>
```

## Boundary

This ETL only uses public registry records. It does not log into COLAs Online, does not fetch private applications, and does not replace synthetic negative fixtures for confidential rejected or Needs Correction scenarios.
