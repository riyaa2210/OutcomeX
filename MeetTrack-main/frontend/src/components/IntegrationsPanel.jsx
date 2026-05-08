import { useState, useEffect, useCallback } from "react";
import {
  ExternalLink,
  RefreshCw,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Trash2,
  Calendar,
  Video,
  CheckSquare,
  Trello,
  FileText,
  Layers,
} from "lucide-react";
import useAuth from "../context/useAuth";

const API =
  import.meta.env.VITE_API_URL ||
  "https://meeting-outcome-tracker-backend.onrender.com";

const PROVIDERS = [
  {
    id: "google_calendar",
    name: "Google Calendar",
    description: "Sync meetings and create reminders",
    icon: Calendar,
    color: "#4285F4",
    category: "calendar",
  },
  {
    id: "zoom",
    name: "Zoom",
    description: "Fetch meetings and recordings",
    icon: Video,
    color: "#2D8CFF",
    category: "calendar",
  },
  {
    id: "microsoft_teams",
    name: "Microsoft Teams",
    description: "Sync Teams meetings and events",
    icon: Video,
    color: "#6264A7",
    category: "calendar",
  },
  {
    id: "google_tasks",
    name: "Google Tasks",
    description: "Push action items as tasks",
    icon: CheckSquare,
    color: "#0F9D58",
    category: "tasks",
  },
  {
    id: "trello",
    name: "Trello",
    description: "Create cards for action items",
    icon: Layers,
    color: "#0052CC",
    category: "tasks",
  },
  {
    id: "notion",
    name: "Notion",
    description: "Add action items to Notion database",
    icon: FileText,
    color: "#000000",
    category: "tasks",
  },
  {
    id: "jira",
    name: "Jira",
    description: "Create Jira issues for action items",
    icon: Layers,
    color: "#0052CC",
    category: "tasks",
  },
];

// ─── Toast ────────────────────────────────────────────────────────────────────

