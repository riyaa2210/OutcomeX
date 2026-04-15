import { motion as M, AnimatePresence } from "framer-motion";
import {
  AlertCircle, Calendar, CheckCircle2,
  Clock, FileText, Loader2, Search, Target, User,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

const ease = [0.25, 0.1, 0.25, 1];
const API  = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
const auth = () => ({ Authorization: `Bearer ${localStorage.getItem("access_token")}` });

/* ── helpers ─────────────────────────────────────────────── */
function fmtDate(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }); }
  catch { return iso; }
}
function fmtTime(iso) {
  if (!iso) return "";
  try { return new Date(iso).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" }); }
  catch { return ""; }
}

/* ── avatar helpers ──────────────────────────────────────── */
const AVATAR_PALETTE = [
  { fg: "#a5b4fc", bg: "rgba(79,70,229,0.25)"  },
  { fg: "#67e8f9", bg: "rgba(6,182,212,0.22)"  },
  { fg: "#6ee7b7", bg: "rgba(16,185,129,0.22)" },
  { fg: "#fcd34d", bg: "rgba(245,158,11,0.22)" },
  { fg: "#f9a8d4", bg: "rgba(236,72,153,0.22)" },
  { fg: "#c4b5fd", bg: "rgba(139,92,246,0.22)" },
];
const avStyle = (name = "") => AVATAR_PALETTE[(name.charCodeAt(0) || 65) % AVATAR_PALETTE.length];
const ini = (name = "?") => name.trim().split(/\s+/).map(w => w[0]).join("").toUpperCase().slice(0, 2) || "?";

/* ── tab button ──────────────────────────────────────────── */
function Tab({ label, icon: Icon, active, onClick, color }) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-xs font-bold transition-all duration-200"
      style={active
        ? { background: color + "18", border: `1px solid ${color}33`, color }
        : { background: "transparent", border: "1px solid transparent", color: "#475569" }
      }
    >
      <Icon className="h-3.5 w-3.5" />
      {label}
    </button>
  );
}

/* ── action items tab ────────────────────────────────────── */
function ActionItemsTab({ meetingId }) {
  const [items,   setItems]   = useState([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(false);

  useEffect(() => {
    setLoading(true); setError(false);
    fetch(`${API}/action-items/?meeting_id=${meetingId}`, { headers: auth() })
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(d => { setItems(d); setLoading(false); })
      .catch(() => { setError(true); setLoading(false); });
  }, [meetingId]);

  if (loading) return <Spinner />;

  if (error) {
    return (
      <div className="rounded-2xl px-5 py-4 text-sm text-red-400"
        style={{ background: "rgba(239,68,68,0.06)", border: "1px solid rgba(239,68,68,0.15)" }}>
        Failed to load action items.
      </div>
    );
  }

  if (!items.length) {
    return (
      <div className="rounded-2xl px-5 py-4 text-sm text-slate-500 italic"
        style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}>
        No action items for this meeting.
      </div>
    );
  }

  return (
    <div className="space-y-2.5">
      <p className="text-[10px] font-black uppercase tracking-widest text-emerald-400 mb-3">
        {items.length} Action Item{items.length !== 1 ? "s" : ""}
      </p>
      {items.map((item, i) => {
        const av  = avStyle(item.assigned_to || "?");
        const ini_ = ini(item.assigned_to || "?");
        const isDone = item.status?.toLowerCase() === "completed" || item.status?.toLowerCase() === "done";

        return (
          <M.div
            key={item.id}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.28, ease, delay: i * 0.04 }}
            className="relative overflow-hidden rounded-2xl p-4"
            style={{
              background: "rgba(12,16,28,0.8)",
              border: "1px solid rgba(255,255,255,0.055)",
            }}
          >
            {/* left accent */}
            <div className="absolute left-0 top-0 h-full w-[3px] rounded-l-2xl"
              style={{
                background: isDone
                  ? "linear-gradient(180deg, #34d399, #059669)"
                  : "linear-gradient(180deg, #6366f1, #06b6d4)",
                opacity: 0.6,
              }} />

            <div className="flex items-start gap-3 pl-3">
              {/* avatar */}
              <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center
                              rounded-xl text-[10px] font-extrabold"
                style={{ color: av.fg, background: av.bg }}>
                {ini_}
              </div>

              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-slate-100 leading-snug">
                  {item.description || item.title || "Untitled task"}
                </p>

                <div className="mt-2 flex flex-wrap items-center gap-2">
                  {/* assignee */}
                  <span className="flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium"
                    style={{ background: "rgba(255,255,255,0.05)", color: "#94a3b8" }}>
                    <User className="h-2.5 w-2.5" />
                    {item.assigned_to || "Unassigned"}
                  </span>

                  {/* deadline */}
                  {item.deadline && (
                    <span className="flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium"
                      style={{ background: "rgba(245,158,11,0.1)", color: "#fbbf24" }}>
                      <Clock className="h-2.5 w-2.5" />
                      {item.deadline}
                    </span>
                  )}

                  {/* status */}
                  <span className="ml-auto flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold"
                    style={isDone
                      ? { background: "rgba(52,211,153,0.1)", color: "#34d399" }
                      : { background: "rgba(99,102,241,0.1)", color: "#a5b4fc" }
                    }>
                    {isDone
                      ? <><CheckCircle2 className="h-2.5 w-2.5" /> Done</>
                      : <>{item.status || "Pending"}</>
                    }
                  </span>
                </div>
              </div>
            </div>
          </M.div>
        );
      })}
    </div>
  );
}

