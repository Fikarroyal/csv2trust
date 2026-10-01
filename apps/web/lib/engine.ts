// Engine CSV2Trust: deterministik, berjalan di browser. Nanti dipindah/diparalelkan ke backend FastAPI.
export type Row = Record<string, string>;
export type Semantic = "email" | "phone" | "date" | "currency" | "age" | "name" | "id" | "number" | "text";
export interface Step { id: string; operation: string; column: string; label: string; enabled: boolean; rows: number; confidence: number }
export interface Issue { id: string; column: string; type: string; severity: "critical" | "warning" | "info"; rows: number[]; message: string; fix: string; confidence: number; fixKey?: string }
export interface ColProfile { name: string; semantic: Semantic; nullPct: number; unique: number; dupes: number; numeric: boolean; min?: number; max?: number; mean?: number; median?: number; std?: number }

const MISSING = new Set(["", "-", "n/a", "na", "null", "none", "nan", "?"]);
export const isMissing = (v: string) => MISSING.has((v ?? "").trim().toLowerCase());
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
export const titleCase = (v: string) => v.trim().replace(/\s+/g, " ").toLowerCase().replace(/(^|\s)\S/g, (m) => m.toUpperCase());

export function parseCurrency(v: string): number | null {
  let s = v.replace(/rp\.?|idr/gi, "").replace(/\s/g, "");
  if (!s || !/^[\d.,]+$/.test(s)) return null;
  if (/^\d{1,3}(\.\d{3})+(,\d+)?$/.test(s)) s = s.replace(/\./g, "").replace(",", ".");
  else if (/^\d{1,3}(,\d{3})+(\.\d+)?$/.test(s)) s = s.replace(/,/g, "");
  else s = s.replace(",", ".");
  const n = Number(s);
  return isFinite(n) ? n : null;
}
function mk(y: number, mo: number, d: number) {
  const dt = new Date(Date.UTC(y, mo - 1, d));
  if (dt.getUTCFullYear() !== y || dt.getUTCMonth() !== mo - 1 || dt.getUTCDate() !== d) return null;
  return dt.toISOString().slice(0, 10);
}
// Asumsi day-first untuk format ambigu (konvensi Indonesia)
export function parseDate(v: string): string | null {
  const s = v.trim();
  let m = s.match(/^(\d{4})[-\/.](\d{1,2})[-\/.](\d{1,2})$/);
  if (m) return mk(+m[1], +m[2], +m[3]);
  m = s.match(/^(\d{1,2})[-\/.](\d{1,2})[-\/.](\d{2}|\d{4})$/);
  if (!m) return null;
  let d = +m[1], mo = +m[2];
  const y = m[3].length === 2 ? 2000 + +m[3] : +m[3];
  if (mo > 12 && d <= 12) [d, mo] = [mo, d];
  return mk(y, mo, d);
}
export function normalizePhone(v: string): string | null {
  if (/[a-z]/i.test(v)) return null;
  let d = v.replace(/\D/g, "");
  if (d.startsWith("62")) d = d.slice(2); else if (d.startsWith("0")) d = d.slice(1);
  return /^8\d{8,11}$/.test(d) ? "+62" + d : null;
}

function detect(name: string, vals: string[]): Semantic {
  if (/mail/i.test(name)) return "email";
  if (/phone|telp|telepon|whatsapp|(^|[_\s])(hp|wa)$/i.test(name)) return "phone";
  if (/date|tgl|tanggal|waktu|time/i.test(name)) return "date";
  if (/revenue|harga|price|amount|total|biaya|nominal|gaji|salary|cost/i.test(name)) return "currency";
  if (/^(age|umur|usia)$/i.test(name)) return "age";
  if (/(^|[_\s-])id$|kode/i.test(name)) return "id";
  if (/name|nama/i.test(name)) return "name";
  const nm = vals.filter((v) => !isMissing(v));
  if (nm.length && nm.filter((v) => EMAIL.test(v)).length / nm.length > 0.7) return "email";
  if (nm.length && nm.every((v) => v.trim() !== "" && !isNaN(Number(v)))) return "number";
  return "text";
}

