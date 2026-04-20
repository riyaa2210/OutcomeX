import { useState, useEffect, useRef } from "react";
import { AnimatePresence, motion as M } from "framer-motion";
import {
  ArrowRight, Clock, Lightbulb, Sparkles, Target, User,
} from "lucide-react";
import { easeSoft, staggerContainer, staggerChild } from "../lib/motionPresets";

/* ─────────────────────────────────────────────────────────
   THEME HOOK — reads the <html class="dark"> toggle
───────────────────────────────────────────────────────── */
function useDark() {
  const [dark, setDark] = useState(
    () => document.documentElement.classList.contains("dark")
  );
  useEffect(() => {
    const obs = new MutationObserver(() =>
      setDark(document.documentElement.classList.contains("dark"))
    );
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);
  return dark;
}

/* ─────────────────────────────────────────────────────────
   COLOUR HELPERS
───────────────────────────────────────────────────────── */
const AVATAR_PALETTE = [
  { fg: "#4338ca", bg: "rgba(79,70,229,0.12)"  },
  { fg: "#0e7490", bg: "rgba(6,182,212,0.12)"  },
  { fg: "#059669", bg: "rgba(16,185,129,0.12)" },
  { fg: "#b45309", bg: "rgba(245,158,11,0.12)" },
  { fg: "#be185d", bg: "rgba(236,72,153,0.12)" },
  { fg: "#7c3aed", bg: "rgba(139,92,246,0.12)" },
];
const AVATAR_PALETTE_DARK = [
  { fg: "#a5b4fc", bg: "rgba(79,70,229,0.25)"  },
  { fg: "#67e8f9", bg: "rgba(6,182,212,0.22)"  },
  { fg: "#6ee7b7", bg: "rgba(16,185,129,0.22)" },
  { fg: "#fcd34d", bg: "rgba(245,158,11,0.22)" },
  { fg: "#f9a8d4", bg: "rgba(236,72,153,0.22)" },
  { fg: "#c4b5fd", bg: "rgba(139,92,246,0.22)" },
];

const avStyle = (name, dark) => {
  const p = dark ? AVATAR_PALETTE_DARK : AVATAR_PALETTE;
  return p[(name?.charCodeAt(0) || 65) % p.length];
};
const ini = n => (n || "?").trim().split(/\s+/).map(w => w[0]).join("").toUpperCase().slice(0, 2) || "?";
const confMeta = s => {
  if (s >= 0.85) return { label: "High confidence", color: "#16a34a", bar: 0.9  };
  if (s >= 0.6)  return { label: "Likely",          color: "#d97706", bar: 0.65 };
  return               { label: "Possible",         color: "#64748b", bar: 0.4  };
};
const confMetaDark = s => {
  if (s >= 0.85) return { label: "High confidence", color: "#34d399", bar: 0.9  };
  if (s >= 0.6)  return { label: "Likely",          color: "#fbbf24", bar: 0.65 };
  return               { label: "Possible",         color: "#64748b", bar: 0.4  };
};

/* ─────────────────────────────────────────────────────────
   TYPING TEXT
───────────────────────────────────────────────────────── */
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

/* ─────────────────────────────────────────────────────────
   SECTION CHIP
───────────────────────────────────────────────────────── */
function Chip({ icon: Icon, label, count, color }) {
  return (
    <div className="flex items-center gap-2 mb-5">
      <div className="flex h-6 w-6 items-center justify-center rounded-lg"
        style={{ background: color + "22" }}>
        <Icon className="h-3.5 w-3.5" style={{ color }} />
      </div>
      <span className="text-xs font-black uppercase tracking-widest" style={{ color }}>{label}</span>
      {count != null && (
        <span className="ml-auto rounded-full px-2 py-0.5 text-xs font-bold"
          style={{ background: color + "20", color }}>{count}</span>
      )}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────
   SUMMARY CARD
───────────────────────────────────────────────────────── */
function SummaryCard({ summary, transcript }) {
  const dark = useDark();

  const cardStyle = dark ? {
    background: "linear-gradient(145deg, rgba(55,48,163,0.42) 0%, rgba(7,9,15,0.75) 55%, rgba(8,51,68,0.25) 100%)",
    border: "1px solid rgba(99,102,241,0.22)",
    boxShadow: "0 12px 40px rgba(79,70,229,0.14)",
  } : {
    background: "linear-gradient(145deg, #eef2ff 0%, #ffffff 60%, #ecfdf5 100%)",
    border: "1px solid rgba(99,102,241,0.25)",
    boxShadow: "0 4px 24px rgba(99,102,241,0.1)",
  };

  const txStyle = dark ? {
    background: "rgba(0,0,0,0.3)",
    border: "1px solid rgba(99,102,241,0.12)",
  } : {
    background: "rgba(99,102,241,0.04)",
    border: "1px solid rgba(99,102,241,0.15)",
  };

  return (
    <M.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: easeSoft }}
      className="grain relative overflow-hidden rounded-3xl p-7"
      style={cardStyle}>

      <div className="pointer-events-none absolute -right-16 -top-16 h-56 w-56 rounded-full"
        style={{ background: "radial-gradient(circle, rgba(99,102,241,0.12) 0%, transparent 65%)", filter: "blur(32px)" }} />

      <Chip icon={Sparkles} label="Meeting Summary" color={dark ? "#818cf8" : "#4338ca"} />

      <p className={`relative z-10 text-base leading-relaxed font-normal ${dark ? "text-slate-100" : "text-slate-900"}`}>
        <TypedText text={summary} speed={11} />
      </p>

      <p className={`relative z-10 mt-4 flex items-center gap-1.5 text-xs italic ${dark ? "text-indigo-400/60" : "text-indigo-500/70"}`}>
        <Sparkles className="h-3 w-3" />
        AI thinks this captures the core of your meeting
      </p>

      {transcript && (
        <div className="relative z-10 mt-6 pt-5"
          style={{ borderTop: dark ? "1px solid rgba(99,102,241,0.15)" : "1px solid rgba(99,102,241,0.2)" }}>
          <pre className={`max-h-56 overflow-y-auto rounded-xl px-4 py-3 text-xs leading-relaxed whitespace-pre-wrap ${dark ? "text-slate-400" : "text-slate-600"}`}
            style={txStyle}>
            {transcript}
          </pre>
        </div>
      )}
    </M.div>
  );
}

/* ─────────────────────────────────────────────────────────
   DECISIONS LIST
───────────────────────────────────────────────────────── */
function DecisionsList({ decisions }) {
  const dark = useDark();
  if (!decisions?.length) return null;

  const cardStyle = dark ? {
    background: "linear-gradient(145deg, rgba(8,51,68,0.48) 0%, rgba(7,9,15,0.72) 100%)",
    border: "1px solid rgba(6,182,212,0.16)",
  } : {
    background: "linear-gradient(145deg, #ecfeff 0%, #ffffff 100%)",
    border: "1px solid rgba(6,182,212,0.3)",
    boxShadow: "0 4px 20px rgba(6,182,212,0.08)",
  };

  return (
    <M.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: easeSoft, delay: 0.1 }}
      className="rounded-3xl p-7" style={cardStyle}>
      <Chip icon={Lightbulb} label="Decisions Reached" count={decisions.length}
        color={dark ? "#22d3ee" : "#0e7490"} />
      <M.ul variants={staggerContainer} initial="initial" animate="animate" className="space-y-1.5">
        {decisions.map((d, i) => (
          <M.li key={i} variants={staggerChild} whileHover={{ x: 4 }}
            className="flex items-start gap-3 rounded-2xl px-4 py-3.5 cursor-default transition-colors"
            style={dark
              ? { background: "rgba(6,182,212,0.04)", border: "1px solid rgba(6,182,212,0.08)" }
              : { background: "rgba(6,182,212,0.05)", border: "1px solid rgba(6,182,212,0.15)" }
            }
            onMouseEnter={e => {
              e.currentTarget.style.borderColor = dark ? "rgba(6,182,212,0.22)" : "rgba(6,182,212,0.35)";
              e.currentTarget.style.background  = dark ? "rgba(6,182,212,0.08)" : "rgba(6,182,212,0.1)";
            }}
            onMouseLeave={e => {
              e.currentTarget.style.borderColor = dark ? "rgba(6,182,212,0.08)" : "rgba(6,182,212,0.15)";
              e.currentTarget.style.background  = dark ? "rgba(6,182,212,0.04)" : "rgba(6,182,212,0.05)";
            }}>
            <ArrowRight className={`mt-0.5 h-3.5 w-3.5 flex-shrink-0 ${dark ? "text-cyan-500/60" : "text-cyan-600"}`} />
            <span className={`text-sm leading-relaxed ${dark ? "text-slate-300" : "text-slate-700"}`}>{d}</span>
          </M.li>
        ))}
      </M.ul>
    </M.div>
  );
}

