"""Engine pipeline CSV2Trust: profiling, deteksi masalah, skor kualitas, transformasi.
Semua deterministik dan reproducible. LLM tidak pernah mengubah data."""
import inspect
import json
import math
import re

import numpy as np
import pandas as pd

from app.validators import rules
from app.validators.rules import (EMAIL, MISSING, check, format_num, is_missing, norm_val,
                                  normalize_phone, parse_currency, parse_date, title_case)

OPS = ["standardize_missing", "normalize_email", "standardize_phone", "parse_date",
       "convert_currency", "normalize_name", "impute_median", "remove_duplicates"]
LABEL = {
    "standardize_missing": "Standarkan penanda missing", "normalize_email": "Normalisasi email (lowercase)",
    "standardize_phone": "Standarkan telepon (E.164 +62)", "parse_date": "Parse tanggal ke ISO 8601",
    "convert_currency": "Konversi currency ke numerik IDR", "normalize_name": "Rapikan kapitalisasi nama",
    "impute_median": "Isi missing dengan median", "remove_duplicates": "Hapus baris duplikat",
}


def _is_num(v) -> bool:
    try:
        float(str(v).replace(",", "."))
        return True
    except ValueError:
        return False


def _num_val(v, sem):
    if sem == "currency":
        return parse_currency(v)
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        return None


def detect_semantic(name, vals):
    n = str(name).lower()
    if re.search(r"mail", n): return "email"
    if re.search(r"phone|telp|telepon|whatsapp|(^|[_\s])(hp|wa)$", n): return "phone"
    if re.search(r"date|tgl|tanggal|waktu|time", n): return "date"
    if re.search(r"revenue|harga|price|amount|total|biaya|nominal|gaji|salary|cost", n): return "currency"
    if re.fullmatch(r"age|umur|usia", n): return "age"
    if re.search(r"(^|[_\s-])id$|kode", n): return "id"
    if re.search(r"name|nama", n): return "name"
    nm = [v for v in vals if not is_missing(v)]
    if nm and sum(bool(EMAIL.match(str(v))) for v in nm) / len(nm) > 0.7: return "email"
    if nm and all(_is_num(v) for v in nm): return "number"
    return "text"


def row_key(row, cols, sem):
    return "|".join(norm_val(row[c], sem.get(c, "text")) for c in cols)


def transform_fn(op):
    return {
        "normalize_email": lambda v: v.strip().lower(),
        "standardize_phone": lambda v: normalize_phone(v) or v,
        "parse_date": lambda v: parse_date(v) or v,
        "convert_currency": lambda v: v if parse_currency(v) is None else format_num(parse_currency(v)),
        "normalize_name": title_case,
    }[op]


def apply_steps(df, steps, sem):
    """Jalankan langkah berurutan. Return (dataframe baru, indeks baris asal)."""
    d = df.copy()
    src = list(range(len(d)))
    cols = list(d.columns)
    for s in steps:
        if not s.get("enabled", True):
            continue
        op, c = s["operation"], s.get("column", "*")
        if op == "standardize_missing":
            d = d.apply(lambda col: col.map(lambda v: "" if is_missing(v) else v))
        elif op == "remove_duplicates":
            keys = [row_key(r, cols, sem) for r in d.to_dict("records")]
            keep = ~pd.Series(keys).duplicated().to_numpy()
            d = d.loc[keep].reset_index(drop=True)
            src = [x for x, k in zip(src, keep) if k]
        elif c in d.columns:
            if op == "impute_median":
                nums = [float(v) for v in d[c] if not is_missing(v) and _is_num(v)]
                if nums:
                    med = float(np.median(nums))
                    fill = str(int(math.floor(med + 0.5))) if sem.get(c) == "age" else format_num(round(med, 2))
                    d[c] = d[c].map(lambda v: fill if is_missing(v) else v)
            else:
                f = transform_fn(op)
                d[c] = d[c].map(lambda v: v if is_missing(v) else f(v))
    return d.reset_index(drop=True), src


