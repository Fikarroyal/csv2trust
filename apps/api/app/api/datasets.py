from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.ai.providers import run_ai
from app.core.config import settings
from app.core.db import get_db
from app.models.entities import Dataset, Pipeline, PipelineRun
from app.pipelines.engine import analyze, apply_steps
from app.schemas.api import CleanRequest
from app.services.loader import audit, clean_file, get_ds, load_frame, make_pipeline, raw_file, safe_name

router = APIRouter(prefix="/api/datasets", tags=["datasets"])
EXTS = {".csv", ".xlsx", ".xls"}


def summary(ds: Dataset) -> dict:
    return {"id": ds.id, "name": ds.name, "status": ds.status, "rows": ds.n_rows, "columns": ds.n_cols,
            "quality_before": ds.quality_before, "quality_after": ds.quality_after, "created_at": ds.created_at}


def _status(a: dict, ok: str) -> str:
    return "Needs Attention" if any(i["severity"] == "critical" for i in a["issues"]) else ok


@router.post("/upload", status_code=201)
def upload(file: UploadFile = File(...), db: Session = Depends(get_db)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in EXTS:
        raise HTTPException(415, "Format tidak didukung. Gunakan .csv, .xlsx, atau .xls.")
    limit = settings.max_upload_mb * 1024 * 1024
    data = file.file.read(limit + 1)
    if not data:
        raise HTTPException(400, "File kosong.")
    if len(data) > limit:
        raise HTTPException(413, f"File terlalu besar (maksimal {settings.max_upload_mb} MB).")
    ds = Dataset(id=str(uuid4()), name=safe_name(file.filename), ext=ext)
    path = raw_file(ds)  # nama file di disk = UUID, bukan nama dari pengguna (anti path traversal)
    path.write_bytes(data)
    try:
        df = load_frame(path)
        a = analyze(df)
    except ValueError as e:
        path.unlink(missing_ok=True)
        raise HTTPException(422, str(e))
    ds.n_rows, ds.n_cols, ds.analysis = len(df), len(df.columns), a
    ds.quality_before, ds.status = a["quality"]["overall"], _status(a, "Analyzed")
    db.add(ds)
    audit(db, "dataset.upload", ds.id)
    db.commit()
    return {**summary(ds), "quality": a["quality"], "issues_detected": len(a["issues"])}


@router.get("")
def list_datasets(db: Session = Depends(get_db)):
    return [summary(d) for d in db.query(Dataset).order_by(Dataset.created_at.desc()).all()]


@router.get("/{ds_id}")
def get_dataset(ds_id: str, db: Session = Depends(get_db)):
    ds = get_ds(db, ds_id)
    return {**summary(ds), "has_clean": clean_file(ds.id).exists(), "semantics": ds.analysis["semantics"]}


@router.delete("/{ds_id}", status_code=204)
def delete_dataset(ds_id: str, db: Session = Depends(get_db)):
    ds = get_ds(db, ds_id)
    pids = [p.id for p in db.query(Pipeline).filter(Pipeline.dataset_id == ds.id).all()]
    db.query(PipelineRun).filter(PipelineRun.pipeline_id.in_(pids) | (PipelineRun.dataset_id == ds.id)).delete(synchronize_session=False)
    db.query(Pipeline).filter(Pipeline.dataset_id == ds.id).delete(synchronize_session=False)
    raw_file(ds).unlink(missing_ok=True)
    clean_file(ds.id).unlink(missing_ok=True)
    audit(db, "dataset.delete", ds.id)
    db.delete(ds)
    db.commit()


@router.get("/{ds_id}/profile")
def profile(ds_id: str, db: Session = Depends(get_db)):
    a = get_ds(db, ds_id).analysis
    return {"stats": a["stats"], "columns": a["profiles"], "quality": a["quality"]}


@router.get("/{ds_id}/issues")
def issues(ds_id: str, db: Session = Depends(get_db)):
    a = get_ds(db, ds_id).analysis
    return {"issues": a["issues"], "recommended_steps": a["steps"]}


@router.post("/{ds_id}/analyze")
def analyze_dataset(ds_id: str, db: Session = Depends(get_db)):
    ds = get_ds(db, ds_id)
    df = load_frame(raw_file(ds))
    a = analyze(df)
    a["ai"] = run_ai(df, a)
    ds.analysis, ds.quality_before, ds.status = a, a["quality"]["overall"], _status(a, "Analyzed")
    audit(db, "dataset.analyze", ds.id)
    db.commit()
    return {"quality": a["quality"], "issues_detected": len(a["issues"]), "ai": a["ai"]}


@router.post("/{ds_id}/clean")
def clean(ds_id: str, body: CleanRequest = CleanRequest(), db: Session = Depends(get_db)):
    ds = get_ds(db, ds_id)
    df = load_frame(raw_file(ds))
    a = ds.analysis
    steps = [s.model_dump() for s in body.steps] if body.steps is not None else a["steps"]
    after, src = apply_steps(df, steps, a["semantics"])
    after.to_csv(clean_file(ds.id), index=False)
    aa = analyze(after)
    cells = int((df.iloc[src].reset_index(drop=True).to_numpy() != after.to_numpy()).sum())
    ds.after_analysis, ds.quality_after, ds.status = aa, aa["quality"]["overall"], _status(aa, "Ready")
    p = make_pipeline(db, ds, steps, ds.quality_after)
    audit(db, "dataset.clean", ds.id)
    db.commit()
    return {"quality_before": ds.quality_before, "quality_after": ds.quality_after, "rows_before": len(df),
            "rows_after": len(after), "rows_removed": len(df) - len(after), "cells_changed": cells,
            "issues_remaining": len(aa["issues"]), "pipeline_id": p.id, "pipeline_steps": p.steps}


@router.post("/{ds_id}/validate")
def validate(ds_id: str, db: Session = Depends(get_db)):
    ds = get_ds(db, ds_id)
    path = clean_file(ds.id) if clean_file(ds.id).exists() else raw_file(ds)
    a = analyze(load_frame(path))
    checks = []
    for c, s in a["semantics"].items():
        iss = [i for i in a["issues"] if i["column"] == c and i["type"] != "Potential outliers (IQR)"]
        st = "FAIL" if any(i["severity"] == "critical" for i in iss) else "WARNING" if any(i["severity"] == "warning" for i in iss) else "PASS"
        checks.append({"column": c, "semantic_type": s, "status": st, "issues": [i["type"] for i in iss]})
    dup = any(i["type"] == "Duplicate rows" for i in a["issues"])
    checks.append({"column": "*", "semantic_type": "dataset", "status": "WARNING" if dup else "PASS", "issues": ["Duplicate rows"] if dup else []})
    counts = {k: sum(c["status"] == k for c in checks) for k in ("PASS", "WARNING", "FAIL")}
    ds.status = "Needs Attention" if counts["FAIL"] else "Validated"
    audit(db, "dataset.validate", ds.id)
    db.commit()
    return {"quality": a["quality"], "quality_before": ds.quality_before, "checks": checks, "summary": counts}


@router.get("/{ds_id}/preview")
def preview(ds_id: str, version: str = "raw", limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    ds = get_ds(db, ds_id)
    if version == "clean":
        if not clean_file(ds.id).exists():
            raise HTTPException(409, "Belum ada hasil cleaning untuk dataset ini.")
        path = clean_file(ds.id)
    else:
        path = raw_file(ds)
    df = load_frame(path)
    limit = max(1, min(limit, 500))
    return {"version": version, "total": len(df), "columns": list(df.columns), "rows": df.iloc[offset:offset + limit].to_dict("records")}


@router.get("/{ds_id}/quality")
def quality(ds_id: str, db: Session = Depends(get_db)):
    ds = get_ds(db, ds_id)
    return {"before": ds.analysis["quality"], "after": ds.after_analysis["quality"] if ds.after_analysis else None}
