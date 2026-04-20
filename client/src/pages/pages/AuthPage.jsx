/**
 * AuthPage — cinematic split-screen auth.
 *
 * Left panel  (hidden on mobile):
 *   - Animated 3D floating orbs
 *   - Rotating feature list
 *   - Live "processing" demo card
 *
 * Right panel:
 *   - Login / Register tab switcher
 *   - Animated form fields
 *   - Gradient submit button
 */
import { AnimatePresence, motion as M } from "framer-motion";
import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { ArrowLeft, CheckCircle2, Eye, EyeOff, Sparkles, Zap } from "lucide-react";
import useAuth from "../context/useAuth";

const ease = [0.25, 0.1, 0.25, 1];

/* ═══════════════════════════════════════════════════════════
   FLOATING ORBS — left panel decoration
═══════════════════════════════════════════════════════════ */
function Orbs() {
  const orbs = [
    { size: 280, x: -80,  y: -80,  color: "rgba(67,56,202,0.25)",  dur: 18 },
    { size: 200, x: 60,   y: 120,  color: "rgba(6,182,212,0.18)",  dur: 22 },
    { size: 160, x: -40,  y: 260,  color: "rgba(16,185,129,0.15)", dur: 26 },
    { size: 120, x: 140,  y: -20,  color: "rgba(139,92,246,0.2)",  dur: 20 },
  ];
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      {orbs.map((o, i) => (
        <M.div key={i}
          className="absolute rounded-full"
          style={{
            width: o.size, height: o.size,
            left: o.x, top: o.y,
            background: `radial-gradient(circle, ${o.color} 0%, transparent 70%)`,
            filter: "blur(40px)",
          }}
          animate={{
            x: [0, 30 + i * 10, -20, 0],
            y: [0, -20, 30 + i * 8, 0],
            scale: [1, 1.1, 0.95, 1],
          }}
          transition={{ duration: o.dur, repeat: Infinity, ease: "easeInOut" }}
        />
      ))}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   DEMO CARD — animated preview on left panel
═══════════════════════════════════════════════════════════ */
function DemoCard() {
  const items = [
    { task: "Deploy auth service",  who: "Bob",   done: true  },
    { task: "Write release notes",  who: "Alice", done: false },
    { task: "Update API docs",      who: "Carol", done: false },
  ];

  return (
    <M.div
      initial={{ opacity: 0, y: 30, rotateX: 10 }}
      animate={{ opacity: 1, y: 0,  rotateX: 0  }}
      transition={{ duration: 0.9, ease, delay: 0.4 }}
      className="relative overflow-hidden rounded-2xl p-5 w-full max-w-xs"
      style={{
        background: "rgba(12,16,28,0.85)",
        border: "1px solid rgba(99,102,241,0.2)",
        boxShadow: "0 24px 60px rgba(0,0,0,0.5)",
        backdropFilter: "blur(12px)",
      }}
    >
      <div className="flex items-center gap-2 mb-4">
        <div className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
        <p className="text-[10px] font-black uppercase tracking-widest text-slate-500">
          AI extracted · just now
        </p>
      </div>

      <p className="text-[11px] font-semibold text-slate-300 mb-3">Sprint Planning · Action Items</p>

      <div className="space-y-2">
        {items.map((item, i) => (
          <M.div key={i}
            initial={{ opacity: 0, x: -12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.7 + i * 0.18, duration: 0.4, ease }}
            className="flex items-center gap-2.5 rounded-xl px-3 py-2.5"
            style={{
              background: item.done ? "rgba(52,211,153,0.06)" : "rgba(255,255,255,0.03)",
              border: `1px solid ${item.done ? "rgba(52,211,153,0.15)" : "rgba(255,255,255,0.05)"}`,
            }}>
            <CheckCircle2 className="h-3.5 w-3.5 flex-shrink-0"
              style={{ color: item.done ? "#34d399" : "#334155" }} />
            <span className="flex-1 text-[11px] text-slate-400">{item.task}</span>
            <span className="text-[9px] font-bold rounded-full px-1.5 py-0.5"
              style={{ background: "rgba(99,102,241,0.15)", color: "#a5b4fc" }}>
              {item.who}
            </span>
          </M.div>
        ))}
      </div>
    </M.div>
  );
}

/* ═══════════════════════════════════════════════════════════
   LEFT PANEL
═══════════════════════════════════════════════════════════ */
function LeftPanel() {
  const bullets = [
    "Transcribe meetings in seconds",
    "Extract decisions automatically",
    "Assign action items to your team",
    "Integrate with n8n workflows",
  ];
  const [activeBullet, setActiveBullet] = useState(0);

  // cycle bullets
  useState(() => {
    const id = setInterval(() => setActiveBullet(v => (v + 1) % bullets.length), 2200);
    return () => clearInterval(id);
  });

  return (
    <div className="relative hidden lg:flex flex-col justify-between overflow-hidden p-10"
      style={{
        background: "linear-gradient(145deg, rgba(30,27,75,0.95) 0%, rgba(7,9,15,0.98) 60%, rgba(8,51,68,0.6) 100%)",
        borderRight: "1px solid rgba(255,255,255,0.06)",
      }}>
      <Orbs />

      {/* brand */}
      <M.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.5, ease }}>
        <Link to="/" className="inline-flex items-center gap-2 text-slate-400 hover:text-slate-200 transition-colors text-sm">
          <ArrowLeft className="h-4 w-4" />
          Back to home
        </Link>
      </M.div>

      {/* centre content */}
      <div className="relative flex flex-col items-start gap-8">
        <M.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease, delay: 0.2 }}>
          <h2 className="text-3xl font-black text-white leading-tight tracking-tight mb-2">
            Every meeting,<br />
            <span style={{
              background: "linear-gradient(135deg, #a5b4fc, #67e8f9)",
              WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text",
            }}>
              fully understood.
            </span>
          </h2>
          <p className="text-sm text-slate-500 max-w-xs leading-relaxed">
            Join teams using MeetTrack to turn conversations into structured, actionable intelligence.
          </p>
        </M.div>

        {/* animated bullet list */}
        <div className="space-y-2 w-full max-w-xs">
          {bullets.map((b, i) => (
            <M.div key={i}
              animate={{
                opacity: activeBullet === i ? 1 : 0.35,
                x: activeBullet === i ? 4 : 0,
              }}
              transition={{ duration: 0.4 }}
              className="flex items-center gap-2.5">
              <div className="h-1.5 w-1.5 rounded-full flex-shrink-0"
                style={{ background: activeBullet === i ? "#818cf8" : "#1e293b" }} />
              <span className="text-[13px] font-medium text-slate-300">{b}</span>
            </M.div>
          ))}
        </div>

        <DemoCard />
      </div>

      {/* bottom tagline */}
      <M.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1, duration: 0.6 }}
        className="relative text-[11px] text-slate-700">
        Powered by Whisper AI + Gemini 2.0
      </M.p>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   INPUT FIELD
