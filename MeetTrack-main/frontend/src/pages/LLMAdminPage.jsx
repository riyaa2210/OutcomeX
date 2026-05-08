import { useEffect, useState, useCallback, useRef } from "react";
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import {
  Brain, Zap, AlertTriangle, CheckCircle2, RefreshCw,
  ChevronDown, Send, Trash2, Settings,
} from "lucide-react";
import useAuth from "../context/useAuth";

const API = import.meta.env.VITE_API_URL || "https://meeting-outcome-tracker-backend.onrender.com";

const PROVIDER_COLORS = {
  gemini: "#6366f1",
  openai: "#10b981",
  local:  "#f59e0b",
};

const TASK_TYPES = [
  "summarization", "extraction", "reasoning",
  "sentiment", "classification", "chat", "fallback",
];

// ── Small helpers ─────────────────────────────────────────────────────────────

const fmt = (n, dec = 2) => (n == null ? "—" : Number(n).toFixed(dec));
const pct = (n) => (n == null ? "—" : `${(Number(n) * 100).toFixed(1)}%`);

function ProviderBadge({ provider }) {
  const color = PROVIDER_COLORS[provider] || "#94a3b8";
  return (
    <span
      className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold text-white"
      style={{ background: color }}
    >
      {provider}
    </span>
  );
}

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

function QualityColor({ value, thresholds = [0.7, 0.5] }) {
  const v = Number(value);
  if (isNaN(v)) return <span className="text-slate-400">—</span>;
  const cls = v >= thresholds[0]
    ? "text-emerald-600 dark:text-emerald-400"
    : v >= thresholds[1]
    ? "text-amber-600 dark:text-amber-400"
    : "text-rose-600 dark:text-rose-400";
  return <span className={cls}>{fmt(v, 3)}</span>;
}

function HallucinationColor({ value }) {
  const v = Number(value);
  if (isNaN(v)) return <span className="text-slate-400">—</span>;
  const cls = v < 0.1
    ? "text-emerald-600 dark:text-emerald-400"
    : v < 0.3
    ? "text-amber-600 dark:text-amber-400"
    : "text-rose-600 dark:text-rose-400";
  return <span className={cls}>{fmt(v, 3)}</span>;
}

// ── Tab button ────────────────────────────────────────────────────────────────

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

// ── Tab 1: Overview ───────────────────────────────────────────────────────────

