"""Build the audit-v6 government-warning typography image set.

``audit-v6`` keeps the audited synthetic label policy from ``audit-v5`` but
seeds the visual domain with real COLA label context:

* real approved COLA warning-heading crops
* real no-warning panels from multi-image applications
* real-background mutated warning crops (non-bold over real crop backgrounds)
* synthetic warning crops for balanced negative/review coverage

This script does not train a model. It creates an ``audit-v5``-style image
inspection set under the gitignored
``data/work/typography-preflight/audit-v6/`` directory.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import os
import random
import shutil
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps, ImageStat

from experiments.typography_preflight.build_audit_dataset import (
    CORRECT_HEADER,
    FONT_WEIGHT_LABELS,
    HEADER_TEXT_LABELS,
    FontRecord,
    apply_quality_recipe,
    choose_source_text,
    discover_fonts,
    render_heading,
    validate_font_pools,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "data/work/typography-preflight/audit-v6"
DEFAULT_FONT_ROOT = Path("/usr/share/fonts")
DEFAULT_IMAGES_MANIFEST = ROOT / "data/work/ocr-conveyor/tri-engine-train-val-v1-chunk16/manifest/images.csv"
DEFAULT_HEADING_CROPS = ROOT / "data/work/typography-preflight/real-cola-smoke-v2-trainval-heading-only/metrics/heading_crops.csv"
DEFAULT_SPLIT_COUNTS = {"train": 6000, "validation": 1500, "test": 1500}
SOURCE_KINDS = (
    "real_heading_positive",
    "real_background_non_bold",
    "real_no_warning_panel",
    "synthetic_bold_positive",
    "synthetic_non_bold",
    "synthetic_incorrect",
    "review_unreadable",
)
SOURCE_SHARES = {
    "real_heading_positive": 0.20,
    "real_background_non_bold": 0.20,
    "real_no_warning_panel": 0.10,
    "synthetic_bold_positive": 0.15,
    "synthetic_non_bold": 0.15,
    "synthetic_incorrect": 0.10,
    "review_unreadable": 0.10,
}
ENGINE_RANK = {"openocr": 3, "paddleocr": 2, "doctr": 1}


@dataclass(frozen=True)
class RealHeadingCrop:
    """One deduplicated real warning-heading crop."""

    ttb_id: str
    image_path: str
    crop_path: str
    engine: str
    match_score: float
    ocr_confidence: float | None


@dataclass(frozen=True)
class ImageRow:
    """One valid label image row from the OCR conveyor manifest."""

    ttb_id: str
    image_path: str


@dataclass(frozen=True)
class V6Sample:
    """Metadata for one v6 dataset sample."""

    split: str
    sample_id: str
    source_kind: str
    source_origin: str
    ttb_id: str
    source_image_path: str
    source_crop_path: str
    derived_from_engine: str
    panel_warning_label: str
    heading_text_label: str
    boldness_label: str
    quality_label: str
    source_text: str
    font_weight_label: str
    font_path: str
    font_family: str
    font_style: str
    font_size: int
    crop_path: str


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--font-root", type=Path, default=DEFAULT_FONT_ROOT)
    parser.add_argument("--images-manifest", type=Path, default=DEFAULT_IMAGES_MANIFEST)
    parser.add_argument("--heading-crops", type=Path, default=DEFAULT_HEADING_CROPS)
    parser.add_argument("--seed", type=int, default=20260503)
    parser.add_argument("--train-count", type=int, default=DEFAULT_SPLIT_COUNTS["train"])
    parser.add_argument("--validation-count", type=int, default=DEFAULT_SPLIT_COUNTS["validation"])
    parser.add_argument("--test-count", type=int, default=DEFAULT_SPLIT_COUNTS["test"])
    parser.add_argument(
        "--contact-sheet-limit",
        type=int,
        default=9000,
        help="Maximum rows in index.html. Use 0 to include every sample.",
    )
    parser.add_argument("--clean", action="store_true", help="Delete the output directory before regenerating audit-v6.")
    return parser.parse_args()


def main() -> None:
    """Generate audit-v6 crops, class views, contact sheet, and summary files."""

    args = parse_args()
    rng = random.Random(args.seed)

    output_dir = resolve_path(args.output_dir)
    if args.clean and output_dir.exists():
        shutil.rmtree(output_dir)
    for child in (
        "crops",
        "by_split",
        "by_source_kind",
        "by_source_origin",
        "by_panel_warning",
        "by_heading_text",
        "by_boldness",
        "by_quality",
        "by_font_weight",
    ):
        (output_dir / child).mkdir(parents=True, exist_ok=True)

    fonts = discover_fonts(resolve_path(args.font_root))
    validate_font_pools(fonts)
    heading_pool, no_warning_pool, app_split = load_real_pools(
        images_manifest=resolve_path(args.images_manifest),
        heading_crops=resolve_path(args.heading_crops),
        seed=args.seed,
    )
    split_counts = {
        "train": args.train_count,
        "validation": args.validation_count,
        "test": args.test_count,
    }
    samples = build_samples(
        output_dir=output_dir,
        fonts=fonts,
        heading_pool=heading_pool,
        no_warning_pool=no_warning_pool,
        split_counts=split_counts,
        rng=rng,
    )

    write_json(
        output_dir / "font_inventory.json",
        {key: [asdict(item) for item in value] for key, value in fonts.items()},
    )
    write_manifest(output_dir / "manifest.csv", samples)
    write_summary(output_dir / "summary.json", samples, split_counts, app_split)
    write_readme(output_dir / "README.md", samples, split_counts)
    write_audit_views(output_dir, samples)
    write_contact_sheet(output_dir / "index.html", samples, args.contact_sheet_limit, rng)

    print(f"Wrote {len(samples)} audit-v6 samples to {output_dir.relative_to(ROOT)}")
    for split in ("train", "validation", "test"):
        print(f"  {split}: {sum(1 for sample in samples if sample.split == split)}")


def resolve_path(path: Path) -> Path:
    """Resolve a possibly relative path against the repo root."""

    return path if path.is_absolute() else ROOT / path


def load_real_pools(
    *,
    images_manifest: Path,
    heading_crops: Path,
    seed: int,
) -> tuple[dict[str, list[RealHeadingCrop]], dict[str, list[ImageRow]], dict[str, str]]:
    """Load and split real COLA heading and no-warning pools by TTB ID."""

    images_by_path: dict[str, ImageRow] = {}
    ttb_ids: list[str] = []
    with images_manifest.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("preflight_status") != "valid":
                continue
            image = ImageRow(ttb_id=row["ttb_id"], image_path=row["image_path"])
            images_by_path[image.image_path] = image
            ttb_ids.append(image.ttb_id)

    app_split = split_ttb_ids(sorted(set(ttb_ids)), seed=seed)
    best_heading_by_image: dict[str, RealHeadingCrop] = {}
    with heading_crops.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            image_path = row["image_path"]
            image = images_by_path.get(image_path)
            if image is None:
                continue
            candidate = RealHeadingCrop(
                ttb_id=image.ttb_id,
                image_path=image_path,
                crop_path=str((heading_crops.parent.parent / row["crop_path"]).relative_to(ROOT)),
                engine=row["engine"],
                match_score=float(row.get("match_score") or 0.0),
                ocr_confidence=parse_optional_float(row.get("ocr_confidence")),
            )
            current = best_heading_by_image.get(image_path)
            if current is None or rank_heading(candidate) > rank_heading(current):
                best_heading_by_image[image_path] = candidate

    heading_images = set(best_heading_by_image)
    heading_pool: dict[str, list[RealHeadingCrop]] = defaultdict(list)
    no_warning_pool: dict[str, list[ImageRow]] = defaultdict(list)
    for crop in best_heading_by_image.values():
        heading_pool[app_split[crop.ttb_id]].append(crop)
    for image in images_by_path.values():
        if image.image_path in heading_images:
            continue
        no_warning_pool[app_split[image.ttb_id]].append(image)

    return dict(heading_pool), dict(no_warning_pool), app_split


def split_ttb_ids(ttb_ids: list[str], *, seed: int) -> dict[str, str]:
    """Assign application IDs to train/validation/test without overlap."""

    rng = random.Random(seed)
    shuffled = list(ttb_ids)
    rng.shuffle(shuffled)
    total = len(shuffled)
    train_cut = int(total * 0.70)
    validation_cut = int(total * 0.85)
    split_map: dict[str, str] = {}
    for idx, ttb_id in enumerate(shuffled):
        if idx < train_cut:
            split_map[ttb_id] = "train"
        elif idx < validation_cut:
            split_map[ttb_id] = "validation"
        else:
            split_map[ttb_id] = "test"
    return split_map


def rank_heading(crop: RealHeadingCrop) -> tuple[float, float, int]:
    """Rank duplicate OCR heading crops from different engines."""

    return (
        crop.match_score,
        crop.ocr_confidence if crop.ocr_confidence is not None else -1.0,
        ENGINE_RANK.get(crop.engine, 0),
    )


def build_samples(
    *,
    output_dir: Path,
    fonts: dict[str, list[FontRecord]],
    heading_pool: dict[str, list[RealHeadingCrop]],
    no_warning_pool: dict[str, list[ImageRow]],
    split_counts: dict[str, int],
    rng: random.Random,
) -> list[V6Sample]:
    """Build the full v6 dataset."""

    samples: list[V6Sample] = []
    for split in ("train", "validation", "test"):
        split_rng = random.Random(f"{rng.random()}:{split}")
        quotas = compute_quotas(split_counts[split])
        heading_source = shuffled_cycle(heading_pool.get(split, []), split_rng)
        no_warning_source = shuffled_cycle(no_warning_pool.get(split, []), split_rng)
        counter = 0

        for _ in range(quotas["real_heading_positive"]):
            crop = next(heading_source)
            samples.append(
                create_real_heading_sample(
                    output_dir=output_dir,
                    split=split,
                    sample_index=counter,
                    crop=crop,
                    source_kind="real_heading_positive",
                    panel_warning_label="warning_present",
                    heading_text_label="correct_government_warning",
                    boldness_label="bold",
                    quality_label="clean",
                )
            )
            counter += 1

        for _ in range(quotas["real_background_non_bold"]):
            crop = next(heading_source)
            font = split_rng.choice(fonts["not_bold"])
            header_text_label = "correct"
            source_text = choose_source_text(header_text_label, "clean", split_rng)
            font_size = estimate_font_size(resolve_path(Path(crop.crop_path)), font.path, split_rng)
            image = mutate_real_background(resolve_path(Path(crop.crop_path)), source_text, font, font_size, split_rng)
            samples.append(
                create_rendered_sample(
                    output_dir=output_dir,
                    split=split,
                    sample_index=counter,
                    source_kind="real_background_non_bold",
                    source_origin="real_cola_background",
                    ttb_id=crop.ttb_id,
                    source_image_path=crop.image_path,
                    source_crop_path=crop.crop_path,
                    derived_from_engine=crop.engine,
                    panel_warning_label="warning_present",
                    heading_text_label="correct_government_warning",
                    boldness_label="not_bold",
                    quality_label="clean",
                    source_text=source_text,
                    font=font,
                    font_size=font_size,
                    image=image,
                )
            )
            counter += 1

        for _ in range(quotas["real_no_warning_panel"]):
            image = next(no_warning_source)
            panel = Image.open(resolve_path(Path(image.image_path))).convert("L")
            panel = normalize_panel_preview(panel)
            samples.append(
                save_image_sample(
                    output_dir=output_dir,
                    split=split,
                    sample_index=counter,
                    source_kind="real_no_warning_panel",
                    source_origin="real_cola_panel",
                    ttb_id=image.ttb_id,
                    source_image_path=image.image_path,
                    source_crop_path="",
                    derived_from_engine="",
                    panel_warning_label="warning_absent",
                    heading_text_label="not_applicable",
                    boldness_label="not_applicable",
                    quality_label="clean",
                    source_text="",
                    font_weight_label="not_applicable",
                    font_path="",
                    font_family="",
                    font_style="",
                    font_size=0,
                    image=panel,
                )
            )
            counter += 1

        for _ in range(quotas["synthetic_bold_positive"]):
            font = split_rng.choice(fonts["bold"])
            font_size = split_rng.randint(24, 46)
            image = render_heading(CORRECT_HEADER, font, font_size)
            quality_label = split_rng.choice(["clean", "mild"])
            image = apply_quality_recipe(image, quality_label, split_rng)
            samples.append(
                create_rendered_sample(
                    output_dir=output_dir,
                    split=split,
                    sample_index=counter,
                    source_kind="synthetic_bold_positive",
                    source_origin="synthetic",
                    ttb_id="",
                    source_image_path="",
                    source_crop_path="",
                    derived_from_engine="",
                    panel_warning_label="warning_present",
                    heading_text_label="correct_government_warning",
                    boldness_label="bold",
                    quality_label=quality_label,
                    source_text=CORRECT_HEADER,
                    font=font,
                    font_size=font_size,
                    image=image,
                )
            )
            counter += 1

        for _ in range(quotas["synthetic_non_bold"]):
            font = split_rng.choice(fonts["not_bold"])
            font_size = split_rng.randint(24, 46)
            image = render_heading(CORRECT_HEADER, font, font_size)
            quality_label = split_rng.choice(["clean", "mild"])
            image = apply_quality_recipe(image, quality_label, split_rng)
            samples.append(
                create_rendered_sample(
                    output_dir=output_dir,
                    split=split,
                    sample_index=counter,
                    source_kind="synthetic_non_bold",
                    source_origin="synthetic",
                    ttb_id="",
                    source_image_path="",
                    source_crop_path="",
                    derived_from_engine="",
                    panel_warning_label="warning_present",
                    heading_text_label="correct_government_warning",
                    boldness_label="not_bold",
                    quality_label=quality_label,
                    source_text=CORRECT_HEADER,
                    font=font,
                    font_size=font_size,
                    image=image,
                )
            )
            counter += 1

        for _ in range(quotas["synthetic_incorrect"]):
            font_weight_label = split_rng.choice(list(FONT_WEIGHT_LABELS))
            font = split_rng.choice(fonts[font_weight_label])
            font_size = split_rng.randint(24, 46)
            source_text = choose_source_text("incorrect", "clean", split_rng)
            image = render_heading(source_text, font, font_size)
            quality_label = split_rng.choice(["clean", "mild"])
            image = apply_quality_recipe(image, quality_label, split_rng)
            samples.append(
                create_rendered_sample(
                    output_dir=output_dir,
                    split=split,
                    sample_index=counter,
                    source_kind="synthetic_incorrect",
                    source_origin="synthetic",
                    ttb_id="",
                    source_image_path="",
                    source_crop_path="",
                    derived_from_engine="",
                    panel_warning_label="warning_present",
                    heading_text_label="incorrect_heading_text",
                    boldness_label="bold" if font_weight_label == "bold" else "not_bold",
                    quality_label=quality_label,
                    source_text=source_text,
                    font=font,
                    font_size=font_size,
                    image=image,
                )
            )
            counter += 1

        for _ in range(quotas["review_unreadable"]):
            use_real = split_rng.random() < 0.5
            if use_real:
                crop = next(heading_source)
                source_text = CORRECT_HEADER
                font = split_rng.choice(fonts["bold"])
                font_size = estimate_font_size(resolve_path(Path(crop.crop_path)), font.path, split_rng)
                image = mutate_real_background(resolve_path(Path(crop.crop_path)), source_text, font, font_size, split_rng)
                image = apply_quality_recipe(image, "degraded", split_rng)
                samples.append(
                    create_rendered_sample(
                        output_dir=output_dir,
                        split=split,
                        sample_index=counter,
                        source_kind="review_unreadable",
                        source_origin="real_cola_background",
                        ttb_id=crop.ttb_id,
                        source_image_path=crop.image_path,
                        source_crop_path=crop.crop_path,
                        derived_from_engine=crop.engine,
                        panel_warning_label="unreadable_review",
                        heading_text_label="unreadable_review",
                        boldness_label="unreadable_review",
                        quality_label="degraded",
                        source_text=source_text,
                        font=font,
                        font_size=font_size,
                        image=image,
                    )
                )
            else:
                font_weight_label = split_rng.choice(list(FONT_WEIGHT_LABELS))
                font = split_rng.choice(fonts[font_weight_label])
                font_size = split_rng.randint(24, 46)
                header_text_label = split_rng.choice(list(HEADER_TEXT_LABELS))
                source_text = choose_source_text(header_text_label, "degraded", split_rng)
                image = render_heading(source_text, font, font_size)
                image = apply_quality_recipe(image, "degraded", split_rng)
                samples.append(
                    create_rendered_sample(
                        output_dir=output_dir,
                        split=split,
                        sample_index=counter,
                        source_kind="review_unreadable",
                        source_origin="synthetic",
                        ttb_id="",
                        source_image_path="",
                        source_crop_path="",
                        derived_from_engine="",
                        panel_warning_label="unreadable_review",
                        heading_text_label="unreadable_review",
                        boldness_label="unreadable_review",
                        quality_label="degraded",
                        source_text=source_text,
                        font=font,
                        font_size=font_size,
                        image=image,
                    )
                )
            counter += 1

    return samples


def compute_quotas(total: int) -> dict[str, int]:
    """Convert split totals into exact per-source quotas."""

    raw = {name: total * SOURCE_SHARES[name] for name in SOURCE_KINDS}
    quotas = {name: int(math.floor(value)) for name, value in raw.items()}
    remainder = total - sum(quotas.values())
    if remainder:
        order = sorted(
            SOURCE_KINDS,
            key=lambda name: (raw[name] - quotas[name], SOURCE_KINDS.index(name)),
            reverse=True,
        )
        for idx in range(remainder):
            quotas[order[idx % len(order)]] += 1
    return quotas


def shuffled_cycle(items: list, rng: random.Random):
    """Yield items forever in reshuffled order."""

    if not items:
        raise SystemExit("A required real-data pool is empty; cannot build v6 dataset.")
    pool = list(items)
    while True:
        rng.shuffle(pool)
        for item in pool:
            yield item


def create_real_heading_sample(
    *,
    output_dir: Path,
    split: str,
    sample_index: int,
    crop: RealHeadingCrop,
    source_kind: str,
    panel_warning_label: str,
    heading_text_label: str,
    boldness_label: str,
    quality_label: str,
) -> V6Sample:
    """Save a direct copy of a real heading crop as one dataset sample."""

    image = normalize_heading_crop(Image.open(resolve_path(Path(crop.crop_path))).convert("L"))
    return save_image_sample(
        output_dir=output_dir,
        split=split,
        sample_index=sample_index,
        source_kind=source_kind,
        source_origin="real_cola_heading",
        ttb_id=crop.ttb_id,
        source_image_path=crop.image_path,
        source_crop_path=crop.crop_path,
        derived_from_engine=crop.engine,
        panel_warning_label=panel_warning_label,
        heading_text_label=heading_text_label,
        boldness_label=boldness_label,
        quality_label=quality_label,
        source_text=CORRECT_HEADER,
        font_weight_label="bold",
        font_path="",
        font_family="",
        font_style="",
        font_size=0,
        image=image,
    )


def create_rendered_sample(
    *,
    output_dir: Path,
    split: str,
    sample_index: int,
    source_kind: str,
    source_origin: str,
    ttb_id: str,
    source_image_path: str,
    source_crop_path: str,
    derived_from_engine: str,
    panel_warning_label: str,
    heading_text_label: str,
    boldness_label: str,
    quality_label: str,
    source_text: str,
    font: FontRecord,
    font_size: int,
    image: Image.Image,
) -> V6Sample:
    """Save a rendered image sample and its manifest row."""

    return save_image_sample(
        output_dir=output_dir,
        split=split,
        sample_index=sample_index,
        source_kind=source_kind,
        source_origin=source_origin,
        ttb_id=ttb_id,
        source_image_path=source_image_path,
        source_crop_path=source_crop_path,
        derived_from_engine=derived_from_engine,
        panel_warning_label=panel_warning_label,
        heading_text_label=heading_text_label,
        boldness_label=boldness_label,
        quality_label=quality_label,
        source_text=source_text,
        font_weight_label=infer_font_weight(font),
        font_path=font.path,
        font_family=font.family,
        font_style=font.style,
        font_size=font_size,
        image=image,
    )


def save_image_sample(
    *,
    output_dir: Path,
    split: str,
    sample_index: int,
    source_kind: str,
    source_origin: str,
    ttb_id: str,
    source_image_path: str,
    source_crop_path: str,
    derived_from_engine: str,
    panel_warning_label: str,
    heading_text_label: str,
    boldness_label: str,
    quality_label: str,
    source_text: str,
    font_weight_label: str,
    font_path: str,
    font_family: str,
    font_style: str,
    font_size: int,
    image: Image.Image,
) -> V6Sample:
    """Persist an image and return its manifest row."""

    sample_id = f"{split}_{sample_index:06d}"
    filename = (
        f"{sample_id}__src-{source_kind}"
        f"__panel-{panel_warning_label}"
        f"__text-{heading_text_label}"
        f"__bold-{boldness_label}"
        f"__quality-{quality_label}.png"
    )
    crop_rel = Path("crops") / filename
    crop_abs = output_dir / crop_rel
    crop_abs.parent.mkdir(parents=True, exist_ok=True)
    image.save(crop_abs)
    return V6Sample(
        split=split,
        sample_id=sample_id,
        source_kind=source_kind,
        source_origin=source_origin,
        ttb_id=ttb_id,
        source_image_path=source_image_path,
        source_crop_path=source_crop_path,
        derived_from_engine=derived_from_engine,
        panel_warning_label=panel_warning_label,
        heading_text_label=heading_text_label,
        boldness_label=boldness_label,
        quality_label=quality_label,
        source_text=source_text,
        font_weight_label=font_weight_label,
        font_path=font_path,
        font_family=font_family,
        font_style=font_style,
        font_size=font_size,
        crop_path=str(crop_rel),
    )


def estimate_font_size(crop_path: Path, font_path: str, rng: random.Random) -> int:
    """Estimate a plausible font size from a real crop width."""

    image = normalize_heading_crop(Image.open(crop_path).convert("L"))
    target_width = max(120, image.size[0] - 24)
    size = 18
    while size < 56:
        face = ImageFont.truetype(font_path, size)
        bbox = ImageDraw.Draw(Image.new("L", (1200, 200), 255)).textbbox((0, 0), CORRECT_HEADER, font=face)
        width = bbox[2] - bbox[0]
        if width >= target_width:
            break
        size += 1
    return max(18, min(size + rng.randint(-1, 2), 54))


def mutate_real_background(crop_path: Path, source_text: str, font: FontRecord, font_size: int, rng: random.Random) -> Image.Image:
    """Create a synthetic heading over a real COLA crop background."""

    base = normalize_heading_crop(Image.open(crop_path).convert("L"))
    blurred = base.filter(ImageFilter.GaussianBlur(radius=7.5))
    background = ImageEnhance.Contrast(blurred).enhance(0.55)
    background = ImageEnhance.Brightness(background).enhance(1.08)
    canvas = background.copy()
    draw = ImageDraw.Draw(canvas)
    bbox = find_dark_bbox(base)
    if bbox is not None:
        pad_x = max(8, int((bbox[2] - bbox[0]) * 0.12))
        pad_y = max(6, int((bbox[3] - bbox[1]) * 0.25))
        fill = int(ImageStat.Stat(background).median[0])
        draw.rectangle(
            (
                max(0, bbox[0] - pad_x),
                max(0, bbox[1] - pad_y),
                min(canvas.size[0], bbox[2] + pad_x),
                min(canvas.size[1], bbox[3] + pad_y),
            ),
            fill=fill,
        )
    face = ImageFont.truetype(font.path, font_size)
    text_bbox = draw.textbbox((0, 0), source_text, font=face)
    text_w = text_bbox[2] - text_bbox[0]
    text_h = text_bbox[3] - text_bbox[1]
    x = max(8, (canvas.size[0] - text_w) // 2 - text_bbox[0] + rng.randint(-4, 4))
    y = max(6, (canvas.size[1] - text_h) // 2 - text_bbox[1] + rng.randint(-2, 2))
    draw.text((x, y), source_text, fill=0, font=face)
    if rng.random() < 0.5:
        canvas = ImageEnhance.Contrast(canvas).enhance(rng.uniform(0.85, 1.1))
    return canvas


def normalize_heading_crop(image: Image.Image) -> Image.Image:
    """Rotate portrait warning crops into a horizontal strip and add padding."""

    working = image
    if working.size[1] > int(working.size[0] * 1.15):
        working = working.rotate(90, expand=True)
    working = ImageOps.expand(working, border=(10, 8, 10, 8), fill=255)
    min_width = 320
    min_height = 52
    canvas_w = max(min_width, working.size[0])
    canvas_h = max(min_height, working.size[1])
    if (canvas_w, canvas_h) == working.size:
        return working
    canvas = Image.new("L", (canvas_w, canvas_h), color=255)
    paste_x = max(0, (canvas_w - working.size[0]) // 2)
    paste_y = max(0, (canvas_h - working.size[1]) // 2)
    canvas.paste(working, (paste_x, paste_y))
    return canvas


def find_dark_bbox(image: Image.Image) -> tuple[int, int, int, int] | None:
    """Find a rough text bounding box inside a grayscale crop."""

    pixels = image.load()
    width, height = image.size
    min_x = width
    min_y = height
    max_x = -1
    max_y = -1
    found = False
    for y in range(height):
        for x in range(width):
            if pixels[x, y] < 190:
                found = True
                if x < min_x:
                    min_x = x
                if y < min_y:
                    min_y = y
                if x > max_x:
                    max_x = x
                if y > max_y:
                    max_y = y
    if not found:
        return None
    return min_x, min_y, max_x + 1, max_y + 1


def normalize_panel_preview(image: Image.Image) -> Image.Image:
    """Resize a full panel image for compact inspection."""

    gray = ImageOps.grayscale(image)
    max_width = 480
    if gray.size[0] <= max_width:
        return gray
    ratio = max_width / gray.size[0]
    return gray.resize((max_width, max(1, int(gray.size[1] * ratio))), Image.Resampling.LANCZOS)


def infer_font_weight(font: FontRecord) -> str:
    """Recover the two-class font-weight provenance."""

    lowered = font.path.lower()
    if any(token in lowered for token in ("extrabold", "extra-bold", "ultrabold", "ultra-bold", "black", "heavy", "bold")):
        return "bold"
    return "not_bold"


def parse_optional_float(value: str | None) -> float | None:
    """Parse a nullable float string."""

    if value in (None, ""):
        return None
    return float(value)


def write_manifest(path: Path, samples: list[V6Sample]) -> None:
    """Write the audit manifest."""

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(samples[0]).keys()))
        writer.writeheader()
        for sample in samples:
            writer.writerow(asdict(sample))


def write_summary(path: Path, samples: list[V6Sample], split_counts: dict[str, int], app_split: dict[str, str]) -> None:
    """Write the audit-v6 machine-readable summary."""

    labels = {
        "source_kind": count_by(samples, "source_kind"),
        "source_origin": count_by(samples, "source_origin"),
        "panel_warning_label": count_by(samples, "panel_warning_label"),
        "heading_text_label": count_by(samples, "heading_text_label"),
        "boldness_label": count_by(samples, "boldness_label"),
        "quality_label": count_by(samples, "quality_label"),
    }
    split_labels: dict[str, dict[str, dict[str, int]]] = {}
    for split in ("train", "validation", "test"):
        subset = [sample for sample in samples if sample.split == split]
        split_labels[split] = {
            "source_kind": count_by(subset, "source_kind"),
            "source_origin": count_by(subset, "source_origin"),
            "panel_warning_label": count_by(subset, "panel_warning_label"),
            "heading_text_label": count_by(subset, "heading_text_label"),
            "boldness_label": count_by(subset, "boldness_label"),
        }
    cola_derived = sum(1 for sample in samples if sample.source_origin.startswith("real_cola"))
    synthetic_only = sum(1 for sample in samples if sample.source_origin == "synthetic")
    summary = {
        "purpose": "audit-v6 seeded typography image set with real COLA visual context",
        "seed": 20260503,
        "split_counts_requested": split_counts,
        "split_counts_actual": {split: sum(1 for sample in samples if sample.split == split) for split in split_counts},
        "total_samples": len(samples),
        "source_mix": {
            "cola_derived_rows": cola_derived,
            "synthetic_only_rows": synthetic_only,
            "cola_derived_share": round(cola_derived / max(len(samples), 1), 6),
            "synthetic_only_share": round(synthetic_only / max(len(samples), 1), 6),
        },
        "labels": labels,
        "labels_by_split": split_labels,
        "real_ttb_id_split_counts": dict(sorted(Counter(app_split.values()).items())),
        "policy": [
            "Generated bold fonts are bold.",
            "Generated non-bold fonts are not bold.",
            "No-warning panels are valid panel-level negatives and are not application-level failures by themselves.",
            "heading_text_label and boldness_label are not_applicable for warning_absent panels.",
            "unreadable_review is reserved for visually unreliable evidence.",
        ],
    }
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_readme(path: Path, samples: list[V6Sample], split_counts: dict[str, int]) -> None:
    """Write a short guide next to the audit-v6 image set."""

    text = f"""# Typography Audit Dataset v6

