from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.entities import Dataset, Pipeline, PipelineRun
from app.pipelines.engine import analyze, apply_steps, detect_semantic
from app.schemas.api import PipelineCreate, PipelineRunRequest
from app.services.loader import audit, clean_file, get_ds, load_frame, raw_file

router = APIRouter(prefix="/api/pipelines", tags=["pipelines"])


def _get(db: Session, pid: str) -> Pipeline:
    p = db.get(Pipeline, pid)
    if not p:
        raise HTTPException(404, "Pipeline tidak ditemukan.")
    return p


def _out(p: Pipeline, db: Session) -> dict:
    ds = db.get(Dataset, p.dataset_id)
    return {"id": p.id, "name": p.name, "version": p.version, "dataset_id": p.dataset_id,
            "dataset_name": ds.name if ds else None, "steps": p.steps, "step_count": len(p.steps),
            "quality_after": p.quality_after, "status": p.status, "created_at": p.created_at}


@router.post("", status_code=201)
def create(body: PipelineCreate, db: Session = Depends(get_db)):
    ds = get_ds(db, body.dataset_id)
    p = Pipeline(dataset_id=ds.id, name=body.name, steps=[{"operation": s.operation, "column": s.column} for s in body.steps if s.enabled])
    db.add(p)
    audit(db, "pipeline.create", ds.id)
    db.commit()
    return _out(p, db)


@router.get("")
def list_pipelines(db: Session = Depends(get_db)):
    return [_out(p, db) for p in db.query(Pipeline).order_by(Pipeline.created_at.desc()).all()]


@router.get("/{pid}")
def get_pipeline(pid: str, db: Session = Depends(get_db)):
    return _out(_get(db, pid), db)


@router.post("/{pid}/run")
def run(pid: str, body: PipelineRunRequest = PipelineRunRequest(), db: Session = Depends(get_db)):
    """Jalankan ulang pipeline pada dataset (default: dataset asal, atau dataset lain dengan skema kompatibel)."""
    p = _get(db, pid)
    ds = get_ds(db, body.dataset_id or p.dataset_id)
    df = load_frame(raw_file(ds))
    missing = sorted({s["column"] for s in p.steps if s["column"] != "*" and s["column"] not in df.columns})
    if missing:
        raise HTTPException(422, f"Pipeline tidak kompatibel dengan dataset ini. Kolom tidak ditemukan: {', '.join(missing)}.")
    sem = {c: detect_semantic(c, df[c].tolist()) for c in df.columns}
    after, src = apply_steps(df, p.steps, sem)
    after.to_csv(clean_file(ds.id), index=False)
    aa = analyze(after)
    ds.after_analysis, ds.quality_after, ds.status = aa, aa["quality"]["overall"], "Ready"
    p.status, p.quality_after = "Ready", ds.quality_after
    summary = {"rows_before": len(df), "rows_after": len(after), "quality_after": ds.quality_after}
    db.add(PipelineRun(pipeline_id=p.id, dataset_id=ds.id, summary=summary))
    audit(db, "pipeline.run", p.id)
    db.commit()
    return {"pipeline_id": p.id, "dataset_id": ds.id, **summary}


@router.delete("/{pid}", status_code=204)
def delete(pid: str, db: Session = Depends(get_db)):
    p = _get(db, pid)
    db.query(PipelineRun).filter(PipelineRun.pipeline_id == p.id).delete(synchronize_session=False)
    audit(db, "pipeline.delete", p.id)
    db.delete(p)
    db.commit()