// [valid, canonical] atau null jika kolom tidak punya aturan
function check(v: string, s: Semantic): [boolean, boolean] | null {
  switch (s) {
    case "email": return [EMAIL.test(v.trim().toLowerCase()), v === v.trim().toLowerCase()];
    case "phone": { const n = normalizePhone(v); return [!!n, v === n]; }
    case "date": { const n = parseDate(v); return [!!n, v === n]; }
    case "currency": { const n = parseCurrency(v); return [n !== null, n !== null && v === String(n)]; }
    case "age": { const n = Number(v); const ok = v.trim() !== "" && n >= 0 && n <= 120; return [ok, ok && /^\d+$/.test(v)]; }
    case "name": return [true, v === titleCase(v)];
    default: return null;
  }
}
function normVal(v: string, s: Semantic) {
  if (isMissing(v)) return "";
  switch (s) {
    case "email": return v.trim().toLowerCase();
    case "phone": return normalizePhone(v) ?? v.trim();
    case "date": return parseDate(v) ?? v.trim();
    case "currency": { const n = parseCurrency(v); return n === null ? v.trim() : String(n); }
    default: return v.trim().replace(/\s+/g, " ").toLowerCase();
  }
}
const rowKey = (r: Row, cols: string[], sem: Record<string, Semantic>) => cols.map((c) => normVal(r[c], sem[c])).join("|");

const q = (a: number[], p: number) => { const s = [...a].sort((x, y) => x - y); const i = (s.length - 1) * p, lo = Math.floor(i); return s[lo] + (s[Math.ceil(i)] - s[lo]) * (i - lo); };
const numVal = (v: string, s: Semantic) => (s === "currency" ? parseCurrency(v) : v.trim() === "" ? null : Number(v.replace(",", ".")));

const ORDER = ["standardize_missing", "normalize_email", "standardize_phone", "parse_date", "convert_currency", "normalize_name", "impute_median", "remove_duplicates"];
const LABEL: Record<string, string> = {
  standardize_missing: "Standarkan penanda missing", normalize_email: "Normalisasi email (lowercase)", standardize_phone: "Standarkan telepon (E.164 +62)",
  parse_date: "Parse tanggal ke ISO 8601", convert_currency: "Konversi currency ke numerik IDR", normalize_name: "Rapikan kapitalisasi nama",
  impute_median: "Isi missing dengan median", remove_duplicates: "Hapus baris duplikat",
};

