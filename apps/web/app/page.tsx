import Link from "next/link";
import { UploadCloud, ScanSearch, Wand2, ShieldCheck, Download, ArrowRight } from "lucide-react";

const steps = [
  { icon: UploadCloud, t: "Upload", d: "CSV atau XLSX langsung dibaca di browser." },
  { icon: ScanSearch, t: "Profile", d: "Tipe kolom, missing, duplikat, outlier." },
  { icon: Wand2, t: "Clean", d: "Pilih transformasi, lihat preview." },
  { icon: ShieldCheck, t: "Validate", d: "Skor kualitas sebelum dan sesudah." },
  { icon: Download, t: "Export", d: "Dataset bersih, pipeline JSON/Python, laporan." },
];

export default function Landing() {
  return (
    <main className="mx-auto max-w-5xl px-5 py-16">
      <p className="text-sm font-semibold tracking-wide text-emerald-700">CSV2Trust</p>
      <h1 className="mt-3 max-w-2xl text-4xl font-bold leading-tight sm:text-5xl">From Messy Spreadsheet to Trusted Data Pipeline.</h1>
      <p className="mt-4 max-w-2xl text-slate-600">Upload your messy spreadsheet, discover hidden data quality issues, clean it intelligently, and generate a reproducible data pipeline.</p>
      <div className="mt-8 flex flex-wrap gap-3">
        <Link href="/studio" className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-5 py-2.5 text-sm font-medium text-white">Start Cleaning Data <ArrowRight size={16} /></Link>
        <Link href="/studio?sample=1" className="rounded-lg border border-slate-300 bg-white px-5 py-2.5 text-sm font-medium">View Sample Dataset</Link>
      </div>
      <h2 className="mt-16 text-lg font-semibold">How it works</h2>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {steps.map((s, i) => (
          <div key={s.t} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex items-center justify-between"><s.icon size={20} className="text-emerald-700" /><span className="text-xs text-slate-400">0{i + 1}</span></div>
            <p className="mt-3 font-medium">{s.t}</p>
            <p className="mt-1 text-sm text-slate-500">{s.d}</p>
          </div>
        ))}
      </div>
    </main>
  );
}
