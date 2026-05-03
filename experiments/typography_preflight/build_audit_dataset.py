"""Build a human-reviewable typography audit dataset.

This script intentionally does **not** train a classifier. It creates a small,
balanced set of synthetic ``GOVERNMENT WARNING:`` heading crops with explicit,
separate provenance labels and model-facing decision labels:

* ``font_weight_label``: ``bold``, ``not_bold``, or ``borderline``
* ``header_text_label``: ``correct``, ``incorrect``, or ``borderline``
* ``quality_label``: ``clean``, ``mild``, or ``degraded``
* ``visual_font_decision_label``: ``clearly_bold``, ``clearly_not_bold``, or
  ``needs_review_unclear``
* ``header_decision_label``: ``correct``, ``incorrect``, or
  ``needs_review_unclear``

The earlier ``svm-v2`` experiment mixed visual quality into the binary target,
which caused clearly bold crops to be labeled as negative when they were
generated with a degraded recipe. This audit dataset fixes that mistake by
keeping the observable labels separate so a human can inspect them before a
new SVM/XGBoost/CatBoost experiment is trained.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import random
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "data/work/typography-preflight/audit-v4"
DEFAULT_FONT_ROOT = Path("/usr/share/fonts")

CORRECT_HEADER = "GOVERNMENT WARNING:"

INCORRECT_HEADERS = [
    # Case & Capitalization Errors
    "Government Warning:",
    "government warning:",
    "GOVERNMENT warning:",
    "Government WARNING:",

    # Punctuation Errors (Missing, wrong character, or bad spacing)
    "GOVERNMENT WARNING",
    "GOVERNMENT WARNING;",
    "GOVERNMENT WARNING.",
    "GOVERNMENT WARNING :",  # Space before colon
    "GOVERNMENT WARNING::",
    "GOVERNMENT WARNING-",

    # Spacing & Typography Errors
    "GOVERNMENT  WARNING:",   # Double space
    "GOVERN MENT WARNING:",   # Split word
    "G O V E R N M E N T   W A R N I N G :", # Kerning/tracking spread

    # OCR Artifacts & Visual Confusion
    "GOVERNMENT WARNlNG:",    # Lowercase 'l' instead of 'I'
    "GOVERNMENT WARN1NG:",    # Number '1' instead of 'I'
    "G0VERNMENT WARNING:",    # Number '0' instead of 'O'
    "COVERNMENT WARNING:",    # 'C' instead of 'G'
    "GOVERNMENT VVAMING:",    # 'VV' instead of 'W', 'rn' merged to 'm'
    "GOVERNMENT WARMING:",    # 'M' instead of 'N'
    "GOVERNNENT WARNING:",    # 'N' instead of 'M'
    "GOVERMENT WARNING:",     # Missing first 'N'
    "GOVERNEMT WARNING:",     # Transposed 'M' and 'E'

    # Abbreviations & Incomplete Strings
    "GOVT WARNING:",
    "GOVT. WARNING:",
    "WARNING:",
    "GOV WARNING:",
    "GOV. WARNING:"
]

BOUNDARY_ARTIFACT_HEADERS = [
    " GOVERNMENT WARNING:",   # Leading space
    "GOVERNMENT WARNING: ",   # Trailing space
    ".GOVERNMENT WARNING:",
    "-GOVERNMENT WARNING:",
    "| GOVERNMENT WARNING:",
    "'GOVERNMENT WARNING:'",
]

FONT_WEIGHT_LABELS = ("bold", "not_bold", "borderline")
HEADER_TEXT_LABELS = ("correct", "incorrect", "borderline")

LATIN_FONT_HINTS = (
    "cantarell",   # Standard UI font
    "dejavu",
    "free",        # Captures FreeSans, FreeSerif, etc.
    "liberation",
    "nimbus",
    "notosans",    # Narrowed from "noto"
    "notoserif",   # Narrowed from "noto"
    "open",
    "roboto",
    "ubuntu",
)

EXCLUDED_FONT_HINTS = (
    # Non-Latin Scripts (Expanded to prevent "tofu" boxes)
    "arabic", "armenian", "bengali", "cjk", "cyrillic", "devanagari",
    "ethiopic", "georgian", "gujarati", "gurmukhi", "hebrew", "japanese",
    "kannada", "khmer", "korean", "lao", "malayalam", "myanmar", "oriya",
    "sinhala", "syriac", "tamil", "telugu", "thaana", "thai", "tibetan",

    # Symbols, Math, Icons, and Developer Fonts
    "awesome", "braille", "dingbats", "emoji", "icons", "math",
    "music", "nerd", "powerline", "stix", "symbol", "webdings", "wingdings"
)


@dataclass(frozen=True)
class FontRecord:
    """One local font and its manually inferred typography label."""

    path: str
    family: str
    font_weight_label: str
    style: str


@dataclass(frozen=True)
class AuditSample:
    """Metadata for one generated audit crop."""

    sample_id: str
    font_weight_label: str
    header_text_label: str
    quality_label: str
    visual_font_decision_label: str
    header_decision_label: str
    source_text: str
    font_path: str
    font_family: str
    font_style: str
    font_size: int
    crop_path: str
    font_weight_view_path: str
    header_text_view_path: str
    visual_font_decision_view_path: str
    header_decision_view_path: str


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--font-root", type=Path, default=DEFAULT_FONT_ROOT)
    parser.add_argument("--seed", type=int, default=20260503)
    parser.add_argument(
        "--samples-per-combo",
        type=int,
        default=36,
        help="Samples for each font_weight_label x header_text_label combination.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete the output directory before regenerating the audit set.",
    )
    return parser.parse_args()


def main() -> None:
    """Generate the audit crops, manifest, class views, and HTML contact sheet."""

    args = parse_args()
    rng = random.Random(args.seed)
    output_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    font_root = args.font_root if args.font_root.is_absolute() else ROOT / args.font_root

    if args.clean and output_dir.exists():
        shutil.rmtree(output_dir)
    for child in [
        "crops",
        "by_font_weight",
        "by_header_text",
        "by_visual_font_decision",
        "by_header_decision",
    ]:
        (output_dir / child).mkdir(parents=True, exist_ok=True)

    fonts = discover_fonts(font_root)
    validate_font_pools(fonts)
    write_json(output_dir / "font_inventory.json", {key: [asdict(item) for item in value] for key, value in fonts.items()})

    samples = build_samples(
        fonts=fonts,
        output_dir=output_dir,
        samples_per_combo=args.samples_per_combo,
        rng=rng,
    )
    write_manifest(output_dir / "manifest.csv", samples)
    write_summary(output_dir / "summary.json", samples, args)
    write_readme(output_dir / "README.md", samples)
    write_contact_sheet(output_dir / "index.html", samples)

    print(f"Wrote {len(samples)} audit crops to {output_dir.relative_to(ROOT)}")
    print(f"Open {output_dir.relative_to(ROOT) / 'index.html'} to inspect labels.")


def discover_fonts(font_root: Path) -> dict[str, list[FontRecord]]:
    """Discover local Latin-ish font files and group them by weight label."""

    pools: dict[str, list[FontRecord]] = {label: [] for label in FONT_WEIGHT_LABELS}
    for path in sorted(font_root.rglob("*")):
        if path.suffix.lower() not in {".ttf", ".otf"}:
            continue
        normalized = _normalize_font_name(path)
        if any(hint in normalized for hint in EXCLUDED_FONT_HINTS):
            continue
        if not any(hint in normalized for hint in LATIN_FONT_HINTS):
            continue
        weight = infer_weight_label(path)
        if weight is None:
            continue
        family = infer_family(path)
        style = "italic" if "italic" in normalized or "oblique" in normalized else "upright"
        pools[weight].append(
            FontRecord(
                path=str(path),
                family=family,
                font_weight_label=weight,
                style=style,
            )
        )
    return pools


def infer_weight_label(path: Path) -> str | None:
    """Infer a simple boldness class from the font filename."""

    name = _normalize_font_name(path)
    if "semibold" in name or "semi-bold" in name or "demibold" in name or "demi-bold" in name:
        return "borderline"
    if "medium" in name:
        return "borderline"
    if any(token in name for token in ["extrabold", "extra-bold", "ultrabold", "ultra-bold", "black", "heavy"]):
        return "bold"
    if re.search(r"(^|[-_])bold($|[-_.])", name):
        return "bold"
    if any(token in name for token in ["extralight", "extra-light", "thin", "light", "regular", "book"]):
        return "not_bold"
    return None


def infer_family(path: Path) -> str:
    """Return a compact family identifier for audit provenance."""

    parent = path.parent.name.lower()
    stem = path.stem.lower()
    stem = re.sub(r"(extra[-_ ]?bold|ultra[-_ ]?bold|semi[-_ ]?bold|demi[-_ ]?bold)", "", stem)
    stem = re.sub(r"(bold|black|heavy|medium|regular|book|thin|light|italic|oblique)", "", stem)
    stem = re.sub(r"[-_ ]+", "-", stem).strip("-")
    return f"{parent}:{stem or path.stem.lower()}"


def validate_font_pools(fonts: dict[str, list[FontRecord]]) -> None:
    """Fail loudly if the local machine cannot produce all audit labels."""

    missing = [label for label, items in fonts.items() if not items]
    if missing:
        raise SystemExit(f"Missing font pools for labels: {', '.join(missing)}")


def build_samples(
    *,
    fonts: dict[str, list[FontRecord]],
    output_dir: Path,
    samples_per_combo: int,
    rng: random.Random,
) -> list[AuditSample]:
    """Generate a balanced grid of font-weight and header-text samples."""

    samples: list[AuditSample] = []
    counter = 0
    for font_weight_label in FONT_WEIGHT_LABELS:
        for header_text_label in HEADER_TEXT_LABELS:
            for _ in range(samples_per_combo):
                sample_id = f"audit_{counter:05d}"
                counter += 1
                font = rng.choice(fonts[font_weight_label])
                source_text, quality_label = choose_text_and_quality(header_text_label, rng)
                font_size = rng.randint(24, 46)
                image = render_heading(source_text, font, font_size)
                image = apply_quality_recipe(image, quality_label, rng)

                filename = (
                    f"{sample_id}__fw-{font_weight_label}"
                    f"__text-{header_text_label}__quality-{quality_label}.png"
                )
                crop_path = output_dir / "crops" / filename
                crop_path.parent.mkdir(parents=True, exist_ok=True)
                image.save(crop_path)

                font_view = output_dir / "by_font_weight" / font_weight_label / filename
                text_view = output_dir / "by_header_text" / header_text_label / filename
                visual_decision = visual_font_decision(font_weight_label, quality_label)
                header_decision = header_text_decision(header_text_label, quality_label)
                visual_view = output_dir / "by_visual_font_decision" / visual_decision / filename
                header_decision_view = output_dir / "by_header_decision" / header_decision / filename
                link_or_copy(crop_path, font_view)
                link_or_copy(crop_path, text_view)
                link_or_copy(crop_path, visual_view)
                link_or_copy(crop_path, header_decision_view)

                samples.append(
                    AuditSample(
                        sample_id=sample_id,
                        font_weight_label=font_weight_label,
                        header_text_label=header_text_label,
                        quality_label=quality_label,
                        visual_font_decision_label=visual_decision,
                        header_decision_label=header_decision,
                        source_text=source_text,
                        font_path=font.path,
                        font_family=font.family,
                        font_style=font.style,
                        font_size=font_size,
                        crop_path=str(crop_path.relative_to(output_dir)),
                        font_weight_view_path=str(font_view.relative_to(output_dir)),
                        header_text_view_path=str(text_view.relative_to(output_dir)),
                        visual_font_decision_view_path=str(visual_view.relative_to(output_dir)),
                        header_decision_view_path=str(header_decision_view.relative_to(output_dir)),
                    )
                )
    return samples


def visual_font_decision(font_weight_label: str, quality_label: str) -> str:
    """Return the human-facing typography decision target.

    The source font weight remains provenance. The model target answers the
    operational question: can an automated preflight make a confident call from
    this raster crop? Fuzzy or degraded crops are routed to human review.

    Medium and semibold source fonts are intentionally treated as
    ``clearly_not_bold`` when the raster crop is readable. The source-backed
    requirement is "bold type"; a medium-weight face is evidence that the
    heading is not in an explicitly bold face, not evidence that the image is
    unreadable.
    """

    if quality_label == "degraded":
        return "needs_review_unclear"
    if font_weight_label == "bold":
        return "clearly_bold"
    return "clearly_not_bold"


def header_text_decision(header_text_label: str, quality_label: str) -> str:
    """Return the human-facing header text decision target."""

    if quality_label == "degraded" or header_text_label == "borderline":
        return "needs_review_unclear"
    return header_text_label


def choose_text_and_quality(header_text_label: str, rng: random.Random) -> tuple[str, str]:
    """Choose source text and quality without corrupting font-weight labels."""

    if header_text_label == "correct":
        return CORRECT_HEADER, rng.choices(["clean", "mild"], weights=[0.7, 0.3], k=1)[0]
    if header_text_label == "incorrect":
        return rng.choice(INCORRECT_HEADERS), rng.choices(["clean", "mild"], weights=[0.7, 0.3], k=1)[0]
    source_text = rng.choice([CORRECT_HEADER, *INCORRECT_HEADERS, *BOUNDARY_ARTIFACT_HEADERS])
    return source_text, "degraded"


def render_heading(source_text: str, font: FontRecord, font_size: int) -> Image.Image:
    """Render one warning-heading crop with generous margins."""

    face = ImageFont.truetype(font.path, font_size)
    scratch = Image.new("L", (1200, 220), color=255)
    draw = ImageDraw.Draw(scratch)
    bbox = draw.textbbox((0, 0), source_text, font=face)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    canvas_w = max(420, text_w + 42)
    canvas_h = max(78, text_h + 34)
    image = Image.new("L", (canvas_w, canvas_h), color=255)
    draw = ImageDraw.Draw(image)
    x = (canvas_w - text_w) // 2 - bbox[0]
    y = (canvas_h - text_h) // 2 - bbox[1]
    draw.text((x, y), source_text, fill=0, font=face)
    return image


def apply_quality_recipe(image: Image.Image, quality_label: str, rng: random.Random) -> Image.Image:
    """Apply visual quality variation while preserving separate labels."""

    if quality_label == "clean":
        return image
    if quality_label == "mild":
        image = maybe_rotate(image, rng, max_degrees=2.0)
        if rng.random() < 0.5:
            image = ImageEnhance.Contrast(image).enhance(rng.uniform(0.65, 0.9))
        if rng.random() < 0.5:
            image = image.filter(ImageFilter.GaussianBlur(radius=rng.uniform(0.2, 0.7)))
        return image

    image = maybe_rotate(image, rng, max_degrees=5.0)
    image = ImageEnhance.Contrast(image).enhance(rng.uniform(0.35, 0.6))
    image = image.filter(ImageFilter.GaussianBlur(radius=rng.uniform(1.0, 2.2)))
    draw = ImageDraw.Draw(image)
    width, height = image.size
    for _ in range(rng.randint(1, 3)):
        band_h = rng.randint(8, max(9, height // 4))
        y = rng.randint(0, max(0, height - band_h))
        fill = rng.randint(210, 255)
        draw.rectangle((0, y, width, y + band_h), fill=fill)
    if rng.random() < 0.5:
        left = rng.randint(0, max(1, width // 5))
        right = rng.randint(width - max(1, width // 5), width)
        image = image.crop((left, 0, right, height))
    return image


def maybe_rotate(image: Image.Image, rng: random.Random, *, max_degrees: float) -> Image.Image:
    """Apply small rotation with white fill."""

    angle = rng.uniform(-max_degrees, max_degrees)
    return image.rotate(angle, expand=True, fillcolor=255)


def link_or_copy(source: Path, destination: Path) -> None:
    """Create a hard link for class views, falling back to a copy."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def write_manifest(path: Path, samples: list[AuditSample]) -> None:
    """Write the audit manifest as CSV."""

    fieldnames = list(asdict(samples[0]).keys()) if samples else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for sample in samples:
            writer.writerow(asdict(sample))


