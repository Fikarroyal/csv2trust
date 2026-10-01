"""Aturan validasi dan normalisasi nilai. Deterministik, tanpa LLM."""
import math
import re
from datetime import date

MISSING = {"", "-", "n/a", "na", "null", "none", "nan", "?"}
EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")


def is_missing(v) -> bool:
    return str(v).strip().lower() in MISSING


def title_case(v) -> str:
    return " ".join(w[:1].upper() + w[1:].lower() for w in str(v).split())


def format_num(n) -> str:
    return str(int(n)) if float(n).is_integer() else str(n)


def parse_currency(v):
    s = re.sub(r"rp\.?|idr", "", str(v), flags=re.I)
    s = re.sub(r"\s", "", s)
    if not s or not re.fullmatch(r"[\d.,]+", s):
        return None
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", s):
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", s):
        s = s.replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        n = float(s)
    except ValueError:
        return None
    return n if math.isfinite(n) else None


def parse_date(v):
    """Format ambigu dibaca day-first (konvensi Indonesia). Mengembalikan ISO 8601 atau None."""
    s = str(v).strip()
    m = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{2}|\d{4})", s)
        if not m:
            return None
        d, mo, y = int(m[1]), int(m[2]), int(m[3])
        if len(m[3]) == 2:
            y += 2000
        if mo > 12 >= d:
            d, mo = mo, d
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def normalize_phone(v):
    v = str(v)
    if re.search(r"[a-zA-Z]", v):
        return None
    d = re.sub(r"\D", "", v)
    d = d[2:] if d.startswith("62") else d[1:] if d.startswith("0") else d
    return "+62" + d if re.fullmatch(r"8\d{8,11}", d) else None


def check(v, sem):
    """Return (valid, canonical) atau None bila kolom tidak punya aturan."""
    v = str(v)
    if sem == "email":
        low = v.strip().lower()
        return bool(EMAIL.match(low)), v == low
    if sem == "phone":
        n = normalize_phone(v)
        return n is not None, v == n
    if sem == "date":
        n = parse_date(v)
        return n is not None, v == n
    if sem == "currency":
        n = parse_currency(v)
        return n is not None, n is not None and v == format_num(n)
    if sem == "age":
        try:
            n = float(v)
        except ValueError:
            return False, False
        ok = 0 <= n <= 120
        return ok, ok and v.isdigit()
    if sem == "name":
        return True, v == title_case(v)
    return None


def norm_val(v, sem) -> str:
    if is_missing(v):
        return ""
    v = str(v)
    if sem == "email":
        return v.strip().lower()
    if sem == "phone":
        return normalize_phone(v) or v.strip()
    if sem == "date":
        return parse_date(v) or v.strip()
    if sem == "currency":
        n = parse_currency(v)
        return v.strip() if n is None else format_num(n)
    return " ".join(v.split()).lower()
