/**
 * MeetingOutput — the heart of the UI.
 *
 * Three visually distinct output sections:
 *   🧾  Summary   — indigo gradient card, typing animation, grain texture
 *   📌  Decisions — cyan-tinted, staggered bullet rows, icon per item
 *   ✅  Actions   — masonry-style task cards, avatar badges, hover lift
 *
 * Plus: loading skeleton, rich empty state, collapsible raw transcript.
 */
import { useState, useEffect, useRef } from "react";
import { AnimatePresence, motion as M } from "framer-motion";
import {
  ArrowRight, ChevronDown, ChevronUp,
  Clock, Lightbulb, Sparkles, Target, User,
} from "lucide-react";
import { easeSoft, easeSpring, staggerContainer, staggerChild } from "../lib/motionPresets";

/* ═══════════════════════════════════════════════════════════
   COLOUR HELPERS
═══════════════════════════════════════════════════════════ */
const AVATAR_PALETTE = [
  { fg: "#a5b4fc", bg: "rgba(79,70,229,0.25)"  },  // indigo
  { fg: "#67e8f9", bg: "rgba(6,182,212,0.22)"  },  // cyan
  { fg: "#6ee7b7", bg: "rgba(16,185,129,0.22)" },  // emerald
  { fg: "#fcd34d", bg: "rgba(245,158,11,0.22)" },  // amber
  { fg: "#f9a8d4", bg: "rgba(236,72,153,0.22)" },  // pink
  { fg: "#c4b5fd", bg: "rgba(139,92,246,0.22)" },  // violet
];

function avatarStyle(name = "") {
  return AVATAR_PALETTE[(name.charCodeAt(0) || 65) % AVATAR_PALETTE.length];
}

function initials(name = "?") {
  return name.trim().split(/\s+/).map(w => w[0]).join("").toUpperCase().slice(0, 2) || "?";
}

function confidenceMeta(score = 0.8) {
  if (score >= 0.85) return { label: "High confidence", color: "#34d399", bar: 0.9  };
  if (score >= 0.6)  return { label: "Likely",          color: "#fbbf24", bar: 0.65 };
  return                    { label: "Possible",        color: "#64748b", bar: 0.4  };
}

/* ═══════════════════════════════════════════════════════════
   TYPING TEXT — character-by-character stream
═══════════════════════════════════════════════════════════ */
function TypedText({ text = "", speed = 12 }) {
  const [shown, setShown] = useState("");
  const [done,  setDone]  = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    setShown(""); setDone(false);
    if (!text) return;
    let i = 0;
    ref.current = setInterval(() => {
      i++;
      setShown(text.slice(0, i));
      if (i >= text.length) { clearInterval(ref.current); setDone(true); }
    }, speed);
    return () => clearInterval(ref.current);
  }, [text]);

  return <span>{shown}{!done && <span className="cursor" />}</span>;
}