/* ─────────────────────────────────────────────────────────
   ACTION CARD
───────────────────────────────────────────────────────── */
function ActionCard({ item, index }) {
  const dark = useDark();
  const conf = dark ? confMetaDark(item.confidence_score ?? 0.8) : confMeta(item.confidence_score ?? 0.8);
  const av   = avStyle(item.assignee || "?", dark);

  const cardStyle = dark
    ? { background: "rgba(12,16,28,0.8)", border: "1px solid rgba(255,255,255,0.055)" }
    : { background: "#ffffff", border: "1px solid rgba(0,0,0,0.08)", boxShadow: "0 2px 12px rgba(0,0,0,0.06)" };

  const assigneeBadge = dark
    ? { background: "rgba(255,255,255,0.05)", color: "#94a3b8" }
    : { background: "rgba(0,0,0,0.05)", color: "#475569" };

  const confBarBg = dark ? "rgba(255,255,255,0.07)" : "rgba(0,0,0,0.08)";

  return (
    <M.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: easeSoft, delay: 0.15 + index * 0.065 }}
      className="lift group relative overflow-hidden rounded-2xl p-5 cursor-default"
      style={cardStyle}>
      <div className="absolute left-0 top-0 h-full w-[3px] rounded-l-2xl"
        style={{ background: "linear-gradient(180deg, #6366f1 0%, #06b6d4 60%, #10b981 100%)", opacity: dark ? 0.45 : 0.7 }} />

      <div className="flex items-start gap-3 pl-3">
        <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl text-xs font-extrabold"
          style={{ color: av.fg, background: av.bg }}>{ini(item.assignee)}</div>

        <div className="flex-1 min-w-0">
          <p className={`text-sm font-semibold leading-snug ${dark ? "text-slate-100" : "text-slate-900"}`}>
            {item.task}
          </p>
          <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
            <span className="flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium"
              style={assigneeBadge}>
              <User className="h-2.5 w-2.5" />{item.assignee || "Unassigned"}
            </span>
            {item.deadline && (
              <span className="flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium"
                style={{ background: "rgba(245,158,11,0.12)", color: dark ? "#fbbf24" : "#b45309" }}>
                <Clock className="h-2.5 w-2.5" />{item.deadline}
              </span>
            )}
            <span className="ml-auto flex items-center gap-1.5 text-xs font-medium" style={{ color: conf.color }}>
              <span className="relative h-1 w-10 overflow-hidden rounded-full" style={{ background: confBarBg }}>
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
        <p className={`mt-3 pl-3 text-xs italic ${dark ? "text-indigo-400/50" : "text-indigo-500/60"}`}>
          ✦ AI thinks this is important
        </p>
      )}
    </M.div>
  );
}

