import { useState, useEffect, useRef } from "react";
import { AnimatePresence, motion as M } from "framer-motion";
import {
  ArrowRight, Clock, Lightbulb, Sparkles, Target, User,
} from "lucide-react";
import { easeSoft, easeSpring, staggerContainer, staggerChild } from "../lib/motionPresets";

/* ── helpers ─────────────────────────────────────────────── */
const AVATAR_PALETTE = [
  { fg: "#a5b4fc", bg: "rgba(79,70,229,0.25)"  },
  { fg: "#67e8f9", bg: "rgba(6,182,212,0.22)"  },
  { fg: "#6ee7b7", bg: "rgba(16,185,129,0.22)" },
  { fg: "#fcd34d", bg: "rgba(245,158,11,0.22)" },
  { fg: "#f9a8d4", bg: "rgba(236,72,153,0.22)" },
  { fg: "#c4b5fd", bg: "rgba(139,92,246,0.22)" },
];
const avStyle = n => AVATAR_PALETTE[(n?.charCodeAt(0) || 65) % AVATAR_PALETTE.length];
const ini     = n => (n || "?").trim().split(/\s+/).map(w => w[0]).join("").toUpperCase().slice(0, 2) || "?";
const confMeta = s => {
  if (s >= 0.85) return { label: "High confidence", color: "#34d399", bar: 0.9  };
  if (s >= 0.6)  return { label: "Likely",          color: "#fbbf24", bar: 0.65 };
  return               { label: "Possible",         color: "#64748b", bar: 0.4  };
};

/* ── typing text ─────────────────────────────────────────── */
function TypedText({ text = "", speed = 12 }) {
  const [shown, setShown] = useState("");
  const [done,  setDone]  = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    setShown(""); setDone(false);
    if (!text) return;
    let i = 0;
    ref.current = setInterval(() => {
      i++; setShown(text.slice(0, i));
      if (i >= text.length) { clearInterval(ref.current); setDone(true); }
    }, speed);
    return () => clearInterval(ref.current);
  }, [text]);
  return <span>{shown}{!done && <span className="cursor" />}</span>;
}

/* ── section chip ────────────────────────────────────────── */
function Chip({ icon: Icon, label, count, color }) {
  return (
    <div className="flex items-center gap-2 mb-5">
      <div className="flex h-6 w-6 items-center justify-center rounded-lg"
        style={{ background: color + "20" }}>
        <Icon className="h-3.5 w-3.5" style={{ color }} />
      </div>
      <span className="text-xs font-black uppercase tracking-widest" style={{ color }}>{label}</span>
      {count != null && (
        <span className="ml-auto rounded-full px-2 py-0.5 text-xs font-bold"
          style={{ background: color + "18", color }}>{count}</span>
      )}
    </div>
  );
}

/* ── summary card ────────────────────────────────────────── */
function SummaryCard({ summary, transcript }) {
  return (
    <M.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: easeSoft }}
      className="grain relative overflow-hidden rounded-3xl p-7"
      style={{
        background: "linear-gradient(145deg, rgba(55,48,163,0.42) 0%, rgba(7,9,15,0.75) 55%, rgba(8,51,68,0.25) 100%)",
        border: "1px solid rgba(99,102,241,0.22)",
        boxShadow: "0 0 0 1px rgba(255,255,255,0.03) inset, 0 12px 40px rgba(79,70,229,0.14)",
      }}>
      <div className="pointer-events-none absolute -right-16 -top-16 h-56 w-56 rounded-full"
        style={{ background: "radial-gradient(circle, rgba(99,102,241,0.14) 0%, transparent 65%)", filter: "blur(32px)" }} />

      <Chip icon={Sparkles} label="Meeting Summary" color="#a5b4fc" />

      <p className="relative z-10 text-sm leading-relaxed text-slate-200 font-light">
        <TypedText text={summary} speed={11} />
      </p>
      <p className="relative z-10 mt-4 flex items-center gap-1.5 text-xs italic text-indigo-400/50">
        <Sparkles className="h-3 w-3" />
        AI thinks this captures the core of your meeting
      </p>

      {transcript && (
        <div className="relative z-10 mt-6 pt-5"
          style={{ borderTop: "1px solid rgba(99,102,241,0.15)" }}>
          <pre className="max-h-56 overflow-y-auto rounded-xl px-4 py-3 text-xs
                          leading-relaxed text-slate-400 whitespace-pre-wrap"
            style={{ background: "rgba(0,0,0,0.3)", border: "1px solid rgba(99,102,241,0.12)" }}>
            {transcript}
          </pre>
        </div>
      )}
    </M.div>
  );
}

