import { useCallback, useEffect, useRef, useState } from "react";
import {
  AreaChart, Area, BarChart, Bar, RadarChart, Radar,
  PolarGrid, PolarAngleAxis, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import {
  FlaskConical, ThumbsUp, ThumbsDown, AlertTriangle,
  CheckCircle2, RefreshCw, Download, ChevronDown,
  Plus, Trash2, Play,
} from "lucide-react";
import useAuth from "../context/useAuth";

const API = import.meta.env.VITE_API_URL || "https://meeting-outcome-tracker-backend.onrender.com";

// ── Colour constants ──────────────────────────────────────────────────────────
const INDIGO  = "#6366f1";
const CYAN    = "#06b6d4";
const EMERALD = "#10b981";
const ROSE    = "#f43f5e";
const AMBER   = "#f59e0b";

// ── Score colour helper ───────────────────────────────────────────────────────
function scoreColor(v, thresholds = [0.7, 0.5]) {
  if (v >= thresholds[0]) return "text-emerald-600 dark:text-emerald-400";
  if (v >= thresholds[1]) return "text-amber-600 dark:text-amber-400";
  return "text-rose-600 dark:text-rose-400";
}

function hallucinationColor(v) {
  if (v < 0.1) return "text-emerald-600 dark:text-emerald-400";
  if (v < 0.3) return "text-amber-600 dark:text-amber-400";
  return "text-rose-600 dark:text-rose-400";
}

const fmt = (n, dec = 3) => (n == null ? "—" : Number(n).toFixed(dec));
const pct = (n) => (n == null ? "—" : `${(Number(n) * 100).toFixed(1)}%`);

// ── Shared UI primitives ──────────────────────────────────────────────────────
function Skeleton({ className = "h-4 w-full" }) {
  return <div className={`animate-pulse rounded-lg bg-slate-200 dark:bg-slate-700 ${className}`} />;
}

function Card({ children, className = "" }) {
  return (
    <div className={`rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900 ${className}`}>
      {children}
    </div>
  );
}

function SectionTitle({ children }) {
  return (
    <h2 className="mb-3 text-xs font-semibold uppercase tracking-widest text-slate-500 dark:text-slate-400">
      {children}
    </h2>
  );
}

function TabBtn({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-xl px-4 py-2 text-sm font-medium transition-colors ${
        active
          ? "bg-indigo-600 text-white"
          : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
      }`}
    >
      {children}
    </button>
  );
}

function StatCard({ icon: Icon, label, value, color = INDIGO, loading }) {
  return (
    <Card>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">{label}</p>
          {loading
            ? <Skeleton className="mt-2 h-8 w-24" />
            : <p className="mt-1 text-2xl font-bold text-slate-800 dark:text-white">{value}</p>
          }
        </div>
        <span className="rounded-xl p-2" style={{ background: color + "22" }}>
          <Icon className="h-5 w-5" style={{ color }} />
        </span>
      </div>
    </Card>
  );
}

function ProviderBadge({ provider }) {
  const colors = { gemini: INDIGO, openai: EMERALD, local: AMBER };
  const bg = colors[provider] || "#94a3b8";
  return (
    <span
      className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold text-white"
      style={{ background: bg }}
    >
      {provider ?? "—"}
    </span>
  );
}

function PriorityBadge({ priority }) {
  const cls =
    priority === "high"   ? "bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300" :
    priority === "medium" ? "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300" :
                            "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300";
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${cls}`}>
      {priority}
    </span>
  );
}