def write_summary(path: Path, samples: list[AuditSample], args: argparse.Namespace) -> None:
    """Write machine-readable dataset counts and generation settings."""

    summary = {
        "purpose": "human-inspection dataset before retraining typography preflight models",
        "seed": args.seed,
        "samples_per_combo": args.samples_per_combo,
        "total_samples": len(samples),
        "labels": {
            "font_weight_label": count_by(samples, "font_weight_label"),
            "header_text_label": count_by(samples, "header_text_label"),
            "quality_label": count_by(samples, "quality_label"),
            "visual_font_decision_label": count_by(samples, "visual_font_decision_label"),
            "header_decision_label": count_by(samples, "header_decision_label"),
            "joint_font_weight_header_text": count_joint(samples),
        },
        "important_policy": [
            "Font weight labels are never overwritten by image quality.",
            "A bold but degraded crop remains font_weight_label=bold.",
            "The model-facing visual_font_decision_label routes degraded/visually unreliable crops to needs_review_unclear.",
            "Readable medium and semibold crops are labeled clearly_not_bold because the requirement is explicit bold type.",
            "Header-text borderline means the crop was intentionally degraded enough to require human review.",
            "Do not train models from this dataset until a human has inspected representative crops.",
        ],
    }
    write_json(path, summary)


