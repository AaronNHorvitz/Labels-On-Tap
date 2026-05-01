from fastapi.testclient import TestClient

from app.main import app


def test_health_route():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_clean_demo_route_renders_pass_result():
    client = TestClient(app)
    response = client.get("/demo/clean", follow_redirects=True)
    assert response.status_code == 200
    assert "Review Results" in response.text
    assert "Pass" in response.text
    assert "fixture ground truth" in response.text


def test_batch_demo_route_renders_counts_and_csv():
    client = TestClient(app)
    response = client.get("/demo/batch", follow_redirects=True)
    assert response.status_code == 200
    assert "8 / 8" in response.text
    assert "Needs Review" in response.text

    job_id = str(response.url).rstrip("/").split("/")[-1]
    csv_response = client.get(f"/jobs/{job_id}/results.csv")
    assert csv_response.status_code == 200
    assert "filename,overall_verdict" in csv_response.text
