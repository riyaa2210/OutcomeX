import { useCallback, useEffect, useRef, useState } from "react";
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import {
  Shield, AlertTriangle, CheckCircle2, XCircle,
  RefreshCw, ChevronDown, LogOut, Users, Lock,
} from "lucide-react";
import useAuth from "../context/useAuth";

const API = import.meta.env.VITE_API_URL || "https://meeting-outcome-tracker-backend.onrender.com";

// ── Event type colour mapping ─────────────────────────────────────────────────
const EVENT_COLORS = {
  "auth.login_success":   "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  "auth.login_failed":    "bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300",
  "auth.register":        "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  "auth.logout":          "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  "auth.token_refresh":   "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300",
  "security.rate_limit":  "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  "security.rbac_denied": "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300",
  "security.anomaly":     "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  "webhook.rejected":     "bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300",
  "data.profile_updated": "bg-cyan-100 text-cyan-700 dark:bg-cyan-900/40 dark:text-cyan-300",
};
const DEFAULT_EVENT_COLOR = "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300";

// ── Tiny helpers ──────────────────────────────────────────────────────────────
function EventBadge({ type }) {
  const cls = EVENT_COLORS[type] ?? DEFAULT_EVENT_COLOR;
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-[11px] font-medium ${cls}`}>
      {type}
    </span>
  );
}

function riskColor(score) {
  if (score >= 50) return "text-rose-500";
  if (score >= 20) return "text-amber-500";
  return "text-emerald-500";
}

function riskBg(score) {
  if (score >= 75) return "bg-rose-500";
  if (score >= 50) return "bg-amber-500";
  return "bg-emerald-500";
}

function StatCard({ icon: Icon, label, value, iconColor = "#6366f1", loading }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">{label}</p>
          {loading
            ? <div className="mt-2 h-8 w-20 animate-pulse rounded-lg bg-slate-200 dark:bg-slate-700" />
            : <p className="mt-1 text-3xl font-bold text-slate-800 dark:text-white">{value ?? "—"}</p>
          }
        </div>
        <span className="rounded-xl p-2" style={{ background: iconColor + "22" }}>
          <Icon className="h-5 w-5" style={{ color: iconColor }} />
        </span>
      </div>
    </div>
  );
}

function ChartCard({ title, children, loading, className = "" }) {
  return (
    <div className={`rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900 ${className}`}>
      <p className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-200">{title}</p>
      {loading
        ? <div className="h-48 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" />
        : children
      }
    </div>
  );
}

// ── TABS ──────────────────────────────────────────────────────────────────────
const TABS = ["Overview", "Audit Log", "Anomalies", "Sessions"];

// ── Overview Tab ──────────────────────────────────────────────────────────────
function OverviewTab({ token }) {
  const [hours, setHours] = useState(24);
  const [data, setData]   = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);

  const fetch_ = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API}/security/dashboard?hours=${hours}`, {
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

  useEffect(() => { fetch_(); }, [fetch_]);

  const stats = data?.stats ?? {};
  const hourlyTrend  = data?.hourly_trend  ?? [];
  const eventBreakdown = data?.event_breakdown ?? [];
  const suspiciousIPs  = data?.suspicious_ips  ?? [];

  return (
    <div className="space-y-6">
      {/* Hours filter */}
      <div className="flex items-center justify-between">
        <div className="relative">
          <select
            value={hours}
            onChange={e => setHours(Number(e.target.value))}
            className="appearance-none rounded-xl border border-slate-200 bg-white py-2 pl-3 pr-8 text-sm text-slate-700 shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
          >
            {[1, 6, 12, 24, 48, 168].map(h => (
              <option key={h} value={h}>Last {h === 168 ? "7 days" : `${h}h`}</option>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute right-2 top-2.5 h-4 w-4 text-slate-400" />
        </div>
        <button
          onClick={fetch_}
          className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
        >
          <RefreshCw className="h-4 w-4" /> Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-xl bg-rose-50 border border-rose-200 px-4 py-3 text-sm text-rose-700 dark:bg-rose-950/30 dark:border-rose-800 dark:text-rose-300">
          {error}
        </div>
      )}

      {/* Row 1 stat cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard icon={Shield}        label="Total Events"       value={stats.total_events}       iconColor="#6366f1" loading={loading} />
        <StatCard icon={XCircle}       label="Failed Logins"      value={stats.failed_logins}      iconColor="#f43f5e" loading={loading} />
        <StatCard icon={AlertTriangle} label="Rate Limit Hits"    value={stats.rate_limit_hits}    iconColor="#f59e0b" loading={loading} />
        <StatCard icon={Lock}          label="RBAC Denials"       value={stats.rbac_denials}       iconColor="#f97316" loading={loading} />
      </div>

      {/* Row 2 stat cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard icon={AlertTriangle} label="Anomalies"          value={stats.anomalies}          iconColor="#ef4444" loading={loading} />
        <StatCard icon={XCircle}       label="Webhook Rejections" value={stats.webhook_rejections} iconColor="#a855f7" loading={loading} />
        <StatCard icon={Shield}        label="Avg Risk Score"     value={stats.avg_risk_score != null ? Number(stats.avg_risk_score).toFixed(1) : "—"} iconColor="#06b6d4" loading={loading} />
        <StatCard icon={Shield}        label="Max Risk Score"     value={stats.max_risk_score}     iconColor="#f43f5e" loading={loading} />
      </div>

      {/* Hourly trend chart */}
      <ChartCard title="Hourly Event Trend" loading={loading}>
        {hourlyTrend.length ? (
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={hourlyTrend} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="gEvents" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#6366f1" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#6366f1" stopOpacity={0}   />
                </linearGradient>
                <linearGradient id="gFail" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#f43f5e" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#f43f5e" stopOpacity={0}   />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f022" />
              <XAxis dataKey="hour" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
              <Tooltip contentStyle={{ fontSize: 12 }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Area type="monotone" dataKey="events"   stroke="#6366f1" fill="url(#gEvents)" strokeWidth={2} name="Events"   />
              <Area type="monotone" dataKey="failures" stroke="#f43f5e" fill="url(#gFail)"   strokeWidth={2} name="Failures" />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <p className="py-12 text-center text-sm text-slate-400">No trend data for this period</p>
        )}
      </ChartCard>

      {/* Event type breakdown */}
      <ChartCard title="Event Type Breakdown (Top 10)" loading={loading}>
        {eventBreakdown.length ? (
          <ResponsiveContainer width="100%" height={240}>
            <BarChart
              data={eventBreakdown.slice(0, 10)}
              layout="vertical"
              margin={{ top: 5, right: 20, left: 10, bottom: 5 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f022" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 10 }} allowDecimals={false} />
              <YAxis type="category" dataKey="event_type" tick={{ fontSize: 10 }} width={140} />
              <Tooltip contentStyle={{ fontSize: 12 }} />
              <Bar dataKey="count" fill="#6366f1" radius={[0, 4, 4, 0]} name="Count" />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p className="py-12 text-center text-sm text-slate-400">No event data</p>
        )}
      </ChartCard>

      {/* Suspicious IPs table */}
      <div className="rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900">
        <div className="border-b border-slate-100 px-5 py-4 dark:border-slate-800">
          <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">Top Suspicious IPs</p>
        </div>
        {loading ? (
          <div className="p-5 space-y-3">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-8 animate-pulse rounded-lg bg-slate-100 dark:bg-slate-800" />
            ))}
          </div>
        ) : suspiciousIPs.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 dark:border-slate-800">
                  <th className="px-5 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-500">IP</th>
                  <th className="px-5 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-500">Events</th>
                  <th className="px-5 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-500">Failures</th>
                  <th className="px-5 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-500">Max Risk Score</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {suspiciousIPs.map((ip, i) => (
                  <tr key={i} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                    <td className="px-5 py-3 font-mono text-slate-700 dark:text-slate-200">{ip.ip_address}</td>
                    <td className="px-5 py-3 text-slate-600 dark:text-slate-300">{ip.events}</td>
                    <td className="px-5 py-3 text-slate-600 dark:text-slate-300">{ip.failures}</td>
                    <td className="px-5 py-3">
                      <span className={`font-semibold ${riskColor(ip.max_risk_score)}`}>
                        {ip.max_risk_score}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="px-5 py-8 text-center text-sm text-slate-400">No suspicious IPs detected</p>
        )}
      </div>
    </div>
  );
}

// ── Audit Log Tab ─────────────────────────────────────────────────────────────
function AuditLogTab({ token }) {
  const [hours, setHours]         = useState(24);
  const [page, setPage]           = useState(1);
  const [eventType, setEventType] = useState("");
  const [success, setSuccess]     = useState("all");
  const [data, setData]           = useState(null);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(null);

  const PAGE_SIZE = 20;

  const fetch_ = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        hours,
        page,
        page_size: PAGE_SIZE,
      });
      if (eventType) params.set("event_type", eventType);
      if (success !== "all") params.set("success", success === "success" ? "true" : "false");

      const res = await fetch(`${API}/security/audit-log?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setData(await res.json());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [hours, page, eventType, success, token]);

  useEffect(() => { fetch_(); }, [fetch_]);

  // Reset to page 1 when filters change
  useEffect(() => { setPage(1); }, [hours, eventType, success]);

  const logs     = data?.logs ?? data?.items ?? [];
  const total    = data?.total ?? 0;
  const hasNext  = page * PAGE_SIZE < total;
  const hasPrev  = page > 1;

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <input
          type="text"
          placeholder="Filter by event type…"
          value={eventType}
          onChange={e => setEventType(e.target.value)}
          className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 w-52"
        />

        <div className="relative">
          <select
            value={success}
            onChange={e => setSuccess(e.target.value)}
            className="appearance-none rounded-xl border border-slate-200 bg-white py-2 pl-3 pr-8 text-sm text-slate-700 shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
          >
            <option value="all">All outcomes</option>
            <option value="success">Success only</option>
            <option value="failed">Failed only</option>
          </select>
          <ChevronDown className="pointer-events-none absolute right-2 top-2.5 h-4 w-4 text-slate-400" />
        </div>

        <div className="relative">
          <select
            value={hours}
            onChange={e => setHours(Number(e.target.value))}
            className="appearance-none rounded-xl border border-slate-200 bg-white py-2 pl-3 pr-8 text-sm text-slate-700 shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
          >
            {[1, 6, 12, 24, 48, 168].map(h => (
              <option key={h} value={h}>Last {h === 168 ? "7 days" : `${h}h`}</option>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute right-2 top-2.5 h-4 w-4 text-slate-400" />
        </div>

        <button
          onClick={fetch_}
          className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
        >
          <RefreshCw className="h-4 w-4" /> Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-xl bg-rose-50 border border-rose-200 px-4 py-3 text-sm text-rose-700 dark:bg-rose-950/30 dark:border-rose-800 dark:text-rose-300">
          {error}
        </div>
      )}

      {/* Table */}
      <div className="rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50">
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-500">ID</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-500">Event Type</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-500">User Email</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-500">IP Address</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-500">Endpoint</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-500">Success</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-500">Risk</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-500">Created At</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {loading ? (
                [...Array(8)].map((_, i) => (
                  <tr key={i}>
                    {[...Array(8)].map((__, j) => (
                      <td key={j} className="px-4 py-3">
                        <div className="h-4 animate-pulse rounded bg-slate-100 dark:bg-slate-800" />
                      </td>
                    ))}
                  </tr>
                ))
              ) : logs.length ? (
                logs.map((log) => (
                  <tr key={log.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                    <td className="px-4 py-3 font-mono text-xs text-slate-400">{log.id}</td>
                    <td className="px-4 py-3"><EventBadge type={log.event_type} /></td>
                    <td className="px-4 py-3 text-slate-600 dark:text-slate-300 max-w-[160px] truncate">{log.user_email ?? "—"}</td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-600 dark:text-slate-300">{log.ip_address ?? "—"}</td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-500 max-w-[180px] truncate">{log.endpoint ?? "—"}</td>
                    <td className="px-4 py-3">
                      {log.success
                        ? <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                        : <XCircle className="h-4 w-4 text-rose-500" />
                      }
                    </td>
                    <td className="px-4 py-3">
                      <span className={`font-semibold ${riskColor(log.risk_score ?? 0)}`}>
                        {log.risk_score ?? 0}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-400 whitespace-nowrap">
                      {log.created_at ? new Date(log.created_at).toLocaleString() : "—"}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={8} className="px-4 py-10 text-center text-sm text-slate-400">
                    No audit log entries found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="flex items-center justify-between border-t border-slate-100 px-5 py-3 dark:border-slate-800">
          <p className="text-xs text-slate-400">
            {total > 0 ? `Showing ${(page - 1) * PAGE_SIZE + 1}–${Math.min(page * PAGE_SIZE, total)} of ${total}` : "No results"}
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => setPage(p => p - 1)}
              disabled={!hasPrev || loading}
              className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50 disabled:opacity-40 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
            >
              ← Prev
            </button>
            <button
              onClick={() => setPage(p => p + 1)}
              disabled={!hasNext || loading}
              className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50 disabled:opacity-40 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
            >
              Next →
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Anomalies Tab ─────────────────────────────────────────────────────────────
function AnomaliesTab({ token }) {
  const [hours, setHours]     = useState(24);
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);

  const fetch_ = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API}/security/anomalies?hours=${hours}`, {
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

  useEffect(() => { fetch_(); }, [fetch_]);

  const anomalies = data?.anomalies ?? data ?? [];

  return (
    <div className="space-y-4">
      {/* Filter row */}
      <div className="flex items-center justify-between">
        <div className="relative">
          <select
            value={hours}
            onChange={e => setHours(Number(e.target.value))}
            className="appearance-none rounded-xl border border-slate-200 bg-white py-2 pl-3 pr-8 text-sm text-slate-700 shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
          >
            {[1, 6, 12, 24, 48, 168].map(h => (
              <option key={h} value={h}>Last {h === 168 ? "7 days" : `${h}h`}</option>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute right-2 top-2.5 h-4 w-4 text-slate-400" />
        </div>
        <button
          onClick={fetch_}
          className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
        >
          <RefreshCw className="h-4 w-4" /> Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-xl bg-rose-50 border border-rose-200 px-4 py-3 text-sm text-rose-700 dark:bg-rose-950/30 dark:border-rose-800 dark:text-rose-300">
          {error}
        </div>
      )}

      {loading ? (
        <div className="space-y-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-32 animate-pulse rounded-2xl bg-slate-100 dark:bg-slate-800" />
          ))}
        </div>
      ) : !Array.isArray(anomalies) || anomalies.length === 0 ? (
        <div className="rounded-2xl border border-slate-200 bg-white p-12 text-center shadow-sm dark:border-slate-700 dark:bg-slate-900">
          <p className="text-2xl mb-2">🎉</p>
          <p className="text-slate-500 dark:text-slate-400">No anomalies detected</p>
        </div>
      ) : (
        <div className="space-y-4">
          {anomalies.map((a, i) => (
            <div
              key={i}
              className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900"
            >
              <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
                <div className="flex flex-wrap items-center gap-2">
                  <EventBadge type={a.event_type} />
                  <span className="font-mono text-xs text-slate-500">{a.ip_address ?? "—"}</span>
                  {a.user_id && (
                    <span className="text-xs text-slate-400">User #{a.user_id}</span>
                  )}
                </div>
                <span className="text-xs text-slate-400">
                  {a.created_at ? new Date(a.created_at).toLocaleString() : "—"}
                </span>
              </div>

              {/* Risk score bar */}
              <div className="mb-4">
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-slate-500">Risk Score</span>
                  <span className={`font-semibold ${riskColor(a.risk_score ?? 0)}`}>{a.risk_score ?? 0} / 100</span>
                </div>
                <div className="h-2 rounded-full bg-slate-100 dark:bg-slate-700">
                  <div
                    className={`h-2 rounded-full transition-all ${riskBg(a.risk_score ?? 0)}`}
                    style={{ width: `${Math.min(a.risk_score ?? 0, 100)}%` }}
                  />
                </div>
              </div>

              {/* Details JSON */}
              {a.details && (
                <details className="group">
                  <summary className="cursor-pointer text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 select-none">
                    View details
                  </summary>
                  <pre className="mt-2 overflow-x-auto rounded-xl bg-slate-50 p-3 text-[11px] text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                    {JSON.stringify(a.details, null, 2)}
                  </pre>
                </details>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Sessions Tab ──────────────────────────────────────────────────────────────
function SessionsTab({ token }) {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);
  const [revoking, setRevoking] = useState(false);
  const [revokeMsg, setRevokeMsg] = useState(null);

  const fetch_ = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API}/security/active-sessions`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setData(await res.json());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { fetch_(); }, [fetch_]);

  const revokeAll = async () => {
    setRevoking(true);
    setRevokeMsg(null);
    try {
      const res = await fetch(`${API}/auth/logout-all`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setRevokeMsg({ type: "success", text: "All sessions revoked successfully." });
      fetch_();
    } catch (e) {
      setRevokeMsg({ type: "error", text: `Failed to revoke sessions: ${e.message}` });
    } finally {
      setRevoking(false);
    }
  };

  const sessions = data?.sessions ?? data ?? [];

  return (
    <div className="space-y-4">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Your currently active sessions
        </p>
        <div className="flex gap-2">
          <button
            onClick={fetch_}
            className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
          >
            <RefreshCw className="h-4 w-4" /> Refresh
          </button>
          <button
            onClick={revokeAll}
            disabled={revoking}
            className="flex items-center gap-1.5 rounded-xl bg-rose-600 px-4 py-2 text-sm font-medium text-white hover:bg-rose-700 disabled:opacity-60"
          >
            <LogOut className="h-4 w-4" />
            {revoking ? "Revoking…" : "Revoke All Sessions"}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl bg-rose-50 border border-rose-200 px-4 py-3 text-sm text-rose-700 dark:bg-rose-950/30 dark:border-rose-800 dark:text-rose-300">
          {error}
        </div>
      )}

      {revokeMsg && (
        <div className={`rounded-xl border px-4 py-3 text-sm ${
          revokeMsg.type === "success"
            ? "bg-emerald-50 border-emerald-200 text-emerald-700 dark:bg-emerald-950/30 dark:border-emerald-800 dark:text-emerald-300"
            : "bg-rose-50 border-rose-200 text-rose-700 dark:bg-rose-950/30 dark:border-rose-800 dark:text-rose-300"
        }`}>
          {revokeMsg.text}
        </div>
      )}

      {loading ? (
        <div className="space-y-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-28 animate-pulse rounded-2xl bg-slate-100 dark:bg-slate-800" />
          ))}
        </div>
      ) : !Array.isArray(sessions) || sessions.length === 0 ? (
        <div className="rounded-2xl border border-slate-200 bg-white p-12 text-center shadow-sm dark:border-slate-700 dark:bg-slate-900">
          <p className="text-slate-500 dark:text-slate-400">No active sessions found</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {sessions.map((s, i) => (
            <div
              key={i}
              className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900"
            >
              <div className="flex items-center gap-2 mb-3">
                <div className="h-2 w-2 rounded-full bg-emerald-500" />
                <span className="text-xs font-medium text-emerald-600 dark:text-emerald-400">Active</span>
              </div>
              <div className="space-y-2 text-sm">
                <div>
                  <p className="text-xs text-slate-400 mb-0.5">IP Address</p>
                  <p className="font-mono text-slate-700 dark:text-slate-200">{s.ip_address ?? "—"}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-400 mb-0.5">User Agent</p>
                  <p className="text-slate-600 dark:text-slate-300 text-xs truncate" title={s.user_agent}>
                    {s.user_agent ? s.user_agent.slice(0, 60) + (s.user_agent.length > 60 ? "…" : "") : "—"}
                  </p>
                </div>
                <div className="grid grid-cols-2 gap-2 pt-1">
                  <div>
                    <p className="text-xs text-slate-400 mb-0.5">Created</p>
                    <p className="text-xs text-slate-600 dark:text-slate-300">
                      {s.created_at ? new Date(s.created_at).toLocaleString() : "—"}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-400 mb-0.5">Expires</p>
                    <p className="text-xs text-slate-600 dark:text-slate-300">
                      {s.expires_at ? new Date(s.expires_at).toLocaleString() : "—"}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function SecurityDashboardPage() {
  const { user, token } = useAuth();
  const [activeTab, setActiveTab]       = useState("Overview");
  const [autoRefresh, setAutoRefresh]   = useState(false);
  const [refreshKey, setRefreshKey]     = useState(0);
  const intervalRef = useRef(null);

  // Auto-refresh every 10 seconds
  useEffect(() => {
    if (autoRefresh) {
      intervalRef.current = setInterval(() => {
        setRefreshKey(k => k + 1);
      }, 10_000);
    } else {
      clearInterval(intervalRef.current);
    }
    return () => clearInterval(intervalRef.current);
  }, [autoRefresh]);

  // Access denied guard
  if (!user || user.role !== "admin") {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 text-center">
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-10 shadow-sm dark:border-rose-800 dark:bg-rose-950/30">
          <Lock className="mx-auto mb-4 h-12 w-12 text-rose-400" />
          <h2 className="text-xl font-bold text-rose-700 dark:text-rose-300">Access Denied</h2>
          <p className="mt-2 text-sm text-rose-500 dark:text-rose-400">
            This page is restricted to administrators only.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 pb-12">
      {/* ── Header ── */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-slate-800 dark:text-white">
            <Shield className="h-6 w-6 text-rose-500" />
            Security
          </h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            RBAC · Audit Log · Anomaly Detection · Session Management
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Auto-refresh toggle */}
          <button
            onClick={() => setAutoRefresh(v => !v)}
            className={`flex items-center gap-2 rounded-xl border px-3 py-2 text-sm transition-colors ${
              autoRefresh
                ? "border-indigo-300 bg-indigo-50 text-indigo-700 dark:border-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300"
                : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
            }`}
          >
            <span
              className={`h-2 w-2 rounded-full ${autoRefresh ? "bg-indigo-500 animate-pulse" : "bg-slate-300"}`}
            />
            Auto-refresh {autoRefresh ? "on" : "off"}
          </button>

          {/* Manual refresh */}
          <button
            onClick={() => setRefreshKey(k => k + 1)}
            className="flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
          >
            <RefreshCw className="h-4 w-4" /> Refresh
          </button>
        </div>
      </div>

      {/* ── Tabs ── */}
      <div className="flex gap-1 rounded-2xl border border-slate-200 bg-slate-100 p-1 dark:border-slate-700 dark:bg-slate-800 w-fit">
        {TABS.map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`rounded-xl px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === tab
                ? "bg-white text-indigo-600 shadow-sm dark:bg-slate-900 dark:text-indigo-400"
                : "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* ── Tab content ── */}
      {/* refreshKey is passed as a key prop to force remount on manual/auto refresh */}
      <div key={refreshKey}>
        {activeTab === "Overview"  && <OverviewTab  token={token} />}
        {activeTab === "Audit Log" && <AuditLogTab  token={token} />}
        {activeTab === "Anomalies" && <AnomaliesTab token={token} />}
        {activeTab === "Sessions"  && <SessionsTab  token={token} />}
      </div>
    </div>
  );
}