def write_readme(path: Path, samples: list[AuditSample]) -> None:
    """Write a short human guide next to the generated dataset."""

    text = f"""# Typography Audit Dataset v4

This dataset is for human inspection before training a new typography
preflight model.

Total crops: {len(samples)}

Important correction from `svm-v2`: font weight, header text, and image quality
are separate labels. A bold crop is still labeled `font_weight_label=bold` even
when the image is degraded.

Important correction from `audit-v1`: the model-facing targets are now explicit:

- `visual_font_decision_label`
- `header_decision_label`

These route degraded, fuzzy, tiny, and visually ambiguous crops to
`needs_review_unclear`.

Important correction from `audit-v2`: medium/semibold source fonts are no longer
automatically treated as review cases. If the crop is readable, they are labeled
`clearly_not_bold` because the requirement is explicit bold type.

Important correction from `audit-v3`: boundary and whitespace artifacts are no
longer included in the visible `incorrect` header class. They are held for the
degraded/borderline review bucket so the header classifier does not learn from
visually ambiguous edge artifacts.

Inspect:

- `index.html` for a browser contact sheet.
- `by_font_weight/` to review `bold`, `not_bold`, and `borderline` groups.
- `by_header_text/` to review `correct`, `incorrect`, and `borderline` groups.
- `by_visual_font_decision/` to review the actual Model 1 target groups.
- `by_header_decision/` to review the actual Model 2 target groups.
- `manifest.csv` for full provenance.

Do not train from this dataset until the label policy passes visual inspection.
"""
    path.write_text(text, encoding="utf-8")