function Toast({ toasts, onDismiss }) {
  return (
    <div className="fixed right-4 top-4 z-50 flex flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`flex items-center gap-2 rounded-xl px-4 py-3 text-sm font-medium shadow-lg transition-all ${
            t.type === "success"
              ? "bg-emerald-600 text-white"
              : "bg-rose-600 text-white"
          }`}
        >
          {t.type === "success" ? (
            <CheckCircle2 size={16} />
          ) : (
            <XCircle size={16} />
          )}
          <span>{t.message}</span>
          <button
            onClick={() => onDismiss(t.id)}
            className="ml-2 opacity-70 hover:opacity-100"
            aria-label="Dismiss notification"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}

// ─── Section title ─────────────────────────────────────────────────────────────

function SectionTitle({ children }) {
  return (
    <h3 className="mb-3 text-xs font-semibold uppercase tracking-widest text-slate-400 dark:text-slate-500">
      {children}
    </h3>
  );
}

// ─── Spinner ──────────────────────────────────────────────────────────────────

function Spinner({ size = 14 }) {
  return (
    <svg
      className="animate-spin"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
      />
    </svg>
  );
}

// ─── Integration card ─────────────────────────────────────────────────────────

function IntegrationCard({
  provider,
  integration,
  isConnecting,
  isDisconnecting,
  onConnect,
  onDisconnect,
}) {
  const Icon = provider.icon;
  const connected = !!integration;
  const busy = isConnecting || isDisconnecting;

  const formattedDate = integration?.last_synced_at
    ? new Date(integration.last_synced_at).toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : null;

  return (
    <div className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
      {/* Left: icon + info */}
      <div className="flex items-center gap-3">
        <div
          className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full"
          style={{ backgroundColor: provider.color + "1A" }}
          aria-hidden="true"
        >
          <Icon size={20} style={{ color: provider.color }} />
        </div>
        <div>
          <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">
            {provider.name}
          </p>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {provider.description}
          </p>
          {connected && (
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
                <CheckCircle2 size={11} />
                Connected
              </span>
              {integration.provider_email && (
                <span className="text-xs text-slate-400 dark:text-slate-500">
                  {integration.provider_email}
                </span>
              )}
              {formattedDate && (
                <span className="text-xs text-slate-400 dark:text-slate-500">
                  · Last synced {formattedDate}
                </span>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Right: action button */}
      <div className="ml-4 flex-shrink-0">
        {connected ? (
          <button
            onClick={() => onDisconnect(provider.id)}
            disabled={busy}
            className="inline-flex items-center gap-1.5 rounded-lg border border-rose-200 px-3 py-1.5 text-xs font-medium text-rose-600 transition hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-rose-800 dark:text-rose-400 dark:hover:bg-rose-900/20"
            aria-label={`Disconnect ${provider.name}`}
          >
            {isDisconnecting ? (
              <Spinner size={12} />
            ) : (
              <Trash2 size={12} />
            )}
            Disconnect
          </button>
        ) : (
          <button
            onClick={() => onConnect(provider.id)}
            disabled={busy}
            className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
            aria-label={`Connect ${provider.name}`}
          >
            {isConnecting ? (
              <Spinner size={12} />
            ) : (
              <ExternalLink size={12} />
            )}
            Connect
          </button>
        )}
      </div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function IntegrationsPanel() {
  const { user } = useAuth();

  const [integrations, setIntegrations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState(null);
  const [auditLogs, setAuditLogs] = useState([]);
  const [showAudit, setShowAudit] = useState(false);
  const [connectingProvider, setConnectingProvider] = useState(null);
  const [disconnectingProvider, setDisconnectingProvider] = useState(null);
  const [toasts, setToasts] = useState([]);

  // ── Helpers ────────────────────────────────────────────────────────────────

  const getToken = () => localStorage.getItem("access_token") || "";

  const addToast = useCallback((message, type = "success") => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  }, []);

  const dismissToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  // ── Fetch integrations ─────────────────────────────────────────────────────

  const fetchIntegrations = useCallback(async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API}/integrations`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!res.ok) throw new Error("Failed to load integrations");
      const data = await res.json();
      setIntegrations(Array.isArray(data) ? data : []);
    } catch (err) {
      addToast(err.message || "Could not load integrations", "error");
    } finally {
      setLoading(false);
    }
  }, [addToast]);

  // ── On mount: load integrations + handle OAuth callback params ─────────────

  useEffect(() => {
    fetchIntegrations();

    const params = new URLSearchParams(window.location.search);
    const success = params.get("integration_success");
    const error = params.get("integration_error");

    if (success) {
      addToast(`${success} connected successfully`, "success");
      // Clean up URL without reloading
      const clean = new URL(window.location.href);
      clean.searchParams.delete("integration_success");
      window.history.replaceState({}, "", clean.toString());
    } else if (error) {
      addToast(`Integration error: ${error}`, "error");
      const clean = new URL(window.location.href);
      clean.searchParams.delete("integration_error");
      window.history.replaceState({}, "", clean.toString());
    }
  }, [fetchIntegrations, addToast]);

  // ── Connect ────────────────────────────────────────────────────────────────

  const handleConnect = useCallback(
    async (providerId) => {
      try {
        setConnectingProvider(providerId);
        const res = await fetch(
          `${API}/integrations/oauth/${providerId}/authorize`,
          { headers: { Authorization: `Bearer ${getToken()}` } }
        );
        if (!res.ok) throw new Error("Could not get authorization URL");
        const { url } = await res.json();
        window.open(url, "_blank", "noopener,noreferrer");
      } catch (err) {
        addToast(err.message || "Failed to start OAuth flow", "error");
      } finally {
        setConnectingProvider(null);
      }
    },
    [addToast]
  );

  // ── Disconnect ─────────────────────────────────────────────────────────────

  const handleDisconnect = useCallback(
    async (providerId) => {
      try {
        setDisconnectingProvider(providerId);
        const res = await fetch(`${API}/integrations/${providerId}`, {
          method: "DELETE",
          headers: { Authorization: `Bearer ${getToken()}` },
        });
        if (!res.ok) throw new Error("Failed to disconnect integration");
        addToast("Integration disconnected", "success");
        await fetchIntegrations();
      } catch (err) {
        addToast(err.message || "Failed to disconnect", "error");
      } finally {
        setDisconnectingProvider(null);
      }
    },
    [addToast, fetchIntegrations]
  );

  // ── Sync calendar ──────────────────────────────────────────────────────────

  const handleSyncCalendar = useCallback(async () => {
    try {
      setSyncing(true);
      setSyncResult(null);
      const res = await fetch(`${API}/integrations/sync/calendar`, {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!res.ok) throw new Error("Calendar sync failed");
      const data = await res.json();
      setSyncResult({ success: true, data });
      addToast(
        `Synced ${data.new_meetings ?? data.synced ?? 0} new meetings`,
        "success"
      );
    } catch (err) {
      setSyncResult({ success: false, error: err.message });
      addToast(err.message || "Sync failed", "error");
    } finally {
      setSyncing(false);
    }
  }, [addToast]);

  // ── Audit logs ─────────────────────────────────────────────────────────────

  const loadAuditLogs = useCallback(async () => {
    try {
      const res = await fetch(`${API}/integrations/audit?days=7`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!res.ok) throw new Error("Failed to load audit logs");
      const data = await res.json();
      setAuditLogs(Array.isArray(data) ? data.slice(0, 10) : []);
    } catch (err) {
      addToast(err.message || "Could not load audit logs", "error");
    }
  }, [addToast]);

  const handleToggleAudit = useCallback(() => {
    if (!showAudit) loadAuditLogs();
    setShowAudit((prev) => !prev);
  }, [showAudit, loadAuditLogs]);

  // ── Derived data ───────────────────────────────────────────────────────────

  const getIntegration = (providerId) =>
    integrations.find((i) => i.provider === providerId) || null;

  const calendarProviders = PROVIDERS.filter((p) => p.category === "calendar");
  const taskProviders = PROVIDERS.filter((p) => p.category === "tasks");

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <>
      <Toast toasts={toasts} onDismiss={dismissToast} />

      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100">
            Integrations
          </h2>
          <button
            onClick={fetchIntegrations}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:text-slate-400 dark:hover:bg-slate-800"
            aria-label="Refresh integrations"
          >
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>

        {/* Calendar & Meeting Platforms */}
        <div>
          <SectionTitle>Calendar &amp; Meeting Platforms</SectionTitle>
          <div className="space-y-3">
            {calendarProviders.map((provider) => (
              <IntegrationCard
                key={provider.id}
                provider={provider}
                integration={getIntegration(provider.id)}
                isConnecting={connectingProvider === provider.id}
                isDisconnecting={disconnectingProvider === provider.id}
                onConnect={handleConnect}
                onDisconnect={handleDisconnect}
              />
            ))}
          </div>

          {/* Sync Calendar button */}
          <div className="mt-4 flex items-center gap-3">
            <button
              onClick={handleSyncCalendar}
              disabled={syncing}
              className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {syncing ? (
                <Spinner size={14} />
              ) : (
                <RefreshCw size={14} />
              )}
              {syncing ? "Syncing…" : "Sync Calendar"}
            </button>

            {syncResult && (
              <span
                className={`flex items-center gap-1 text-sm ${
                  syncResult.success
                    ? "text-emerald-600 dark:text-emerald-400"
                    : "text-rose-600 dark:text-rose-400"
                }`}
              >
                {syncResult.success ? (
                  <>
                    <CheckCircle2 size={14} />
                    Synced{" "}
                    {syncResult.data?.new_meetings ??
                      syncResult.data?.synced ??
                      0}{" "}
                    new meetings
                  </>
                ) : (
                  <>
                    <AlertTriangle size={14} />
                    {syncResult.error}
                  </>
                )}
              </span>
            )}
          </div>
        </div>

        {/* Task Management */}
        <div>
          <SectionTitle>Task Management</SectionTitle>
          <div className="space-y-3">
            {taskProviders.map((provider) => (
              <IntegrationCard
                key={provider.id}
                provider={provider}
                integration={getIntegration(provider.id)}
                isConnecting={connectingProvider === provider.id}
                isDisconnecting={disconnectingProvider === provider.id}
                onConnect={handleConnect}
                onDisconnect={handleDisconnect}
              />
            ))}
          </div>
        </div>

        {/* Audit Log */}
        <div>
          <button
            onClick={handleToggleAudit}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-indigo-600 hover:text-indigo-700 dark:text-indigo-400 dark:hover:text-indigo-300"
          >
            <FileText size={14} />
            {showAudit ? "Hide Audit Log" : "View Audit Log"}
          </button>

          {showAudit && (
            <div className="mt-3 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900">
              {auditLogs.length === 0 ? (
                <p className="px-4 py-6 text-center text-sm text-slate-400 dark:text-slate-500">
                  No audit events in the last 7 days.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-slate-100 dark:border-slate-800">
                        <th className="px-4 py-2.5 font-semibold text-slate-500 dark:text-slate-400">
                          Provider
                        </th>
                        <th className="px-4 py-2.5 font-semibold text-slate-500 dark:text-slate-400">
                          Action
                        </th>
                        <th className="px-4 py-2.5 font-semibold text-slate-500 dark:text-slate-400">
                          Status
                        </th>
                        <th className="px-4 py-2.5 font-semibold text-slate-500 dark:text-slate-400">
                          Details
                        </th>
                        <th className="px-4 py-2.5 font-semibold text-slate-500 dark:text-slate-400">
                          Time
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {auditLogs.map((log, idx) => (
                        <tr
                          key={log.id ?? idx}
                          className="border-b border-slate-50 last:border-0 dark:border-slate-800"
                        >
                          <td className="px-4 py-2.5 font-medium text-slate-700 dark:text-slate-300">
                            {PROVIDERS.find((p) => p.id === log.provider)
                              ?.name ?? log.provider}
                          </td>
                          <td className="px-4 py-2.5 text-slate-600 dark:text-slate-400">
                            {log.action}
                          </td>
                          <td className="px-4 py-2.5">
                            {log.success ? (
                              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
                                <CheckCircle2 size={10} />
                                OK
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 rounded-full bg-rose-100 px-2 py-0.5 text-xs font-medium text-rose-700 dark:bg-rose-900/40 dark:text-rose-300">
                                <XCircle size={10} />
                                Failed
                              </span>
                            )}
                          </td>
                          <td className="max-w-[200px] truncate px-4 py-2.5 text-slate-500 dark:text-slate-400">
                            {log.error_message ?? "—"}
                          </td>
                          <td className="whitespace-nowrap px-4 py-2.5 text-slate-400 dark:text-slate-500">
                            {log.created_at
                              ? new Date(log.created_at).toLocaleString(
                                  undefined,
                                  { dateStyle: "short", timeStyle: "short" }
                                )
                              : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