function OverviewTab({ status, loading }) {
  if (loading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {[0, 1, 2].map(i => <Card key={i}><Skeleton className="h-24 w-full" /></Card>)}
        </div>
        <Card><Skeleton className="h-40 w-full" /></Card>
      </div>
    );
  }

  const providers = status?.providers || {};
  const routing   = status?.routing   || {};
  const cache     = status?.cache     || {};
  const quotas    = status?.quotas    || {};

  return (
    <div className="space-y-6">
      {/* Provider status cards */}
      <div>
        <SectionTitle>Provider Status</SectionTitle>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {["gemini", "openai", "local"].map(p => {
            const info = providers[p] || {};
            const available = info.available !== false;
            const cb = info.circuit_breaker || "closed";
            return (
              <Card key={p}>
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-base font-bold capitalize text-slate-800 dark:text-white">{p}</p>
                    <p className="mt-0.5 text-xs text-slate-400">{info.model || "—"}</p>
                  </div>
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                      available
                        ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
                        : "bg-rose-100 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300"
                    }`}
                  >
                    {available ? "Available" : "Unavailable"}
                  </span>
                </div>
                <div className="mt-3 flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                  <span>Circuit breaker:</span>
                  <span
                    className={`font-semibold ${
                      cb === "open"
                        ? "text-rose-500"
                        : cb === "half_open"
                        ? "text-amber-500"
                        : "text-emerald-500"
                    }`}
                  >
                    {cb}
                  </span>
                </div>
                {info.error_rate != null && (
                  <div className="mt-1 text-xs text-slate-400">
                    Error rate: <span className="font-medium text-slate-600 dark:text-slate-300">{pct(info.error_rate)}</span>
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      </div>

      {/* Routing table */}
      <div>
        <SectionTitle>Routing Table</SectionTitle>
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 dark:border-slate-800 text-left text-xs text-slate-400">
                <th className="px-4 py-3 font-medium">Task Type</th>
                <th className="px-4 py-3 font-medium">Provider Chain (ordered)</th>
              </tr>
            </thead>
            <tbody>
              {TASK_TYPES.map(task => {
                const chain = routing[task] || [];
                return (
                  <tr key={task} className="border-b border-slate-50 dark:border-slate-800 last:border-0">
                    <td className="px-4 py-2.5 font-medium text-slate-700 dark:text-slate-200">{task}</td>
                    <td className="px-4 py-2.5">
                      <div className="flex flex-wrap gap-1.5">
                        {chain.length
                          ? chain.map((p, i) => (
                              <span key={i} className="flex items-center gap-1">
                                {i > 0 && <span className="text-slate-300 dark:text-slate-600">→</span>}
                                <ProviderBadge provider={p} />
                              </span>
                            ))
                          : <span className="text-slate-400 text-xs">No chain configured</span>
                        }
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      </div>

      {/* Cache stats + Quota usage */}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <div>
          <SectionTitle>Cache Stats</SectionTitle>
          <Card>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-slate-500 dark:text-slate-400">Memory size</span>
                <span className="font-semibold text-slate-700 dark:text-slate-200">{cache.memory_size ?? "—"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500 dark:text-slate-400">Redis available</span>
                <span className={`font-semibold ${cache.redis_available ? "text-emerald-500" : "text-rose-500"}`}>
                  {cache.redis_available ? "Yes" : "No"}
                </span>
              </div>
              {cache.hit_rate != null && (
                <div className="flex justify-between">
                  <span className="text-slate-500 dark:text-slate-400">Hit rate</span>
                  <span className="font-semibold text-slate-700 dark:text-slate-200">{pct(cache.hit_rate)}</span>
                </div>
              )}
            </div>
          </Card>
        </div>

        <div>
          <SectionTitle>Quota Usage</SectionTitle>
          <Card>
            <div className="space-y-3">
              {Object.entries(quotas).length
                ? Object.entries(quotas).map(([provider, q]) => {
                    const used = q.used ?? 0;
                    const limit = q.limit ?? 1;
                    const ratio = Math.min((used / limit) * 100, 100);
                    const color = PROVIDER_COLORS[provider] || "#6366f1";
                    return (
                      <div key={provider}>
                        <div className="flex justify-between text-xs mb-1">
                          <span className="font-medium capitalize text-slate-700 dark:text-slate-200">{provider}</span>
                          <span className="text-slate-400">{used.toLocaleString()} / {limit.toLocaleString()}</span>
                        </div>
                        <div className="h-2 rounded-full bg-slate-100 dark:bg-slate-700">
                          <div
                            className="h-2 rounded-full transition-all"
                            style={{ width: `${ratio}%`, background: color }}
                          />
                        </div>
                      </div>
                    );
                  })
                : <p className="text-sm text-slate-400">No quota data available</p>
              }
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

// ── Tab 2: Metrics ────────────────────────────────────────────────────────────

function MetricsTab({ hours, setHours, metrics, loading }) {
  if (loading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {[0, 1, 2, 3].map(i => <Card key={i}><Skeleton className="h-16 w-full" /></Card>)}
        </div>
        <Card><Skeleton className="h-52 w-full" /></Card>
        <Card><Skeleton className="h-52 w-full" /></Card>
      </div>
    );
  }

  const summary    = metrics?.summary    || {};
  const byProvider = metrics?.by_provider || [];
  const trend      = metrics?.trend       || [];

  // Build latency trend data: array of { period, gemini, openai, local }
  const latencyMap = {};
  trend.forEach(row => {
    if (!latencyMap[row.period]) latencyMap[row.period] = { period: row.period };
    latencyMap[row.period][row.provider] = row.avg_latency;
  });
  const latencyData = Object.values(latencyMap);

  // Build calls per provider per period
  const callsMap = {};
  trend.forEach(row => {
    if (!callsMap[row.period]) callsMap[row.period] = { period: row.period };
    callsMap[row.period][row.provider] = (callsMap[row.period][row.provider] || 0) + (row.calls || 0);
  });
  const callsData = Object.values(callsMap);

  return (
    <div className="space-y-6">
      {/* Hours filter */}
      <div className="flex items-center gap-3">
        <label className="text-sm text-slate-500 dark:text-slate-400">Time window:</label>
        <div className="relative">
          <select
            value={hours}
            onChange={e => setHours(Number(e.target.value))}
            className="appearance-none rounded-xl border border-slate-200 bg-white py-2 pl-3 pr-8 text-sm text-slate-700 shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
          >
            {[1, 6, 12, 24, 48, 168].map(h => (
              <option key={h} value={h}>Last {h}h</option>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute right-2 top-2.5 h-4 w-4 text-slate-400" />
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {[
          { label: "Total Calls",   value: summary.total_calls   ?? "—" },
          { label: "Total Cost",    value: summary.total_cost    != null ? `$${fmt(summary.total_cost, 4)}` : "—" },
          { label: "Total Tokens",  value: summary.total_tokens  != null ? summary.total_tokens.toLocaleString() : "—" },
          { label: "Avg Quality",   value: summary.avg_quality   != null ? fmt(summary.avg_quality, 3) : "—" },
        ].map(({ label, value }) => (
          <Card key={label}>
            <p className="text-xs font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">{label}</p>
            <p className="mt-1 text-2xl font-bold text-slate-800 dark:text-white">{value}</p>
          </Card>
        ))}
      </div>

      {/* Latency trend chart */}
      <Card>
        <p className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-200">Avg Latency Trend (ms)</p>
        {latencyData.length ? (
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={latencyData} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
              <defs>
                {Object.entries(PROVIDER_COLORS).map(([p, color]) => (
                  <linearGradient key={p} id={`grad-${p}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor={color} stopOpacity={0.3} />
                    <stop offset="95%" stopColor={color} stopOpacity={0}   />
                  </linearGradient>
                ))}
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f022" />
              <XAxis dataKey="period" tick={{ fontSize: 10 }} tickFormatter={v => String(v).slice(0, 13)} />
              <YAxis tick={{ fontSize: 10 }} unit="ms" />
              <Tooltip contentStyle={{ fontSize: 12 }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {Object.entries(PROVIDER_COLORS).map(([p, color]) => (
                <Area
                  key={p}
                  type="monotone"
                  dataKey={p}
                  stroke={color}
                  fill={`url(#grad-${p})`}
                  strokeWidth={2}
                  name={p}
                  connectNulls
                />
              ))}
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <p className="py-12 text-center text-sm text-slate-400">No trend data for this window</p>
        )}
      </Card>

      {/* Calls per provider chart */}
      <Card>
        <p className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-200">Calls per Provider</p>
        {callsData.length ? (
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={callsData} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f022" />
              <XAxis dataKey="period" tick={{ fontSize: 10 }} tickFormatter={v => String(v).slice(0, 13)} />
              <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
              <Tooltip contentStyle={{ fontSize: 12 }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {Object.entries(PROVIDER_COLORS).map(([p, color]) => (
                <Bar key={p} dataKey={p} fill={color} name={p} radius={[3, 3, 0, 0]} stackId="a" />
              ))}
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p className="py-12 text-center text-sm text-slate-400">No call data for this window</p>
        )}
      </Card>

      {/* By-provider stats table */}
      {byProvider.length > 0 && (
        <Card className="overflow-x-auto p-0">
          <p className="px-5 pt-4 pb-3 text-sm font-semibold text-slate-700 dark:text-slate-200">Detailed Stats by Provider</p>
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-100 dark:border-slate-800 text-left text-slate-400">
                {["Provider","Model","Task","Calls","Success%","Avg ms","P95 ms","Cost $","Avg Quality","Avg Halluc"].map(h => (
                  <th key={h} className="px-4 py-2 font-medium whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {byProvider.map((row, i) => (
                <tr key={i} className="border-b border-slate-50 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/50">
                  <td className="px-4 py-2"><ProviderBadge provider={row.provider} /></td>
                  <td className="px-4 py-2 text-slate-500 max-w-[120px] truncate">{row.model || "—"}</td>
                  <td className="px-4 py-2 text-slate-500">{row.task_type || "—"}</td>
                  <td className="px-4 py-2 font-medium text-slate-700 dark:text-slate-200">{row.total_calls ?? "—"}</td>
                  <td className="px-4 py-2">{row.success_rate != null ? `${(row.success_rate * 100).toFixed(1)}%` : "—"}</td>
                  <td className="px-4 py-2 text-slate-500">{row.avg_latency_ms != null ? `${Math.round(row.avg_latency_ms)}` : "—"}</td>
                  <td className="px-4 py-2 text-slate-500">{row.p95_latency_ms != null ? `${Math.round(row.p95_latency_ms)}` : "—"}</td>
                  <td className="px-4 py-2 text-slate-500">{row.total_cost_usd != null ? `$${fmt(row.total_cost_usd, 5)}` : "—"}</td>
                  <td className="px-4 py-2"><QualityColor value={row.avg_quality} /></td>
                  <td className="px-4 py-2"><HallucinationColor value={row.avg_hallucination} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

// ── Tab 3: Quality ────────────────────────────────────────────────────────────

function QualityTab({ quality, loading }) {
  if (loading) {
    return <Card><Skeleton className="h-64 w-full" /></Card>;
  }

  const rows = quality?.distribution || [];

  return (
    <div className="space-y-6">
      <SectionTitle>Quality Score Distribution</SectionTitle>
      {rows.length ? (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-100 dark:border-slate-800 text-left text-slate-400">
                {["Provider","Task Type","Avg Quality","Min Quality","Max Quality","Avg Halluc","High Halluc Count"].map(h => (
                  <th key={h} className="px-4 py-3 font-medium whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i} className="border-b border-slate-50 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/50">
                  <td className="px-4 py-2.5"><ProviderBadge provider={row.provider} /></td>
                  <td className="px-4 py-2.5 text-slate-600 dark:text-slate-300">{row.task_type || "—"}</td>
                  <td className="px-4 py-2.5 font-semibold"><QualityColor value={row.avg_quality} /></td>
                  <td className="px-4 py-2.5"><QualityColor value={row.min_quality} /></td>
                  <td className="px-4 py-2.5"><QualityColor value={row.max_quality} /></td>
                  <td className="px-4 py-2.5 font-semibold"><HallucinationColor value={row.avg_hallucination} /></td>
                  <td className="px-4 py-2.5">
                    {row.high_hallucination_count != null ? (
                      <span className={`font-semibold ${row.high_hallucination_count > 0 ? "text-rose-500" : "text-emerald-500"}`}>
                        {row.high_hallucination_count}
                      </span>
                    ) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      ) : (
        <Card>
          <p className="py-8 text-center text-sm text-slate-400">No quality data available yet</p>
        </Card>
      )}

      {/* Legend */}
      <div className="flex flex-wrap gap-4 text-xs text-slate-500 dark:text-slate-400">
        <div className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
          Quality ≥ 0.7 (good)
        </div>
        <div className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-amber-500" />
          Quality ≥ 0.5 (fair)
        </div>
        <div className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-rose-500" />
          Quality &lt; 0.5 (poor)
        </div>
        <span className="mx-2 text-slate-300 dark:text-slate-600">|</span>
        <div className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
          Halluc &lt; 0.1 (low)
        </div>
        <div className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-amber-500" />
          Halluc &lt; 0.3 (medium)
        </div>
        <div className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-rose-500" />
          Halluc ≥ 0.3 (high)
        </div>
      </div>
    </div>
  );
}

// ── Tab 4: Logs ───────────────────────────────────────────────────────────────

function LogsTab({ token, hours }) {
  const [logs, setLogs]             = useState(null);
  const [loading, setLoading]       = useState(true);
  const [page, setPage]             = useState(1);
  const [filterProvider, setFilterProvider] = useState("");
  const [filterTask, setFilterTask] = useState("");
  const [successOnly, setSuccessOnly] = useState(false);
  const [filterHours, setFilterHours] = useState(hours);

  const headers = { Authorization: `Bearer ${token}` };

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        hours: filterHours,
        page,
        page_size: 20,
      });
      if (filterProvider) params.set("provider", filterProvider);
      if (filterTask)     params.set("task_type", filterTask);
      if (successOnly)    params.set("success_only", "true");

      const res = await fetch(`${API}/llm/logs?${params}`, { headers });
      setLogs(await res.json());
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [filterProvider, filterTask, successOnly, filterHours, page, token]);

  useEffect(() => { fetchLogs(); }, [fetchLogs]);

  const rows = logs?.logs || logs?.items || [];
  const total = logs?.total ?? 0;
  const pages = logs?.pages ?? 1;

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative">
          <select
            value={filterProvider}
            onChange={e => { setFilterProvider(e.target.value); setPage(1); }}
            className="appearance-none rounded-xl border border-slate-200 bg-white py-2 pl-3 pr-8 text-sm text-slate-700 shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
          >
            <option value="">All providers</option>
            {Object.keys(PROVIDER_COLORS).map(p => <option key={p} value={p}>{p}</option>)}
          </select>
          <ChevronDown className="pointer-events-none absolute right-2 top-2.5 h-4 w-4 text-slate-400" />
        </div>

        <div className="relative">
          <select
            value={filterTask}
            onChange={e => { setFilterTask(e.target.value); setPage(1); }}
            className="appearance-none rounded-xl border border-slate-200 bg-white py-2 pl-3 pr-8 text-sm text-slate-700 shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
          >
            <option value="">All task types</option>
            {TASK_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
          <ChevronDown className="pointer-events-none absolute right-2 top-2.5 h-4 w-4 text-slate-400" />
        </div>

        <div className="relative">
          <select
            value={filterHours}
            onChange={e => { setFilterHours(Number(e.target.value)); setPage(1); }}
            className="appearance-none rounded-xl border border-slate-200 bg-white py-2 pl-3 pr-8 text-sm text-slate-700 shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
          >
            {[1, 6, 12, 24, 48, 168].map(h => <option key={h} value={h}>Last {h}h</option>)}
          </select>
          <ChevronDown className="pointer-events-none absolute right-2 top-2.5 h-4 w-4 text-slate-400" />
        </div>

        <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={successOnly}
            onChange={e => { setSuccessOnly(e.target.checked); setPage(1); }}
            className="rounded border-slate-300 text-indigo-600 dark:border-slate-600"
          />
          Success only
        </label>

        <span className="ml-auto text-xs text-slate-400">{total} total</span>
      </div>

      {/* Table */}
      <Card className="overflow-x-auto p-0">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-slate-100 dark:border-slate-800 text-left text-slate-400">
              {["ID","Provider","Model","Task","Latency","Tokens","Cost","Quality","Halluc","Cache","Success","Fallback","Time"].map(h => (
                <th key={h} className="px-3 py-2.5 font-medium whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading
              ? Array.from({ length: 10 }).map((_, i) => (
                  <tr key={i} className="border-b border-slate-50 dark:border-slate-800">
                    {Array.from({ length: 13 }).map((_, j) => (
                      <td key={j} className="px-3 py-2">
                        <div className="h-3 animate-pulse rounded bg-slate-100 dark:bg-slate-700" />
                      </td>
                    ))}
                  </tr>
                ))
              : rows.length
              ? rows.map(row => (
                  <tr key={row.id} className="border-b border-slate-50 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/50">
                    <td className="px-3 py-2 text-slate-400 font-mono">{row.id}</td>
                    <td className="px-3 py-2"><ProviderBadge provider={row.provider} /></td>
                    <td className="px-3 py-2 text-slate-500 max-w-[100px] truncate">{row.model || "—"}</td>
                    <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{row.task_type || "—"}</td>
                    <td className="px-3 py-2 text-slate-500">{row.latency_ms != null ? `${Math.round(row.latency_ms)}ms` : "—"}</td>
                    <td className="px-3 py-2 text-slate-500">{row.tokens != null ? row.tokens.toLocaleString() : "—"}</td>
                    <td className="px-3 py-2 text-slate-500">{row.cost != null ? `$${fmt(row.cost, 5)}` : "—"}</td>
                    <td className="px-3 py-2"><QualityColor value={row.quality} /></td>
                    <td className="px-3 py-2"><HallucinationColor value={row.hallucination} /></td>
                    <td className="px-3 py-2">
                      {row.cache_hit
                        ? <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300">hit</span>
                        : <span className="text-slate-300 dark:text-slate-600">—</span>
                      }
                    </td>
                    <td className="px-3 py-2">
                      {row.success
                        ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                        : <AlertTriangle className="h-3.5 w-3.5 text-rose-500" />
                      }
                    </td>
                    <td className="px-3 py-2">
                      {row.fallback
                        ? <span className="rounded-full bg-amber-100 px-2 py-0.5 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">fallback</span>
                        : <span className="text-slate-300 dark:text-slate-600">—</span>
                      }
                    </td>
                    <td className="px-3 py-2 text-slate-400 whitespace-nowrap">{row.created_at?.slice(0, 16) || "—"}</td>
                  </tr>
                ))
              : (
                <tr>
                  <td colSpan={13} className="px-4 py-10 text-center text-sm text-slate-400">
                    No logs found for the selected filters
                  </td>
                </tr>
              )
            }
          </tbody>
        </table>
      </Card>

      {/* Pagination */}
      {pages > 1 && (
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-400">Page {page} of {pages}</span>
          <div className="flex gap-2">
            <button
              disabled={page <= 1}
              onClick={() => setPage(p => p - 1)}
              className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs disabled:opacity-40 dark:border-slate-700 dark:text-slate-300"
            >
              Prev
            </button>
            <button
              disabled={page >= pages}
              onClick={() => setPage(p => p + 1)}
              className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs disabled:opacity-40 dark:border-slate-700 dark:text-slate-300"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Tab 5: Test ───────────────────────────────────────────────────────────────

function TestTab({ token }) {
  const [prompt, setPrompt]       = useState("");
  const [taskType, setTaskType]   = useState("chat");
  const [provider, setProvider]   = useState("auto");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult]       = useState(null);
  const [error, setError]         = useState(null);

  const headers = {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };

  const handleSubmit = async () => {
    if (!prompt.trim()) return;
    setSubmitting(true);
    setResult(null);
    setError(null);
    try {
      const body = { prompt, task_type: taskType };
      if (provider !== "auto") body.provider = provider;

      const res = await fetch(`${API}/llm/test`, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail || data.error || `HTTP ${res.status}`);
      } else {
        setResult(data);
      }
    } catch (e) {
      setError(e.message || "Request failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6 max-w-3xl">
      <Card>
        <p className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-200">
          <Send className="inline h-4 w-4 mr-1.5 text-indigo-500" />
          Test LLM Endpoint
        </p>

        <div className="space-y-4">
          {/* Prompt */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-500 dark:text-slate-400">Prompt</label>
            <textarea
              value={prompt}
              onChange={e => setPrompt(e.target.value)}
              rows={5}
              placeholder="Enter your prompt here…"
              className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-700 placeholder-slate-400 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-200 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:placeholder-slate-500 dark:focus:ring-indigo-800"
            />
          </div>

          {/* Task type + Provider */}
          <div className="flex flex-wrap gap-4">
            <div className="flex-1 min-w-[160px]">
              <label className="mb-1.5 block text-xs font-medium text-slate-500 dark:text-slate-400">Task Type</label>
              <div className="relative">
                <select
                  value={taskType}
                  onChange={e => setTaskType(e.target.value)}
                  className="w-full appearance-none rounded-xl border border-slate-200 bg-white py-2 pl-3 pr-8 text-sm text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
                >
                  {TASK_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
                <ChevronDown className="pointer-events-none absolute right-2 top-2.5 h-4 w-4 text-slate-400" />
              </div>
            </div>

            <div className="flex-1 min-w-[160px]">
              <label className="mb-1.5 block text-xs font-medium text-slate-500 dark:text-slate-400">Provider (optional)</label>
              <div className="relative">
                <select
                  value={provider}
                  onChange={e => setProvider(e.target.value)}
                  className="w-full appearance-none rounded-xl border border-slate-200 bg-white py-2 pl-3 pr-8 text-sm text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
                >
                  <option value="auto">auto (router decides)</option>
                  {Object.keys(PROVIDER_COLORS).map(p => <option key={p} value={p}>{p}</option>)}
                </select>
                <ChevronDown className="pointer-events-none absolute right-2 top-2.5 h-4 w-4 text-slate-400" />
              </div>
            </div>
          </div>

          <button
            onClick={handleSubmit}
            disabled={submitting || !prompt.trim()}
            className="flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting
              ? <RefreshCw className="h-4 w-4 animate-spin" />
              : <Send className="h-4 w-4" />
            }
            {submitting ? "Running…" : "Send"}
          </button>
        </div>
      </Card>

      {/* Error */}
      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-800 dark:bg-rose-950/30 dark:text-rose-300">
          <AlertTriangle className="inline h-4 w-4 mr-1.5" />
          {error}
        </div>
      )}

      {/* Result */}
      {result && (
        <Card>
          <p className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-200">
            <CheckCircle2 className="inline h-4 w-4 mr-1.5 text-emerald-500" />
            Response
          </p>

          {/* Metadata grid */}
          <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-3 text-xs">
            {[
              { label: "Provider",    value: result.provider    ? <ProviderBadge provider={result.provider} /> : "—" },
              { label: "Model",       value: result.model       || "—" },
              { label: "Latency",     value: result.latency_ms  != null ? `${Math.round(result.latency_ms)}ms` : "—" },
              { label: "Tokens",      value: result.tokens      != null ? result.tokens.toLocaleString() : "—" },
              { label: "Cost",        value: result.cost        != null ? `$${fmt(result.cost, 5)}` : "—" },
              { label: "Quality",     value: result.quality_score != null ? <QualityColor value={result.quality_score} /> : "—" },
            ].map(({ label, value }) => (
              <div key={label} className="rounded-lg bg-slate-50 px-3 py-2 dark:bg-slate-800">
                <p className="text-slate-400 mb-0.5">{label}</p>
                <p className="font-semibold text-slate-700 dark:text-slate-200">{value}</p>
              </div>
            ))}
          </div>

          {/* Output text */}
          <div>
            <p className="mb-1.5 text-xs font-medium text-slate-400">Output</p>
            <div className="rounded-xl bg-slate-50 p-4 text-sm text-slate-700 whitespace-pre-wrap dark:bg-slate-800 dark:text-slate-200 max-h-96 overflow-y-auto">
              {result.text || result.output || result.content || JSON.stringify(result, null, 2)}
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}

// ── Main page component ───────────────────────────────────────────────────────

const TABS = ["Overview", "Metrics", "Quality", "Logs", "Test"];

export default function LLMAdminPage() {
  const { token } = useAuth();
  const headers = { Authorization: `Bearer ${token}` };

  const [activeTab, setActiveTab] = useState("Overview");
  const [hours, setHours]         = useState(24);

  const [status,  setStatus]  = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [quality, setQuality] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);

  const [autoRefresh, setAutoRefresh] = useState(false);
  const [cacheClearing, setCacheClearing] = useState(false);
  const [cacheMsg, setCacheMsg] = useState(null);

  const intervalRef = useRef(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [st, mt, ql] = await Promise.all([
        fetch(`${API}/llm/status`,                    { headers }).then(r => r.json()),
        fetch(`${API}/llm/metrics?hours=${hours}`,    { headers }).then(r => r.json()),
        fetch(`${API}/llm/quality?hours=${hours}`,    { headers }).then(r => r.json()),
      ]);
      setStatus(st);
      setMetrics(mt);
      setQuality(ql);
    } catch (e) {
      setError("Failed to load LLM admin data. Check your connection.");
    } finally {
      setLoading(false);
    }
  }, [hours, token]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  useEffect(() => {
    if (autoRefresh) {
      intervalRef.current = setInterval(fetchAll, 10_000);
    } else {
      clearInterval(intervalRef.current);
    }
    return () => clearInterval(intervalRef.current);
  }, [autoRefresh, fetchAll]);

  const clearCache = async () => {
    setCacheClearing(true);
    setCacheMsg(null);
    try {
      const res = await fetch(`${API}/llm/cache/clear`, { method: "POST", headers });
      const data = await res.json();
      setCacheMsg(data.message || "Cache cleared");
      setTimeout(() => setCacheMsg(null), 4000);
    } catch (e) {
      setCacheMsg("Failed to clear cache");
      setTimeout(() => setCacheMsg(null), 4000);
    } finally {
      setCacheClearing(false);
    }
  };

  return (
    <div className="space-y-6 pb-12">
      {/* ── Header ── */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-slate-800 dark:text-white">
            <Brain className="h-6 w-6 text-indigo-500" />
            AI Provider Admin
          </h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Monitor and manage LLM providers, routing, metrics, and quality
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Cache clear */}
          <button
            onClick={clearCache}
            disabled={cacheClearing}
            className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            <Trash2 className={`h-4 w-4 ${cacheClearing ? "animate-pulse text-rose-500" : ""}`} />
            Clear Cache
          </button>

          {/* Auto-refresh toggle */}
          <button
            onClick={() => setAutoRefresh(v => !v)}
            className={`flex items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-medium transition-colors ${
              autoRefresh
                ? "bg-indigo-600 text-white"
                : "border border-slate-200 bg-white text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
            }`}
          >
            <RefreshCw className={`h-4 w-4 ${autoRefresh ? "animate-spin" : ""}`} />
            {autoRefresh ? "Live" : "Auto"}
          </button>

          {/* Manual refresh */}
          <button
            onClick={fetchAll}
            className="flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
        </div>
      </div>

      {/* Cache message toast */}
      {cacheMsg && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-sm text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-300">
          <CheckCircle2 className="inline h-4 w-4 mr-1.5" />
          {cacheMsg}
        </div>
      )}

      {/* Error banner */}
      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-800 dark:bg-rose-950/30 dark:text-rose-300">
          <AlertTriangle className="inline h-4 w-4 mr-1.5" />
          {error}
        </div>
      )}

      {/* ── Tabs ── */}
      <div className="flex flex-wrap gap-1 rounded-2xl border border-slate-200 bg-white p-1.5 shadow-sm dark:border-slate-700 dark:bg-slate-900">
        {TABS.map(tab => (
          <TabBtn key={tab} active={activeTab === tab} onClick={() => setActiveTab(tab)}>
            {tab === "Overview"  && <Settings  className="inline h-3.5 w-3.5 mr-1.5" />}
            {tab === "Metrics"   && <Zap       className="inline h-3.5 w-3.5 mr-1.5" />}
            {tab === "Quality"   && <CheckCircle2 className="inline h-3.5 w-3.5 mr-1.5" />}
            {tab === "Logs"      && <Brain     className="inline h-3.5 w-3.5 mr-1.5" />}
            {tab === "Test"      && <Send      className="inline h-3.5 w-3.5 mr-1.5" />}
            {tab}
          </TabBtn>
        ))}
      </div>

      {/* ── Tab content ── */}
      {activeTab === "Overview" && (
        <OverviewTab status={status} loading={loading} />
      )}

      {activeTab === "Metrics" && (
        <MetricsTab
          hours={hours}
          setHours={h => { setHours(h); }}
          metrics={metrics}
          loading={loading}
        />
      )}

      {activeTab === "Quality" && (
        <QualityTab quality={quality} loading={loading} />
      )}

      {activeTab === "Logs" && (
        <LogsTab token={token} hours={hours} />
      )}

      {activeTab === "Test" && (
        <TestTab token={token} />
      )}
    </div>
  );
}