═══════════════════════════════════════════════════════════ */
function Field({ label, type = "text", value, onChange, placeholder, disabled }) {
  const [focused, setFocused] = useState(false);
  const [show,    setShow]    = useState(false);
  const isPass = type === "password";

  return (
    <div>
      <label className="block text-[11px] font-bold uppercase tracking-widest text-slate-600 mb-1.5">
        {label}
      </label>
      <div className="relative">
        <input
          type={isPass && !show ? "password" : "text"}
          value={value}
          onChange={onChange}
          placeholder={placeholder}
          disabled={disabled}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          className="w-full rounded-xl px-4 py-3 text-sm text-slate-200
                     placeholder-slate-700 outline-none transition-all duration-200"
          style={{
            background: "rgba(255,255,255,0.04)",
            border: `1px solid ${focused ? "rgba(99,102,241,0.5)" : "rgba(255,255,255,0.07)"}`,
            boxShadow: focused ? "0 0 0 3px rgba(99,102,241,0.1)" : "none",
          }}
        />
        {isPass && (
          <button type="button" onClick={() => setShow(v => !v)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-600
                       hover:text-slate-400 transition-colors">
            {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        )}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   AUTH FORM
═══════════════════════════════════════════════════════════ */
function AuthForm({ mode, onSwitch }) {
  const [form, setForm]     = useState({ email: "", password: "", fullName: "", role: "employee" });
  const [error, setError]   = useState("");
  const [loading, setLoad]  = useState(false);
  const { login, register } = useAuth();
  const navigate            = useNavigate();
  const isLogin             = mode === "login";

  const set = (k) => (e) => setForm(p => ({ ...p, [k]: e.target.value }));

  async function handleSubmit(e) {
    e.preventDefault();
    if (!form.email.includes("@") || form.password.length < 6) {
      setError("Valid email and password (min 6 chars) required.");
      return;
    }
    setLoad(true); setError("");
    try {
      if (isLogin) {
        await login(form.email, form.password);
      } else {
        await register(form.email, form.password, form.fullName, form.role);
        await login(form.email, form.password);
      }
      navigate("/dashboard");
    } catch (err) {
      setError(err.message || (isLogin ? "Login failed" : "Registration failed"));
    } finally {
      setLoad(false);
    }
  }

  return (
    <M.form
      key={mode}
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20 }}
      transition={{ duration: 0.3, ease }}
      onSubmit={handleSubmit}
      className="space-y-4"
    >
      {!isLogin && (
        <>
          <Field label="Full Name" value={form.fullName} onChange={set("fullName")}
            placeholder="Jane Smith" disabled={loading} />
          <div>
            <label className="block text-[11px] font-bold uppercase tracking-widest text-slate-600 mb-1.5">
              Role
            </label>
            <select value={form.role} onChange={set("role")} disabled={loading}
              className="w-full rounded-xl px-4 py-3 text-sm text-slate-300 outline-none"
              style={{
                background: "rgba(255,255,255,0.04)",
                border: "1px solid rgba(255,255,255,0.07)",
              }}>
              <option value="employee">Employee</option>
              <option value="manager">Manager</option>
            </select>
          </div>
        </>
      )}

      <Field label="Email" value={form.email} onChange={set("email")}
        placeholder="you@company.com" disabled={loading} />
      <Field label="Password" type="password" value={form.password} onChange={set("password")}
        placeholder="••••••••" disabled={loading} />

      {/* error */}
      <AnimatePresence>
        {error && (
          <M.p initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            className="text-[12px] text-red-400 rounded-xl px-3 py-2"
            style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.15)" }}>
            {error}
          </M.p>
        )}
      </AnimatePresence>

      {/* submit */}
      <M.button type="submit" disabled={loading}
        whileHover={!loading ? { scale: 1.02 } : {}}
        whileTap={!loading ? { scale: 0.98 } : {}}
        className="w-full rounded-xl py-3.5 text-[14px] font-bold text-white
                   transition-all duration-200 flex items-center justify-center gap-2"
        style={loading
          ? { background: "rgba(255,255,255,0.06)", cursor: "not-allowed", color: "#475569" }
          : {
              background: "linear-gradient(135deg, #4338ca 0%, #0e7490 100%)",
              boxShadow: "0 4px 24px rgba(67,56,202,0.4), 0 1px 0 rgba(255,255,255,0.1) inset",
            }
        }>
        {loading ? (
          <>
            <M.span animate={{ rotate: 360 }} transition={{ duration: 0.9, repeat: Infinity, ease: "linear" }}
              className="inline-block h-4 w-4 rounded-full border-2 border-white/25 border-t-white" />
            {isLogin ? "Signing in…" : "Creating account…"}
          </>
        ) : (
          <>
            <Zap className="h-4 w-4" />
            {isLogin ? "Sign in" : "Create account"}
          </>
        )}
      </M.button>

      {/* switch mode */}
      <p className="text-center text-[12px] text-slate-600">
        {isLogin ? "Don't have an account? " : "Already have an account? "}
        <button type="button" onClick={onSwitch}
          className="font-semibold text-indigo-400 hover:text-indigo-300 transition-colors">
          {isLogin ? "Sign up" : "Sign in"}
        </button>
      </p>
    </M.form>
  );
}

/* ═══════════════════════════════════════════════════════════
   MAIN EXPORT
═══════════════════════════════════════════════════════════ */
export default function AuthPage() {
  const [mode, setMode] = useState("login");

  return (
    <div className="min-h-screen flex items-stretch" style={{ background: "#07090f" }}>

      {/* ── left panel ── */}
      <div className="lg:w-[48%]">
        <LeftPanel />
      </div>

      {/* ── right panel ── */}
      <div className="flex flex-1 items-center justify-center px-5 py-20 lg:py-0">
        <M.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, ease }}
          className="w-full max-w-sm"
        >
          {/* header */}
          <div className="mb-8">
            {/* mobile back link */}
            <Link to="/" className="inline-flex items-center gap-1.5 text-[12px] text-slate-600
                                    hover:text-slate-400 transition-colors mb-6 lg:hidden">
              <ArrowLeft className="h-3.5 w-3.5" />
              Back to home
            </Link>

            <div className="flex items-center gap-2 mb-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-xl"
                style={{ background: "linear-gradient(135deg, #4338ca, #0e7490)", boxShadow: "0 4px 16px rgba(67,56,202,0.4)" }}>
                <Sparkles className="h-4 w-4 text-white" />
              </div>
              <span className="text-[11px] font-black uppercase tracking-widest text-indigo-400">
                MeetTrack
              </span>
            </div>

            <h1 className="text-2xl font-black text-white tracking-tight">
              {mode === "login" ? "Welcome back" : "Create your account"}
            </h1>
            <p className="mt-1 text-[13px] text-slate-600">
              {mode === "login"
                ? "Sign in to access your meeting intelligence."
                : "Start turning meetings into action items today."}
            </p>
          </div>

          {/* tab switcher */}
          <div className="flex rounded-xl p-1 mb-6"
            style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.06)" }}>
            {["login", "register"].map(m => (
              <button key={m} onClick={() => setMode(m)}
                className="relative flex-1 rounded-lg py-2 text-[12px] font-bold transition-colors"
                style={{ color: mode === m ? "#fff" : "#475569" }}>
                {mode === m && (
                  <M.div layoutId="tab-bg" className="absolute inset-0 rounded-lg"
                    style={{ background: "linear-gradient(135deg, rgba(67,56,202,0.5), rgba(14,116,144,0.4))" }}
                    transition={{ duration: 0.25, ease }} />
                )}
                <span className="relative">{m === "login" ? "Sign in" : "Sign up"}</span>
              </button>
            ))}
          </div>

          {/* form */}
          <AnimatePresence mode="wait">
            <AuthForm key={mode} mode={mode} onSwitch={() => setMode(m => m === "login" ? "register" : "login")} />
          </AnimatePresence>
        </M.div>
      </div>
    </div>
  );
}
