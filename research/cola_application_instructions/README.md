# COLAs Online Application Workflow Research

This directory contains the downloaded COLAs Online task guides used to understand how a Certificate of Label Approval (COLA) application is created and submitted through the current web workflow.

Source PDFs in this folder:

- `create-an-application.pdf`
- `upload-label-images.pdf`
- `upload-other-attachments.pdf`
- `verify-application.pdf`

## Core Finding

COLAs Online applications are not submitted as a single PDF file.

The applicant creates a COLA eApplication through a manually entered web UI:

```text
Allowable changes acknowledgement
  -> Step 1 of 3: Application Type
  -> Step 2 of 3: COLA Information
  -> Step 3 of 3: Upload Labels
  -> Verify Application
  -> Submit
```

The public printable COLA form is a rendered artifact of that web submission. It combines structured application fields, certificate/status data, and one or more uploaded label images.

For Labels On Tap, the correct data model is therefore:

```text
structured COLAs Online application fields
  + one to ten uploaded label image files
  + optional supporting attachments
```

The prototype should not treat the submitted application as one monolithic PDF. It should model the workflow as application data plus label artwork.

## Allowable Changes Acknowledgement

Before creating an eApplication, the user must review and acknowledge the list of allowable label revisions.

Important implications:

- Applicants may not need a new COLA for every label change.
- The workflow starts with a decision about whether a new application is required.
- A production system could eventually help classify whether a change is allowable, but that is outside the current Phase 1 verification scope.

## Step 1 Of 3: Application Type

The `create-an-application.pdf` guide states that all fields in Step 1 are required.

The user enters/selects:

```text
type_of_product:
  - Wine
  - Domestic SAKE Application
  - Distilled Spirit
  - Malt Beverage

source_of_product:
  - Domestic
  - Imported

type_of_application:
  - Certificate of Label Approval
  - Certificate of Exemption from Label Approval

state_for_exemption:
  - required when Certificate of Exemption from Label Approval is selected

resubmission_after_rejection:
  - yes/no
  - if yes, select or enter prior TTB ID
```

Important notes from the guide:

- Certificate of Label Approval is the default.
- If Certificate of Exemption from Label Approval is selected, the applicant selects the state where the product will be sold.
- If Certificate of Label Approval is selected with Source of Product as Imported, the state dropdown is disabled.
- If the submission is a resubmission of a rejected application, the user must select or enter a TTB ID.
- The dropdown contains rejected eApplications.
- The text field can reference an electronic or paper application rejected within the past two years.

## Step 2 Of 3: COLA Information

Step 2 collects COLA information. This is the main structured application-data source that label artwork should be compared against.

Fields and behaviors documented in `create-an-application.pdf` include:

```text
distinctive_liquor_bottle_approval:
  - appears for distilled spirits when applicable
  - includes total bottle capacity before closure

serial_number:
  - entered by applicant

plant_registry_basic_permit_brewers_number:
  - selected from dropdown
  - repeatable for multiple permits except wineries

dba_trade_name:
  - entered when used on the label
  - must match the label
  - must be approved/registered before use

brand_name:
  - entered manually

fanciful_name:
  - entered manually when applicable

formula_id:
  - selected from approved formula IDs associated with the selected permit
  - repeatable/removable
  - formula class/type shown is the approved class/type

net_contents:
  - selected from dropdown
  - repeatable for labels used on multiple container sizes

alcohol_content:
  - text or numeric value
  - numeric value must be between 0.00 and 100.00

wine_vintage:
  - wine applications only
  - required when shown on label
  - numeric range from 1700 through current year

grape_varietals:
  - wine applications only
  - entered when shown on label

wine_appellation:
  - wine applications only
  - entered when shown on label
  - required when wine vintage is entered

notes_to_specialist:
  - optional
  - up to 2000 characters
```

Important warning from the guide:

> Product class/type or wine appellation should not be entered into the Brand Name or Fanciful Name fields. Doing so will result in the application being returned for correction.

This matters for Phase 1 because it is a concrete Needs Correction reason: the app should detect obvious application-field misuse, such as class/type text placed in brand or fanciful name fields.

## Step 3 Of 3: Upload Labels

Step 3 is where the applicant uploads label images and optional attachments.

The user can:

- enter translations of foreign text,
- enter special wording or designs appearing on materials affixed to the container,
- add/remove label images,
- add/remove other attachments,
- return to Step 2,
- proceed to Verify Application.

Examples of materials mentioned in the guide include:

```text
label
bottle
cork
other affixed materials
```

This is important because label-relevant text may appear outside the main rectangular label artwork. The application form has a field for special wording/designs appearing on affixed materials.

## Upload Label Images

The `upload-label-images.pdf` guide describes the label image upload workflow.

A user may attach up to ten label image files per application.

Each label image file must:

```text
file type:
  - JPG
  - TIFF

extensions:
  - .jpg
  - .jpeg
  - .jpe
  - .tif
  - .tiff

max_size:
  - 750 KB

compression:
  - medium
  - 7 out of 10
  - 70 out of 100

color_mode:
  - RGB
  - not CMYK

cropping:
  - no surrounding white space
  - no printer's proof detail
```