export function analyze(rows: Row[]) {
  const cols = Object.keys(rows[0]);
  const sem: Record<string, Semantic> = {};
  cols.forEach((c) => (sem[c] = detect(c, rows.map((r) => r[c]))));
  const issues: Issue[] = [];
  const add = (i: Omit<Issue, "id">) => issues.push({ id: "i" + issues.length, ...i });
  const pick = (c: string, pred: (v: string) => boolean) => rows.flatMap((r, i) => (!isMissing(r[c]) && pred(r[c]) ? [i + 1] : []));
  const profiles: ColProfile[] = [];
  let missingCells = 0;

  cols.forEach((c) => {
    const s = sem[c], vals = rows.map((r) => r[c]);
    const miss = vals.flatMap((v, i) => (isMissing(v) ? [i + 1] : []));
    missingCells += miss.length;
    const nm = vals.filter((v) => !isMissing(v));
    const nums = !["phone", "date", "id", "email", "name"].includes(s) ? nm.map((v) => numVal(v, s)).filter((n) => n !== null && !isNaN(n)) as number[] : [];
    const numeric = nm.length > 0 && nums.length >= 0.6 * nm.length;
    const p: ColProfile = { name: c, semantic: s, nullPct: +((miss.length / rows.length) * 100).toFixed(1), unique: new Set(nm).size, dupes: nm.length - new Set(nm).size, numeric };
    if (numeric) {
      const mean = nums.reduce((a, b) => a + b, 0) / nums.length;
      Object.assign(p, { min: nums.reduce((m, x) => (x < m ? x : m), Infinity), max: nums.reduce((m, x) => (x > m ? x : m), -Infinity), mean, median: q(nums, 0.5), std: Math.sqrt(nums.reduce((a, b) => a + (b - mean) ** 2, 0) / nums.length) });
    }
    profiles.push(p);

    if (miss.length) add({ column: c, type: "Missing values", severity: p.nullPct > 10 ? "warning" : "info", rows: miss, message: `${p.nullPct}% nilai kosong di kolom ${c}.`, fix: ["age", "number"].includes(s) ? "Isi dengan median kolom." : "Tinjau manual atau lengkapi dari sumber data.", confidence: 0.9, fixKey: ["age", "number"].includes(s) && numeric ? `impute_median:${c}` : undefined });
    if (s === "email") {
      const bad = pick(c, (v) => !EMAIL.test(v.trim().toLowerCase()));
      if (bad.length) add({ column: c, type: "Invalid email format", severity: "critical", rows: bad, message: `${bad.length} email tidak valid (mis. "${rows[bad[0] - 1][c]}").`, fix: "Perbaiki manual; email tidak valid tidak ditebak otomatis.", confidence: 0.98 });
      const cs = pick(c, (v) => v !== v.trim().toLowerCase() && EMAIL.test(v.trim().toLowerCase()));
      if (cs.length) add({ column: c, type: "Inconsistent email casing", severity: "warning", rows: cs, message: "Email memakai huruf kapital/spasi.", fix: "Ubah ke lowercase.", confidence: 0.97, fixKey: `normalize_email:${c}` });
    }
    if (s === "phone") {
      const bad = pick(c, (v) => !normalizePhone(v));
      if (bad.length) add({ column: c, type: "Invalid phone number", severity: "warning", rows: bad, message: `${bad.length} nomor telepon tidak valid (mis. "${rows[bad[0] - 1][c]}").`, fix: "Periksa manual.", confidence: 0.9 });
      const f = pick(c, (v) => { const n = normalizePhone(v); return !!n && n !== v; });
      if (f.length) add({ column: c, type: "Inconsistent phone format", severity: "warning", rows: f, message: "Format nomor telepon berbeda-beda.", fix: "Standarkan ke format E.164 Indonesia (+62...).", confidence: 0.95, fixKey: `standardize_phone:${c}` });
    }
    if (s === "date") {
      const bad = pick(c, (v) => !parseDate(v));
      if (bad.length) add({ column: c, type: "Invalid date", severity: "critical", rows: bad, message: `${bad.length} tanggal tidak dapat dibaca (mis. "${rows[bad[0] - 1][c]}").`, fix: "Perbaiki manual.", confidence: 0.95 });
      const f = pick(c, (v) => { const n = parseDate(v); return !!n && n !== v; });
      if (f.length) add({ column: c, type: "Inconsistent date formats", severity: "warning", rows: f, message: "Format tanggal tidak konsisten. Format ambigu dibaca day-first.", fix: "Normalisasi ke ISO 8601 (YYYY-MM-DD).", confidence: 0.9, fixKey: `parse_date:${c}` });
    }
    if (s === "currency") {
      const bad = pick(c, (v) => parseCurrency(v) === null);
      if (bad.length) add({ column: c, type: "Invalid numeric value", severity: "critical", rows: bad, message: `${bad.length} nilai bukan angka/currency valid.`, fix: "Perbaiki manual.", confidence: 0.95 });
      const f = pick(c, (v) => { const n = parseCurrency(v); return n !== null && String(n) !== v; });
      if (f.length) add({ column: c, type: "Inconsistent currency formatting", severity: "warning", rows: f, message: `Contoh: ${[...new Set(f.slice(0, 3).map((i) => rows[i - 1][c]))].join(" | ")}`, fix: "Normalisasi semua nilai menjadi angka IDR.", confidence: 0.95, fixKey: `convert_currency:${c}` });
    }
    if (s === "age") {
      const bad = pick(c, (v) => !(Number(v) >= 0 && Number(v) <= 120));
      if (bad.length) add({ column: c, type: "Age out of range", severity: "critical", rows: bad, message: `${bad.length} umur di luar 0-120 (mis. ${rows[bad[0] - 1][c]}).`, fix: "Periksa manual.", confidence: 0.99 });
    }
    if (s === "name") {
      const f = pick(c, (v) => v !== titleCase(v));
      if (f.length) add({ column: c, type: "Inconsistent capitalization", severity: "info", rows: f, message: "Kapitalisasi/spasi nama tidak seragam.", fix: "Ubah ke Title Case.", confidence: 0.85, fixKey: `normalize_name:${c}` });
    }
    if (numeric && nums.length >= 4 && ["age", "number", "currency"].includes(s)) {
      const q1 = q(nums, 0.25), q3 = q(nums, 0.75), lo = q1 - 1.5 * (q3 - q1), hi = q3 + 1.5 * (q3 - q1);
      const out = pick(c, (v) => { const n = numVal(v, s); return n !== null && (n < lo || n > hi); });
      if (out.length) add({ column: c, type: "Potential outliers (IQR)", severity: "info", rows: out, message: `${out.length} nilai di luar rentang ${lo.toFixed(0)} - ${hi.toFixed(0)}.`, fix: "Tidak dihapus otomatis; tentukan sendiri.", confidence: 0.7 });
    }
  });

  if (rows.some((r) => cols.some((c) => { const v = r[c].trim().toLowerCase(); return v !== "" && MISSING.has(v); })))
    add({ column: "*", type: "Inconsistent missing markers", severity: "info", rows: [], message: 'Ada penanda kosong seperti "-", "N/A".', fix: "Ubah semua menjadi sel kosong.", confidence: 0.9, fixKey: "standardize_missing:*" });

  const seen = new Set<string>(), dup: number[] = [];
  rows.forEach((r, i) => { const k = rowKey(r, cols, sem); seen.has(k) ? dup.push(i + 1) : seen.add(k); });
  if (dup.length) add({ column: "*", type: "Duplicate rows", severity: "warning", rows: dup, message: `${dup.length} baris duplikat setelah normalisasi (kapitalisasi, format tanggal, currency).`, fix: "Hapus duplikat, simpan kemunculan pertama.", confidence: 0.92, fixKey: "remove_duplicates:*" });

  // Skor kualitas dari data aktual
  let valid = 0, vTot = 0, canon = 0, cTot = 0;
  cols.forEach((c) => rows.forEach((r) => {
    if (isMissing(r[c])) return;
    const k = check(r[c], sem[c]); if (!k) return;
    vTot++; if (k[0]) { valid++; cTot++; if (k[1]) canon++; }
  }));
  const pc = (a: number, b: number) => (b ? +((a / b) * 100).toFixed(1) : 100);
  const completeness = pc(rows.length * cols.length - missingCells, rows.length * cols.length);
  const validity = pc(valid, vTot), consistency = pc(canon, cTot), uniqueness = pc(seen.size, rows.length);
  const overall = +(completeness * 0.25 + validity * 0.3 + consistency * 0.25 + uniqueness * 0.2).toFixed(1);

  const steps: Step[] = [], keys = new Set<string>();
  issues.forEach((i) => {
    if (!i.fixKey || keys.has(i.fixKey)) return;
    keys.add(i.fixKey);
    const [operation, column] = i.fixKey.split(":");
    steps.push({ id: "s" + steps.length, operation, column, label: LABEL[operation], enabled: true, rows: i.rows.length, confidence: i.confidence });
  });
  steps.sort((a, b) => ORDER.indexOf(a.operation) - ORDER.indexOf(b.operation));

  return { semantics: sem, profiles, issues, steps, quality: { completeness, validity, consistency, uniqueness, overall }, stats: { rows: rows.length, cols: cols.length, missingCells, dupRows: dup.length } };
}

