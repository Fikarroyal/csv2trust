"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import Papa from "papaparse";
import * as XLSX from "xlsx";
import { UploadCloud, AlertTriangle, AlertCircle, Info, ArrowUp, ArrowDown, Copy, Trash2, Download, Play } from "lucide-react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { analyze, applySteps, pipelineJson, toPython, Row, Step } from "@/lib/engine";

type Tab = "profil" | "masalah" | "studio" | "banding" | "pipeline" | "ekspor";
const TABS: [Tab, string][] = [["profil", "Profiling"], ["masalah", "Masalah"], ["studio", "Cleaning Studio"], ["banding", "Sebelum / Sesudah"], ["pipeline", "Pipeline"], ["ekspor", "Ekspor"]];
const MAX_MB = 150;

function save(name: string, content: BlobPart, type = "text/plain") {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([content], { type }));
  a.download = name;
  a.click();
}
const SEV = {
  critical: { c: "bg-red-100 text-red-700", Icon: AlertCircle },
  warning: { c: "bg-amber-100 text-amber-700", Icon: AlertTriangle },
  info: { c: "bg-sky-100 text-sky-700", Icon: Info },
};
const Card = ({ children, className = "" }: { children: React.ReactNode; className?: string }) => (
  <div className={`rounded-xl border border-slate-200 bg-white p-4 shadow-sm ${className}`}>{children}</div>
);