def write_contact_sheet(path: Path, samples: list[AuditSample]) -> None:
    """Write an HTML contact sheet for fast visual inspection."""

    rows = []
    for sample in samples:
        rows.append(
            "<tr>"
            f"<td>{html.escape(sample.sample_id)}</td>"
            f"<td>{html.escape(sample.font_weight_label)}</td>"
            f"<td>{html.escape(sample.header_text_label)}</td>"
            f"<td>{html.escape(sample.quality_label)}</td>"
            f"<td>{html.escape(sample.visual_font_decision_label)}</td>"
            f"<td>{html.escape(sample.header_decision_label)}</td>"
            f"<td>{html.escape(sample.source_text)}</td>"
            f"<td>{html.escape(sample.font_family)}</td>"
            f"<td>{html.escape(sample.font_style)}</td>"
            f"<td><img src=\"{html.escape(sample.crop_path)}\" alt=\"{html.escape(sample.sample_id)}\"></td>"
            "</tr>"
        )
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Typography Audit Dataset v4</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 24px; color: #111; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 6px 8px; vertical-align: middle; }}
    th {{ position: sticky; top: 0; background: #f5f5f5; }}
    img {{ max-height: 72px; max-width: 540px; background: white; }}
    code {{ background: #f5f5f5; padding: 1px 4px; }}
  </style>
</head>
<body>
  <h1>Typography Audit Dataset v4</h1>
  <p>
    Separate labels: <code>font_weight_label</code>,
    <code>header_text_label</code>, and <code>quality_label</code>.
    Model-facing targets are <code>visual_font_decision_label</code>
    and <code>header_decision_label</code>. This is an inspection set only.
  </p>
  <table>
    <thead>
      <tr>
        <th>Sample</th>
        <th>Font Weight</th>
        <th>Header Text</th>
        <th>Quality</th>
        <th>Visual Font Decision</th>
        <th>Header Decision</th>
        <th>Source Text</th>
        <th>Font Family</th>
        <th>Style</th>
        <th>Crop</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>
</body>
</html>
"""
    path.write_text(document, encoding="utf-8")


def count_by(samples: Iterable[AuditSample], attr: str) -> dict[str, int]:
    """Count sample values by dataclass attribute."""

    counts: dict[str, int] = {}
    for sample in samples:
        value = str(getattr(sample, attr))
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def count_joint(samples: Iterable[AuditSample]) -> dict[str, int]:
    """Count font/header label combinations."""

    counts: dict[str, int] = {}
    for sample in samples:
        key = f"{sample.font_weight_label}|{sample.header_text_label}"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def write_json(path: Path, payload: object) -> None:
    """Write pretty JSON."""

    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _normalize_font_name(path: Path) -> str:
    return re.sub(r"\s+", "", f"{path.parent.name}-{path.stem}".lower())


if __name__ == "__main__":
    main()