export function applySteps(rows: Row[], steps: Step[], sem: Record<string, Semantic>) {
  let cur = rows.map((r, i) => ({ src: i, d: { ...r } }));
  const cols = rows.length ? Object.keys(rows[0]) : [];
  for (const s of steps) {
    if (!s.enabled) continue;
    const c = s.column;
    const map = (f: (v: string) => string) => cur.forEach((x) => { if (c in x.d && !isMissing(x.d[c])) x.d[c] = f(x.d[c]); });
    switch (s.operation) {
      case "standardize_missing": cur.forEach((x) => { for (const k in x.d) if (isMissing(x.d[k])) x.d[k] = ""; }); break;
      case "normalize_email": map((v) => v.trim().toLowerCase()); break;
      case "standardize_phone": map((v) => normalizePhone(v) ?? v); break;
      case "parse_date": map((v) => parseDate(v) ?? v); break;
      case "convert_currency": map((v) => { const n = parseCurrency(v); return n === null ? v : String(n); }); break;
      case "normalize_name": map(titleCase); break;
      case "impute_median": {
        const nums = cur.filter((x) => !isMissing(x.d[c])).map((x) => Number(x.d[c])).filter((n) => !isNaN(n));
        if (!nums.length) break;
        const med = q(nums, 0.5), fill = sem[c] === "age" ? String(Math.round(med)) : String(+med.toFixed(2));
        cur.forEach((x) => { if (isMissing(x.d[c])) x.d[c] = fill; });
        break;
      }
      case "remove_duplicates": { const seen = new Set<string>(); cur = cur.filter((x) => { const k = rowKey(x.d, cols, sem); if (seen.has(k)) return false; seen.add(k); return true; }); break; }
    }
  }
  return { rows: cur.map((x) => x.d), src: cur.map((x) => x.src) };
}

