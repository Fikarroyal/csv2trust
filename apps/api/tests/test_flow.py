from pathlib import Path

SAMPLE = Path(__file__).resolve().parents[3] / "data" / "samples" / "messy_customers.csv"


def up(client, name="messy_customers.csv", content=None):
    content = SAMPLE.read_bytes() if content is None else content
    return client.post("/api/datasets/upload", files={"file": (name, content, "text/csv")})


def test_full_flow(client):
    r = up(client)
    assert r.status_code == 201
    ds = r.json()
    i = ds["id"]
    assert ds["rows"] == 11 and ds["columns"] == 7

    prof = client.get(f"/api/datasets/{i}/profile").json()
    assert len(prof["columns"]) == 7 and prof["stats"]["duplicate_rows"] == 1

    types = {x["type"] for x in client.get(f"/api/datasets/{i}/issues").json()["issues"]}
    assert {"Invalid email format", "Inconsistent date formats", "Duplicate rows", "Age out of range"} <= types

    ai = client.post(f"/api/datasets/{i}/analyze").json()["ai"]
    assert ai["provider"] == "mock" and ai["recommendations"]

    c = client.post(f"/api/datasets/{i}/clean").json()
    assert c["quality_after"] > c["quality_before"] and c["rows_after"] == 10 and c["cells_changed"] > 0

    v = client.post(f"/api/datasets/{i}/validate").json()
    assert v["summary"]["FAIL"] >= 1 and any(x["column"] == "Email" and x["status"] == "FAIL" for x in v["checks"])

    csv = client.get(f"/api/export/{i}/csv").text
    assert "+628123456789" in csv and "2026-09-01" in csv and "Rp" not in csv
    assert client.get(f"/api/export/{i}/xlsx").content[:2] == b"PK"
    assert client.get(f"/api/export/{i}/parquet").content[:4] == b"PAR1"
    pj = client.get(f"/api/export/{i}/pipeline").json()
    assert any(s["operation"] == "remove_duplicates" for s in pj["steps"])
    compile(client.get(f"/api/export/{i}/pipeline?format=python").text, "pipeline.py", "exec")
    assert client.get(f"/api/export/{i}/report").json()["quality_after"]["overall"] > 0

    pid = client.get("/api/pipelines").json()[0]["id"]
    j = up(client, "second.csv").json()["id"]
    run = client.post(f"/api/pipelines/{pid}/run", json={"dataset_id": j})
    assert run.status_code == 200 and run.json()["rows_after"] == 10
    assert client.delete(f"/api/pipelines/{pid}").status_code == 204
    assert client.delete(f"/api/datasets/{i}").status_code == 204
    assert client.get(f"/api/datasets/{i}").status_code == 404


def test_upload_errors(client):
    assert up(client, "x.exe", b"abc").status_code == 415
    assert up(client, "empty.csv", b"").status_code == 400
    assert up(client, "header_only.csv", b"a,b,c\n").status_code == 422
    assert up(client, "../../evil.csv", b"a,b\n1,2\n").status_code == 201
    assert client.get("/api/datasets/tidak-ada").status_code == 404
    assert client.get("/api/export/tidak-ada/csv").status_code == 404