/* ── transcript tab ──────────────────────────────────────── */
function TranscriptTab({ meetingId }) {
  const [transcript, setTranscript] = useState(null);
  const [loading,    setLoading]    = useState(true);

  useEffect(() => {
    setLoading(true);
    fetch(`${API}/meeting/${meetingId}`, { headers: auth() })
      .then(r => r.ok ? r.json() : null)
      .then(d => { setTranscript(d?.transcript || null); setLoading(false); })
      .catch(() => setLoading(false));
  }, [meetingId]);

  if (loading) return <Spinner />;

  if (!transcript) {
    return (
      <div className="rounded-2xl px-5 py-4 text-sm text-slate-500 italic"
        style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}>
        No transcript available.
      </div>
    );
  }

  return (
    <pre className="max-h-[420px] overflow-y-auto rounded-2xl px-5 py-4 text-xs
                    leading-relaxed text-slate-400 whitespace-pre-wrap"
      style={{ background: "rgba(0,0,0,0.4)", border: "1px solid rgba(99,102,241,0.12)" }}>
      {transcript}
    </pre>
  );
}

/* ── spinner ─────────────────────────────────────────────── */
function Spinner() {
  return (
    <div className="flex items-center gap-2 py-6 text-slate-600 text-sm">
      <Loader2 className="h-4 w-4 animate-spin" />
      Loading…
    </div>
  );
}

/* ── meeting detail drawer ───────────────────────────────── */
const TABS = [
  { id: "actions",    label: "Action Items", icon: Target,   color: "#34d399" },
  { id: "transcript", label: "Transcript",   icon: FileText, color: "#67e8f9" },
];