export function pipelineJson(steps: Step[], name: string) {
  return { pipeline_name: name.replace(/\.[^.]+$/, "") + "_cleaning", version: "1.0.0", steps: steps.filter((s) => s.enabled).map((s) => ({ operation: s.operation, column: s.column })) };
}

export function toPython(steps: Step[], name: string) {
  const js = JSON.stringify(pipelineJson(steps, name).steps);
  return String.raw`"""Pipeline CSV2Trust (dibuat otomatis). Jalankan: python pipeline.py input.csv output.csv"""
import json, re, sys
import pandas as pd

STEPS = json.loads('''${js}''')
MISSING = {"", "-", "n/a", "na", "null", "none", "nan", "?"}
def miss(v): return str(v).strip().lower() in MISSING

def phone(v):
    if miss(v) or re.search(r"[a-zA-Z]", v): return v
    d = re.sub(r"\D", "", v)
    d = d[2:] if d.startswith("62") else d[1:] if d.startswith("0") else d
    return "+62" + d if re.fullmatch(r"8\d{8,11}", d) else v

def date(v):
    if miss(v): return v
    s = str(v).strip()
    m = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s)
    if m: y, mo, d = map(int, m.groups())
    else:
        m = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{2}|\d{4})", s)
        if not m: return v
        d, mo, y = int(m[1]), int(m[2]), int(m[3])
        if y < 100: y += 2000
        if mo > 12 >= d: d, mo = mo, d
    try: return pd.Timestamp(year=y, month=mo, day=d).strftime("%Y-%m-%d")
    except ValueError: return v

def currency(v):
    if miss(v): return v
    s = re.sub(r"(?i)rp\.?|idr|\s", "", str(v))
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", s): s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", s): s = s.replace(",", "")
    else: s = s.replace(",", ".")
    try: n = float(s)
    except ValueError: return v
    return str(int(n)) if n == int(n) else str(n)

def run(df):
    for st in STEPS:
        op, c = st["operation"], st["column"]
        if op == "standardize_missing": df = df.map(lambda v: "" if miss(v) else v)
        elif op == "normalize_email": df[c] = [v if miss(v) else v.strip().lower() for v in df[c]]
        elif op == "standardize_phone": df[c] = df[c].map(phone)
        elif op == "parse_date": df[c] = df[c].map(date)
        elif op == "convert_currency": df[c] = df[c].map(currency)
        elif op == "normalize_name": df[c] = [v if miss(v) else " ".join(v.split()).title() for v in df[c]]
        elif op == "impute_median":
            med = pd.to_numeric(df[c], errors="coerce").median()
            df[c] = [str(round(med)) if miss(v) else v for v in df[c]]
        elif op == "remove_duplicates":
            key = df.apply(lambda r: "|".join(" ".join(str(x).lower().split()) for x in r), axis=1)
            df = df[~key.duplicated()]
    return df

if __name__ == "__main__":
    data = pd.read_csv(sys.argv[1], dtype=str, keep_default_na=False)
    run(data).to_csv(sys.argv[2], index=False)
`;
}
