import io
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.entities import Pipeline
from app.pipelines.engine import pipeline_json, standalone_script
from app.services.loader import clean_file, get_ds, load_frame

router = APIRouter(prefix="/api/export", tags=["export"])


@router.get("/{ds_id}/{kind}")
def export(ds_id: str, kind: str, format: str = "json", db: Session = Depends(get_db)):
    """kind: csv | xlsx | parquet | pipeline (format=json|python) | report"""
    ds = get_ds(db, ds_id)
    if not clean_file(ds.id).exists():
        raise HTTPException(409, "Belum ada hasil cleaning. Jalankan POST /api/datasets/{id}/clean terlebih dahulu.")
    stem = ds.name.rsplit(".", 1)[0]

    def send(content, media, ext):
        return Response(content, media_type=media, headers={"Content-Disposition": f'attachment; filename="{stem}_clean{ext}"'})

    if kind == "csv":
        return send(clean_file(ds.id).read_bytes(), "text/csv", ".csv")
    if kind in ("xlsx", "parquet"):
        df, buf = load_frame(clean_file(ds.id)), io.BytesIO()
        if kind == "xlsx":
            df.to_excel(buf, index=False, engine="openpyxl")
            return send(buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx")
        df.to_parquet(buf, index=False, engine="pyarrow")
        return send(buf.getvalue(), "application/octet-stream", ".parquet")
    if kind in ("pipeline", "report"):
        p = db.query(Pipeline).filter(Pipeline.dataset_id == ds.id).order_by(Pipeline.created_at.desc()).first()
        if not p:
            raise HTTPException(409, "Pipeline belum dibuat untuk dataset ini.")
        steps = [{**s, "enabled": True} for s in p.steps]
        if kind == "report":
            body = {"dataset": ds.name, "rows": ds.n_rows, "quality_before": ds.analysis["quality"],
                    "quality_after": ds.after_analysis["quality"], "issues_before": ds.analysis["issues"],
                    "issues_after": ds.after_analysis["issues"], "pipeline": pipeline_json(steps, p.name)}
            return Response(json.dumps(body, indent=2, default=str), media_type="application/json")
        if format == "python":
            return Response(standalone_script(steps, p.name), media_type="text/x-python", headers={"Content-Disposition": 'attachment; filename="pipeline.py"'})
        return Response(json.dumps(pipeline_json(steps, p.name), indent=2), media_type="application/json")
    raise HTTPException(404, "Jenis ekspor tidak dikenal. Gunakan csv, xlsx, parquet, pipeline, atau report.")