function MeetingDrawer({ meeting, initialTab = "actions", onClose }) {
  const [tab, setTab] = useState(initialTab);

  if (!meeting) return null;

  return (
    <AnimatePresence>
      {/* overlay */}
      <M.div
        key="overlay"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
      />

      {/* drawer */}
      <M.div
        key="drawer"
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        exit={{ x: "100%" }}
        transition={{ duration: 0.35, ease }}
        className="fixed right-0 top-0 bottom-0 z-50 w-full max-w-xl flex flex-col"
        style={{
          background: "rgba(9,12,22,0.98)",
          borderLeft: "1px solid rgba(99,102,241,0.2)",
          boxShadow: "-20px 0 60px rgba(0,0,0,0.6)",
        }}
      >
        {/* ── sticky header ── */}
        <div className="flex-shrink-0 px-6 pt-5 pb-4"
          style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
          <div className="flex items-start justify-between mb-4">
            <div>
              <p className="text-[10px] font-black uppercase tracking-widest text-indigo-400">
                Meeting #{meeting.id}
              </p>
              <h2 className="text-base font-bold text-slate-100 mt-0.5 leading-snug">
                {meeting.title || "Untitled Meeting"}
              </h2>
              <div className="mt-2 flex flex-wrap gap-2">
                <span className="flex items-center gap-1 text-[11px] text-slate-500">
                  <Calendar className="h-3 w-3" />
                  {fmtDate(meeting.created_at)}
                </span>
                <span className="flex items-center gap-1 text-[11px] text-slate-500">
                  <Clock className="h-3 w-3" />
                  {fmtTime(meeting.created_at)}
                </span>
              </div>
            </div>
            <button
              onClick={onClose}
              className="rounded-xl p-2 text-slate-500 hover:text-slate-200 transition-colors"
              style={{ background: "rgba(255,255,255,0.04)" }}
            >
              ✕
            </button>
          </div>

          {/* tab bar */}
          <div className="flex gap-1.5">
            {TABS.map(t => (
              <Tab
                key={t.id}
                label={t.label}
                icon={t.icon}
                active={tab === t.id}
                onClick={() => setTab(t.id)}
                color={t.color}
              />
            ))}
          </div>
        </div>

        {/* ── scrollable content ── */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          <AnimatePresence mode="wait">
            <M.div
              key={tab}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.22, ease }}
            >
              {tab === "actions"    && <ActionItemsTab meetingId={meeting.id} />}
              {tab === "transcript" && <TranscriptTab  meetingId={meeting.id} />}
            </M.div>
          </AnimatePresence>
        </div>
      </M.div>
    </AnimatePresence>
  );
}