/* ── decisions list ──────────────────────────────────────── */
function DecisionsList({ decisions }) {
  if (!decisions?.length) return null;
  return (
    <M.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: easeSoft, delay: 0.1 }}
      className="rounded-3xl p-7"
      style={{
        background: "linear-gradient(145deg, rgba(8,51,68,0.48) 0%, rgba(7,9,15,0.72) 100%)",
        border: "1px solid rgba(6,182,212,0.16)",
      }}>
      <Chip icon={Lightbulb} label="Decisions Reached" count={decisions.length} color="#22d3ee" />
      <M.ul variants={staggerContainer} initial="initial" animate="animate" className="space-y-1.5">
        {decisions.map((d, i) => (
          <M.li key={i} variants={staggerChild} whileHover={{ x: 4 }}
            className="flex items-start gap-3 rounded-2xl px-4 py-3.5 cursor-default"
            style={{ background: "rgba(6,182,212,0.04)", border: "1px solid rgba(6,182,212,0.08)" }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = "rgba(6,182,212,0.22)"; e.currentTarget.style.background = "rgba(6,182,212,0.08)"; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = "rgba(6,182,212,0.08)"; e.currentTarget.style.background = "rgba(6,182,212,0.04)"; }}>
            <ArrowRight className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-cyan-500/60" />
            <span className="text-sm leading-relaxed text-slate-300">{d}</span>
          </M.li>
        ))}
      </M.ul>
    </M.div>
  );
}

/* ── action card ─────────────────────────────────────────── */
function ActionCard({ item, index }) {
  const conf = confMeta(item.confidence_score ?? 0.8);
  const av   = avStyle(item.assignee || "?");
  return (
    <M.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: easeSoft, delay: 0.15 + index * 0.065 }}
      className="lift group relative overflow-hidden rounded-2xl p-5 cursor-default"
      style={{ background: "rgba(12,16,28,0.8)", border: "1px solid rgba(255,255,255,0.055)" }}>
      <div className="absolute left-0 top-0 h-full w-[3px] rounded-l-2xl"
        style={{ background: "linear-gradient(180deg, #6366f1 0%, #06b6d4 60%, #10b981 100%)", opacity: 0.45 }} />
      <div className="flex items-start gap-3 pl-3">
        <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl text-xs font-extrabold"
          style={{ color: av.fg, background: av.bg }}>{ini(item.assignee)}</div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold leading-snug text-slate-100">{item.task}</p>
          <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
            <span className="flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium"
              style={{ background: "rgba(255,255,255,0.05)", color: "#94a3b8" }}>
              <User className="h-2.5 w-2.5" />{item.assignee || "Unassigned"}
            </span>
            {item.deadline && (
              <span className="flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium"
                style={{ background: "rgba(245,158,11,0.1)", color: "#fbbf24" }}>
                <Clock className="h-2.5 w-2.5" />{item.deadline}
              </span>
            )}
            <span className="ml-auto flex items-center gap-1.5 text-xs font-medium" style={{ color: conf.color }}>
              <span className="relative h-1 w-10 overflow-hidden rounded-full"
                style={{ background: "rgba(255,255,255,0.07)" }}>
                <M.span className="absolute left-0 top-0 h-full rounded-full"
                  style={{ background: conf.color }}
                  initial={{ width: 0 }}
                  animate={{ width: `${conf.bar * 100}%` }}
                  transition={{ duration: 0.6, ease: easeSoft, delay: 0.3 + index * 0.06 }} />
              </span>
              {conf.label}
            </span>
          </div>
        </div>
      </div>
      {(item.confidence_score ?? 0.8) >= 0.85 && (
        <p className="mt-3 pl-3 text-xs italic" style={{ color: "rgba(165,180,252,0.45)" }}>
          ✦ AI thinks this is important
        </p>
      )}
    </M.div>
  );
}