/* ═══════════════════════════════════════════════════════════
   SECTION CHIP — small labelled header
═══════════════════════════════════════════════════════════ */
function Chip({ icon: Icon, label, count, color }) {
  return (
    <div className="flex items-center gap-2 mb-5">
      <div className="flex h-6 w-6 items-center justify-center rounded-lg"
        style={{ background: color + "20" }}>
        <Icon className="h-3.5 w-3.5" style={{ color }} />
      </div>
      <span className="text-[10px] font-black uppercase tracking-[0.14em]"
        style={{ color }}>
        {label}
      </span>
      {count != null && (
        <span className="ml-auto rounded-full px-2 py-0.5 text-[10px] font-bold"
          style={{ background: color + "18", color }}>
          {count}
        </span>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   SUMMARY CARD
═══════════════════════════════════════════════════════════ */
function SummaryCard({ summary, transcript }) {
  return (
    <M.div
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: easeSoft }}
      className="grain relative overflow-hidden rounded-3xl p-7"
      style={{
        background: "linear-gradient(145deg, rgba(55,48,163,0.42) 0%, rgba(7,9,15,0.75) 55%, rgba(8,51,68,0.25) 100%)",
        border: "1px solid rgba(99,102,241,0.22)",
        boxShadow: "0 0 0 1px rgba(255,255,255,0.03) inset, 0 12px 40px rgba(79,70,229,0.14)",
      }}
    >
      {/* decorative orbs */}
      <div className="pointer-events-none absolute -right-16 -top-16 h-56 w-56 rounded-full"
        style={{ background: "radial-gradient(circle, rgba(99,102,241,0.14) 0%, transparent 65%)", filter: "blur(32px)" }} />
      <div className="pointer-events-none absolute -left-10 bottom-4 h-36 w-36 rounded-full"
        style={{ background: "radial-gradient(circle, rgba(139,92,246,0.10) 0%, transparent 65%)", filter: "blur(24px)" }} />

      <Chip icon={Sparkles} label="Meeting Summary" color="#a5b4fc" />

      {/* AI summary text */}
      <p className="relative z-10 text-[15px] leading-[1.85] text-slate-200 font-light tracking-[0.01em]">
        <TypedText text={summary} speed={11} />
      </p>

      <p className="relative z-10 mt-4 flex items-center gap-1.5 text-[11px] italic text-indigo-400/50">
        <Sparkles className="h-3 w-3" />
        AI thinks this captures the core of your meeting
      </p>

      {/* ── Transcript shown directly below summary ── */}
      {transcript && (
        <div className="relative z-10 mt-6 pt-5"
          style={{ borderTop: "1px solid rgba(99,102,241,0.15)" }}>
          <pre className="max-h-56 overflow-y-auto rounded-xl px-4 py-3 text-[11px]
                          leading-relaxed text-slate-400 whitespace-pre-wrap"
            style={{ background: "rgba(0,0,0,0.3)", border: "1px solid rgba(99,102,241,0.12)" }}>
            {transcript}
          </pre>
        </div>
      )}
    </M.div>
  );
}

/* ═══════════════════════════════════════════════════════════
   DECISIONS LIST
═══════════════════════════════════════════════════════════ */
function DecisionsList({ decisions }) {
  if (!decisions?.length) return null;

  return (
    <M.div
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: easeSoft, delay: 0.1 }}
      className="rounded-3xl p-7"
      style={{
        background: "linear-gradient(145deg, rgba(8,51,68,0.48) 0%, rgba(7,9,15,0.72) 100%)",
        border: "1px solid rgba(6,182,212,0.16)",
        boxShadow: "0 12px 40px rgba(6,182,212,0.07)",
      }}
    >
      <Chip icon={Lightbulb} label="Decisions Reached" count={decisions.length} color="#22d3ee" />

      <M.ul
        variants={staggerContainer}
        initial="initial"
        animate="animate"
        className="space-y-1.5"
      >
        {decisions.map((d, i) => (
          <M.li
            key={i}
            variants={staggerChild}
            whileHover={{ x: 4 }}
            transition={{ duration: 0.18 }}
            className="group flex items-start gap-3 rounded-2xl px-4 py-3.5 cursor-default"
            style={{
              background: "rgba(6,182,212,0.04)",
              border: "1px solid rgba(6,182,212,0.08)",
              transition: "border-color 0.2s, background 0.2s",
            }}
            onMouseEnter={e => {
              e.currentTarget.style.borderColor = "rgba(6,182,212,0.22)";
              e.currentTarget.style.background  = "rgba(6,182,212,0.08)";
            }}
            onMouseLeave={e => {
              e.currentTarget.style.borderColor = "rgba(6,182,212,0.08)";
              e.currentTarget.style.background  = "rgba(6,182,212,0.04)";
            }}
          >
            <ArrowRight className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-cyan-500/60
                                   transition-colors group-hover:text-cyan-400" />
            <span className="text-sm leading-relaxed text-slate-300">{d}</span>
          </M.li>
        ))}
      </M.ul>
    </M.div>
  );
}

