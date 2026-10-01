import re
from pathlib import Path

import pandas as pd
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import AuditLog, Dataset, Pipeline
from app.pipelines.engine import pipeline_json


def load_frame(path: Path) -> pd.DataFrame:
    """Baca CSV/XLSX sebagai string. Error dikonversi ke ValueError dengan pesan yang manusiawi."""
    try:
        if path.suffix.lower() == ".csv":
            for enc in ("utf-8-sig", "cp1252"):
                try:
                    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding=enc)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raise ValueError("Dataset gagal diproses karena encoding file tidak dapat dikenali. Coba gunakan UTF-8 encoded CSV.")
        else:
            df = pd.read_excel(path, dtype=str, keep_default_na=False)
    except pd.errors.EmptyDataError:
        raise ValueError("Dataset kosong atau tidak memiliki header.")
    except pd.errors.ParserError:
        raise ValueError("Struktur CSV rusak dan tidak dapat dibaca. Periksa pemisah kolom dan tanda kutip.")
    except ValueError:
        raise
    except Exception:
        raise ValueError("File rusak atau formatnya tidak dapat dibaca.")
    df = df.fillna("").astype(str)
    df.columns = [str(c).strip() or f"kolom_{i + 1}" for i, c in enumerate(df.columns)]
    if df.empty:
        raise ValueError("Dataset tidak memiliki baris data.")
    return df


def raw_file(ds: Dataset) -> Path:
    return settings.data_dir / "uploads" / f"{ds.id}{ds.ext}"


def clean_file(ds_id: str) -> Path:
    return settings.data_dir / "processed" / f"{ds_id}.csv"


def get_ds(db: Session, ds_id: str) -> Dataset:
    ds = db.get(Dataset, ds_id)
    if not ds:
        raise HTTPException(404, "Dataset tidak ditemukan.")
    return ds


def audit(db: Session, action: str, entity_id: str) -> None:
    db.add(AuditLog(action=action, entity_id=entity_id))


def safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", Path(name or "dataset").name)[:100] or "dataset"


def make_pipeline(db: Session, ds: Dataset, steps: list, quality: float | None) -> Pipeline:
    stem = Path(ds.name).stem
    p = Pipeline(dataset_id=ds.id, name=f"{stem}_cleaning", steps=pipeline_json(steps, stem)["steps"], quality_after=quality)
    db.add(p)
    return p