This image set has the same inspection role as `audit-v5`, but it seeds the
synthetic typography audit with real visual context from approved COLA
Cloud-derived public label images.

Requested split sizes:

- train: {split_counts['train']:,}
- validation: {split_counts['validation']:,}
- test: {split_counts['test']:,}

Actual total image samples: {len(samples):,}

Source kinds:

- `real_heading_positive`
- `real_background_non_bold`
- `real_no_warning_panel`
- `synthetic_bold_positive`
- `synthetic_non_bold`
- `synthetic_incorrect`
- `review_unreadable`

Task labels:

- `panel_warning_label`: `warning_present`, `warning_absent`, `unreadable_review`
- `heading_text_label`: `correct_government_warning`, `incorrect_heading_text`, `unreadable_review`, `not_applicable`
- `boldness_label`: `bold`, `not_bold`, `unreadable_review`, `not_applicable`

Important:

- Split assignment is by `ttb_id` for real COLA-derived rows.
- No-warning panels are panel-level negatives only.
- Real-background mutations keep real COLA visual context while injecting
  explicit non-bold or review examples.
- `index.html` is the browser contact sheet.
- `manifest.csv` is the full image manifest.
- `by_*` directories are hard-linked class views for fast visual inspection.
- This image set is for inspection and later training; it does not itself
  train or promote a runtime model.
