/**
 * useLiveMeeting — WebSocket hook for real-time meeting collaboration
 *
 * Handles:
 *   - Connection + JWT auth handshake
 *   - Automatic reconnect (exponential backoff: 1s, 2s, 4s, 8s)
 *   - Heartbeat ping/pong
 *   - All incoming event types
 *   - Sending transcript chunks, notes, task assignments
 */
import { useCallback, useEffect, useRef, useState } from "react";

const WS_BASE = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000")
  .replace(/^http/, "ws");

const MAX_RECONNECT_DELAY = 16000;
const PING_INTERVAL       = 25000;  // 25s heartbeat

export function useLiveMeeting(meetingId, userName) {
  const [connected,    setConnected]    = useState(false);
  const [participants, setParticipants] = useState([]);
  const [transcript,   setTranscript]   = useState("");
  const [summary,      setSummary]      = useState("");
  const [decisions,    setDecisions]    = useState([]);
  const [actionItems,  setActionItems]  = useState([]);
  const [suggestions,  setSuggestions]  = useState([]);
  const [notes,        setNotes]        = useState([]);
  const [speakerActivity, setSpeakerActivity] = useState({});
  const [snapshotSaved, setSnapshotSaved] = useState(null);
  const [error,        setError]        = useState(null);
  const [wordCount,    setWordCount]    = useState(0);

  const wsRef           = useRef(null);
  const reconnectDelay  = useRef(1000);
  const reconnectTimer  = useRef(null);
  const pingTimer       = useRef(null);
  const mountedRef      = useRef(true);

  const connect = useCallback(() => {
    if (!meetingId || !mountedRef.current) return;

    const token = localStorage.getItem("access_token");
    if (!token) {
      setError("Not authenticated");
      return;
    }

    const url = `${WS_BASE}/live/ws/${meetingId}`;
    const ws  = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      // Send auth as first message
      ws.send(JSON.stringify({
        type:      "auth",
        token,
        user_name: userName || "Anonymous",
      }));
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleMessage(msg);
      } catch (e) {
        console.warn("[WS] Invalid message:", event.data);
      }
    };

    ws.onclose = (event) => {
      setConnected(false);
      clearInterval(pingTimer.current);

      if (!mountedRef.current) return;

      // Reconnect with exponential backoff
      if (event.code !== 1000) {  // 1000 = normal close
        console.log(`[WS] Reconnecting in ${reconnectDelay.current}ms…`);
        reconnectTimer.current = setTimeout(() => {
          if (mountedRef.current) connect();
        }, reconnectDelay.current);
        reconnectDelay.current = Math.min(reconnectDelay.current * 2, MAX_RECONNECT_DELAY);
      }
    };

    ws.onerror = (err) => {
      console.error("[WS] Error:", err);
      setError("WebSocket connection error");
    };
  }, [meetingId, userName]);

  function handleMessage(msg) {
    switch (msg.type) {
      case "connected":
        setConnected(true);
        setError(null);
        reconnectDelay.current = 1000;  // reset backoff
        if (msg.participants) setParticipants(msg.participants);
        if (msg.session) {
          setSummary(msg.session.summary || "");
          setDecisions(msg.session.decisions || []);
          setActionItems(msg.session.action_items || []);
        }
        // Start heartbeat
        clearInterval(pingTimer.current);
        pingTimer.current = setInterval(() => {
          if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({ type: "pong" }));
          }
        }, PING_INTERVAL);
        break;

      case "transcript_chunk":
        setTranscript(prev => prev + (msg.speaker ? `\n${msg.speaker}: ` : "\n") + msg.text);
        setWordCount(msg.word_count || 0);
        break;

      case "ai_update":
        if (msg.summary)      setSummary(msg.summary);
        if (msg.decisions)    setDecisions(msg.decisions);
        if (msg.action_items) setActionItems(msg.action_items);
        break;

      case "suggestion":
        setSuggestions(prev => [
          { ...msg, id: Date.now() },
          ...prev.slice(0, 9),  // keep last 10
        ]);
        break;

      case "note_added":
        setNotes(prev => [...prev, msg]);
        break;

      case "task_assigned":
        setActionItems(prev => [
          ...prev,
          { task: msg.task, assignee: msg.assignee, deadline: msg.deadline, confidence_score: 1.0 },
        ]);
        break;

      case "speaker_active":
        setSpeakerActivity(prev => ({ ...prev, [msg.speaker]: msg.words }));
        break;

      case "participant_joined":
      case "participant_left":
        if (msg.participants) setParticipants(msg.participants);
        break;

      case "snapshot_saved":
        setSnapshotSaved(msg.timestamp);
        break;

      case "meeting_ended":
        setConnected(false);
        break;

      case "ping":
        // Respond to server ping
        wsRef.current?.send(JSON.stringify({ type: "pong" }));
        break;

      case "error":
        setError(msg.message);
        break;

      default:
        break;
    }
  }

  // ── Send helpers ────────────────────────────────────────────────────────────

  const sendChunk = useCallback((text, speaker = null) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "transcript_chunk", text, speaker }));
    }
  }, []);

  const sendNote = useCallback((text) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "note", text }));
    }
  }, []);

  const sendTaskAssignment = useCallback((task, assignee, deadline = null) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "assign_task", task, assignee, deadline }));
    }
  }, []);

  const endMeeting = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "end_meeting" }));
      wsRef.current.close(1000);
    }
  }, []);

  const dismissSuggestion = useCallback((id) => {
    setSuggestions(prev => prev.filter(s => s.id !== id));
  }, []);

  // ── Lifecycle ───────────────────────────────────────────────────────────────

  useEffect(() => {
    mountedRef.current = true;
    if (meetingId) connect();

    return () => {
      mountedRef.current = false;
      clearTimeout(reconnectTimer.current);
      clearInterval(pingTimer.current);
      wsRef.current?.close(1000);
    };
  }, [meetingId, connect]);

  return {
    connected,
    participants,
    transcript,
    summary,
    decisions,
    actionItems,
    suggestions,
    notes,
    speakerActivity,
    snapshotSaved,
    wordCount,
    error,
    sendChunk,
    sendNote,
    sendTaskAssignment,
    endMeeting,
    dismissSuggestion,
  };
}
