import { motion as M, AnimatePresence } from "framer-motion";
import {
  BarChart2, Calendar, CheckCircle2, ChevronDown, ChevronUp,
  Clock, FileText, Lightbulb, Search, Sparkles, Target,
} from "lucide-react";
import { useMemo, useState, useEffect } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Area, AreaChart,
} from "recharts";
import { fadeInProps, subtle } from "../lib/motionPresets";
import useAuth from "../context/useAuth";

const API = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
const authH = () => ({ Authorization: `Bearer ${localStorage.getItem("access_token")}` });

/* ── helpers ─────────────────────────────────────────────── */
function fmtDate(s) {
  try {
    const d = new Date(s);
    return d.toLocaleDateString("en-US", { month: "short", day: "2-digit", year: "numeric" });
  } catch { return "—"; }
}
function fmtTime(s) {
  try {
    return new Date(s).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
  } catch { return ""; }
}
function parseSummary(raw) {
  if (!raw) return null;
  try {
    const p = JSON.parse(raw);
    if (p && typeof p === "object") return p;
  } catch { /* plain text */ }
  return { summary: raw, decisions: [], action_items: [] };
}

/* ── avatar ──────────────────────────────────────────────── */
const COLORS = ["#6366f1","#0891b2","#059669","#d97706","#be185d","#7c3aed"];
const avColor = n => COLORS[(n?.charCodeAt(0) || 65) % COLORS.length];
const ini = n => (n || "?").trim().split(/\s+/).map(w => w[0]).join("").toUpperCase().slice(0,2);

