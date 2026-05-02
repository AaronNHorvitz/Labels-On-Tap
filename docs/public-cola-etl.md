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

The first parser target is the public printable Form 5100.31 HTML exposed by:

```text
https://ttbonline.gov/colasonline/viewColaDetails.do?action=publicFormDisplay&ttbid=<TTB_ID>
```

## Boundary

This ETL only uses public registry records. It does not log into COLAs Online, does not fetch private applications, and does not replace synthetic negative fixtures for confidential rejected or Needs Correction scenarios.