def analyze(df):
    cols = list(df.columns)
    n = len(df)
    data = {c: [str(v) for v in df[c].tolist()] for c in cols}
    sem = {c: detect_semantic(c, data[c]) for c in cols}
    issues, profiles = [], []

    def add(column, type_, severity, rows, message, fix, confidence, fix_key=None):
        issues.append({"id": f"i{len(issues)}", "column": column, "type": type_, "severity": severity,
                       "affected_rows": len(rows), "row_samples": rows[:20], "message": message,
                       "suggested_fix": fix, "confidence": confidence, "fix_key": fix_key})

    def pick(c, pred):
        return [i + 1 for i, v in enumerate(data[c]) if not is_missing(v) and pred(v)]

    missing_cells = 0
    for c in cols:
        s, vals = sem[c], data[c]
        miss = [i + 1 for i, v in enumerate(vals) if is_missing(v)]
        missing_cells += len(miss)
        nm = [v for v in vals if not is_missing(v)]
        nums = []
        if s not in ("phone", "date", "id", "email", "name"):
            nums = [x for x in (_num_val(v, s) for v in nm) if x is not None]
        numeric = bool(nm) and len(nums) >= 0.6 * len(nm)
        null_pct = round(len(miss) / n * 100, 1)
        prof = {"name": c, "semantic": s, "null_pct": null_pct, "unique": len(set(nm)),
                "duplicates": len(nm) - len(set(nm)), "numeric": numeric}
        if numeric:
            arr = np.array(nums, dtype=float)
            prof.update(min=float(arr.min()), max=float(arr.max()), mean=float(arr.mean()),
                        median=float(np.median(arr)), std=float(arr.std()))
        profiles.append(prof)

        can_impute = s in ("age", "number") and numeric
        if miss:
            add(c, "Missing values", "warning" if null_pct > 10 else "info", miss,
                f"{null_pct}% nilai kosong di kolom {c}.",
                "Isi dengan median kolom." if can_impute else "Tinjau manual atau lengkapi dari sumber data.",
                0.9, f"impute_median:{c}" if can_impute else None)
        if s == "email":
            bad = pick(c, lambda v: not EMAIL.match(v.strip().lower()))
            if bad:
                add(c, "Invalid email format", "critical", bad, f'{len(bad)} email tidak valid (mis. "{vals[bad[0]-1]}").',
                    "Perbaiki manual; email tidak valid tidak ditebak otomatis.", 0.98)
            cs = pick(c, lambda v: v != v.strip().lower() and EMAIL.match(v.strip().lower()))
            if cs:
                add(c, "Inconsistent email casing", "warning", cs, "Email memakai huruf kapital/spasi.", "Ubah ke lowercase.", 0.97, f"normalize_email:{c}")
        if s == "phone":
            bad = pick(c, lambda v: normalize_phone(v) is None)
            if bad:
                add(c, "Invalid phone number", "warning", bad, f'{len(bad)} nomor telepon tidak valid (mis. "{vals[bad[0]-1]}").', "Periksa manual.", 0.9)
            f = pick(c, lambda v: normalize_phone(v) not in (None, v))
            if f:
                add(c, "Inconsistent phone format", "warning", f, "Format nomor telepon berbeda-beda.", "Standarkan ke format E.164 Indonesia (+62...).", 0.95, f"standardize_phone:{c}")
        if s == "date":
            bad = pick(c, lambda v: parse_date(v) is None)
            if bad:
                add(c, "Invalid date", "critical", bad, f'{len(bad)} tanggal tidak dapat dibaca (mis. "{vals[bad[0]-1]}").', "Perbaiki manual.", 0.95)
            f = pick(c, lambda v: parse_date(v) not in (None, v))
            if f:
                add(c, "Inconsistent date formats", "warning", f, "Format tanggal tidak konsisten. Format ambigu dibaca day-first.", "Normalisasi ke ISO 8601 (YYYY-MM-DD).", 0.9, f"parse_date:{c}")
        if s == "currency":
            bad = pick(c, lambda v: parse_currency(v) is None)
            if bad:
                add(c, "Invalid numeric value", "critical", bad, f"{len(bad)} nilai bukan angka/currency valid.", "Perbaiki manual.", 0.95)
            f = pick(c, lambda v: parse_currency(v) is not None and format_num(parse_currency(v)) != v)
            if f:
                ex = list(dict.fromkeys(vals[i - 1] for i in f[:3]))
                add(c, "Inconsistent currency formatting", "warning", f, "Contoh: " + " | ".join(ex), "Normalisasi semua nilai menjadi angka IDR.", 0.95, f"convert_currency:{c}")
        if s == "age":
            bad = pick(c, lambda v: not (_num_val(v, s) is not None and 0 <= _num_val(v, s) <= 120))
            if bad:
                add(c, "Age out of range", "critical", bad, f"{len(bad)} umur di luar 0-120 (mis. {vals[bad[0]-1]}).", "Periksa manual.", 0.99)
        if s == "name":
            f = pick(c, lambda v: v != title_case(v))
            if f:
                add(c, "Inconsistent capitalization", "info", f, "Kapitalisasi/spasi nama tidak seragam.", "Ubah ke Title Case.", 0.85, f"normalize_name:{c}")
        if numeric and len(nums) >= 4 and s in ("age", "number", "currency"):
            q1, q3 = np.percentile(arr, [25, 75])
            lo, hi = q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)
            out = pick(c, lambda v: _num_val(v, s) is not None and (_num_val(v, s) < lo or _num_val(v, s) > hi))
            if out:
                add(c, "Potential outliers (IQR)", "info", out, f"{len(out)} nilai di luar rentang {lo:.0f} - {hi:.0f}.", "Tidak dihapus otomatis; tentukan sendiri.", 0.7)

    if any(v.strip() != "" and v.strip().lower() in MISSING for c in cols for v in data[c]):
        add("*", "Inconsistent missing markers", "info", [], 'Ada penanda kosong seperti "-", "N/A".', "Ubah semua menjadi sel kosong.", 0.9, "standardize_missing:*")

    records = df.to_dict("records")
    seen, dup = set(), []
    for i, r in enumerate(records):
        k = row_key(r, cols, sem)
        if k in seen:
            dup.append(i + 1)
        seen.add(k)
    if dup:
        add("*", "Duplicate rows", "warning", dup, f"{len(dup)} baris duplikat setelah normalisasi (kapitalisasi, format tanggal, currency).", "Hapus duplikat, simpan kemunculan pertama.", 0.92, "remove_duplicates:*")

    # Anomali multivariat (Isolation Forest) pada kolom numerik. Hanya kandidat, tidak dihapus otomatis.
    ncols = [p["name"] for p in profiles if p["numeric"] and sem[p["name"]] in ("age", "number", "currency")]
    if ncols and n >= 50:
        idx = [i for i in range(n) if all(_num_val(data[c][i], sem[c]) is not None and not is_missing(data[c][i]) for c in ncols)]
        if len(idx) >= 50:
            from sklearn.ensemble import IsolationForest
            X = np.array([[_num_val(data[c][i], sem[c]) for c in ncols] for i in idx])
            pred = IsolationForest(n_estimators=100, contamination=0.01, random_state=42).fit_predict(X)
            rows = [idx[j] + 1 for j, p in enumerate(pred) if p == -1]
            add("*", "Multivariate anomalies (Isolation Forest)", "info", rows, f"{len(rows)} baris memiliki kombinasi nilai paling tidak biasa pada kolom {', '.join(ncols)}.", "Kandidat saja, tinjau manual.", 0.6)

    valid = vt = canon = ct = 0
    for c in cols:
        for v in data[c]:
            if is_missing(v):
                continue
            k = check(v, sem[c])
            if k is None:
                continue
            vt += 1
            if k[0]:
                valid += 1
                ct += 1
                canon += bool(k[1])
    pc = lambda a, b: round(a / b * 100, 1) if b else 100.0
    comp = pc(n * len(cols) - missing_cells, n * len(cols))
    val, cons, uniq = pc(valid, vt), pc(canon, ct), pc(len(seen), n)
    quality = {"completeness": comp, "validity": val, "consistency": cons, "uniqueness": uniq,
               "overall": round(comp * 0.25 + val * 0.3 + cons * 0.25 + uniq * 0.2, 1)}

    steps, keys = [], set()
    for i in issues:
        k = i["fix_key"]
        if not k or k in keys:
            continue
        keys.add(k)
        op, col = k.split(":", 1)
        steps.append({"id": f"s{len(steps)}", "operation": op, "column": col, "label": LABEL[op], "enabled": True,
                      "rows": i["affected_rows"], "confidence": i["confidence"]})
    steps.sort(key=lambda s: OPS.index(s["operation"]))
    return {"semantics": sem, "profiles": profiles, "issues": issues, "steps": steps, "quality": quality,
            "stats": {"rows": n, "columns": len(cols), "missing_cells": missing_cells, "duplicate_rows": len(dup)}}