"""
    path.write_text(text, encoding="utf-8")


def write_audit_views(output_dir: Path, samples: list[V6Sample]) -> None:
    """Create audit-v5-style hard-linked class views."""

    for sample in samples:
        source = output_dir / sample.crop_path
        filename = source.name
        destinations = [
            output_dir / "by_split" / sample.split / filename,
            output_dir / "by_source_kind" / sample.source_kind / filename,
            output_dir / "by_source_origin" / sample.source_origin / filename,
            output_dir / "by_panel_warning" / sample.panel_warning_label / filename,
            output_dir / "by_heading_text" / sample.heading_text_label / filename,
            output_dir / "by_boldness" / sample.boldness_label / filename,
            output_dir / "by_quality" / sample.quality_label / filename,
            output_dir / "by_font_weight" / sample.font_weight_label / filename,
        ]
        for destination in destinations:
            link_or_copy(source, destination)


def link_or_copy(source: Path, destination: Path) -> None:
    """Create a hard link for class views, falling back to a copy."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def sample_for_contact_sheet(rows: list[V6Sample], limit: int, rng: random.Random) -> list[V6Sample]:
    """Sample a representative subset stratified by source kind."""

    by_kind: dict[str, list[V6Sample]] = defaultdict(list)
    for row in rows:
        by_kind[row.source_kind].append(row)
    sampled: list[V6Sample] = []
    per_kind = max(1, limit // max(len(by_kind), 1))
    for kind in SOURCE_KINDS:
        bucket = list(by_kind.get(kind, []))
        rng.shuffle(bucket)
        sampled.extend(bucket[:per_kind])
    if len(sampled) < min(limit, len(rows)):
        seen = {row.sample_id for row in sampled}
        remainder = [row for row in rows if row.sample_id not in seen]
        rng.shuffle(remainder)
        sampled.extend(remainder[: min(limit, len(rows)) - len(sampled)])
    sampled.sort(key=lambda row: row.sample_id)
    return sampled


def write_contact_sheet(path: Path, rows: list[V6Sample], limit: int, rng: random.Random) -> None:
    """Write the audit-v6 browser contact sheet."""

    visible_rows = rows if limit <= 0 or limit >= len(rows) else sample_for_contact_sheet(rows, limit, rng)
    table_rows = []
    for row in visible_rows:
        table_rows.append(
            "<tr>"
            f"<td>{html.escape(row.sample_id)}</td>"
            f"<td>{html.escape(row.split)}</td>"
            f"<td>{html.escape(row.source_kind)}</td>"
            f"<td>{html.escape(row.panel_warning_label)}</td>"
            f"<td>{html.escape(row.heading_text_label)}</td>"
            f"<td>{html.escape(row.boldness_label)}</td>"
            f"<td>{html.escape(row.quality_label)}</td>"
            f"<td>{html.escape(row.ttb_id)}</td>"
            f"<td>{html.escape(row.source_origin)}</td>"
            f"<td><img src=\"../{html.escape(row.crop_path)}\" alt=\"{html.escape(row.sample_id)}\"></td>"
            "</tr>"
        )
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Typography Audit Dataset v6</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 24px; color: #111; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 6px 8px; vertical-align: middle; }}
    th {{ position: sticky; top: 0; background: #f5f5f5; }}
    img {{ max-height: 84px; max-width: 520px; background: white; }}
    code {{ background: #f5f5f5; padding: 1px 4px; }}
  </style>
</head>
<body>
  <h1>Typography Audit Dataset v6</h1>
  <p>
    Audit-v5-style inspection sheet from the gitignored audit-v6 image set.
    Showing {len(visible_rows):,} of {len(rows):,} rows.
  </p>
  <table>
    <thead>
      <tr>
        <th>Sample</th>
        <th>Split</th>
        <th>Source Kind</th>
        <th>Panel Label</th>
        <th>Heading Label</th>
        <th>Boldness Label</th>
        <th>Quality</th>
        <th>TTB ID</th>
        <th>Origin</th>
        <th>Preview</th>
      </tr>
    </thead>
    <tbody>
      {''.join(table_rows)}
    </tbody>
  </table>
</body>
</html>
"""
    path.write_text(document, encoding="utf-8")


def count_by(samples: Iterable[V6Sample], attr: str) -> dict[str, int]:
    """Count sample values by attribute."""

    counts: dict[str, int] = {}
    for sample in samples:
        value = str(getattr(sample, attr))
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def write_json(path: Path, payload: object) -> None:
    """Write stable pretty JSON."""

    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
