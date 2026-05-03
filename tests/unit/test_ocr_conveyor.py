import csv

from PIL import Image

from scripts.run_ocr_conveyor import build_image_manifest, build_jobs, chunked, job_id_for


def write_split_manifest(path, image_dir):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["ttb_id", "image_dir"])
        writer.writeheader()
        writer.writerow({"ttb_id": "12345678901234", "image_dir": str(image_dir)})


def test_chunked_and_job_ids_are_stable():
    assert [[1, 2], [3, 4], [5]] == list(chunked([1, 2, 3, 4, 5], 2))
    assert job_id_for("doctr", "train", 7) == "doctr_train_000007"


def test_build_manifest_preflights_images_and_jobs_ignore_invalid_files(tmp_path):
    split_dir = tmp_path / "splits"
    image_dir = tmp_path / "images" / "12345678901234"
    split_dir.mkdir()
    image_dir.mkdir(parents=True)
    Image.new("RGB", (16, 16), "white").save(image_dir / "valid.png")
    (image_dir / "broken.png").write_bytes(b"not a real png")
    write_split_manifest(split_dir / "train_applications.csv", image_dir)

    rows = build_image_manifest(split_dir=split_dir, splits=["train"], limit_images=None)

    assert [row.preflight_status for row in rows] == ["invalid", "valid"]
    jobs = build_jobs(rows, engines=["doctr", "openocr"], chunk_size=1)
    assert [job.engine for job in jobs] == ["doctr", "openocr"]
    assert all(job.image_count == 1 for job in jobs)
    assert all(job.image_paths[0].endswith("valid.png") for job in jobs)
