/**
 * LiveMeetingPage — Real-time collaborative AI meeting assistant
 *
 * Features:
 *   - Live transcript input (type or paste chunks)
 *   - Real-time AI summary / decisions / action items
 *   - AI suggestions (blockers, missing deadlines, etc.)
 *   - Collaborative notes
 *   - Task assignment
 *   - Speaker activity tracker
 *   - Participant list
 *   - Snapshot indicator
 */
import { useState, useRef, useEffect } from "react";
import { AnimatePresence, motion as M } from "framer-motion";
import {
  AlertTriangle, CheckCircle2, Clock, Lightbulb,
  Loader2, MessageSquare, Mic, MicOff, Plus,
  Send, Sparkles, Target, Users, Wifi, WifiOff, X,
} from "lucide-react";
import { useParams, useNavigate } from "react-router-dom";
import { useLiveMeeting } from "../hooks/useLiveMeeting";
import useAuth from "../context/useAuth";
import { easeSoft } from "../lib/motionPresets";

/* ── helpers ─────────────────────────────────────────────── */
const AVATAR_COLORS = ["#6366f1","#0891b2","#059669","#d97706","#be185d","#7c3aed"];
const avColor = n => AVATAR_COLORS[(n?.charCodeAt(0) || 65) % AVATAR_COLORS.length];
const ini = n => (n || "?").trim().split(/\s+/).map(w => w[0]).join("").toUpperCase().slice(0,2);

/* ── suggestion banner ───────────────────────────────────── */
function SuggestionBanner({ suggestion, onDismiss }) {
  const icons = {
    unassigned_tasks:  { icon: Target,       color: "#f59e0b", bg: "rgba(245,158,11,0.1)"  },
    missing_deadlines: { icon: Clock,        color: "#6366f1", bg: "rgba(99,102,241,0.1)"  },
    blocker_detected:  { icon: AlertTriangle, color: "#ef4444", bg: "rgba(239,68,68,0.1)"  },
    no_decisions:      { icon: Lightbulb,    color: "#06b6d4", bg: "rgba(6,182,212,0.1)"   },
  };
  const meta = icons[suggestion.type] || icons.no_decisions;
  const Icon = meta.icon;

  return (
    <M.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 20 }}
      transition={{ duration: 0.3, ease: easeSoft }}
      className="flex items-start gap-3 rounded-xl px-4 py-3"
      style={{ background: meta.bg, border: `1px solid ${meta.color}30` }}
    >
      <Icon className="h-4 w-4 flex-shrink-0 mt-0.5" style={{ color: meta.color }} />
      <p className="flex-1 text-xs font-medium text-slate-700 dark:text-slate-300">
        {suggestion.message}
      </p>
      <button onClick={() => onDismiss(suggestion.id)}
        className="text-slate-400 hover:text-slate-600 transition-colors">
        <X className="h-3.5 w-3.5" />
      </button>
    </M.div>
  );
}

/* ── action item card ────────────────────────────────────── */
function LiveActionCard({ item, index }) {
  const conf = item.confidence_score ?? 0.8;
  const color = conf >= 0.8 ? "#34d399" : conf >= 0.5 ? "#fbbf24" : "#94a3b8";
  return (
    <M.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: easeSoft, delay: index * 0.04 }}
      className="flex items-start gap-2.5 rounded-xl border border-slate-100 bg-white p-3 dark:border-slate-700/40 dark:bg-slate-800/40"
    >
      <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg text-[10px] font-bold text-white"
        style={{ background: avColor(item.assignee || "?") }}>
        {ini(item.assignee || "?")}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-xs font-semibold text-slate-800 dark:text-slate-200 leading-snug">
          {item.task || item.description || "Action item"}
        </p>
        <div className="mt-1 flex items-center gap-2">
          <span className="text-[10px] text-slate-500">{item.assignee || "Unassigned"}</span>
          {item.deadline && (
            <span className="flex items-center gap-0.5 text-[10px] text-amber-600">
              <Clock className="h-2.5 w-2.5" />{item.deadline}
            </span>
          )}
          <span className="ml-auto text-[10px] font-semibold" style={{ color }}>
            {Math.round(conf * 100)}%
          </span>
        </div>
      </div>
    </M.div>
  );
}