The upload flow also requires:

```text
attachment_type:
  - selected from dropdown
  - identifies which label/panel the image represents
  - examples: brand, neck, back

image_height:
  - entered manually
  - NN.NN numeric format

image_width:
  - entered manually
  - NN.NN numeric format
```

Important notes:

- Include only one label per image.
- After upload, the user should select the image link to confirm the file uploaded correctly and is clear/readable.
- Uploaded label images may become corrupted or distorted.
- If an image is corrupted/distorted, the applicant should remove it, re-save with a different compression/quality ratio, and upload again.
- TIFF files should not be saved with JPG compression.

## Upload Other Attachments

The `upload-other-attachments.pdf` guide describes supporting attachments, which are separate from label image files.

Examples include:

```text
formulas
SOPs
lab analyses
pre-import letters
cover letters
```

Acceptable attachment types:

```text
.doc
.txt
.pdf
.jpg
.jpeg
.jpe
.tif
.tiff
```

Limits:

```text
up to 10 files per application
up to 750 KB per file
```

These files are supporting evidence and should not be treated as primary label artwork unless their attachment type indicates label-relevant material.

## Verify Application

The `verify-application.pdf` guide shows that the applicant reviews the entered data and attachments before submission.

The user can:

- edit Step 1,
- edit Step 2,
- edit Step 3,
- view image attachments,
- view other attachments,
- verify uploaded images against the specified actual dimensions,
- agree to the penalty-of-perjury certification,
- submit the application,
- save without submitting for up to 30 days.

Important constraints:

- The application cannot be submitted until the applicant selects the Verify Uploaded Images link.
- The application cannot be submitted until the applicant selects the "I agree" checkbox.
- Only an External User can submit an application.
- An External Preparer/Reviewer can save an application but cannot submit it.
- Some steps may not be editable after submission in Needs Correction status.

## Implications For Labels On Tap

### Correct Input Contract

The app should emulate this workflow with a standalone import format:

```text
cola_application.json or cola_application.csv
  + label image files
  + optional attachment metadata
```

The prototype should not require authenticated COLAs Online access. It should accept a COLAs Online-shaped export or public registry-derived record.

### Multiple Label Images Per Application

One application can have multiple label images:

```text
brand/front
back
neck
keg collar
other panel types
```

Therefore, the app should:

- store each image as a separate panel,
- OCR each panel independently,
- preserve panel-level evidence,
- aggregate OCR text across panels when comparing application fields to label text,
- show which panel produced each piece of evidence.

### Field-To-Label Matching

The Phase 1 comparison should prioritize fields that are directly entered into COLAs Online and visible on labels:

```text
brand_name
fanciful_name
dba_trade_name
alcohol_content
net_contents
country_of_origin for imports
special_wording/translations
government_warning_text
```

Class/type is more nuanced. The guide explicitly says the applicant is not required to tell TTB the class/type designation that appears on the label, and that entering class/type into Brand Name or Fanciful Name can trigger correction. For Phase 1, class/type should be handled as:

- label-required text to detect on artwork,
- formula/registry/public-form-derived metadata where available,
- and an application-field misuse warning when class/type appears in the wrong field.

### File-Type Handling

For COLAs Online historical compatibility, the ingestion pipeline should support:

```text
.jpg
.jpeg
.jpe
.tif
.tiff
```

For current public web app uploads, `.png` may still be accepted because existing app fixtures and modern public guidance use PNG, but the COLAs Online task guide in this directory specifically lists JPG and TIFF for label images.

### Image Quality Checks

The upload instructions make image quality a real intake requirement, not a cosmetic concern.

Phase 1 should check or flag:

- file type,
- file size,
- RGB versus CMYK where detectable,
- excessive whitespace,
- printer proof details or obvious non-label margins where feasible,
- readability,
- corruption/distortion,
- dimensions metadata,
- one-label-per-image assumption.

### Reviewer Output

The reviewer-facing report should include:

```text
application_id / TTB ID
application step / field
expected value from application
observed value from label OCR
label panel evidence
verdict
reviewer action
OCR source
OCR confidence
image-quality warnings
```

## Open Questions

- The task-guide PDFs list JPG/TIFF label images and 750 KB limits, while newer public FAQ material may describe different accepted formats and size limits. The app should document this as version-sensitive and support historical registry ingestion separately from current runtime upload policy.
- Public registry `publicFormDisplay` HTML may expose application fields and label image URLs directly, which is preferable to parsing screenshots when available.
- Some printable public forms include status, class/type description, qualifications, and affixed label images. Those public artifacts can be used as realistic fixtures with provenance.
- The prototype still should not integrate with authenticated COLAs Online directly.

## Working Conclusion

The assignment should be implemented as:

```text
read COLAs Online-style application data
  -> load one or more uploaded label images
  -> OCR each label image locally
  -> compare label OCR against application fields and required screen-out rules
  -> return Pass / Needs Review / Fail with evidence and reviewer action
```

That is the workflow described by the task guides and by the stakeholder interviews.