// ── Tab 1: Dashboard ──────────────────────────────────────────────────────────
function DashboardTab({ token }) {
  const [hours, setHours] = useState(24);
  const [data, setData]   = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API}/eval/dashboard?hours=${hours}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setData(await res.json());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [hours, token]);

  useEffect(() => { load(); }, [load]);

  const acc  = data?.model_accuracy  || {};
  const llm  = data?.llm_performance || {};
  const fb   = data?.human_feedback  || {};
  const trend = data?.score_trend    || [];

  return (
    <div className="space-y-8">
      {/* Hours filter */}
      <div className="flex items-center gap-3">
        <span className="text-sm text-slate-500 dark:text-slate-400">Time window:</span>
        <div className="relative">
          <select
            value={hours}
            onChange={e => setHours(Number(e.target.value))}
            className="appearance-none rounded-xl border border-slate-200 bg-white py-1.5 pl-3 pr-8 text-sm text-slate-700 shadow-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
          >
            {[1, 6, 12, 24, 48, 168].map(h => (
              <option key={h} value={h}>{h === 168 ? "7 days" : `${h}h`}</option>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute right-2 top-2 h-4 w-4 text-slate-400" />
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700 dark:border-rose-800 dark:bg-rose-900/20 dark:text-rose-300">
          {error}
        </div>
      )}

      {/* Model Accuracy */}
      <section>
        <SectionTitle>Model Accuracy</SectionTitle>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard icon={CheckCircle2} label="Avg Overall Score"    value={fmt(acc.avg_overall_score)}    color={INDIGO}  loading={loading} />
          <StatCard icon={CheckCircle2} label="Avg Action Precision" value={fmt(acc.avg_action_precision)} color={CYAN}    loading={loading} />
          <StatCard icon={CheckCircle2} label="Avg F1 Score"         value={fmt(acc.avg_f1_score)}         color={EMERALD} loading={loading} />
          <StatCard icon={AlertTriangle} label="High Hallucination"  value={acc.high_hallucination_count ?? "—"} color={ROSE} loading={loading} />
        </div>
      </section>

      {/* LLM Performance */}
      <section>
        <SectionTitle>LLM Performance</SectionTitle>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard icon={FlaskConical} label="Total Calls"     value={llm.total_calls ?? "—"}                    color={INDIGO}  loading={loading} />
          <StatCard icon={FlaskConical} label="Avg Latency ms"  value={llm.avg_latency_ms != null ? `${Math.round(llm.avg_latency_ms)} ms` : "—"} color={CYAN}    loading={loading} />
          <StatCard icon={AlertTriangle} label="Failure Rate"   value={pct(llm.failure_rate)}                     color={ROSE}    loading={loading} />
          <StatCard icon={CheckCircle2} label="Cache Hit Rate"  value={pct(llm.cache_hit_rate)}                   color={EMERALD} loading={loading} />
        </div>
      </section>

      {/* Human Feedback */}
      <section>
        <SectionTitle>Human Feedback</SectionTitle>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <StatCard icon={ThumbsUp}   label="Thumbs Up"         value={fb.thumbs_up ?? "—"}                                    color={EMERALD} loading={loading} />
          <StatCard icon={ThumbsDown} label="Thumbs Down"       value={fb.thumbs_down ?? "—"}                                  color={ROSE}    loading={loading} />
          <StatCard icon={CheckCircle2} label="Satisfaction Rate" value={fb.satisfaction_rate != null ? `${(fb.satisfaction_rate * 100).toFixed(1)}%` : "—"} color={INDIGO} loading={loading} />
        </div>
      </section>

      {/* Score Trend */}
      <section>
        <Card>
          <p className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-200">Score Trend</p>
          {loading
            ? <Skeleton className="h-56 w-full" />
            : trend.length === 0
            ? <p className="py-12 text-center text-sm text-slate-400">No trend data available</p>
            : (
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={trend} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="gradScore" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor={INDIGO} stopOpacity={0.25} />
                      <stop offset="95%" stopColor={INDIGO} stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="gradHall" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor={ROSE} stopOpacity={0.25} />
                      <stop offset="95%" stopColor={ROSE} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" strokeOpacity={0.5} />
                  <XAxis dataKey="hour" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} domain={[0, 1]} />
                  <Tooltip />
                  <Legend />
                  <Area type="monotone" dataKey="avg_score"        name="Avg Score"       stroke={INDIGO} fill="url(#gradScore)" strokeWidth={2} dot={false} />
                  <Area type="monotone" dataKey="avg_hallucination" name="Avg Hallucination" stroke={ROSE}  fill="url(#gradHall)"  strokeWidth={2} dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            )
          }
        </Card>
      </section>
    </div>
  );
}