/* ── main page ───────────────────────────────────────────── */
export default function LiveMeetingPage() {
  const { meetingId } = useParams();
  const { user }      = useAuth();
  const navigate      = useNavigate();

  const {
    connected, participants, transcript, summary,
    decisions, actionItems, suggestions, notes,
    speakerActivity, snapshotSaved, wordCount, error,
    sendChunk, sendNote, sendTaskAssignment, endMeeting, dismissSuggestion,
  } = useLiveMeeting(meetingId, user?.full_name || user?.email);

  const [inputText,    setInputText]    = useState("");
  const [speaker,      setSpeaker]      = useState(user?.full_name?.split(" ")[0] || "Me");
  const [noteText,     setNoteText]     = useState("");
  const [taskText,     setTaskText]     = useState("");
  const [taskAssignee, setTaskAssignee] = useState("");
  const [activeTab,    setActiveTab]    = useState("transcript");
  const [isRecording,  setIsRecording]  = useState(false);
  const txEndRef = useRef(null);

  useEffect(() => {
    txEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [transcript]);

  function handleSendChunk(e) {
    e.preventDefault();
    if (!inputText.trim()) return;
    sendChunk(inputText.trim(), speaker || null);
    setInputText("");
  }

  function handleSendNote(e) {
    e.preventDefault();
    if (!noteText.trim()) return;
    sendNote(noteText.trim());
    setNoteText("");
  }

  function handleAssignTask(e) {
    e.preventDefault();
    if (!taskText.trim() || !taskAssignee.trim()) return;
    sendTaskAssignment(taskText.trim(), taskAssignee.trim());
    setTaskText("");
    setTaskAssignee("");
  }

  const TABS = [
    { id: "transcript", label: "Transcript", count: wordCount ? `${wordCount}w` : null },
    { id: "ai",         label: "AI Insights", count: actionItems.length || null },
    { id: "notes",      label: "Notes",       count: notes.length || null },
    { id: "tasks",      label: "Assign Task"  },
  ];

  return (
    <div className="flex h-[calc(100vh-80px)] flex-col gap-4">

      {/* ── header ── */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <div className={`flex h-3 w-3 rounded-full ${connected ? "bg-emerald-400 animate-pulse" : "bg-slate-400"}`} />
          <h1 className="text-xl font-black text-slate-900 dark:text-slate-100">
            Live Meeting #{meetingId}
          </h1>
          {connected
            ? <span className="flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-bold text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"><Wifi className="h-3 w-3" /> Live</span>
            : <span className="flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-bold text-slate-500 dark:bg-slate-800"><WifiOff className="h-3 w-3" /> Connecting…</span>
          }
          {snapshotSaved && (
            <span className="text-[10px] text-slate-400">
              Saved {new Date(snapshotSaved).toLocaleTimeString()}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Participants */}
          <div className="flex items-center gap-1">
            {participants.slice(0, 4).map(p => (
              <div key={p.user_id} title={p.user_name}
                className="flex h-7 w-7 items-center justify-center rounded-full text-[10px] font-bold text-white ring-2 ring-white dark:ring-slate-900"
                style={{ background: avColor(p.user_name) }}>
                {ini(p.user_name)}
              </div>
            ))}
            {participants.length > 4 && (
              <span className="text-xs text-slate-500">+{participants.length - 4}</span>
            )}
          </div>

          <button onClick={() => { endMeeting(); navigate("/history"); }}
            className="rounded-xl border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-bold text-red-600 hover:bg-red-100 transition-colors dark:border-red-800/40 dark:bg-red-950/30 dark:text-red-400">
            End Meeting
          </button>
        </div>
      </div>

      {/* ── error ── */}
      {error && (
        <div className="rounded-xl bg-red-50 px-4 py-2 text-sm text-red-600 dark:bg-red-950/30 dark:text-red-400">
          {error}
        </div>
      )}

      {/* ── suggestions ── */}
      <AnimatePresence>
        {suggestions.map(s => (
          <SuggestionBanner key={s.id} suggestion={s} onDismiss={dismissSuggestion} />
        ))}
      </AnimatePresence>

      {/* ── main layout ── */}
      <div className="flex flex-1 gap-4 overflow-hidden">

        {/* LEFT — input + tabs */}
        <div className="flex w-full flex-col gap-3 lg:w-3/5">

          {/* tab bar */}
          <div className="flex gap-1 rounded-xl bg-slate-100 p-1 dark:bg-slate-800/60">
            {TABS.map(t => (
              <button key={t.id} onClick={() => setActiveTab(t.id)}
                className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg py-1.5 text-xs font-semibold transition-all
                  ${activeTab === t.id
                    ? "bg-white text-slate-900 shadow-sm dark:bg-slate-700 dark:text-slate-100"
                    : "text-slate-500 hover:text-slate-700 dark:text-slate-400"
                  }`}>
                {t.label}
                {t.count != null && (
                  <span className="rounded-full bg-indigo-100 px-1.5 py-0.5 text-[10px] font-bold text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300">
                    {t.count}
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* tab content */}
          <div className="flex flex-1 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white dark:border-slate-700/60 dark:bg-slate-900/60">

            {/* TRANSCRIPT TAB */}
            {activeTab === "transcript" && (
              <>
                <div className="flex-1 overflow-y-auto p-4">
                  {transcript ? (
                    <pre className="whitespace-pre-wrap text-xs leading-relaxed text-slate-700 dark:text-slate-300 font-mono">
                      {transcript}
                    </pre>
                  ) : (
                    <div className="flex h-full items-center justify-center text-slate-400 text-sm">
                      Start typing or paste transcript chunks below…
                    </div>
                  )}
                  <div ref={txEndRef} />
                </div>
                <div className="border-t border-slate-100 p-3 dark:border-slate-700/40">
                  <form onSubmit={handleSendChunk} className="space-y-2">
                    <div className="flex gap-2">
                      <input value={speaker} onChange={e => setSpeaker(e.target.value)}
                        placeholder="Speaker"
                        className="w-24 rounded-lg border border-slate-200 bg-slate-50 px-2 py-1.5 text-xs outline-none focus:border-indigo-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200" />
                      <textarea value={inputText} onChange={e => setInputText(e.target.value)}
                        onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSendChunk(e); }}}
                        placeholder="Type or paste transcript chunk… (Enter to send)"
                        rows={2}
                        className="flex-1 resize-none rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs outline-none focus:border-indigo-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200" />
                      <button type="submit" disabled={!inputText.trim() || !connected}
                        className="flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-bold text-white disabled:opacity-40"
                        style={{ background: "linear-gradient(135deg, #4338ca, #0e7490)" }}>
                        <Send className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </form>
                </div>
              </>
            )}

            {/* NOTES TAB */}
            {activeTab === "notes" && (
              <>
                <div className="flex-1 overflow-y-auto p-4 space-y-2">
                  {notes.length === 0 && (
                    <p className="text-center text-sm text-slate-400 py-8">No notes yet</p>
                  )}
                  {notes.map((n, i) => (
                    <M.div key={i} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                      className="rounded-xl border border-slate-100 bg-slate-50 p-3 dark:border-slate-700/40 dark:bg-slate-800/40">
                      <div className="flex items-center gap-2 mb-1">
                        <div className="h-5 w-5 rounded-full flex items-center justify-center text-[9px] font-bold text-white"
                          style={{ background: avColor(n.user_name) }}>{ini(n.user_name)}</div>
                        <span className="text-[10px] font-semibold text-slate-600 dark:text-slate-400">{n.user_name}</span>
                        <span className="ml-auto text-[10px] text-slate-400">
                          {new Date(n.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                      <p className="text-xs text-slate-700 dark:text-slate-300">{n.text}</p>
                    </M.div>
                  ))}
                </div>
                <div className="border-t border-slate-100 p-3 dark:border-slate-700/40">
                  <form onSubmit={handleSendNote} className="flex gap-2">
                    <input value={noteText} onChange={e => setNoteText(e.target.value)}
                      placeholder="Add a note…"
                      className="flex-1 rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs outline-none focus:border-indigo-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200" />
                    <button type="submit" disabled={!noteText.trim() || !connected}
                      className="rounded-lg px-3 py-1.5 text-xs font-bold text-white disabled:opacity-40"
                      style={{ background: "linear-gradient(135deg, #4338ca, #0e7490)" }}>
                      <Plus className="h-3.5 w-3.5" />
                    </button>
                  </form>
                </div>
              </>
            )}

            {/* ASSIGN TASK TAB */}
            {activeTab === "tasks" && (
              <div className="flex-1 p-4">
                <form onSubmit={handleAssignTask} className="space-y-3">
                  <div>
                    <label className="mb-1 block text-xs font-bold uppercase tracking-wider text-slate-500">Task</label>
                    <textarea value={taskText} onChange={e => setTaskText(e.target.value)}
                      placeholder="Describe the task…" rows={3}
                      className="w-full resize-none rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm outline-none focus:border-indigo-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200" />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-bold uppercase tracking-wider text-slate-500">Assign to</label>
                    <input value={taskAssignee} onChange={e => setTaskAssignee(e.target.value)}
                      placeholder="Person's name or email"
                      className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm outline-none focus:border-indigo-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200" />
                  </div>
                  <button type="submit" disabled={!taskText.trim() || !taskAssignee.trim() || !connected}
                    className="w-full rounded-xl py-2.5 text-sm font-bold text-white disabled:opacity-40"
                    style={{ background: "linear-gradient(135deg, #059669, #0d9488)" }}>
                    Assign Task to Room
                  </button>
                </form>
              </div>
            )}

            {/* AI INSIGHTS TAB */}
            {activeTab === "ai" && (
              <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {!summary && !decisions.length && !actionItems.length && (
                  <div className="flex flex-col items-center gap-3 py-8 text-center">
                    <Loader2 className="h-6 w-6 animate-spin text-indigo-400" />
                    <p className="text-sm text-slate-400">AI insights appear as the meeting progresses…</p>
                  </div>
                )}
                {summary && (
                  <div className="rounded-xl bg-indigo-50 p-3 dark:bg-indigo-950/30">
                    <p className="mb-1 text-[10px] font-black uppercase tracking-widest text-indigo-500">Summary</p>
                    <p className="text-xs leading-relaxed text-slate-700 dark:text-slate-300">{summary}</p>
                  </div>
                )}
                {decisions.length > 0 && (
                  <div>
                    <p className="mb-2 text-[10px] font-black uppercase tracking-widest text-cyan-500">Decisions</p>
                    <ul className="space-y-1">
                      {decisions.map((d, i) => (
                        <li key={i} className="flex items-start gap-2 text-xs text-slate-700 dark:text-slate-300">
                          <CheckCircle2 className="h-3.5 w-3.5 flex-shrink-0 mt-0.5 text-cyan-500" />
                          {d}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* RIGHT — live action items + speaker activity */}
        <div className="hidden lg:flex lg:w-2/5 flex-col gap-3">

          {/* Action items */}
          <div className="flex-1 overflow-hidden rounded-2xl border border-slate-200 bg-white dark:border-slate-700/60 dark:bg-slate-900/60">
            <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3 dark:border-slate-700/40">
              <div className="flex items-center gap-2">
                <Target className="h-4 w-4 text-emerald-500" />
                <p className="text-xs font-black uppercase tracking-widest text-slate-500">Live Action Items</p>
              </div>
              <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400">
                {actionItems.length}
              </span>
            </div>
            <div className="overflow-y-auto p-3 space-y-2" style={{ maxHeight: "calc(50% - 48px)" }}>
              <AnimatePresence>
                {actionItems.length === 0 && (
                  <p className="text-center text-xs text-slate-400 py-4">Action items appear here in real time</p>
                )}
                {actionItems.map((item, i) => (
                  <LiveActionCard key={i} item={item} index={i} />
                ))}
              </AnimatePresence>
            </div>
          </div>

          {/* Speaker activity */}
          <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700/60 dark:bg-slate-900/60">
            <div className="flex items-center gap-2 mb-3">
              <Users className="h-4 w-4 text-indigo-400" />
              <p className="text-xs font-black uppercase tracking-widest text-slate-500">Speaker Activity</p>
            </div>
            {Object.keys(speakerActivity).length === 0 ? (
              <p className="text-xs text-slate-400 text-center py-2">No speakers yet</p>
            ) : (
              <div className="space-y-2">
                {Object.entries(speakerActivity)
                  .sort(([,a],[,b]) => b - a)
                  .map(([name, words]) => {
                    const total = Object.values(speakerActivity).reduce((s,v) => s+v, 0);
                    const pct   = total ? Math.round((words / total) * 100) : 0;
                    return (
                      <div key={name}>
                        <div className="flex items-center justify-between mb-0.5">
                          <span className="text-xs font-semibold text-slate-700 dark:text-slate-300">{name}</span>
                          <span className="text-[10px] text-slate-400">{words}w · {pct}%</span>
                        </div>
                        <div className="h-1.5 w-full rounded-full bg-slate-100 dark:bg-slate-800">
                          <M.div className="h-full rounded-full"
                            style={{ background: avColor(name) }}
                            initial={{ width: 0 }}
                            animate={{ width: `${pct}%` }}
                            transition={{ duration: 0.5 }} />
                        </div>
                      </div>
                    );
                  })}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
