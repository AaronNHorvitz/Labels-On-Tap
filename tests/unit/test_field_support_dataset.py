from scripts.build_field_support_dataset import build_pairs, clean_cell


def test_clean_cell_preserves_zero_label():
    assert clean_cell(0) == "0"
    assert clean_cell(1) == "1"
    assert clean_cell(None) == ""


def test_build_pairs_creates_same_split_negative_labels():
    targets = [
        {
            "target_id": "target-a",
            "split": "train",
            "ttb_id": "1",
            "field_name": "brand_name",
            "expected": "Alpha",
            "expected_normalized": "alpha",
            "application_path": "a.json",
            "image_dir": "images/1",
            "local_image_count": "1",
            "product_type": "wine",
            "origin_bucket": "domestic",
            "image_bucket": "single_panel",
            "month_key": "2026-01",
            "imported": "false",
        },
        {
            "target_id": "target-b",
            "split": "train",
            "ttb_id": "2",
            "field_name": "brand_name",
            "expected": "Beta",
            "expected_normalized": "beta",
            "application_path": "b.json",
            "image_dir": "images/2",
            "local_image_count": "1",
            "product_type": "wine",
            "origin_bucket": "domestic",
            "image_bucket": "single_panel",
            "month_key": "2026-01",
            "imported": "false",
        },
    ]

    pairs = build_pairs(targets, negative_per_positive=1, seed=20260503)

    labels = [pair["label"] for pair in pairs]
    assert labels.count(1) == 2
    assert labels.count(0) == 2
    assert all(pair["split"] == "train" for pair in pairs)
    assert all(
        pair["source_ttb_id"] != pair["ttb_id"]
        for pair in pairs
        if pair["label"] == 0
    )
