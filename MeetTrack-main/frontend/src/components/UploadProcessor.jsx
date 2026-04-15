/**
 * UploadProcessor — animated pipeline tracker.
 * Three steps: Upload → Transcribe → Extract Insights
 * Each step has its own colour, icon, and sub-label.
 */
import { AnimatePresence, motion as M } from "framer-motion";
import { easeSoft, easeSpring } from "../lib/motionPresets";

const STEPS = [
  { id: "upload",     label: "Uploading file",          sub: "Sending to secure server",              color: "#a78bfa", bg: "rgba(139,92,246,0.08)",  border: "rgba(139,92,246,0.22)" },
  { id: "transcribe", label: "Transcribing speech",     sub: "Whisper AI · audio → text",             color: "#22d3ee", bg: "rgba(6,182,212,0.08)",   border: "rgba(6,182,212,0.22)"  },
  { id: "analyze",    label: "Extracting insights",     sub: "Gemini AI · actions & decisions",       color: "#818cf8", bg: "rgba(99,102,241,0.08)",  border: "rgba(99,102,241,0.22)" },
];

/* ── SVG spinner ─────────────────────────────────────────── */
function Spinner({ color }) {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
      <circle cx="10" cy="10" r="8" stroke="rgba(255,255,255,0.07)" strokeWidth="2.5" />
      <M.circle cx="10" cy="10" r="8"
        stroke={color} strokeWidth="2.5" strokeLinecap="round"
        strokeDasharray="50" strokeDashoffset="38"
        animate={{ rotate: 360 }}
        transition={{ duration: 0.9, repeat: Infinity, ease: "linear" }}
        style={{ originX: "10px", originY: "10px" }}
      />
    </svg>
  );
}

/* ── animated checkmark ──────────────────────────────────── */
function Check() {
  return (
    <M.svg width="20" height="20" viewBox="0 0 20 20" fill="none"
      initial={{ scale: 0 }} animate={{ scale: 1 }} transition={easeSpring}>
      <circle cx="10" cy="10" r="9" fill="rgba(52,211,153,0.14)" />
      <M.path d="M6 10.5l2.8 2.8 5-5.5"
        stroke="#34d399" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
        initial={{ pathLength: 0 }} animate={{ pathLength: 1 }}
        transition={{ duration: 0.38, ease: easeSoft, delay: 0.08 }}
      />
    </M.svg>
  );
}

/* ── step row ────────────────────────────────────────────── */
function StepRow({ step, status, index }) {
  const active  = status === "active";
  const done    = status === "done";
  const pending = status === "pending";

  return (
    <M.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: pending ? 0.3 : 1, x: 0 }}
      transition={{ duration: 0.28, ease: easeSoft, delay: index * 0.04 }}
      className="flex items-center gap-3 rounded-xl px-4 py-3 transition-all duration-250"
      style={active ? { background: step.bg, border: `1px solid ${step.border}` }
                    : { border: "1px solid transparent" }}
    >
      {/* icon */}
      <div className="w-5 h-5 flex-shrink-0 flex items-center justify-center">
        {done    && <Check />}
        {active  && <Spinner color={step.color} />}
        {pending && (
          <span className="flex h-5 w-5 items-center justify-center rounded-full
                           bg-slate-800 text-[10px] font-bold text-slate-600">
            {index + 1}
          </span>
        )}
      </div>

      {/* text */}
      <div className="flex-1 min-w-0">
        <p className={`text-[13px] font-semibold leading-tight
          ${done ? "text-slate-500" : active ? "text-slate-100" : "text-slate-700"}`}>
          {step.label}
        </p>
        {active && (
          <M.p initial={{ opacity: 0, y: 3 }} animate={{ opacity: 1, y: 0 }}
            className="text-[10px] mt-0.5" style={{ color: step.color }}>
            {step.sub}
          </M.p>
        )}
      </div>

      {/* badge */}
      {done && (
        <M.span initial={{ opacity: 0, scale: 0.7 }} animate={{ opacity: 1, scale: 1 }}
          className="rounded-full px-2 py-0.5 text-[9px] font-bold text-emerald-400"
          style={{ background: "rgba(52,211,153,0.12)" }}>
          Done
        </M.span>
      )}
      {active && (
        <span className="text-[9px] font-bold" style={{ color: step.color }}>
          Running…
        </span>
      )}
    </M.div>
  );
}

/* ── progress bar ────────────────────────────────────────── */
function Bar({ step, total }) {
  return (
    <div className="h-px w-full overflow-hidden rounded-full"
      style={{ background: "rgba(255,255,255,0.06)" }}>
      <M.div className="h-full rounded-full"
        style={{ background: "linear-gradient(90deg, #6366f1, #06b6d4, #34d399)" }}
        initial={{ width: "0%" }}
        animate={{ width: `${Math.min((step / total) * 100, 100)}%` }}
        transition={{ duration: 0.55, ease: easeSoft }}
      />
    </div>
  );
}

/* ── success banner ──────────────────────────────────────── */
function SuccessBanner() {
  return (
    <M.div
      initial={{ opacity: 0, y: 8, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.4, ease: easeSoft }}
      className="relative overflow-hidden rounded-2xl px-5 py-4"
      style={{
        background: "rgba(6,78,59,0.25)",
        border: "1px solid rgba(52,211,153,0.22)",
        boxShadow: "0 4px 20px rgba(52,211,153,0.08)",
      }}
    >
      <div className="pointer-events-none absolute -right-8 -top-8 h-24 w-24 rounded-full"
        style={{ background: "radial-gradient(circle, rgba(52,211,153,0.12) 0%, transparent 70%)", filter: "blur(16px)" }} />

      <div className="flex items-center gap-3">
        <M.div initial={{ scale: 0 }} animate={{ scale: 1 }} transition={easeSpring}
          className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full"
          style={{ background: "rgba(52,211,153,0.18)" }}>
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <M.path d="M2.5 7.5l3 3 6-6.5"
              stroke="#34d399" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
              initial={{ pathLength: 0 }} animate={{ pathLength: 1 }}
              transition={{ duration: 0.45, ease: easeSoft, delay: 0.12 }}
            />
          </svg>
        </M.div>
        <div>
          <p className="text-[13px] font-semibold text-emerald-300">Analysis complete</p>
          <p className="text-[10px] text-emerald-700">Your insights are ready on the right</p>
        </div>
        <div className="ml-auto pulse-dot" />
      </div>
    </M.div>
  );
}

/* ── main export ─────────────────────────────────────────── */
export function UploadProcessor({ step }) {
  const done = step >= STEPS.length;
  return (
    <div className="space-y-2.5">
      <div className="flex items-center justify-between">
        <p className="text-[10px] font-black uppercase tracking-[0.14em] text-slate-600">
          Processing pipeline
        </p>
        <p className="text-[10px] text-slate-700">
          {done ? `${STEPS.length} / ${STEPS.length}` : `${step} / ${STEPS.length}`}
        </p>
      </div>

      <Bar step={step} total={STEPS.length} />

      <div className="rounded-2xl p-2.5 space-y-0.5"
        style={{ border: "1px solid rgba(255,255,255,0.05)", background: "rgba(7,9,15,0.6)" }}>
        {STEPS.map((s, i) => (
          <StepRow key={s.id} step={s}
            status={i < step ? "done" : i === step ? "active" : "pending"}
            index={i} />
        ))}
      </div>

      <AnimatePresence>
        {done && <M.div key="ok"><SuccessBanner /></M.div>}
      </AnimatePresence>
    </div>
  );
}