// ── Tab 2: Results ────────────────────────────────────────────────────────────
function ResultsTab({ token }) {
  const [days, setDays]       = useState(30);
  const [page, setPage]       = useState(1);
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);
  const [expanded, setExpanded] = useState(null);
  const [running, setRunning]   = useState({});

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API}/eval/results?days=${days}&page=${page}&page_size=20`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setData(await res.json());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [days, page, token]);

  useEffect(() => { load(); }, [load]);

  const runEval = async (meetingId) => {
    setRunning(r => ({ ...r, [meetingId]: true }));
    try {
      const res = await fetch(`${API}/eval/run/${meetingId}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await load();
    } catch (e) {
      alert(`Eval failed: ${e.message}`);
    } finally {
      setRunning(r => ({ ...r, [meetingId]: false }));
    }
  };

  const results = data?.results || data || [];
  const total   = data?.total   || results.length;

  return (
    <div className="space-y-6">
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm text-slate-500 dark:text-slate-400">Days:</span>
        <div className="relative">
          <select
            value={days}
            onChange={e => { setDays(Number(e.target.value)); setPage(1); }}
            className="appearance-none rounded-xl border border-slate-200 bg-white py-1.5 pl-3 pr-8 text-sm text-slate-700 shadow-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
          >
            {[7, 14, 30, 60, 90].map(d => <option key={d} value={d}>{d} days</option>)}
          </select>
          <ChevronDown className="pointer-events-none absolute right-2 top-2 h-4 w-4 text-slate-400" />
        </div>
        <span className="ml-auto text-xs text-slate-400">{total} results</span>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700 dark:border-rose-800 dark:bg-rose-900/20 dark:text-rose-300">
          {error}
        </div>
      )}

      <Card className="overflow-hidden p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/60">
                {["Meeting ID", "Overall", "Summary", "Action Prec.", "Hallucination", "F1", "Flagged", "Provider", "Created"].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">{h}</th>
                ))}
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {loading
                ? Array.from({ length: 6 }).map((_, i) => (
                  <tr key={i} className="border-b border-slate-100 dark:border-slate-800">
                    {Array.from({ length: 10 }).map((__, j) => (
                      <td key={j} className="px-4 py-3"><Skeleton className="h-4 w-full" /></td>
                    ))}
                  </tr>
                ))
                : results.length === 0
                ? (
                  <tr>
                    <td colSpan={10} className="py-12 text-center text-sm text-slate-400">No evaluation results found</td>
                  </tr>
                )
                : results.map(r => {
                  const isOpen = expanded === r.id;
                  const overall = Number(r.overall_score);
                  const hall    = Number(r.hallucination_score);
                  return (
                    <>
                      <tr
                        key={r.id}
                        className="cursor-pointer border-b border-slate-100 transition-colors hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/40"
                        onClick={() => setExpanded(isOpen ? null : r.id)}
                      >
                        <td className="px-4 py-3 font-mono text-xs text-slate-600 dark:text-slate-300">{r.meeting_id ?? r.id}</td>
                        <td className={`px-4 py-3 font-semibold ${scoreColor(overall)}`}>{fmt(overall)}</td>
                        <td className={`px-4 py-3 ${scoreColor(Number(r.summary_quality))}`}>{fmt(r.summary_quality)}</td>
                        <td className={`px-4 py-3 ${scoreColor(Number(r.action_precision))}`}>{fmt(r.action_precision)}</td>
                        <td className={`px-4 py-3 font-semibold ${hallucinationColor(hall)}`}>{fmt(hall)}</td>
                        <td className={`px-4 py-3 ${scoreColor(Number(r.f1_score))}`}>{fmt(r.f1_score)}</td>
                        <td className="px-4 py-3">
                          {r.flagged_terms_count > 0 && (
                            <span className="rounded-full bg-rose-100 px-2 py-0.5 text-xs font-semibold text-rose-700 dark:bg-rose-900/40 dark:text-rose-300">
                              {r.flagged_terms_count}
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3"><ProviderBadge provider={r.provider} /></td>
                        <td className="px-4 py-3 text-xs text-slate-400">{r.created_at ? new Date(r.created_at).toLocaleDateString() : "—"}</td>
                        <td className="px-4 py-3">
                          <button
                            onClick={e => { e.stopPropagation(); runEval(r.meeting_id ?? r.id); }}
                            disabled={running[r.meeting_id ?? r.id]}
                            className="flex items-center gap-1 rounded-lg bg-indigo-50 px-2 py-1 text-xs font-medium text-indigo-600 hover:bg-indigo-100 disabled:opacity-50 dark:bg-indigo-900/30 dark:text-indigo-300 dark:hover:bg-indigo-900/50"
                          >
                            <Play className="h-3 w-3" />
                            {running[r.meeting_id ?? r.id] ? "Running…" : "Run Eval"}
                          </button>
                        </td>
                      </tr>
                      {isOpen && (
                        <tr key={`${r.id}-detail`} className="bg-slate-50 dark:bg-slate-800/30">
                          <td colSpan={10} className="px-6 py-4">
                            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                              <div>
                                <p className="mb-1 text-xs font-semibold uppercase text-slate-500">Unsupported Claims</p>
                                {r.unsupported_claims?.length
                                  ? <ul className="space-y-1">{r.unsupported_claims.map((c, i) => <li key={i} className="text-xs text-slate-600 dark:text-slate-300">• {c}</li>)}</ul>
                                  : <p className="text-xs text-slate-400">None</p>
                                }
                              </div>
                              <div>
                                <p className="mb-1 text-xs font-semibold uppercase text-slate-500">Fabricated Deadlines</p>
                                {r.fabricated_deadlines?.length
                                  ? <ul className="space-y-1">{r.fabricated_deadlines.map((c, i) => <li key={i} className="text-xs text-slate-600 dark:text-slate-300">• {c}</li>)}</ul>
                                  : <p className="text-xs text-slate-400">None</p>
                                }
                              </div>
                              <div>
                                <p className="mb-1 text-xs font-semibold uppercase text-slate-500">Incorrect Assignees</p>
                                {r.incorrect_assignees?.length
                                  ? <ul className="space-y-1">{r.incorrect_assignees.map((c, i) => <li key={i} className="text-xs text-slate-600 dark:text-slate-300">• {c}</li>)}</ul>
                                  : <p className="text-xs text-slate-400">None</p>
                                }
                              </div>
                              <div>
                                <p className="mb-1 text-xs font-semibold uppercase text-slate-500">Score Breakdown</p>
                                <div className="space-y-0.5 text-xs text-slate-600 dark:text-slate-300">
                                  <p>Overall: <span className={`font-semibold ${scoreColor(overall)}`}>{fmt(overall)}</span></p>
                                  <p>Summary: <span className={`font-semibold ${scoreColor(Number(r.summary_quality))}`}>{fmt(r.summary_quality)}</span></p>
                                  <p>Action Prec.: <span className={`font-semibold ${scoreColor(Number(r.action_precision))}`}>{fmt(r.action_precision)}</span></p>
                                  <p>Hallucination: <span className={`font-semibold ${hallucinationColor(hall)}`}>{fmt(hall)}</span></p>
                                  <p>F1: <span className={`font-semibold ${scoreColor(Number(r.f1_score))}`}>{fmt(r.f1_score)}</span></p>
                                </div>
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  );
                })
              }
            </tbody>
          </table>
        </div>
      </Card>

      {/* Pagination */}
      {!loading && total > 20 && (
        <div className="flex items-center justify-center gap-2">
          <button
            disabled={page === 1}
            onClick={() => setPage(p => p - 1)}
            className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-40 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            Previous
          </button>
          <span className="text-sm text-slate-500">Page {page}</span>
          <button
            disabled={results.length < 20}
            onClick={() => setPage(p => p + 1)}
            className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-40 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}

// ── Tab 3: Feedback ───────────────────────────────────────────────────────────
function FeedbackTab({ token }) {
  const [form, setForm] = useState({
    meeting_id: "",
    signal: "thumbs_up",
    comment: "",
    corrected_summary: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [submitMsg, setSubmitMsg]   = useState(null);
  const [recent, setRecent]         = useState([]);
  const [loadingRecent, setLoadingRecent] = useState(true);

  const loadRecent = useCallback(async () => {
    setLoadingRecent(true);
    try {
      const res = await fetch(`${API}/eval/results?days=7&page=1&page_size=10`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const d = await res.json();
      setRecent(d?.results || d || []);
    } catch {
      setRecent([]);
    } finally {
      setLoadingRecent(false);
    }
  }, [token]);

  useEffect(() => { loadRecent(); }, [loadRecent]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setSubmitMsg(null);
    try {
      const body = { ...form };
      if (form.signal !== "edited") delete body.corrected_summary;
      const res = await fetch(`${API}/eval/feedback`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setSubmitMsg({ type: "success", text: "Feedback submitted successfully." });
      setForm({ meeting_id: "", signal: "thumbs_up", comment: "", corrected_summary: "" });
      loadRecent();
    } catch (e) {
      setSubmitMsg({ type: "error", text: `Submission failed: ${e.message}` });
    } finally {
      setSubmitting(false);
    }
  };

  const SIGNALS = [
    { value: "thumbs_up",   label: "👍 Thumbs Up" },
    { value: "thumbs_down", label: "👎 Thumbs Down" },
    { value: "edited",      label: "✏️ Edited" },
    { value: "flagged",     label: "🚩 Flagged" },
  ];

  return (
    <div className="space-y-8">
      {/* Submission form */}
      <Card>
        <p className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-200">Submit Feedback</p>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-400">Meeting ID</label>
            <input
              required
              value={form.meeting_id}
              onChange={e => setForm(f => ({ ...f, meeting_id: e.target.value }))}
              placeholder="e.g. meeting-abc123"
              className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
          </div>

          <div>
            <label className="mb-2 block text-xs font-medium text-slate-600 dark:text-slate-400">Signal</label>
            <div className="flex flex-wrap gap-3">
              {SIGNALS.map(s => (
                <label key={s.value} className="flex cursor-pointer items-center gap-2">
                  <input
                    type="radio"
                    name="signal"
                    value={s.value}
                    checked={form.signal === s.value}
                    onChange={() => setForm(f => ({ ...f, signal: s.value }))}
                    className="accent-indigo-600"
                  />
                  <span className="text-sm text-slate-700 dark:text-slate-300">{s.label}</span>
                </label>
              ))}
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-400">Comment</label>
            <textarea
              rows={3}
              value={form.comment}
              onChange={e => setForm(f => ({ ...f, comment: e.target.value }))}
              placeholder="Optional comment…"
              className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
          </div>

          {form.signal === "edited" && (
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-400">Corrected Summary</label>
              <textarea
                rows={4}
                value={form.corrected_summary}
                onChange={e => setForm(f => ({ ...f, corrected_summary: e.target.value }))}
                placeholder="Paste the corrected summary here…"
                className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
          )}

          {submitMsg && (
            <div className={`rounded-xl border p-3 text-sm ${
              submitMsg.type === "success"
                ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-300"
                : "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-800 dark:bg-rose-900/20 dark:text-rose-300"
            }`}>
              {submitMsg.text}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {submitting ? <RefreshCw className="h-4 w-4 animate-spin" /> : <ThumbsUp className="h-4 w-4" />}
            {submitting ? "Submitting…" : "Submit Feedback"}
          </button>
        </form>
      </Card>

      {/* Recent feedback */}
      <section>
        <SectionTitle>Recent Evaluations</SectionTitle>
        <Card className="overflow-hidden p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/60">
                  {["Meeting ID", "Overall Score", "Hallucination", "Provider", "Created"].map(h => (
                    <th key={h} className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loadingRecent
                  ? Array.from({ length: 4 }).map((_, i) => (
                    <tr key={i} className="border-b border-slate-100 dark:border-slate-800">
                      {Array.from({ length: 5 }).map((__, j) => (
                        <td key={j} className="px-4 py-3"><Skeleton className="h-4 w-full" /></td>
                      ))}
                    </tr>
                  ))
                  : recent.length === 0
                  ? <tr><td colSpan={5} className="py-8 text-center text-sm text-slate-400">No recent evaluations</td></tr>
                  : recent.map(r => (
                    <tr key={r.id} className="border-b border-slate-100 dark:border-slate-800">
                      <td className="px-4 py-3 font-mono text-xs text-slate-600 dark:text-slate-300">{r.meeting_id ?? r.id}</td>
                      <td className={`px-4 py-3 font-semibold ${scoreColor(Number(r.overall_score))}`}>{fmt(r.overall_score)}</td>
                      <td className={`px-4 py-3 font-semibold ${hallucinationColor(Number(r.hallucination_score))}`}>{fmt(r.hallucination_score)}</td>
                      <td className="px-4 py-3"><ProviderBadge provider={r.provider} /></td>
                      <td className="px-4 py-3 text-xs text-slate-400">{r.created_at ? new Date(r.created_at).toLocaleDateString() : "—"}</td>
                    </tr>
                  ))
                }
              </tbody>
            </table>
          </div>
        </Card>
      </section>
    </div>
  );
}

// ── Tab 4: Benchmark ──────────────────────────────────────────────────────────
function BenchmarkTab({ token }) {
  const [samples, setSamples]       = useState([]);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState(null);
  const [showForm, setShowForm]     = useState(false);
  const [running, setRunning]       = useState(false);
  const [leaderboard, setLeaderboard] = useState(null);
  const [form, setForm] = useState({
    transcript_excerpt: "",
    expected_summary: "",
    expected_actions: "[]",
    category: "general",
    difficulty: "medium",
  });
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API}/eval/benchmark`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const d = await res.json();
      setSamples(d?.samples || d || []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setSaveMsg(null);
    try {
      let actions;
      try { actions = JSON.parse(form.expected_actions); } catch { throw new Error("Expected actions must be valid JSON"); }
      const res = await fetch(`${API}/eval/benchmark`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ ...form, expected_actions: actions }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setSaveMsg({ type: "success", text: "Benchmark sample saved." });
      setForm({ transcript_excerpt: "", expected_summary: "", expected_actions: "[]", category: "general", difficulty: "medium" });
      setShowForm(false);
      load();
    } catch (e) {
      setSaveMsg({ type: "error", text: e.message });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id) => {
    if (!confirm("Delete this benchmark sample?")) return;
    try {
      const res = await fetch(`${API}/eval/benchmark/${id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      load();
    } catch (e) {
      alert(`Delete failed: ${e.message}`);
    }
  };

  const runSuite = async () => {
    setRunning(true);
    setLeaderboard(null);
    try {
      const res = await fetch(`${API}/eval/benchmark/run`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const d = await res.json();
      setLeaderboard(d?.leaderboard || d?.results || d || []);
    } catch (e) {
      alert(`Benchmark run failed: ${e.message}`);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Actions bar */}
      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={() => setShowForm(v => !v)}
          className="flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700"
        >
          <Plus className="h-4 w-4" />
          Create Sample
        </button>
        <button
          onClick={runSuite}
          disabled={running}
          className="flex items-center gap-2 rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-2 text-sm font-semibold text-indigo-700 hover:bg-indigo-100 disabled:opacity-50 dark:border-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-300"
        >
          {running ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          {running ? "Running Suite…" : "Run Benchmark Suite"}
        </button>
      </div>

      {/* Create form */}
      {showForm && (
        <Card>
          <p className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-200">New Benchmark Sample</p>
          <form onSubmit={handleSave} className="space-y-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-400">Transcript Excerpt</label>
              <textarea
                required rows={4}
                value={form.transcript_excerpt}
                onChange={e => setForm(f => ({ ...f, transcript_excerpt: e.target.value }))}
                className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-400">Expected Summary</label>
              <textarea
                required rows={3}
                value={form.expected_summary}
                onChange={e => setForm(f => ({ ...f, expected_summary: e.target.value }))}
                className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-400">Expected Actions (JSON array)</label>
              <textarea
                required rows={3}
                value={form.expected_actions}
                onChange={e => setForm(f => ({ ...f, expected_actions: e.target.value }))}
                className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 font-mono text-sm text-slate-800 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-400">Category</label>
                <select
                  value={form.category}
                  onChange={e => setForm(f => ({ ...f, category: e.target.value }))}
                  className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 shadow-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
                >
                  {["general", "engineering", "sales", "hr", "finance"].map(c => (
                    <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-400">Difficulty</label>
                <select
                  value={form.difficulty}
                  onChange={e => setForm(f => ({ ...f, difficulty: e.target.value }))}
                  className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 shadow-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
                >
                  {["easy", "medium", "hard"].map(d => (
                    <option key={d} value={d}>{d.charAt(0).toUpperCase() + d.slice(1)}</option>
                  ))}
                </select>
              </div>
            </div>

            {saveMsg && (
              <div className={`rounded-xl border p-3 text-sm ${
                saveMsg.type === "success"
                  ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-300"
                  : "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-800 dark:bg-rose-900/20 dark:text-rose-300"
              }`}>
                {saveMsg.text}
              </div>
            )}

            <div className="flex gap-3">
              <button
                type="submit"
                disabled={saving}
                className="flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {saving ? <RefreshCw className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                {saving ? "Saving…" : "Save Sample"}
              </button>
              <button
                type="button"
                onClick={() => setShowForm(false)}
                className="rounded-xl border border-slate-200 px-5 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
              >
                Cancel
              </button>
            </div>
          </form>
        </Card>
      )}

      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700 dark:border-rose-800 dark:bg-rose-900/20 dark:text-rose-300">
          {error}
        </div>
      )}

      {/* Samples table */}
      <Card className="overflow-hidden p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/60">
                {["ID", "Category", "Difficulty", "Excerpt", "Actions", "Last Run", "Best Provider", ""].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading
                ? Array.from({ length: 4 }).map((_, i) => (
                  <tr key={i} className="border-b border-slate-100 dark:border-slate-800">
                    {Array.from({ length: 8 }).map((__, j) => (
                      <td key={j} className="px-4 py-3"><Skeleton className="h-4 w-full" /></td>
                    ))}
                  </tr>
                ))
                : samples.length === 0
                ? <tr><td colSpan={8} className="py-10 text-center text-sm text-slate-400">No benchmark samples yet</td></tr>
                : samples.map(s => (
                  <tr key={s.id} className="border-b border-slate-100 dark:border-slate-800">
                    <td className="px-4 py-3 font-mono text-xs text-slate-500">{s.id}</td>
                    <td className="px-4 py-3 capitalize text-slate-700 dark:text-slate-300">{s.category}</td>
                    <td className="px-4 py-3">
                      <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                        s.difficulty === "hard"   ? "bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300" :
                        s.difficulty === "medium" ? "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300" :
                                                    "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
                      }`}>
                        {s.difficulty}
                      </span>
                    </td>
                    <td className="max-w-xs truncate px-4 py-3 text-xs text-slate-500 dark:text-slate-400">
                      {s.transcript_excerpt?.slice(0, 80)}{s.transcript_excerpt?.length > 80 ? "…" : ""}
                    </td>
                    <td className="px-4 py-3 text-center text-slate-700 dark:text-slate-300">
                      {Array.isArray(s.expected_actions) ? s.expected_actions.length : "—"}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-400">{s.last_run ? new Date(s.last_run).toLocaleDateString() : "Never"}</td>
                    <td className="px-4 py-3"><ProviderBadge provider={s.best_provider} /></td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => handleDelete(s.id)}
                        className="rounded-lg p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600 dark:hover:bg-rose-900/30 dark:hover:text-rose-400"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))
              }
            </tbody>
          </table>
        </div>
      </Card>

      {/* Leaderboard */}
      {leaderboard && (
        <section>
          <SectionTitle>Benchmark Leaderboard</SectionTitle>
          <Card className="overflow-hidden p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/60">
                    {["Rank", "Provider", "Avg F1", "Samples"].map(h => (
                      <th key={h} className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {leaderboard.map((row, i) => (
                    <tr key={row.provider} className="border-b border-slate-100 dark:border-slate-800">
                      <td className="px-4 py-3 font-bold text-slate-500">#{i + 1}</td>
                      <td className="px-4 py-3"><ProviderBadge provider={row.provider} /></td>
                      <td className={`px-4 py-3 font-semibold ${scoreColor(Number(row.avg_f1))}`}>{fmt(row.avg_f1)}</td>
                      <td className="px-4 py-3 text-slate-600 dark:text-slate-300">{row.samples ?? row.count ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </section>
      )}
    </div>
  );
}

// ── Tab 5: Report ─────────────────────────────────────────────────────────────
function ReportTab({ token }) {
  const [days, setDays]       = useState(7);
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);
  const [downloading, setDownloading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API}/eval/report?days=${days}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setData(await res.json());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [days, token]);

  useEffect(() => { load(); }, [load]);

  const handleDownload = async () => {
    setDownloading(true);
    try {
      const res = await fetch(`${API}/eval/report/download`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement("a");
      a.href     = url;
      a.download = `eval-report-${days}d.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert(`Download failed: ${e.message}`);
    } finally {
      setDownloading(false);
    }
  };

  const gradeColor = (g) => {
    if (g === "A") return "text-emerald-600 dark:text-emerald-400";
    if (g === "B") return "text-cyan-600 dark:text-cyan-400";
    if (g === "C") return "text-amber-600 dark:text-amber-400";
    return "text-rose-600 dark:text-rose-400";
  };

  const summary    = data?.summary    || {};
  const providers  = data?.by_provider || [];
  const trend      = data?.daily_trend || [];
  const suggestions = data?.refinement_suggestions || [];

  return (
    <div className="space-y-8">
      {/* Days filter + download */}
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm text-slate-500 dark:text-slate-400">Period:</span>
        <div className="relative">
          <select
            value={days}
            onChange={e => setDays(Number(e.target.value))}
            className="appearance-none rounded-xl border border-slate-200 bg-white py-1.5 pl-3 pr-8 text-sm text-slate-700 shadow-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
          >
            {[7, 14, 30].map(d => <option key={d} value={d}>{d} days</option>)}
          </select>
          <ChevronDown className="pointer-events-none absolute right-2 top-2 h-4 w-4 text-slate-400" />
        </div>
        <button
          onClick={handleDownload}
          disabled={downloading || loading}
          className="ml-auto flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
        >
          {downloading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
          Download Report
        </button>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700 dark:border-rose-800 dark:bg-rose-900/20 dark:text-rose-300">
          {error}
        </div>
      )}

      {/* Grade badge */}
      <Card>
        <div className="flex flex-col items-center gap-2 py-4 sm:flex-row sm:gap-6">
          {loading
            ? <Skeleton className="h-24 w-24 rounded-full" />
            : (
              <div className="flex h-24 w-24 items-center justify-center rounded-full border-4 border-indigo-200 dark:border-indigo-800">
                <span className={`text-5xl font-black ${gradeColor(data?.grade)}`}>{data?.grade ?? "—"}</span>
              </div>
            )
          }
          <div>
            <p className="text-lg font-bold text-slate-800 dark:text-white">Evaluation Report</p>
            <p className="text-sm text-slate-500 dark:text-slate-400">Last {days} days · {data?.total_evaluations ?? "—"} evaluations</p>
          </div>
        </div>
      </Card>

      {/* Summary metrics */}
      <section>
        <SectionTitle>Summary Metrics</SectionTitle>
        {loading
          ? <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">{Array.from({ length: 8 }).map((_, i) => <Card key={i}><Skeleton className="h-16 w-full" /></Card>)}</div>
          : (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
              {Object.entries(summary).map(([key, val]) => (
                <Card key={key}>
                  <p className="text-xs font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
                    {key.replace(/_/g, " ")}
                  </p>
                  <p className="mt-1 text-xl font-bold text-slate-800 dark:text-white">
                    {typeof val === "number" ? fmt(val) : String(val ?? "—")}
                  </p>
                </Card>
              ))}
            </div>
          )
        }
      </section>

      {/* By-provider comparison */}
      <section>
        <SectionTitle>Provider Comparison</SectionTitle>
        <Card className="overflow-hidden p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/60">
                  {["Provider", "Evaluations", "Avg Overall", "Avg F1", "Avg Hallucination", "Avg Latency ms"].map(h => (
                    <th key={h} className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loading
                  ? Array.from({ length: 3 }).map((_, i) => (
                    <tr key={i} className="border-b border-slate-100 dark:border-slate-800">
                      {Array.from({ length: 6 }).map((__, j) => (
                        <td key={j} className="px-4 py-3"><Skeleton className="h-4 w-full" /></td>
                      ))}
                    </tr>
                  ))
                  : providers.length === 0
                  ? <tr><td colSpan={6} className="py-8 text-center text-sm text-slate-400">No provider data</td></tr>
                  : providers.map(p => (
                    <tr key={p.provider} className="border-b border-slate-100 dark:border-slate-800">
                      <td className="px-4 py-3"><ProviderBadge provider={p.provider} /></td>
                      <td className="px-4 py-3 text-slate-700 dark:text-slate-300">{p.count ?? p.evaluations ?? "—"}</td>
                      <td className={`px-4 py-3 font-semibold ${scoreColor(Number(p.avg_overall))}`}>{fmt(p.avg_overall)}</td>
                      <td className={`px-4 py-3 font-semibold ${scoreColor(Number(p.avg_f1))}`}>{fmt(p.avg_f1)}</td>
                      <td className={`px-4 py-3 font-semibold ${hallucinationColor(Number(p.avg_hallucination))}`}>{fmt(p.avg_hallucination)}</td>
                      <td className="px-4 py-3 text-slate-600 dark:text-slate-300">{p.avg_latency_ms != null ? `${Math.round(p.avg_latency_ms)} ms` : "—"}</td>
                    </tr>
                  ))
                }
              </tbody>
            </table>
          </div>
        </Card>
      </section>

      {/* Daily trend chart */}
      <section>
        <Card>
          <p className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-200">Daily Trend</p>
          {loading
            ? <Skeleton className="h-56 w-full" />
            : trend.length === 0
            ? <p className="py-12 text-center text-sm text-slate-400">No trend data available</p>
            : (
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={trend} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="gradRptScore" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor={INDIGO} stopOpacity={0.25} />
                      <stop offset="95%" stopColor={INDIGO} stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="gradRptHall" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor={ROSE} stopOpacity={0.25} />
                      <stop offset="95%" stopColor={ROSE} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" strokeOpacity={0.5} />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} domain={[0, 1]} />
                  <Tooltip />
                  <Legend />
                  <Area type="monotone" dataKey="avg_overall"       name="Avg Overall"       stroke={INDIGO} fill="url(#gradRptScore)" strokeWidth={2} dot={false} />
                  <Area type="monotone" dataKey="avg_hallucination"  name="Avg Hallucination" stroke={ROSE}   fill="url(#gradRptHall)"  strokeWidth={2} dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            )
          }
        </Card>
      </section>

      {/* Refinement suggestions */}
      {(loading || suggestions.length > 0) && (
        <section>
          <SectionTitle>Refinement Suggestions</SectionTitle>
          <div className="space-y-3">
            {loading
              ? Array.from({ length: 3 }).map((_, i) => <Card key={i}><Skeleton className="h-10 w-full" /></Card>)
              : suggestions.map((s, i) => (
                <Card key={i} className="flex items-start gap-3">
                  <PriorityBadge priority={s.priority} />
                  <p className="text-sm text-slate-700 dark:text-slate-300">{s.suggestion ?? s.text ?? String(s)}</p>
                </Card>
              ))
            }
          </div>
        </section>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
const TABS = ["Dashboard", "Results", "Feedback", "Benchmark", "Report"];

export default function EvalDashboardPage() {
  const { token } = useAuth();
  const [activeTab, setActiveTab] = useState("Dashboard");
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [refreshKey, setRefreshKey]   = useState(0);
  const intervalRef = useRef(null);

  const refresh = useCallback(() => setRefreshKey(k => k + 1), []);

  // Auto-refresh every 10 s
  useEffect(() => {
    if (autoRefresh) {
      intervalRef.current = setInterval(refresh, 10_000);
    } else {
      clearInterval(intervalRef.current);
    }
    return () => clearInterval(intervalRef.current);
  }, [autoRefresh, refresh]);

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">

        {/* Header */}
        <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-indigo-100 dark:bg-indigo-900/40">
              <FlaskConical className="h-6 w-6 text-indigo-600 dark:text-indigo-400" />
            </span>
            <div>
              <h1 className="text-2xl font-bold text-slate-900 dark:text-white">AI Evaluation</h1>
              <p className="text-sm text-slate-500 dark:text-slate-400">Quality scoring, hallucination detection, human feedback</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Auto-refresh toggle */}
            <button
              onClick={() => setAutoRefresh(v => !v)}
              className={`flex items-center gap-2 rounded-xl border px-3 py-2 text-sm font-medium transition-colors ${
                autoRefresh
                  ? "border-indigo-300 bg-indigo-50 text-indigo-700 dark:border-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300"
                  : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
              }`}
            >
              <RefreshCw className={`h-4 w-4 ${autoRefresh ? "animate-spin" : ""}`} />
              Auto {autoRefresh ? "On" : "Off"}
            </button>

            {/* Manual refresh */}
            <button
              onClick={refresh}
              className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
            >
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
          </div>
        </div>

        {/* Tab bar */}
        <div className="mb-6 flex flex-wrap gap-1 rounded-2xl border border-slate-200 bg-white p-1 shadow-sm dark:border-slate-700 dark:bg-slate-900">
          {TABS.map(tab => (
            <TabBtn key={tab} active={activeTab === tab} onClick={() => setActiveTab(tab)}>
              {tab}
            </TabBtn>
          ))}
        </div>

        {/* Tab content — key forces remount on manual refresh */}
        <div key={`${activeTab}-${refreshKey}`}>
          {activeTab === "Dashboard" && <DashboardTab token={token} />}
          {activeTab === "Results"   && <ResultsTab   token={token} />}
          {activeTab === "Feedback"  && <FeedbackTab  token={token} />}
          {activeTab === "Benchmark" && <BenchmarkTab token={token} />}
          {activeTab === "Report"    && <ReportTab    token={token} />}
        </div>

      </div>
    </div>
  );
}