def pipeline_json(steps, name):
    return {"pipeline_name": name, "version": "1.0.0",
            "steps": [{"operation": s["operation"], "column": s.get("column", "*")} for s in steps if s.get("enabled", True)]}


def standalone_script(steps, name):
    """Script Python mandiri (pandas) yang memakai fungsi engine yang sama persis."""
    fns = [rules.is_missing, rules.title_case, rules.format_num, rules.parse_currency, rules.parse_date,
           rules.normalize_phone, rules.norm_val, _is_num, detect_semantic, row_key, transform_fn, apply_steps]
    head = ('"""Pipeline CSV2Trust (dibuat otomatis). Jalankan: python pipeline.py input.csv output.csv"""\n'
            "import json, math, re, sys\nfrom datetime import date\nimport numpy as np\nimport pandas as pd\n\n"
            f"MISSING = set({sorted(MISSING)!r})\nEMAIL = re.compile({EMAIL.pattern!r})\n"
            f"STEPS = json.loads({json.dumps(pipeline_json(steps, name)['steps'])!r})\n\n")
    main = ('\nif __name__ == "__main__":\n'
            '    df = pd.read_csv(sys.argv[1], dtype=str, keep_default_na=False)\n'
            '    sem = {c: detect_semantic(c, df[c].tolist()) for c in df.columns}\n'
            '    out, _ = apply_steps(df, STEPS, sem)\n'
            '    out.to_csv(sys.argv[2], index=False)\n')
    return head + "\n\n".join(inspect.getsource(f) for f in fns) + main