function Table({ cols, rows, cell, rowCls }: { cols: string[]; rows: Row[]; cell?: (i: number, c: string) => string; rowCls?: (i: number) => string }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="min-w-full text-left text-xs">
        <thead className="bg-slate-100 text-slate-600"><tr><th className="px-2 py-1.5">#</th>{cols.map((c) => <th key={c} className="whitespace-nowrap px-2 py-1.5">{c}</th>)}</tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className={`border-t border-slate-100 ${rowCls?.(i) ?? ""}`}>
              <td className="px-2 py-1 text-slate-400">{i + 1}</td>
              {cols.map((c) => <td key={c} className={`whitespace-nowrap px-2 py-1 ${cell?.(i, c) ?? ""}`}>{r[c] === "" ? <span className="text-slate-300">kosong</span> : r[c]}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Studio() {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [name, setName] = useState("");
  const [steps, setSteps] = useState<Step[]>([]);
  const [applied, setApplied] = useState<Step[] | null>(null);
  const [tab, setTab] = useState<Tab>("profil");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const a = useMemo(() => (rows ? analyze(rows) : null), [rows]);
  const live = useMemo(() => (rows && a ? applySteps(rows, steps, a.semantics) : null), [rows, steps, a]);
  const fin = useMemo(() => (rows && a && applied ? applySteps(rows, applied, a.semantics) : null), [rows, applied, a]);
  const after = useMemo(() => (fin && fin.rows.length ? analyze(fin.rows) : null), [fin]);
  const diff = useMemo(() => {
    if (!fin || !rows) return null;
    let changed = 0;
    const hl = new Set<string>();
    fin.rows.forEach((r, i) => { for (const k in r) if (r[k] !== rows[fin.src[i]][k]) { changed++; hl.add(i + ":" + k); } });
    const kept = new Set(fin.src);
    return { changed, hl, removed: new Set(rows.map((_, i) => i).filter((i) => !kept.has(i))) };
  }, [fin, rows]);

  function load(r: Row[], n: string) {
    if (!r.length || !Object.keys(r[0]).length) return setErr("Dataset kosong atau tidak punya header. Pastikan baris pertama berisi nama kolom.");
    setRows(r); setName(n); setSteps(analyze(r).steps); setApplied(null); setErr(""); setTab("profil");
  }
  async function onFile(f: File) {
    const ext = f.name.split(".").pop()?.toLowerCase();
    if (!["csv", "xlsx", "xls"].includes(ext || "")) return setErr("Format tidak didukung. Gunakan .csv, .xlsx, atau .xls.");
    if (f.size === 0) return setErr("File kosong.");
    if (f.size > MAX_MB * 1024 * 1024) return setErr(`File terlalu besar (maks ${MAX_MB} MB).`);
    setBusy(true); setErr("");
    try {
      if (ext === "csv") {
        // Parse langsung dari File (dibaca per chunk) agar file besar tidak membekukan browser
        const res = await new Promise<Papa.ParseResult<Row>>((resolve, reject) =>
          Papa.parse<Row>(f, { header: true, skipEmptyLines: true, complete: resolve, error: reject }));
        const h = res.meta.fields ?? [];
        load(res.data.map((r) => { const o: Row = {}; for (const k of h) o[k] = String(r[k] ?? ""); return o; }), f.name);
      } else {
        const wb = XLSX.read(await f.arrayBuffer());
        const data = XLSX.utils.sheet_to_json<Record<string, unknown>>(wb.Sheets[wb.SheetNames[0]], { raw: false, defval: "" });
        load(data.map((r) => Object.fromEntries(Object.entries(r).map(([k, v]) => [k, String(v)]))), f.name);
      }
    } catch {
      setErr("Dataset gagal diproses. File mungkin rusak, encoding tidak dikenali, atau terlalu besar untuk memori browser. Coba simpan ulang sebagai UTF-8 CSV.");
    } finally { setBusy(false); }
  }
  async function loadSample() {
    const t = await (await fetch("/samples/messy_customers.csv")).text();
    load(Papa.parse<Row>(t, { header: true, skipEmptyLines: true }).data, "messy_customers.csv");
  }
  useEffect(() => { if (new URLSearchParams(location.search).get("sample")) loadSample(); }, []);

  const upd = (id: string, p: Partial<Step>) => setSteps((s) => s.map((x) => (x.id === id ? { ...x, ...p } : x)));
  const move = (i: number, d: number) => setSteps((s) => { const n = [...s], j = i + d; if (j < 0 || j >= n.length) return s; [n[i], n[j]] = [n[j], n[i]]; return n; });
  const apply = () => { setApplied(steps.map((s) => ({ ...s }))); setTab("banding"); };
  const ApplyBtn = () => <button onClick={apply} className="inline-flex items-center gap-2 rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white"><Play size={14} />Terapkan Transformasi</button>;

  // ---------- Halaman upload ----------
  if (!rows || !a || !live) {
    return (
      <main className="mx-auto max-w-2xl px-5 py-16">
        <Link href="/" className="text-sm font-semibold text-emerald-700">CSV2Trust</Link>
        <h1 className="mt-2 text-2xl font-bold">Upload Dataset</h1>
        <label onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) onFile(f); }}
          className="mt-6 flex cursor-pointer flex-col items-center rounded-xl border-2 border-dashed border-slate-300 bg-white p-12 text-center">
          <UploadCloud className="text-slate-400" size={32} />
          <p className="mt-3 font-medium">Tarik file ke sini atau klik untuk memilih</p>
          <p className="text-sm text-slate-500">.csv, .xlsx, .xls (maks {MAX_MB} MB), diproses di browser, tidak diupload ke server</p>
          <input type="file" accept=".csv,.xlsx,.xls" className="hidden" onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])} />
        </label>
        {busy && <p className="mt-4 rounded-lg bg-slate-100 p-3 text-sm text-slate-700">Memproses dataset, mohon tunggu...</p>}
        {err && <p className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{err}</p>}
        <button onClick={loadSample} className="mt-4 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium">Pakai sample: messy_customers.csv</button>
      </main>
    );
  }

  const cols = Object.keys(rows[0]);
  const q = a.quality;
  const scoreBars: [string, number][] = [["Completeness", q.completeness], ["Validity", q.validity], ["Consistency", q.consistency], ["Uniqueness", q.uniqueness]];

  return (
    <main className="mx-auto max-w-6xl px-4 py-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><Link href="/" className="text-sm font-semibold text-emerald-700">CSV2Trust</Link><p className="text-lg font-semibold">{name}</p></div>
        <button onClick={() => setRows(null)} className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm">Ganti dataset</button>
      </div>
      <nav className="mt-4 flex gap-1 overflow-x-auto border-b border-slate-200">
        {TABS.map(([k, l]) => <button key={k} onClick={() => setTab(k)} className={`whitespace-nowrap px-3 py-2 text-sm ${tab === k ? "border-b-2 border-emerald-700 font-semibold text-emerald-700" : "text-slate-500"}`}>{l}</button>)}
      </nav>

      <div className="mt-5 space-y-4">
        {tab === "profil" && (<>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            {([["Baris", a.stats.rows], ["Kolom", a.stats.cols], ["Sel kosong", a.stats.missingCells], ["Baris duplikat", a.stats.dupRows], ["Skor kualitas", q.overall]] as [string, number][]).map(([l, v]) => (
              <Card key={l}><p className="text-xs text-slate-500">{l}</p><p className="text-2xl font-bold">{v}</p></Card>
            ))}
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <Card><p className="mb-3 font-medium">Komponen skor</p>
              {scoreBars.map(([l, v]) => (<div key={l} className="mb-2"><div className="flex justify-between text-sm"><span>{l}</span><span>{v}</span></div><div className="h-2 rounded bg-slate-100"><div className="h-2 rounded bg-emerald-600" style={{ width: v + "%" }} /></div></div>))}
            </Card>
            <Card><p className="mb-3 font-medium">Persentase missing per kolom</p>
              <div className="h-48"><ResponsiveContainer><BarChart data={a.profiles.map((p) => ({ name: p.name, missing: p.nullPct }))}><XAxis dataKey="name" tick={{ fontSize: 10 }} /><YAxis unit="%" tick={{ fontSize: 10 }} /><Tooltip /><Bar dataKey="missing" fill="#0f766e" /></BarChart></ResponsiveContainer></div>
            </Card>
          </div>
          <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
            <table className="min-w-full text-left text-xs">
              <thead className="bg-slate-100 text-slate-600"><tr>{["Kolom", "Tipe semantik", "Null %", "Unik", "Duplikat", "Min", "Max", "Mean", "Median", "Std"].map((h) => <th key={h} className="px-2 py-1.5">{h}</th>)}</tr></thead>
              <tbody>{a.profiles.map((p) => (
                <tr key={p.name} className="border-t border-slate-100"><td className="px-2 py-1 font-medium">{p.name}</td><td className="px-2 py-1">{p.semantic}</td><td className="px-2 py-1">{p.nullPct}</td><td className="px-2 py-1">{p.unique}</td><td className="px-2 py-1">{p.dupes}</td>
                  {[p.min, p.max, p.mean, p.median, p.std].map((v, i) => <td key={i} className="px-2 py-1">{v === undefined ? "-" : +v.toFixed(2)}</td>)}</tr>
              ))}</tbody>
            </table>
          </div>
          <Table cols={cols} rows={rows.slice(0, 10)} />
        </>)}

        {tab === "masalah" && (a.issues.length === 0 ? <Card>Tidak ada masalah terdeteksi.</Card> : a.issues.map((i) => {
          const S = SEV[i.severity];
          const st = steps.find((s) => i.fixKey === s.operation + ":" + s.column);
          return (
            <Card key={i.id}>
              <div className="flex flex-wrap items-center gap-2"><span className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-semibold uppercase ${S.c}`}><S.Icon size={12} />{i.severity}</span><p className="font-medium">{i.type}</p><span className="text-xs text-slate-500">kolom: {i.column}</span></div>
              <p className="mt-2 text-sm text-slate-700">{i.message}</p>
              <p className="mt-1 text-sm text-slate-500">Saran: {i.fix} · confidence {(i.confidence * 100).toFixed(0)}% · baris: {i.rows.slice(0, 8).join(", ")}{i.rows.length > 8 ? "..." : ""}</p>
              {st && <button onClick={() => { upd(st.id, { enabled: true }); setTab("studio"); }} className="mt-3 rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-medium text-white">Apply Fix</button>}
            </Card>
          );
        }))}

        {tab === "studio" && (
          <div className="grid gap-4 lg:grid-cols-[200px_1fr_320px]">
            <Card><p className="mb-2 font-medium">Kolom</p>{a.profiles.map((p) => <div key={p.name} className="flex justify-between border-t border-slate-100 py-1.5 text-sm"><span>{p.name}</span><span className="rounded bg-slate-100 px-1.5 text-xs">{p.semantic}</span></div>)}</Card>
            <div className="min-w-0"><p className="mb-2 text-sm text-slate-500">Preview langsung hasil transformasi terpilih ({live.rows.length} baris)</p><Table cols={cols} rows={live.rows.slice(0, 15)} cell={(i, c) => (live.rows[i][c] !== rows[live.src[i]][c] ? "bg-amber-50" : "")} /></div>
            <Card><p className="mb-2 font-medium">Rekomendasi</p>
              {steps.length === 0 && <p className="text-sm text-slate-500">Tidak ada rekomendasi otomatis.</p>}
              {steps.map((s) => (
                <label key={s.id} className="flex cursor-pointer gap-2 border-t border-slate-100 py-2 text-sm">
                  <input type="checkbox" checked={s.enabled} onChange={(e) => upd(s.id, { enabled: e.target.checked })} />
                  <span><span className="font-medium">{s.label}</span><br /><span className="text-xs text-slate-500">kolom {s.column === "*" ? "semua" : s.column} · {s.rows || "semua"} baris · confidence {(s.confidence * 100).toFixed(0)}%</span></span>
                </label>
              ))}
              <div className="mt-3"><ApplyBtn /></div>
            </Card>
          </div>
        )}

        {tab === "banding" && (!fin || !diff || !after ? <Card>Belum ada transformasi yang diterapkan. Buka Cleaning Studio lalu klik Terapkan.</Card> : (<>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            {([["Skor sebelum", q.overall], ["Skor sesudah", after.quality.overall], ["Baris dihapus", diff.removed.size], ["Sel berubah", diff.changed], ["Masalah tersisa", after.issues.length]] as [string, number][]).map(([l, v]) => <Card key={l}><p className="text-xs text-slate-500">{l}</p><p className="text-2xl font-bold">{v}</p></Card>)}
          </div>
          <Card><p className="mb-2 font-medium">Hasil validasi</p>
            {Object.keys(after.semantics).map((c) => {
              const is = after.issues.filter((i) => i.column === c);
              const st = is.some((i) => i.severity === "critical") ? "FAIL" : is.some((i) => i.severity === "warning") ? "WARNING" : "PASS";
              return <div key={c} className="flex items-center gap-3 border-t border-slate-100 py-1.5 text-sm"><span className={`w-20 rounded px-2 py-0.5 text-center text-xs font-semibold ${st === "PASS" ? "bg-emerald-100 text-emerald-700" : st === "FAIL" ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-700"}`}>{st}</span><span>{c}</span><span className="text-xs text-slate-500">{is.map((i) => i.type).join(", ")}</span></div>;
            })}
          </Card>
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="min-w-0"><p className="mb-2 text-sm font-medium">BEFORE</p><Table cols={cols} rows={rows.slice(0, 30)} rowCls={(i) => (diff.removed.has(i) ? "bg-red-50 line-through" : "")} /></div>
            <div className="min-w-0"><p className="mb-2 text-sm font-medium">AFTER</p><Table cols={cols} rows={fin.rows.slice(0, 30)} cell={(i, c) => (diff.hl.has(i + ":" + c) ? "bg-amber-100" : "")} /></div>
          </div>
          <p className="text-xs text-slate-500">Merah = baris dihapus. Kuning = sel dimodifikasi/dinormalisasi.</p>
        </>))}

        {tab === "pipeline" && (<>
          <div className="flex items-center justify-between"><p className="text-sm text-slate-500">Urutan langkah menentukan hasil. Load Dataset → langkah di bawah → Export.</p><ApplyBtn /></div>
          {steps.length === 0 && <Card>Pipeline kosong.</Card>}
          {steps.map((s, i) => (
            <Card key={s.id} className={`flex flex-wrap items-center gap-3 ${s.enabled ? "" : "opacity-50"}`}>
              <span className="flex h-7 w-7 items-center justify-center rounded-full bg-slate-900 text-xs text-white">{i + 1}</span>
              <div className="min-w-0 flex-1"><p className="font-medium">{s.label}</p><p className="text-xs text-slate-500">{s.operation} · kolom {s.column === "*" ? "semua" : s.column} · {s.rows || "semua"} baris</p></div>
              <input type="checkbox" checked={s.enabled} onChange={(e) => upd(s.id, { enabled: e.target.checked })} title="Aktif/nonaktif" />
              <button onClick={() => move(i, -1)} title="Naik"><ArrowUp size={16} /></button>
              <button onClick={() => move(i, 1)} title="Turun"><ArrowDown size={16} /></button>
              <button onClick={() => setSteps((x) => { const n = [...x]; n.splice(i + 1, 0, { ...s, id: "s" + Date.now() }); return n; })} title="Duplikat"><Copy size={16} /></button>
              <button onClick={() => confirm("Hapus langkah ini?") && setSteps((x) => x.filter((y) => y.id !== s.id))} title="Hapus"><Trash2 size={16} className="text-red-600" /></button>
            </Card>
          ))}
        </>)}

        {tab === "ekspor" && (!fin || !after ? <Card>Terapkan transformasi dulu agar hasil bisa diekspor.</Card> : (() => {
          const base = name.replace(/\.[^.]+$/, "");
          const ws = () => XLSX.utils.json_to_sheet(fin.rows);
          const items: [string, () => void][] = [
            ["Clean CSV", () => save(base + "_clean.csv", Papa.unparse(fin.rows), "text/csv")],
            ["Excel (.xlsx)", () => { const wb = XLSX.utils.book_new(); XLSX.utils.book_append_sheet(wb, ws(), "clean"); XLSX.writeFile(wb, base + "_clean.xlsx"); }],
            ["Clean JSON", () => save(base + "_clean.json", JSON.stringify(fin.rows, null, 2), "application/json")],
            ["Pipeline JSON", () => save(base + "_pipeline.json", JSON.stringify(pipelineJson(applied!, name), null, 2), "application/json")],
            ["Pipeline Python", () => save("pipeline.py", toPython(applied!, name))],
            ["Schema JSON", () => save(base + "_schema.json", JSON.stringify(after.profiles, null, 2), "application/json")],
            ["Data Quality Report", () => save(base + "_report.json", JSON.stringify({ dataset: name, before: q, after: after.quality, issues_before: a.issues.length, issues_after: after.issues, steps: applied!.filter((s) => s.enabled) }, null, 2), "application/json")],
          ];
          return <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{items.map(([l, f]) => <button key={l} onClick={f} className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-4 text-left text-sm font-medium shadow-sm">{l}<Download size={16} /></button>)}<p className="text-xs text-slate-500 sm:col-span-3">Parquet tersedia setelah backend FastAPI (PyArrow) ditambahkan.</p></div>;
        })())}
      </div>
    </main>
  );
}