/* ═══════════════════════════════════════════════════════════
   SINGLE ACTION CARD
═══════════════════════════════════════════════════════════ */
function ActionCard({ item, index }) {
  const conf  = confidenceMeta(item.confidence_score ?? 0.8);
  const av    = avatarStyle(item.assignee || "?");
  const ini   = initials(item.assignee || "?");
  const isHigh = (item.confidence_score ?? 0.8) >= 0.85;

  return (
    <M.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: easeSoft, delay: 0.15 + index * 0.065 }}
      className="lift group relative overflow-hidden rounded-2xl p-5 cursor-default"
      style={{
        background: "rgba(12,16,28,0.8)",
        border: "1px solid rgba(255,255,255,0.055)",
        boxShadow: "0 2px 12px rgba(0,0,0,0.35)",
      }}
    >
      {/* left accent stripe — gradient, brightens on hover */}
      <div
        className="absolute left-0 top-0 h-full w-[3px] rounded-l-2xl transition-opacity duration-200"
        style={{
          background: "linear-gradient(180deg, #6366f1 0%, #06b6d4 60%, #10b981 100%)",
          opacity: 0.45,
        }}
      />

      <div className="flex items-start gap-3 pl-3">
        {/* avatar */}
        <div
          className="flex h-9 w-9 flex-shrink-0 items-center justify-center
                     rounded-xl text-[11px] font-extrabold tracking-wide"
          style={{ color: av.fg, background: av.bg }}
        >
          {ini}
        </div>

        <div className="flex-1 min-w-0">
          {/* task */}
          <p className="text-[13.5px] font-semibold leading-snug text-slate-100">
            {item.task}
          </p>

          {/* badges row */}
          <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
            {/* assignee */}
            <span className="flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-medium"
              style={{ background: "rgba(255,255,255,0.05)", color: "#94a3b8" }}>
              <User className="h-2.5 w-2.5" />
              {item.assignee || "Unassigned"}
            </span>

            {/* deadline */}
            {item.deadline && (
              <span className="flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-medium"
                style={{ background: "rgba(245,158,11,0.1)", color: "#fbbf24" }}>
                <Clock className="h-2.5 w-2.5" />
                {item.deadline}
              </span>
            )}

            {/* confidence bar + label */}
            <span className="ml-auto flex items-center gap-1.5 text-[10px] font-medium"
              style={{ color: conf.color }}>
              {/* mini bar */}
              <span className="relative h-1 w-10 overflow-hidden rounded-full"
                style={{ background: "rgba(255,255,255,0.07)" }}>
                <M.span
                  className="absolute left-0 top-0 h-full rounded-full"
                  style={{ background: conf.color }}
                  initial={{ width: 0 }}
                  animate={{ width: `${conf.bar * 100}%` }}
                  transition={{ duration: 0.6, ease: easeSoft, delay: 0.3 + index * 0.06 }}
                />
              </span>
              {conf.label}
            </span>
          </div>
        </div>
      </div>

      {/* microcopy — high confidence only */}
      {isHigh && (
        <p className="mt-3 pl-3 text-[10px] italic"
          style={{ color: "rgba(165,180,252,0.45)" }}>
          ✦ AI thinks this is important
        </p>
      )}
    </M.div>
  );
}

/* ═══════════════════════════════════════════════════════════
   ACTION ITEMS SECTION
═══════════════════════════════════════════════════════════ */
function ActionItemsSection({ items }) {
  if (!items?.length) return null;

  // Split into two unequal columns for asymmetry
  const col1 = items.filter((_, i) => i % 2 === 0);
  const col2 = items.filter((_, i) => i % 2 === 1);

  return (
    <M.div
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: easeSoft, delay: 0.2 }}
    >
      <Chip icon={Target} label="Action Items" count={items.length} color="#34d399" />

      {/* Two-column masonry — col1 slightly wider */}
      <div className="flex gap-3 items-start">
        <div className="flex flex-col gap-3 flex-[1.1]">
          {col1.map((item, i) => (
            <ActionCard key={i * 2} item={item} index={i * 2} />
          ))}
        </div>
        {col2.length > 0 && (
          <div className="flex flex-col gap-3 flex-1 mt-5">
            {/* offset second column slightly for visual rhythm */}
            {col2.map((item, i) => (
              <ActionCard key={i * 2 + 1} item={item} index={i * 2 + 1} />
            ))}
          </div>
        )}
      </div>
    </M.div>
  );
}