/* ── main page ───────────────────────────────────────────── */
export default function HistoryPage() {
  const [meetings, setMeetings] = useState([]);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState("");
  const [query,    setQuery]    = useState("");
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    setLoading(true);
    fetch(`${API}/meeting/`, { headers: auth() })
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(data => setMeetings([...data].sort((a, b) => new Date(b.created_at) - new Date(a.created_at))))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(
    () => meetings.filter(m => (m.title || "").toLowerCase().includes(query.toLowerCase())),
    [meetings, query],
  );

  return (
    <>
      <M.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease }}
        className="space-y-6"
      >
        {/* header */}
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-black tracking-tight text-slate-100">Meeting History</h1>
            <p className="mt-0.5 text-sm text-slate-500">
              {loading ? "Loading…" : `${filtered.length} meeting${filtered.length !== 1 ? "s" : ""}`}
            </p>
          </div>
          <div className="relative w-full sm:w-72">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-600" />
            <input
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search meetings…"
              className="w-full rounded-xl py-2.5 pl-10 pr-4 text-sm text-slate-200 placeholder-slate-600 outline-none transition-all"
              style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)" }}
              onFocus={e => { e.currentTarget.style.borderColor = "rgba(99,102,241,0.45)"; e.currentTarget.style.boxShadow = "0 0 0 3px rgba(99,102,241,0.1)"; }}
              onBlur={e  => { e.currentTarget.style.borderColor = "rgba(255,255,255,0.08)"; e.currentTarget.style.boxShadow = "none"; }}
            />
          </div>
        </div>

        {/* loading */}
        {loading && (
          <div className="flex items-center justify-center gap-3 py-20 text-slate-500">
            <Loader2 className="h-5 w-5 animate-spin" />
            <span className="text-sm">Fetching your meetings…</span>
          </div>
        )}

        {/* error */}
        {error && !loading && (
          <div className="flex items-center gap-3 rounded-2xl px-5 py-4 text-sm text-red-400"
            style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.18)" }}>
            <AlertCircle className="h-4 w-4 flex-shrink-0" />
            Failed to load meetings: {error}
          </div>
        )}

        {/* cards */}
        {!loading && !error && (
          <div className="space-y-3">
            <AnimatePresence>
              {filtered.map((meeting, i) => (
                <M.div
                  key={meeting.id}
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{ duration: 0.32, ease, delay: i * 0.04 }}
                  whileHover={{ y: -2, boxShadow: "0 12px 32px rgba(0,0,0,0.4)" }}
                  className="group relative overflow-hidden rounded-2xl p-5 cursor-default transition-all duration-200"
                  style={{
                    background: "rgba(12,16,28,0.75)",
                    border: "1px solid rgba(255,255,255,0.055)",
                    boxShadow: "0 2px 12px rgba(0,0,0,0.3)",
                  }}
                >
                  <div className="absolute left-0 top-0 h-full w-[3px] rounded-l-2xl"
                    style={{ background: "linear-gradient(180deg, #6366f1, #06b6d4)", opacity: 0.5 }} />

                  <div className="flex items-center gap-4 pl-3">
                    <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl"
                      style={{ background: "rgba(99,102,241,0.12)", border: "1px solid rgba(99,102,241,0.2)" }}>
                      <FileText className="h-4 w-4 text-indigo-400" />
                    </div>

                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="font-bold text-slate-100 text-sm truncate">
                          {meeting.title || "Untitled Meeting"}
                        </p>
                        <span className="text-[10px] font-semibold text-slate-700">#{meeting.id}</span>
                      </div>
                      <div className="mt-1.5 flex flex-wrap items-center gap-3">
                        <span className="flex items-center gap-1 text-[11px] text-slate-500">
                          <Calendar className="h-3 w-3" />{fmtDate(meeting.created_at)}
                        </span>
                        <span className="flex items-center gap-1 text-[11px] text-slate-500">
                          <Clock className="h-3 w-3" />{fmtTime(meeting.created_at)}
                        </span>
                      </div>
                    </div>

                    {/* quick-access buttons */}
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <M.button
                        whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}
                        onClick={() => setSelected({ ...meeting, _tab: "actions" })}
                        className="flex items-center gap-1 rounded-xl px-2.5 py-1.5 text-[11px] font-bold"
                        style={{ background: "rgba(52,211,153,0.1)", border: "1px solid rgba(52,211,153,0.2)", color: "#34d399" }}
                      >
                        <Target className="h-3 w-3" />
                        Actions
                      </M.button>
                      <M.button
                        whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}
                        onClick={() => setSelected({ ...meeting, _tab: "transcript" })}
                        className="flex items-center gap-1 rounded-xl px-2.5 py-1.5 text-[11px] font-bold"
                        style={{ background: "rgba(67,56,202,0.15)", border: "1px solid rgba(99,102,241,0.25)", color: "#818cf8" }}
                      >
                        <FileText className="h-3 w-3" />
                        Transcript
                      </M.button>
                    </div>
                  </div>
                </M.div>
              ))}
            </AnimatePresence>

            {filtered.length === 0 && meetings.length > 0 && (
              <M.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                className="flex flex-col items-center gap-3 py-16 text-center">
                <Search className="h-8 w-8 text-slate-700" />
                <p className="font-semibold text-slate-500">No meetings match "{query}"</p>
              </M.div>
            )}

            {meetings.length === 0 && (
              <M.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                className="flex flex-col items-center gap-4 py-20 text-center">
                <div className="flex h-16 w-16 items-center justify-center rounded-2xl"
                  style={{ background: "rgba(99,102,241,0.1)", border: "1px solid rgba(99,102,241,0.2)" }}>
                  <FileText className="h-7 w-7 text-indigo-400" />
                </div>
                <div>
                  <p className="font-semibold text-slate-400">No meetings yet</p>
                  <p className="mt-1 text-sm text-slate-600">Upload a recording on the Dashboard to get started</p>
                </div>
              </M.div>
            )}
          </div>
        )}
      </M.div>

      {/* drawer */}
      {selected && (
        <MeetingDrawer
          meeting={selected}
          initialTab={selected._tab || "actions"}
          onClose={() => setSelected(null)}
        />
      )}
    </>
  );
}