/* ── action items section ────────────────────────────────── */
function ActionItemsSection({ items }) {
  if (!items?.length) return null;
  const col1 = items.filter((_, i) => i % 2 === 0);
  const col2 = items.filter((_, i) => i % 2 === 1);
  return (
    <M.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: easeSoft, delay: 0.2 }}>
      <Chip icon={Target} label="Action Items" count={items.length} color="#34d399" />
      <div className="flex gap-3 items-start">
        <div className="flex flex-col gap-3 flex-[1.1]">
          {col1.map((item, i) => <ActionCard key={i * 2} item={item} index={i * 2} />)}
        </div>
        {col2.length > 0 && (
          <div className="flex flex-col gap-3 flex-1 mt-5">
            {col2.map((item, i) => <ActionCard key={i * 2 + 1} item={item} index={i * 2 + 1} />)}
          </div>
        )}
      </div>
    </M.div>
  );
}

/* ── skeleton ────────────────────────────────────────────── */
function Skeleton() {
  return (
    <div className="space-y-4">
      {[1, 2].map(k => (
        <div key={k} className="rounded-3xl p-7"
          style={{ border: "1px solid rgba(99,102,241,0.1)", background: "rgba(12,16,28,0.6)" }}>
          <div className="shimmer h-2.5 w-28 rounded-full mb-5" />
          <div className="space-y-2.5">
            <div className="shimmer h-2.5 rounded-full w-full" />
            <div className="shimmer h-2.5 rounded-full w-4/5" />
          </div>
        </div>
      ))}
    </div>
  );
}

/* ── empty state ─────────────────────────────────────────── */
function EmptyState() {
  return (
    <M.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.55, ease: easeSoft }}
      className="flex flex-col items-center justify-center gap-7 py-20 px-6 text-center">
      <div className="relative">
        <M.div animate={{ scale: [1, 1.12, 1], opacity: [0.25, 0.45, 0.25] }}
          transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
          className="absolute inset-0 rounded-3xl"
          style={{ background: "radial-gradient(circle, rgba(99,102,241,0.22) 0%, transparent 70%)" }} />
        <div className="relative flex h-24 w-24 items-center justify-center rounded-3xl"
          style={{
            background: "linear-gradient(145deg, rgba(55,48,163,0.45), rgba(7,9,15,0.85))",
            border: "1px solid rgba(99,102,241,0.28)",
          }}>
          <Sparkles className="h-10 w-10 text-indigo-400" />
        </div>
      </div>
      <div className="max-w-xs">
        <p className="text-base font-semibold text-slate-300">Your meeting insights will appear here</p>
        <p className="mt-2 text-sm leading-relaxed text-slate-600">
          Paste a transcript or upload a recording — the AI extracts a summary, decisions, and action items.
        </p>
      </div>
      <div className="flex flex-wrap justify-center gap-2">
        {[
          { label: "🧾 Summary",      color: "rgba(99,102,241,0.15)",  border: "rgba(99,102,241,0.2)"  },
          { label: "📌 Decisions",    color: "rgba(6,182,212,0.12)",   border: "rgba(6,182,212,0.2)"   },
          { label: "✅ Action Items", color: "rgba(16,185,129,0.12)",  border: "rgba(16,185,129,0.2)"  },
        ].map(f => (
          <span key={f.label} className="rounded-full px-3.5 py-1.5 text-xs font-medium text-slate-500"
            style={{ background: f.color, border: `1px solid ${f.border}` }}>{f.label}</span>
        ))}
      </div>
    </M.div>
  );
}

/* ── main export ─────────────────────────────────────────── */
export default function MeetingOutput({ structured, transcript, show, loading }) {
  const hasOutput = structured?.summary || structured?.decisions?.length || structured?.action_items?.length;

  return (
    <AnimatePresence mode="wait">
      {loading ? (
        <M.div key="skel" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <Skeleton />
        </M.div>
      ) : show && hasOutput ? (
        <M.div key="out" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          transition={{ duration: 0.4, ease: easeSoft }} className="space-y-5">
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
