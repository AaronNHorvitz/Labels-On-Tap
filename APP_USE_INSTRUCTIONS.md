# Labels On Tap App Use Instructions

This guide explains how to use the deployed Labels On Tap prototype.

Public app:

```text
https://www.labelsontap.ai
```

## 1. Start At The Home Page

The home page has three navigation buttons:

- `Home`: returns to the landing page.
- `LOT Demo`: opens the server-hosted public COLA demonstration data.
- `LOT Actual`: opens the upload workspace for your own test data.

Use `LOT Demo` first. It is the fastest way to see the full workflow.

## 2. Use LOT Demo

`LOT Demo` contains 300 public COLA applications prepared for the live
walkthrough. Each application has application data and one or more label images.

On the demo page:

1. Use `Next Application` and `Previous Application` to move between
   applications.
2. Use `Next Photo` and `Previous Photo` to move between label images inside the
   selected application.
3. Look below the image viewer. The `Actual` column shows the data from the
   application record. The `Scraped` column is blank until parsing runs.
4. Choose a review mode:
   - `Human Review Required`: every parsed application keeps the reviewer
     accept/reject step.
   - `Auto-Route Clear Decisions`: clear pass/fail results are routed
     automatically. Uncertain evidence still goes to review.
5. Click `Parse This Application` to parse only the selected application.
6. Click `Parse This Directory of Applications` to parse the full 300-application
   demo set.
7. Click `Reset Demo` if you want to clear the visible parsed values and run the
   demo again.

When parsing finishes, the page shows scraped evidence beside the actual
application fields. This is the main thing to demonstrate: the app reads label
artwork and compares it to the application data.

## 3. Review Results

After a directory parse, the app opens a `Review Results` page.

This page shows:

- queue status,
- progress,
- total parse time,
- time per application,
- pass / needs review / fail counts,
- reviewer queue counts,
- result cards for each application,
- CSV export.

Each result card shows `Actual COLA Application Data` on the left and `Parsed
Label Data` on the right.

Use the `Accept` and `Reject` buttons to show reviewer action capture. The saved
decision appears on the page and is included in CSV export.

## 4. Export CSV

Click `Export CSV` from the `Review Results` page.

The CSV includes:

- application ID,
- final status,
- reviewer queue,
- expected values,
- observed values,
- evidence text,
- OCR source and confidence,
- processing time,
- reviewer decision,
- reviewer note,
- reviewed timestamp.

## 5. Use LOT Actual

`LOT Actual` is for user-supplied test data.

Use this path when you want to upload:

- one application folder, or
- a folder containing many application folders.

The uploaded workspace stays available in that browser until you click `Reset`.

## 6. Download Example Data

On `LOT Actual`, click `Download Examples`.

The downloaded ZIP contains:

- a root folder,
- `manifest.csv`,
- image folders for each application,
- label image files.

Extract the ZIP before uploading. If your operating system extracts the contents
without creating a parent folder, create one folder yourself and place the
manifest plus image folders inside it.

## 7. Application Folder Format

Each upload must include one manifest file at the selected folder root.

Example:

```text
labels-on-tap-example-data/
  manifest.csv
  images/
    25139001000329/
      01_25139001000329_0.png
      02_25139001000329_1.png
    25140001000011/
      01_25140001000011_0.png
```

The manifest tells the app which images belong to each application and what the
application says the label should contain.

Important manifest fields:

```text
filename
panel_filenames
product_type
brand_name
fanciful_name
class_type
alcohol_content
net_contents
bottler_producer_name_address
imported
country_of_origin
```

For applications with multiple label images, put the image paths in
`panel_filenames` separated by semicolons.

Example:

```csv
filename,panel_filenames,product_type,brand_name,class_type,alcohol_content,net_contents,imported,country_of_origin
25139001000329,images/25139001000329/01_25139001000329_0.png;images/25139001000329/02_25139001000329_1.png,distilled_spirits,Protect And Serve,bourbon whisky,40% ALC/VOL,750 mL,false,
```

## 8. Data Format Instructions

Click `Data Format Instructions` on `LOT Actual` for the same folder rules in
the web app.

## 9. Photo Intake

The app also has a photo OCR intake workflow for one bottle, can, or shelf photo.
This is a demonstration aid only. It extracts likely fields from a photo, but it
is not a formal COLA verification result because no application fields are
provided for comparison.

## 10. What The App Checks

The prototype checks common COLA-style label fields:

- brand name,
- fanciful name when provided,
- product type,
- class/type,
- alcohol content,
- net contents,
- bottler or producer when provided,
- country of origin for imports,
- government warning text,
- `GOVERNMENT WARNING:` capitalization,
- `GOVERNMENT WARNING:` boldness evidence.

## 11. How To Explain The Result

The app is conservative.

- `Pass`: the evidence is strong enough.
- `Needs Review`: the evidence is missing, unclear, or not strong enough.
- `Fail`: the app found a clear mismatch or required text problem.

The app does not replace a human reviewer. It moves routine work faster and
shows the reviewer the evidence behind each decision.

