/**
 * AskMeetingsPage — Chat-style RAG interface
 *
 * Users can ask natural language questions about their meetings:
 *   "What tasks were assigned to Alice?"
 *   "Which meetings discussed JWT auth?"
 *   "What decisions were made last week?"
 *
 * Each answer shows source citations with meeting title + excerpt.
 */
import { useState, useRef, useEffect } from "react";
import { AnimatePresence, motion as M } from "framer-motion";
import {
  BookOpen, ChevronDown, ChevronUp, Clock,
  Loader2, MessageSquare, Search, Send, Sparkles, X,
} from "lucide-react";
import { easeSoft } from "../lib/motionPresets";

const API   = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
const auth  = () => ({ Authorization: `Bearer ${localStorage.getItem("access_token")}` });

/* ── suggested queries ───────────────────────────────────────────────────── */
const SUGGESTIONS = [
  "What tasks were assigned to Alice?",
  "Which meetings discussed authentication?",
  "What decisions were made about deployment?",
  "Summarise all action items from recent meetings",
  "Who is responsible for the frontend work?",
  "What bugs were mentioned in meetings?",
];

/* ── confidence badge ────────────────────────────────────────────────────── */
function ConfidenceBadge({ score }) {
  const pct = Math.round(score * 100);
  const color = score >= 0.7 ? "#34d399" : score >= 0.4 ? "#fbbf24" : "#f87171";
  return (
    <span className="flex items-center gap-1 text-xs font-semibold"
      style={{ color }}>
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} />
      {pct}% confidence
    </span>
  );
}