/* ═══════════════════════════════════════════════════════════
   TRANSCRIPT COLLAPSIBLE
═══════════════════════════════════════════════════════════ */
function TranscriptCollapsible({ transcript }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="overflow-hidden rounded-2xl"
      style={{ border: "1px solid rgba(255,255,255,0.05)", background: "rgba(7,9,15,0.6)" }}>
      <button
        onClick={() => setOpen(v => !v)}
        className="flex w-full items-center gap-3 px-5 py-4 text-left
                   transition-colors hover:bg-white/[0.015]"
      >
        <FileText className="h-3.5 w-3.5 text-slate-600" />
        <span className="flex-1 text-xs font-semibold uppercase tracking-widest text-slate-600">
          Raw Transcript
        </span>
        {open
          ? <ChevronUp className="h-3.5 w-3.5 text-slate-600" />
          : <ChevronDown className="h-3.5 w-3.5 text-slate-600" />}
      </button>
      <AnimatePresence>
        {open && (
          <M.div key="body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: easeSoft }}
            className="overflow-hidden">
            <pre className="max-h-60 overflow-y-auto px-5 pb-5 text-[11px]
                            leading-relaxed text-slate-600 whitespace-pre-wrap">
              {transcript}
            </pre>
          </M.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   EMPTY STATE
═══════════════════════════════════════════════════════════ */
function EmptyState() {
  return (
    <M.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.55, ease: easeSoft }}
      className="flex flex-col items-center justify-center gap-7 py-20 px-6 text-center"
    >
      {/* illustration */}
      <div className="relative">
        {/* pulsing outer ring */}
        <M.div
          animate={{ scale: [1, 1.12, 1], opacity: [0.25, 0.45, 0.25] }}
          transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
          className="absolute inset-0 rounded-3xl"
          style={{ background: "radial-gradient(circle, rgba(99,102,241,0.22) 0%, transparent 70%)" }}
        />

        {/* icon box */}
        <div className="relative flex h-24 w-24 items-center justify-center rounded-3xl"
          style={{
            background: "linear-gradient(145deg, rgba(55,48,163,0.45), rgba(7,9,15,0.85))",
            border: "1px solid rgba(99,102,241,0.28)",
            boxShadow: "0 12px 40px rgba(79,70,229,0.18)",
          }}>
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
            {/* main chat bubble */}
            <rect x="4" y="5" width="30" height="22" rx="5"
              fill="rgba(99,102,241,0.18)" stroke="rgba(99,102,241,0.55)" strokeWidth="1.5" />
            {/* tail */}
            <path d="M11 27l-5 6 7-2.5" fill="rgba(99,102,241,0.18)"
              stroke="rgba(99,102,241,0.55)" strokeWidth="1.5" strokeLinejoin="round" />
            {/* text lines */}
            <line x1="10" y1="13" x2="27" y2="13" stroke="rgba(165,180,252,0.7)" strokeWidth="1.5" strokeLinecap="round" />
            <line x1="10" y1="18" x2="21" y2="18" stroke="rgba(165,180,252,0.45)" strokeWidth="1.5" strokeLinecap="round" />
            {/* rotating sparkle gear */}
            <M.g
              animate={{ rotate: 360 }}
              transition={{ duration: 10, repeat: Infinity, ease: "linear" }}
              style={{ originX: "38px", originY: "34px" }}>
              <circle cx="38" cy="34" r="7" fill="rgba(6,182,212,0.12)"
                stroke="rgba(6,182,212,0.45)" strokeWidth="1.5" />
              {[0,60,120,180,240,300].map(a => {
                const r = 7, rad = a * Math.PI / 180;
                const x1 = 38 + (r-1)*Math.cos(rad), y1 = 34 + (r-1)*Math.sin(rad);
                const x2 = 38 + (r+2)*Math.cos(rad), y2 = 34 + (r+2)*Math.sin(rad);
                return <line key={a} x1={x1} y1={y1} x2={x2} y2={y2}
                  stroke="#06b6d4" strokeWidth="1.5" strokeLinecap="round" />;
              })}
            </M.g>
          </svg>
        </div>
      </div>

      {/* copy */}
      <div className="max-w-[280px]">
        <p className="text-[15px] font-semibold text-slate-300 leading-snug">
          Your meeting insights will appear here
        </p>
        <p className="mt-2.5 text-sm leading-relaxed text-slate-600">
          Paste a transcript or upload a recording — the AI extracts a summary,
          decisions, and action items automatically.
        </p>
      </div>

      {/* feature pills */}
      <div className="flex flex-wrap justify-center gap-2">
        {[
          { label: "🧾 Summary",      color: "rgba(99,102,241,0.15)",  border: "rgba(99,102,241,0.2)"  },
          { label: "📌 Decisions",    color: "rgba(6,182,212,0.12)",   border: "rgba(6,182,212,0.2)"   },
          { label: "✅ Action Items", color: "rgba(16,185,129,0.12)",  border: "rgba(16,185,129,0.2)"  },
        ].map(f => (
          <span key={f.label}
            className="rounded-full px-3.5 py-1.5 text-xs font-medium text-slate-500"
            style={{ background: f.color, border: `1px solid ${f.border}` }}>
            {f.label}
          </span>
        ))}
      </div>
    </M.div>
  );
}

/* ═══════════════════════════════════════════════════════════
   LOADING SKELETON
═══════════════════════════════════════════════════════════ */
function Skeleton() {
  return (
    <div className="space-y-4">
      {/* summary skeleton */}
      <div className="rounded-3xl p-7"
        style={{ border: "1px solid rgba(99,102,241,0.1)", background: "rgba(12,16,28,0.6)" }}>
        <div className="shimmer h-2.5 w-28 rounded-full mb-5" />
        <div className="space-y-2.5">
          <div className="shimmer h-2.5 rounded-full w-full" />
          <div className="shimmer h-2.5 rounded-full w-[88%]" />
          <div className="shimmer h-2.5 rounded-full w-[72%]" />
        </div>
      </div>
      {/* decisions skeleton */}
      <div className="rounded-3xl p-7"
        style={{ border: "1px solid rgba(6,182,212,0.1)", background: "rgba(12,16,28,0.6)" }}>
        <div className="shimmer h-2.5 w-32 rounded-full mb-5" />
        {[100, 80, 90].map((w, i) => (
          <div key={i} className="flex items-center gap-3 mb-3">
            <div className="shimmer h-2 w-2 rounded-full flex-shrink-0" />
            <div className="shimmer h-2.5 rounded-full" style={{ width: `${w}%` }} />
          </div>
        ))}
      </div>
      {/* action items skeleton */}
      <div className="flex gap-3">
        {[0, 1].map(col => (
          <div key={col} className={`flex-1 space-y-3 ${col === 1 ? "mt-5" : ""}`}>
            {[0, 1].map(row => (
              <div key={row} className="rounded-2xl p-5"
                style={{ border: "1px solid rgba(255,255,255,0.05)", background: "rgba(12,16,28,0.6)" }}>
                <div className="flex gap-3">
                  <div className="shimmer h-9 w-9 rounded-xl flex-shrink-0" />
                  <div className="flex-1 space-y-2">
                    <div className="shimmer h-2.5 rounded-full w-full" />
                    <div className="shimmer h-2.5 rounded-full w-[65%]" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   MAIN EXPORT
═══════════════════════════════════════════════════════════ */
export default function MeetingOutput({ structured, transcript, show, loading }) {
  const hasOutput =
    structured?.summary ||
    structured?.decisions?.length ||
    structured?.action_items?.length;

  return (
    <AnimatePresence mode="wait">
      {loading ? (
        <M.div key="skel" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <Skeleton />
        </M.div>
      ) : show && hasOutput ? (
        <M.div key="out"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          transition={{ duration: 0.4, ease: easeSoft }}
          className="space-y-5">
          {structured?.summary && <SummaryCard summary={structured.summary} transcript={transcript} />}
          {structured?.decisions?.length > 0 && <DecisionsList decisions={structured.decisions} />}
          {structured?.action_items?.length > 0 && <ActionItemsSection items={structured.action_items} />}
        </M.div>
      ) : (
        <M.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <EmptyState />
        </M.div>
      )}
    </AnimatePresence>
  );
}