/* ── expandable meeting card ─────────────────────────────── */
function MeetingCard({ meeting, index }) {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);

  async function loadDetail() {
    if (detail) { setOpen(v => !v); return; }
    setLoading(true);
    try {
      // Fetch action items
      const [aiRes, sumRes] = await Promise.all([
        fetch(`${API}/action-items/?meeting_id=${meeting.id}`, { headers: authH() }),
        fetch(`${API}/meeting/${meeting.id}/summary`, { headers: authH() }).catch(() => null),
      ]);
      const actionItems = aiRes.ok ? await aiRes.json() : [];
      let summaryData = null;
      if (sumRes?.ok) {
        const sd = await sumRes.json();
        summaryData = parseSummary(sd.summary);
      }
      setDetail({ actionItems, summaryData });
      setOpen(true);
    } catch (e) {
      console.error(e);
      setDetail({ actionItems: [], summaryData: null });
      setOpen(true);
    } finally {
      setLoading(false);
    }
  }

  const aiCount = detail?.actionItems?.length ?? 0;
  const hasSummary = !!detail?.summaryData?.summary;

  return (
    <M.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: index * 0.06 }}
      className="group overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm
                 transition-all duration-300 hover:shadow-lg hover:shadow-indigo-100/60
                 dark:border-slate-700/60 dark:bg-slate-900/70 dark:hover:shadow-indigo-900/20"
    >
      {/* ── card header ── */}
      <div className="p-5">
        {/* top row */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            {/* icon */}
            <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl
                            bg-gradient-to-br from-indigo-500 to-violet-600 shadow-md shadow-indigo-200
                            dark:shadow-indigo-900/40">
              <FileText className="h-5 w-5 text-white" />
            </div>
            <div className="min-w-0">
              <h3 className="truncate text-base font-bold text-slate-900 dark:text-slate-100">
                {meeting.title || "Untitled Meeting"}
              </h3>
              <div className="mt-0.5 flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                <Calendar className="h-3 w-3" />
                {fmtDate(meeting.created_at)}
                <span className="text-slate-300 dark:text-slate-600">·</span>
                <Clock className="h-3 w-3" />
                {fmtTime(meeting.created_at)}
              </div>
            </div>
          </div>

          {/* expand button */}
          <button
            onClick={loadDetail}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-xl bg-indigo-50 px-3 py-1.5 text-xs
                       font-semibold text-indigo-600 transition-colors hover:bg-indigo-100
                       disabled:opacity-50 dark:bg-indigo-950/40 dark:text-indigo-400
                       dark:hover:bg-indigo-950/60 flex-shrink-0"
          >
            {loading ? (
              <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-indigo-300 border-t-indigo-600" />
            ) : open ? (
              <><ChevronUp className="h-3.5 w-3.5" /> Hide</>
            ) : (
              <><ChevronDown className="h-3.5 w-3.5" /> View Details</>
            )}
          </button>
        </div>

        {/* quick stats row — shown before expanding */}
        {!open && (
          <div className="mt-4 flex gap-2">
            <div className="flex items-center gap-1.5 rounded-lg bg-slate-50 px-3 py-1.5
                            dark:bg-slate-800/60">
              <Target className="h-3.5 w-3.5 text-emerald-500" />
              <span className="text-xs font-medium text-slate-600 dark:text-slate-400">
                {detail ? `${aiCount} action item${aiCount !== 1 ? "s" : ""}` : "Click to load"}
              </span>
            </div>
            {detail?.summaryData?.decisions?.length > 0 && (
              <div className="flex items-center gap-1.5 rounded-lg bg-slate-50 px-3 py-1.5
                              dark:bg-slate-800/60">
                <Lightbulb className="h-3.5 w-3.5 text-amber-500" />
                <span className="text-xs font-medium text-slate-600 dark:text-slate-400">
                  {detail.summaryData.decisions.length} decision{detail.summaryData.decisions.length !== 1 ? "s" : ""}
                </span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── expanded detail ── */}
      <AnimatePresence>
        {open && detail && (
          <M.div
            key="detail"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3 }}
            className="overflow-hidden"
          >
            <div className="border-t border-slate-100 dark:border-slate-700/50 px-5 pb-5 pt-4 space-y-5">

              {/* ── Summary ── */}
              {hasSummary && (
                <div className="rounded-xl bg-gradient-to-br from-indigo-50 to-violet-50 p-4
                                dark:from-indigo-950/30 dark:to-violet-950/30
                                border border-indigo-100 dark:border-indigo-800/30">
                  <div className="flex items-center gap-2 mb-2">
                    <Sparkles className="h-3.5 w-3.5 text-indigo-500" />
                    <span className="text-xs font-bold uppercase tracking-widest text-indigo-500">
                      AI Summary
                    </span>
                  </div>
                  <p className="text-sm leading-relaxed text-slate-700 dark:text-slate-300">
                    {detail.summaryData.summary}
                  </p>
                </div>
              )}

              {/* ── Decisions ── */}
              {detail.summaryData?.decisions?.length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <Lightbulb className="h-3.5 w-3.5 text-amber-500" />
                    <span className="text-xs font-bold uppercase tracking-widest text-amber-600 dark:text-amber-400">
                      Decisions
                    </span>
                  </div>
                  <ul className="space-y-1.5">
                    {detail.summaryData.decisions.map((d, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-slate-700 dark:text-slate-300">
                        <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-amber-400" />
                        {d}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* ── Action Items ── */}
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Target className="h-3.5 w-3.5 text-emerald-500" />
                    <span className="text-xs font-bold uppercase tracking-widest text-emerald-600 dark:text-emerald-400">
                      Action Items
                    </span>
                  </div>
                  <span className="flex h-5 w-5 items-center justify-center rounded-full
                                   bg-emerald-100 text-xs font-bold text-emerald-700
                                   dark:bg-emerald-900/40 dark:text-emerald-400">
                    {aiCount}
                  </span>
                </div>

                {aiCount === 0 ? (
                  <p className="text-sm italic text-slate-400 dark:text-slate-600">
                    No action items for this meeting.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {detail.actionItems.map((item, i) => {
                      const isDone = item.status?.toLowerCase() === "completed" || item.status?.toLowerCase() === "done";
                      const color  = avColor(item.assigned_to || "?");
                      return (
                        <div key={item.id || i}
                          className="flex items-start gap-3 rounded-xl border border-slate-100 bg-slate-50/80
                                     p-3 dark:border-slate-700/40 dark:bg-slate-800/40">
                          {/* avatar */}
                          <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center
                                          rounded-lg text-[10px] font-bold text-white"
                            style={{ background: color }}>
                            {ini(item.assigned_to)}
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className={`text-sm font-medium leading-snug
                              ${isDone ? "line-through text-slate-400" : "text-slate-800 dark:text-slate-200"}`}>
                              {item.description || item.title || "Untitled task"}
                            </p>
                            <div className="mt-1 flex flex-wrap items-center gap-2">
                              <span className="text-xs text-slate-500 dark:text-slate-400">
                                {item.assigned_to || "Unassigned"}
                              </span>
                              {item.deadline && (
                                <span className="flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400">
                                  <Clock className="h-3 w-3" />{item.deadline}
                                </span>
                              )}
                            </div>
                          </div>
                          {/* status badge */}
                          <span className={`flex-shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold
                            ${isDone
                              ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"
                              : "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400"
                            }`}>
                            {isDone ? "Done" : item.status || "Pending"}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          </M.div>
        )}
      </AnimatePresence>
    </M.div>
  );
}

/* ── main page ───────────────────────────────────────────── */
export default function HistoryPage() {
  const { user } = useAuth();
  const [query,     setQuery]     = useState("");
  const [meetings,  setMeetings]  = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [timeRange, setTimeRange] = useState(7);

  useEffect(() => {
    if (!user?.id) { setIsLoading(false); return; }
    (async () => {
      try {
        const res = await fetch(`${API}/meeting/`, { headers: authH() });
        const data = res.ok ? await res.json() : [];
        setMeetings(
          (Array.isArray(data) ? data : [])
            .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
        );
      } catch { setMeetings([]); }
      finally { setIsLoading(false); }
    })();
  }, [user?.id]);

  const filtered = useMemo(
    () => meetings.filter(m => (m.title || "").toLowerCase().includes(query.toLowerCase())),
    [query, meetings],
  );

  // Analytics chart data
  const chartData = useMemo(() => {
    const today = new Date();
    const map = {};
    for (let i = timeRange - 1; i >= 0; i--) {
      const d = new Date(today);
      d.setDate(today.getDate() - i);
      map[d.toISOString().split("T")[0]] = 0;
    }
    meetings.forEach(m => {
      const key = m.created_at?.split("T")[0];
      if (key && map.hasOwnProperty(key)) map[key]++;
    });
    return Object.entries(map).map(([date, count]) => ({
      date: new Date(date + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" }),
      meetings: count,
    }));
  }, [meetings, timeRange]);

  const totalMeetings = meetings.length;

  return (
    <M.div className="space-y-8 px-1 py-2" {...fadeInProps}>

      {/* ── Header ── */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <M.h1
            className="text-3xl font-black tracking-tight text-slate-900 dark:text-slate-100"
            initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={subtle}
          >
            Meeting History
          </M.h1>
          <p className="mt-1 text-slate-500 dark:text-slate-400">
            {isLoading ? "Loading…" : `${totalMeetings} meeting${totalMeetings !== 1 ? "s" : ""} recorded`}
          </p>
        </div>

        {/* stat chips */}
        {!isLoading && meetings.length > 0 && (
          <div className="flex gap-3 flex-wrap">
            {[
              { label: "Total Meetings", val: totalMeetings, color: "indigo" },
            ].map(s => (
              <div key={s.label}
                className="rounded-2xl border border-indigo-100 bg-indigo-50 px-4 py-2.5 text-center
                           dark:border-indigo-900/40 dark:bg-indigo-950/30">
                <p className="text-2xl font-black text-indigo-600 dark:text-indigo-400">{s.val}</p>
                <p className="text-xs font-medium text-indigo-500 dark:text-indigo-500">{s.label}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Analytics chart ── */}
      {!isLoading && meetings.length > 0 && (
        <M.div
          initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}
          transition={{ ...subtle, delay: 0.06 }}
          className="rounded-2xl border border-slate-200/90 bg-white p-6 shadow-sm
                     dark:border-slate-700/60 dark:bg-slate-900/60"
        >
          <div className="mb-5 flex items-center justify-between gap-4 flex-wrap">
            <div className="flex items-center gap-2">
              <BarChart2 className="h-5 w-5 text-indigo-500" />
              <div>
                <h2 className="text-base font-bold text-slate-900 dark:text-slate-100">
                  Meetings Over Time
                </h2>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Meetings recorded per day
                </p>
              </div>
            </div>
            <div className="flex gap-2">
              {[7, 30].map(d => (
                <button key={d} onClick={() => setTimeRange(d)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
                    timeRange === d
                      ? "bg-indigo-600 text-white shadow-sm shadow-indigo-600/25"
                      : "bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300"
                  }`}>
                  {d} Days
                </button>
              ))}
            </div>
          </div>

          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 4, right: 16, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="grad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#6366f1" stopOpacity={0.18} />
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0}    />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                <XAxis dataKey="date" stroke="#94a3b8" style={{ fontSize: 11 }} tickLine={false} />
                <YAxis stroke="#94a3b8" style={{ fontSize: 11 }} tickLine={false} axisLine={false} allowDecimals={false} />
                <Tooltip
                  contentStyle={{
                    background: "#1e293b", border: "1px solid #334155",
                    borderRadius: 10, padding: "8px 12px", fontSize: 12,
                  }}
                  labelStyle={{ color: "#f1f5f9" }}
                  formatter={v => [`${v} meeting${v !== 1 ? "s" : ""}`, ""]}
                />
                <Area type="monotone" dataKey="meetings" stroke="#6366f1" strokeWidth={2.5}
                  fill="url(#grad)" dot={{ fill: "#6366f1", r: 3 }} activeDot={{ r: 5 }} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </M.div>
      )}

      {/* ── Search ── */}
      <div className="relative">
        <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search meetings…"
          className="w-full rounded-xl border border-slate-200 bg-white py-2.5 pl-10 pr-4
                     text-sm text-slate-900 shadow-sm outline-none transition-all
                     focus:border-indigo-400 focus:ring-2 focus:ring-indigo-400/15
                     dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-100"
        />
      </div>

      {/* ── Loading ── */}
      {isLoading && (
        <div className="flex h-64 items-center justify-center rounded-2xl border border-slate-200
                        bg-white dark:border-slate-700 dark:bg-slate-900/60">
          <div className="text-center">
            <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-4
                            border-indigo-200 border-t-indigo-600" />
            <p className="text-sm text-slate-500">Loading meetings…</p>
          </div>
        </div>
      )}

      {/* ── Empty ── */}
      {!isLoading && meetings.length === 0 && (
        <div className="flex h-64 flex-col items-center justify-center gap-3 rounded-2xl
                        border border-dashed border-slate-300 bg-slate-50/50
                        dark:border-slate-700 dark:bg-slate-900/30">
          <FileText className="h-10 w-10 text-slate-300 dark:text-slate-600" />
          <p className="font-semibold text-slate-600 dark:text-slate-400">No meetings yet</p>
          <p className="text-sm text-slate-400">Upload an audio file on the Dashboard to get started</p>
        </div>
      )}

      {/* ── No search results ── */}
      {!isLoading && meetings.length > 0 && filtered.length === 0 && (
        <div className="flex h-40 items-center justify-center rounded-2xl border border-dashed
                        border-slate-300 bg-slate-50/50 dark:border-slate-700 dark:bg-slate-900/30">
          <p className="text-slate-500">No meetings match "{query}"</p>
        </div>
      )}

      {/* ── Meeting cards ── */}
      {!isLoading && filtered.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-1 lg:grid-cols-2">
          {filtered.map((meeting, i) => (
            <MeetingCard key={meeting.id || i} meeting={meeting} index={i} />
          ))}
        </div>
      )}
    </M.div>
  );
}