/* ─────────────────────────────────────────────────────────
   ACTION ITEMS SECTION
───────────────────────────────────────────────────────── */
function ActionItemsSection({ items }) {
  const dark = useDark();
  if (!items?.length) return null;
  const col1 = items.filter((_, i) => i % 2 === 0);
  const col2 = items.filter((_, i) => i % 2 === 1);
  return (
    <M.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: easeSoft, delay: 0.2 }}>
      <Chip icon={Target} label="Action Items" count={items.length}
        color={dark ? "#34d399" : "#059669"} />
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

/* ─────────────────────────────────────────────────────────
   SKELETON
───────────────────────────────────────────────────────── */
function Skeleton() {
  const dark = useDark();
  return (
    <div className="space-y-4">
      {[1, 2].map(k => (
        <div key={k} className="rounded-3xl p-7"
          style={dark
            ? { border: "1px solid rgba(99,102,241,0.1)", background: "rgba(12,16,28,0.6)" }
            : { border: "1px solid rgba(99,102,241,0.15)", background: "#f8faff" }}>
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

/* ─────────────────────────────────────────────────────────
   EMPTY STATE
───────────────────────────────────────────────────────── */
function EmptyState() {
  const dark = useDark();
  return (
    <M.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.55, ease: easeSoft }}
      className="flex flex-col items-center justify-center gap-7 py-20 px-6 text-center">
      <div className="relative">
        <M.div animate={{ scale: [1, 1.12, 1], opacity: [0.25, 0.45, 0.25] }}
          transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
          className="absolute inset-0 rounded-3xl"
          style={{ background: "radial-gradient(circle, rgba(99,102,241,0.2) 0%, transparent 70%)" }} />
        <div className="relative flex h-24 w-24 items-center justify-center rounded-3xl"
          style={dark
            ? { background: "linear-gradient(145deg, rgba(55,48,163,0.45), rgba(7,9,15,0.85))", border: "1px solid rgba(99,102,241,0.28)" }
            : { background: "linear-gradient(145deg, #eef2ff, #f8faff)", border: "1px solid rgba(99,102,241,0.3)", boxShadow: "0 4px 20px rgba(99,102,241,0.12)" }
          }>
          <Sparkles className={`h-10 w-10 ${dark ? "text-indigo-400" : "text-indigo-500"}`} />
        </div>
      </div>
      <div className="max-w-xs">
        <p className={`text-base font-semibold ${dark ? "text-slate-300" : "text-slate-700"}`}>
          Your meeting insights will appear here
        </p>
        <p className={`mt-2 text-sm leading-relaxed ${dark ? "text-slate-600" : "text-slate-500"}`}>
          Paste a transcript or upload a recording — the AI extracts a summary, decisions, and action items.
        </p>
      </div>
      <div className="flex flex-wrap justify-center gap-2">
        {[
          { label: "🧾 Summary",      color: "rgba(99,102,241,0.12)",  border: "rgba(99,102,241,0.25)"  },
          { label: "📌 Decisions",    color: "rgba(6,182,212,0.1)",    border: "rgba(6,182,212,0.25)"   },
          { label: "✅ Action Items", color: "rgba(16,185,129,0.1)",   border: "rgba(16,185,129,0.25)"  },
        ].map(f => (
          <span key={f.label}
            className={`rounded-full px-3.5 py-1.5 text-xs font-medium ${dark ? "text-slate-500" : "text-slate-600"}`}
            style={{ background: f.color, border: `1px solid ${f.border}` }}>{f.label}</span>
        ))}
      </div>
    </M.div>
  );
}

/* ─────────────────────────────────────────────────────────
   MAIN EXPORT
───────────────────────────────────────────────────────── */
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
