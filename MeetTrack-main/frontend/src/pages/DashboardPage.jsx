/**
 * DashboardPage — AI Meeting Intelligence
 *
 * Layout (lg+):
 *   ┌──────────────────────┬──────────────────────────────────┐
 *   │  Input panel  5/12   │  Output panel  7/12              │
 *   │  ─ drop zone         │  ─ empty state / results         │
 *   │  ─ OR divider        │                                  │
 *   │  ─ glow textarea     │                                  │
 *   │  ─ CTA button        │                                  │
 *   │  ─ stat pills        │                                  │
 *   │  ─ pipeline tracker  │                                  │
 *   └──────────────────────┴──────────────────────────────────┘
 */
import { useState, useRef } from "react";
import { AnimatePresence, motion as M } from "framer-motion";
import { FileAudio, Mic2, UploadCloud, X, Zap } from "lucide-react";
import { easeSoft, buttonHoverProps } from "../lib/motionPresets";
import { UploadProcessor } from "../components/UploadProcessor";
import MeetingOutput from "../components/MeetingOutput";

const API = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
const token = () => localStorage.getItem("access_token");
const auth  = (extra = {}) => ({ Authorization: `Bearer ${token()}`, ...extra });

/* ═══════════════════════════════════════════════════════════
   DROP ZONE
═══════════════════════════════════════════════════════════ */
function DropZone({ file, onFile, onClear }) {
  const ref  = useRef(null);
  const [drag, setDrag] = useState(false);

  return (
    <div
      onDragOver={e => { e.preventDefault(); setDrag(true); }}
      onDragLeave={() => setDrag(false)}
      onDrop={e => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files?.[0]; if (f) onFile(f); }}
      onClick={() => !file && ref.current?.click()}
      className="relative flex cursor-pointer flex-col items-center justify-center
                 gap-3 rounded-2xl px-6 py-7 text-center transition-all duration-200"
      style={{
        border: `2px dashed ${drag ? "rgba(99,102,241,0.55)" : file ? "rgba(52,211,153,0.3)" : "rgba(255,255,255,0.07)"}`,
        background: drag ? "rgba(99,102,241,0.05)" : file ? "rgba(52,211,153,0.03)" : "rgba(255,255,255,0.015)",
      }}
    >
      <input ref={ref} type="file" accept=".mp3,.wav,.m4a,audio/*" className="hidden"
        onChange={e => { const f = e.target.files?.[0]; if (f) onFile(f); }} />

      {file ? (
        <>
          <div className="flex h-10 w-10 items-center justify-center rounded-xl"
            style={{ background: "rgba(52,211,153,0.12)" }}>
            <FileAudio className="h-5 w-5 text-emerald-400" />
          </div>
          <div>
            <p className="text-sm font-semibold text-emerald-300">{file.name}</p>
            <p className="text-[11px] text-slate-600 mt-0.5">
              {(file.size / 1024 / 1024).toFixed(2)} MB · ready to process
            </p>
          </div>
          <button onClick={e => { e.stopPropagation(); onClear(); }}
            className="absolute right-3 top-3 rounded-full p-1.5 text-slate-600
                       hover:bg-slate-800 hover:text-slate-300 transition-colors">
            <X className="h-3.5 w-3.5" />
          </button>
        </>
      ) : (
        <>
          <div className="flex h-10 w-10 items-center justify-center rounded-xl"
            style={{ background: "rgba(255,255,255,0.04)" }}>
            <UploadCloud className="h-5 w-5 text-slate-600" />
          </div>
          <div>
            <p className="text-sm font-semibold text-slate-400">Drop your recording here</p>
            <p className="text-[11px] text-slate-600 mt-0.5">.mp3 · .wav · .m4a — or click to browse</p>
          </div>
        </>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   OR DIVIDER
═══════════════════════════════════════════════════════════ */
function OrDivider() {
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-px" style={{ background: "rgba(255,255,255,0.05)" }} />
      <span className="text-[10px] font-semibold uppercase tracking-widest text-slate-700">
        or paste transcript
      </span>
      <div className="flex-1 h-px" style={{ background: "rgba(255,255,255,0.05)" }} />
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   GLOW TEXTAREA
═══════════════════════════════════════════════════════════ */
function TranscriptInput({ value, onChange }) {
  const [focused, setFocused] = useState(false);
  return (
    <div className={`glow-ring rounded-2xl ${focused ? "focused" : ""}`}>
      <textarea
        value={value}
        onChange={e => onChange(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        rows={9}
        placeholder={"Paste your meeting transcript here…\n\ne.g.\nAlice: We need to ship the auth feature by Friday.\nBob: I'll handle the backend — can someone write tests?\nAlice: I'll take tests. Bob, can you also update the docs?"}
        className="relative z-10 w-full resize-none rounded-2xl px-5 py-4 text-sm
                   leading-relaxed text-slate-200 placeholder-slate-700 outline-none"
        style={{ background: "rgba(7,9,15,0.75)" }}
      />
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   CTA BUTTON
═══════════════════════════════════════════════════════════ */
function AnalyseButton({ onClick, loading, disabled }) {
  return (
    <M.button
      onClick={onClick}
      disabled={disabled}
      {...(disabled ? {} : buttonHoverProps)}
      className="relative w-full overflow-hidden rounded-xl py-3.5 text-sm
                 font-bold text-white transition-all duration-200"
      style={disabled
        ? { background: "rgba(255,255,255,0.04)", color: "#334155", cursor: "not-allowed" }
        : { background: "linear-gradient(135deg, #4338ca 0%, #0e7490 100%)",
            boxShadow: "0 4px 28px rgba(67,56,202,0.38), 0 1px 0 rgba(255,255,255,0.08) inset" }}
    >
      {/* shimmer sweep */}
      {!disabled && (
        <span className="pointer-events-none absolute inset-0 -translate-x-full
                         bg-gradient-to-r from-transparent via-white/8 to-transparent
                         transition-transform duration-700 hover:translate-x-full" />
      )}
      <span className="relative flex items-center justify-center gap-2">
        {loading ? (
          <>
            <M.span animate={{ rotate: 360 }} transition={{ duration: 0.9, repeat: Infinity, ease: "linear" }}
              className="inline-block h-4 w-4 rounded-full border-2 border-white/25 border-t-white" />
            Analysing…
          </>
        ) : (
          <>
            <Zap className="h-4 w-4" />
            Analyse Meeting
          </>
        )}
      </span>
    </M.button>
  );
}

/* ═══════════════════════════════════════════════════════════
   STAT PILLS
═══════════════════════════════════════════════════════════ */
function StatPills({ structured }) {
  if (!structured) return null;
  const stats = [
    { label: "Decisions",    val: structured.decisions?.length    ?? 0, color: "#22d3ee" },
    { label: "Action Items", val: structured.action_items?.length ?? 0, color: "#34d399" },
  ];
  return (
    <M.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: easeSoft }}
      className="flex gap-2">
      {stats.map(s => (
        <div key={s.label} className="flex-1 rounded-xl px-3 py-3 text-center"
          style={{ background: s.color + "0d", border: `1px solid ${s.color}1e` }}>
          <p className="text-xl font-black" style={{ color: s.color }}>{s.val}</p>
          <p className="text-[10px] font-semibold text-slate-600 mt-0.5">{s.label}</p>
        </div>
      ))}
    </M.div>
  );
}

/* ═══════════════════════════════════════════════════════════
   PAGE HEADER
═══════════════════════════════════════════════════════════ */
function Header() {
  return (
    <div className="mb-8 flex items-center gap-4">
      {/* icon */}
      <div className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-2xl"
        style={{
          background: "linear-gradient(145deg, rgba(67,56,202,0.35), rgba(14,116,144,0.2))",
          border: "1px solid rgba(99,102,241,0.28)",
          boxShadow: "0 4px 20px rgba(67,56,202,0.22)",
        }}>
        <Mic2 className="h-5 w-5 text-indigo-400" />
      </div>

      <div>
        <h1 className="text-[22px] font-black leading-tight tracking-tight text-slate-100">
          Meeting Intelligence
        </h1>
        <p className="mt-0.5 text-[12px] text-slate-600">
          Upload a recording or paste a transcript — structured insights in seconds
        </p>
      </div>

      {/* live badge */}
      <div className="ml-auto flex items-center gap-2 rounded-full px-3 py-1.5"
        style={{ border: "1px solid rgba(52,211,153,0.18)", background: "rgba(52,211,153,0.05)" }}>
        <div className="pulse-dot" />
        <span className="text-[10px] font-bold text-emerald-500">Live</span>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   MAIN PAGE
═══════════════════════════════════════════════════════════ */
export default function DashboardPage() {
  const [file,       setFile]       = useState(null);
  const [transcript, setTranscript] = useState("");
  const [step,       setStep]       = useState(-1);
  const [loading,    setLoading]    = useState(false);
  const [structured, setStructured] = useState(null);
  const [rawTx,      setRawTx]      = useState("");

  async function handleProcess() {
    if (!file && !transcript.trim()) return;
    setLoading(true); setStep(0); setStructured(null); setRawTx("");

    try {
      if (file) {
        // ── audio path ──
        const fd = new FormData();
        fd.append("file", file);
        const upRes = await fetch(`${API}/audio`, { method: "POST", headers: auth(), body: fd });
        if (!upRes.ok) throw new Error((await upRes.json()).detail || "Upload failed");
        const upData = await upRes.json();

        setStep(1);

        const prRes = await fetch(`${API}/process`, {
          method: "POST",
          headers: auth({ "Content-Type": "application/json" }),
          body: JSON.stringify({ file_path: upData.file_path, file_name: upData.file_name }),
        });
        if (!prRes.ok) throw new Error((await prRes.json()).detail || "Processing failed");
        const prData = await prRes.json();

        setStep(2);
        setRawTx(prData.transcript || "");

        setStructured(prData.structured_output ?? {
          summary: prData.summary || "",
          decisions: [],
          action_items: (prData.action_items || []).map(i => ({
            task:             i.task || i.description || i.title || "",
            assignee:         i.assignee || i.assigned_to || "Unassigned",
            deadline:         i.deadline || null,
            confidence_score: i.confidence_score ?? 0.8,
          })),
        });

      } else {
        // ── transcript-only path ──
        setStep(1);
        const res = await fetch(`${API}/extract-tasks`, {
          method: "POST",
          headers: auth({ "Content-Type": "application/json" }),
          body: JSON.stringify({ meeting_text: transcript.trim() }),
        });
        setStep(2);
        setRawTx(transcript.trim());

        if (res.ok) {
          const data = await res.json();
          setStructured({
            summary: "Transcript analysed — action items extracted below.",
            decisions: [],
            action_items: (data.tasks || []).map(t => ({
              task:             t.task_description || t.task || "",
              assignee:         t.person_name || t.assignee || "Unassigned",
              deadline:         t.deadline || null,
              confidence_score: t.confidence_score ?? 0.8,
            })),
          });
        } else {
          setStructured({ summary: "Could not process transcript.", decisions: [], action_items: [] });
        }
      }

      await new Promise(r => setTimeout(r, 500));
      setStep(3);

    } catch (err) {
      console.error(err);
      alert("Error: " + err.message);
      setStep(-1);
    } finally {
      setLoading(false);
    }
  }

  const canSubmit  = (file || transcript.trim()) && !loading;
  const showOutput = step === 3;

  return (
    <M.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
      transition={{ duration: 0.45, ease: easeSoft }}>

      <Header />

      <div className="flex flex-col gap-6 lg:flex-row lg:items-start">

        {/* ── LEFT: input panel ── */}
        <div className="w-full lg:w-5/12 space-y-3">

          {/* main input card */}
          <div className="rounded-3xl p-5 space-y-4"
            style={{
              background: "rgba(12,16,28,0.7)",
              border: "1px solid rgba(255,255,255,0.055)",
              boxShadow: "0 8px 32px rgba(0,0,0,0.35)",
            }}>

            {/* section label */}
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-black uppercase tracking-[0.14em] text-slate-700">
                Input
              </span>
              <div className="flex-1 h-px" style={{ background: "rgba(255,255,255,0.04)" }} />
            </div>

            <DropZone file={file} onFile={setFile} onClear={() => setFile(null)} />
            <OrDivider />
            <TranscriptInput value={transcript} onChange={setTranscript} />
            <AnalyseButton onClick={handleProcess} loading={loading} disabled={!canSubmit} />
          </div>

          {/* stat pills */}
          <AnimatePresence>
            {showOutput && structured && (
              <M.div key="pills" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }} transition={{ duration: 0.28, ease: easeSoft }}>
                <StatPills structured={structured} />
              </M.div>
            )}
          </AnimatePresence>

          {/* pipeline tracker */}
          <AnimatePresence>
            {step >= 0 && (
              <M.div key="tracker"
                initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.28, ease: easeSoft }}>
                <UploadProcessor step={step} />
              </M.div>
            )}
          </AnimatePresence>
        </div>

        {/* ── RIGHT: output panel ── */}
        <div className="w-full lg:w-7/12">
          <MeetingOutput
            structured={structured}
            transcript={rawTx}
            show={showOutput}
            loading={loading && step >= 1}
          />
        </div>

      </div>
    </M.div>
  );
}