/* ── source citation card ────────────────────────────────────────────────── */
function SourceCard({ source, index }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border text-xs overflow-hidden"
      style={{ borderColor: "rgba(99,102,241,0.2)", background: "rgba(99,102,241,0.04)" }}>
      <button onClick={() => setOpen(v => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-indigo-50/50 dark:hover:bg-indigo-950/20">
        <BookOpen className="h-3 w-3 flex-shrink-0 text-indigo-400" />
        <span className="flex-1 font-semibold text-slate-700 dark:text-slate-300 truncate">
          {source.meeting_title}
        </span>
        <span className="rounded-full px-1.5 py-0.5 text-[10px] font-bold"
          style={{ background: "rgba(99,102,241,0.12)", color: "#818cf8" }}>
          {source.chunk_type}
        </span>
        {open ? <ChevronUp className="h-3 w-3 text-slate-400" /> : <ChevronDown className="h-3 w-3 text-slate-400" />}
      </button>
      <AnimatePresence>
        {open && (
          <M.div key="body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden">
            <p className="px-3 pb-3 text-slate-600 dark:text-slate-400 leading-relaxed">
              {source.excerpt}
            </p>
          </M.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ── message bubble ──────────────────────────────────────────────────────── */
function MessageBubble({ msg, index }) {
  const isUser = msg.role === "user";
  const [showSources, setShowSources] = useState(false);

  return (
    <M.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: easeSoft, delay: index * 0.03 }}
      className={`flex gap-3 ${isUser ? "flex-row-reverse" : "flex-row"}`}
    >
      {/* avatar */}
      <div className={`flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-xl text-xs font-bold
        ${isUser
          ? "bg-gradient-to-br from-indigo-500 to-violet-600 text-white"
          : "bg-gradient-to-br from-emerald-500 to-teal-600 text-white"
        }`}>
        {isUser ? "You" : "AI"}
      </div>

      <div className={`flex-1 max-w-[85%] space-y-2 ${isUser ? "items-end" : "items-start"} flex flex-col`}>
        {/* bubble */}
        <div className={`rounded-2xl px-4 py-3 text-sm leading-relaxed
          ${isUser
            ? "bg-gradient-to-br from-indigo-600 to-violet-600 text-white rounded-tr-sm"
            : "bg-white dark:bg-slate-800/80 text-slate-800 dark:text-slate-200 border border-slate-200 dark:border-slate-700/60 rounded-tl-sm shadow-sm"
          }`}>
          {msg.content}
        </div>

        {/* metadata row */}
        {!isUser && (
          <div className="flex items-center gap-3 px-1">
            {msg.confidence != null && <ConfidenceBadge score={msg.confidence} />}
            {msg.sources?.length > 0 && (
              <button onClick={() => setShowSources(v => !v)}
                className="flex items-center gap-1 text-xs font-semibold text-indigo-500 hover:text-indigo-700 transition-colors">
                <BookOpen className="h-3 w-3" />
                {msg.sources.length} source{msg.sources.length !== 1 ? "s" : ""}
                {showSources ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
              </button>
            )}
            {msg.timestamp && (
              <span className="flex items-center gap-1 text-[10px] text-slate-400">
                <Clock className="h-2.5 w-2.5" />
                {msg.timestamp}
              </span>
            )}
          </div>
        )}

        {/* sources */}
        <AnimatePresence>
          {showSources && msg.sources?.length > 0 && (
            <M.div key="sources"
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              className="w-full space-y-1.5">
              {msg.sources.map((s, i) => (
                <SourceCard key={i} source={s} index={i} />
              ))}
            </M.div>
          )}
        </AnimatePresence>
      </div>
    </M.div>
  );
}

/* ── main page ───────────────────────────────────────────────────────────── */
export default function AskMeetingsPage() {
  const [messages,  setMessages]  = useState([]);
  const [input,     setInput]     = useState("");
  const [loading,   setLoading]   = useState(false);
  const [history,   setHistory]   = useState([]);
  const [showHist,  setShowHist]  = useState(false);
  const bottomRef = useRef(null);
  const inputRef  = useRef(null);

  // Load query history on mount
  useEffect(() => {
    fetch(`${API}/rag/query-history?limit=10`, { headers: auth() })
      .then(r => r.ok ? r.json() : [])
      .then(setHistory)
      .catch(() => {});
  }, []);

  // Scroll to bottom on new message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function sendQuery(query) {
    if (!query.trim() || loading) return;

    const userMsg = {
      role:      "user",
      content:   query.trim(),
      timestamp: new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" }),
    };
    setMessages(prev => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch(`${API}/rag/ask-meetings`, {
        method:  "POST",
        headers: { ...auth(), "Content-Type": "application/json" },
        body:    JSON.stringify({ query: query.trim() }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Query failed");
      }

      const data = await res.json();
      const aiMsg = {
        role:       "assistant",
        content:    data.answer,
        confidence: data.confidence,
        sources:    data.sources || [],
        timestamp:  new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" }),
      };
      setMessages(prev => [...prev, aiMsg]);

      // Refresh history
      fetch(`${API}/rag/query-history?limit=10`, { headers: auth() })
        .then(r => r.ok ? r.json() : [])
        .then(setHistory)
        .catch(() => {});

    } catch (err) {
      setMessages(prev => [...prev, {
        role:    "assistant",
        content: `Error: ${err.message}`,
        confidence: 0,
        sources: [],
      }]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }

  function handleSubmit(e) {
    e.preventDefault();
    sendQuery(input);
  }

  return (
    <div className="flex h-[calc(100vh-80px)] flex-col gap-0">

      {/* ── header ── */}
      <div className="flex items-center justify-between px-1 pb-4">
        <div>
          <h1 className="text-2xl font-black tracking-tight text-slate-900 dark:text-slate-100">
            Ask Meetings
          </h1>
          <p className="mt-0.5 text-sm text-slate-500 dark:text-slate-400">
            Ask anything about your meeting history
          </p>
        </div>
        <button onClick={() => setShowHist(v => !v)}
          className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 transition-colors dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
          <Clock className="h-3.5 w-3.5" />
          History
        </button>
      </div>

      <div className="flex flex-1 gap-4 overflow-hidden">

        {/* ── chat area ── */}
        <div className="flex flex-1 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-slate-50/50 dark:border-slate-700/60 dark:bg-slate-900/40">

          {/* messages */}
          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
            {messages.length === 0 && (
              <M.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                className="flex flex-col items-center justify-center h-full gap-6 py-12">
                <div className="flex h-16 w-16 items-center justify-center rounded-2xl"
                  style={{ background: "linear-gradient(135deg, #4338ca, #0e7490)", boxShadow: "0 8px 32px rgba(67,56,202,0.3)" }}>
                  <Sparkles className="h-8 w-8 text-white" />
                </div>
                <div className="text-center">
                  <p className="font-bold text-slate-700 dark:text-slate-300">Ask anything about your meetings</p>
                  <p className="mt-1 text-sm text-slate-500">Powered by Gemini AI + semantic search</p>
                </div>
                {/* suggestion chips */}
                <div className="flex flex-wrap justify-center gap-2 max-w-lg">
                  {SUGGESTIONS.map(s => (
                    <button key={s} onClick={() => sendQuery(s)}
                      className="rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-xs font-medium text-indigo-700 hover:bg-indigo-100 transition-colors dark:border-indigo-800/40 dark:bg-indigo-950/30 dark:text-indigo-300">
                      {s}
                    </button>
                  ))}
                </div>
              </M.div>
            )}

            {messages.map((msg, i) => (
              <MessageBubble key={i} msg={msg} index={i} />
            ))}

            {loading && (
              <M.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                className="flex gap-3">
                <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 text-xs font-bold text-white">
                  AI
                </div>
                <div className="flex items-center gap-2 rounded-2xl rounded-tl-sm border border-slate-200 bg-white px-4 py-3 dark:border-slate-700/60 dark:bg-slate-800/80">
                  <Loader2 className="h-4 w-4 animate-spin text-indigo-500" />
                  <span className="text-sm text-slate-500">Searching your meetings…</span>
                </div>
              </M.div>
            )}

            <div ref={bottomRef} />
          </div>

          {/* input bar */}
          <div className="border-t border-slate-200 bg-white p-3 dark:border-slate-700/60 dark:bg-slate-900/60">
            <form onSubmit={handleSubmit} className="flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                <input
                  ref={inputRef}
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  placeholder="Ask about your meetings…"
                  disabled={loading}
                  className="w-full rounded-xl border border-slate-200 bg-slate-50 py-2.5 pl-9 pr-4 text-sm text-slate-900 outline-none transition-all focus:border-indigo-400 focus:ring-2 focus:ring-indigo-400/15 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
                />
                {input && (
                  <button type="button" onClick={() => setInput("")}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
              <button type="submit" disabled={!input.trim() || loading}
                className="flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-bold text-white transition-all disabled:opacity-40"
                style={{ background: "linear-gradient(135deg, #4338ca, #0e7490)", boxShadow: "0 2px 12px rgba(67,56,202,0.3)" }}>
                <Send className="h-4 w-4" />
                Ask
              </button>
            </form>
          </div>
        </div>

        {/* ── history sidebar ── */}
        <AnimatePresence>
          {showHist && (
            <M.div key="hist"
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: 280, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              transition={{ duration: 0.25, ease: easeSoft }}
              className="flex-shrink-0 overflow-hidden rounded-2xl border border-slate-200 bg-white dark:border-slate-700/60 dark:bg-slate-900/60">
              <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3 dark:border-slate-700/40">
                <p className="text-xs font-black uppercase tracking-widest text-slate-500">
                  Recent Queries
                </p>
                <button onClick={() => setShowHist(false)}
                  className="text-slate-400 hover:text-slate-600 transition-colors">
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="overflow-y-auto p-3 space-y-2" style={{ maxHeight: "calc(100% - 48px)" }}>
                {history.length === 0 && (
                  <p className="text-xs text-slate-400 italic text-center py-4">No queries yet</p>
                )}
                {history.map(h => (
                  <button key={h.id} onClick={() => sendQuery(h.query)}
                    className="w-full rounded-xl border border-slate-100 bg-slate-50 p-3 text-left transition-colors hover:border-indigo-200 hover:bg-indigo-50/50 dark:border-slate-700/40 dark:bg-slate-800/40">
                    <p className="text-xs font-semibold text-slate-700 dark:text-slate-300 line-clamp-2">
                      {h.query}
                    </p>
                    <div className="mt-1.5 flex items-center gap-2">
                      <ConfidenceBadge score={h.confidence} />
                      <span className="text-[10px] text-slate-400">
                        {new Date(h.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            </M.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
