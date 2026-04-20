/**
 * LandingPage — immersive, animated, non-generic.
 *
 * Sections:
 *   1. Hero        — headline, sub, CTA, animated 3D preview card
 *   2. How it works — 3-step animated pipeline
 *   3. Features    — 3 cards with staggered entrance
 *   4. Social proof — floating stat chips
 *   5. CTA banner  — gradient with particle dots
 */
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion as M, useMotionValue, useSpring, useTransform } from "framer-motion";
import { ArrowRight, Brain, CheckCircle2, Mic2, Shield, Sparkles, Zap } from "lucide-react";
import { Link } from "react-router-dom";

const ease = [0.25, 0.1, 0.25, 1];

/* ═══════════════════════════════════════════════════════════
   FLOATING PARTICLE FIELD
═══════════════════════════════════════════════════════════ */
function Particles({ count = 28 }) {
  const dots = useRef(
    Array.from({ length: count }, (_, i) => ({
      id: i,
      x: Math.random() * 100,
      y: Math.random() * 100,
      size: 1 + Math.random() * 2,
      dur: 6 + Math.random() * 10,
      delay: Math.random() * 5,
      opacity: 0.15 + Math.random() * 0.35,
    }))
  ).current;

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      {dots.map(d => (
        <M.div
          key={d.id}
          className="absolute rounded-full"
          style={{
            left: `${d.x}%`, top: `${d.y}%`,
            width: d.size, height: d.size,
            background: d.id % 3 === 0 ? "#818cf8" : d.id % 3 === 1 ? "#22d3ee" : "#34d399",
            opacity: d.opacity,
          }}
          animate={{
            y: [0, -30 - Math.random() * 40, 0],
            opacity: [d.opacity, d.opacity * 0.3, d.opacity],
          }}
          transition={{ duration: d.dur, delay: d.delay, repeat: Infinity, ease: "easeInOut" }}
        />
      ))}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   3D TILT CARD — mouse-tracked perspective
═══════════════════════════════════════════════════════════ */
function TiltCard() {
  const ref = useRef(null);
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const rotX = useSpring(useTransform(y, [-0.5, 0.5], [12, -12]), { stiffness: 200, damping: 30 });
  const rotY = useSpring(useTransform(x, [-0.5, 0.5], [-12, 12]), { stiffness: 200, damping: 30 });

  function onMove(e) {
    const r = ref.current?.getBoundingClientRect();
    if (!r) return;
    x.set((e.clientX - r.left) / r.width - 0.5);
    y.set((e.clientY - r.top)  / r.height - 0.5);
  }
  function onLeave() { x.set(0); y.set(0); }

  /* animated waveform bars */
  const bars = [0.4, 0.7, 1, 0.85, 0.6, 0.9, 0.5, 0.75, 1, 0.65];

  return (
    <M.div
      ref={ref}
      onMouseMove={onMove}
      onMouseLeave={onLeave}
      initial={{ opacity: 0, y: 40, rotateX: 15 }}
      animate={{ opacity: 1, y: 0,  rotateX: 0  }}
      transition={{ duration: 0.9, ease, delay: 0.3 }}
      style={{ rotateX: rotX, rotateY: rotY, transformStyle: "preserve-3d", perspective: 1000 }}
      className="relative w-full max-w-md mx-auto cursor-default select-none"
    >
      {/* card body */}
      <div className="relative overflow-hidden rounded-3xl p-6"
        style={{
          background: "linear-gradient(145deg, rgba(30,27,75,0.9) 0%, rgba(7,9,15,0.95) 60%, rgba(8,51,68,0.5) 100%)",
          border: "1px solid rgba(99,102,241,0.3)",
          boxShadow: "0 32px 80px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.04) inset",
          transform: "translateZ(0)",
        }}>

        {/* glow orb */}
        <div className="pointer-events-none absolute -right-12 -top-12 h-48 w-48 rounded-full"
          style={{ background: "radial-gradient(circle, rgba(99,102,241,0.2) 0%, transparent 65%)", filter: "blur(24px)" }} />

        {/* header row */}
        <div className="flex items-center justify-between mb-5">
          <div>
            <p className="text-[10px] font-black uppercase tracking-widest text-indigo-400">
              Live Analysis
            </p>
            <p className="text-sm font-semibold text-slate-200 mt-0.5">Q3 Strategy Meeting</p>
          </div>
          <div className="flex items-center gap-1.5 rounded-full px-2.5 py-1"
            style={{ background: "rgba(52,211,153,0.12)", border: "1px solid rgba(52,211,153,0.2)" }}>
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-[10px] font-bold text-emerald-400">Processing</span>
          </div>
        </div>

        {/* waveform */}
        <div className="flex items-end gap-1 h-12 mb-5">
          {bars.map((h, i) => (
            <M.div key={i}
              className="flex-1 rounded-full"
              style={{ background: `linear-gradient(180deg, #818cf8, #06b6d4)` }}
              animate={{ scaleY: [h, h * 0.4 + 0.1, h * 0.8, h] }}
              transition={{ duration: 1.4 + i * 0.12, repeat: Infinity, ease: "easeInOut", delay: i * 0.08 }}
              initial={{ scaleY: h }}
            />
          ))}
        </div>

        {/* transcript lines */}
        <div className="space-y-2 mb-5">
          {[
            { speaker: "Alice", text: "We need to ship auth by Friday.", color: "#a5b4fc" },
            { speaker: "Bob",   text: "I'll handle the backend pipeline.", color: "#67e8f9" },
            { speaker: "Alice", text: "Can someone write the tests?",     color: "#a5b4fc" },
          ].map((line, i) => (
            <M.div key={i}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.8 + i * 0.25, duration: 0.4, ease }}
              className="flex items-start gap-2">
              <span className="text-[10px] font-bold mt-0.5 flex-shrink-0" style={{ color: line.color }}>
                {line.speaker}:
              </span>
              <span className="text-[11px] text-slate-400 leading-relaxed">{line.text}</span>
            </M.div>
          ))}
        </div>

        {/* divider */}
        <div className="h-px mb-4" style={{ background: "rgba(255,255,255,0.06)" }} />

        {/* extracted action items */}
        <p className="text-[10px] font-black uppercase tracking-widest text-emerald-400 mb-3">
          Extracted Action Items
        </p>
        {[
          { task: "Ship auth feature", who: "Bob",   deadline: "Fri" },
          { task: "Write test suite",  who: "Alice", deadline: "Mon" },
        ].map((item, i) => (
          <M.div key={i}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 1.4 + i * 0.2, duration: 0.4, ease }}
            className="flex items-center gap-2 mb-2">
            <CheckCircle2 className="h-3.5 w-3.5 flex-shrink-0 text-emerald-400" />
            <span className="flex-1 text-[11px] text-slate-300">{item.task}</span>
            <span className="text-[10px] font-semibold rounded-full px-2 py-0.5"
              style={{ background: "rgba(99,102,241,0.15)", color: "#a5b4fc" }}>
              {item.who}
            </span>
            <span className="text-[10px] text-slate-600">{item.deadline}</span>
          </M.div>
        ))}

        {/* floating badge — translateZ for 3D pop */}
        <M.div
          animate={{ y: [0, -6, 0] }}
          transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
          className="absolute -right-3 -top-3 rounded-2xl px-3 py-2"
          style={{
            background: "linear-gradient(135deg, #4338ca, #0e7490)",
            boxShadow: "0 8px 24px rgba(67,56,202,0.5)",
            transform: "translateZ(40px)",
          }}>
          <Sparkles className="h-4 w-4 text-white" />
        </M.div>
      </div>
    </M.div>
  );
}

/* ═══════════════════════════════════════════════════════════
   ANIMATED COUNTER
═══════════════════════════════════════════════════════════ */
function Counter({ to, suffix = "" }) {
  const [val, setVal] = useState(0);
  useEffect(() => {
    let start = 0;
    const step = to / 60;
    const id = setInterval(() => {
      start += step;
      if (start >= to) { setVal(to); clearInterval(id); }
      else setVal(Math.floor(start));
    }, 16);
    return () => clearInterval(id);
  }, [to]);
  return <>{val}{suffix}</>;
}

/* ═══════════════════════════════════════════════════════════
   HERO SECTION
═══════════════════════════════════════════════════════════ */
function Hero() {
  return (
    <section className="relative min-h-screen flex items-center overflow-hidden pt-20">
      <Particles />

      {/* large background glow */}
      <div className="pointer-events-none absolute inset-0"
        style={{
          background: "radial-gradient(ellipse 80% 60% at 50% 0%, rgba(67,56,202,0.18) 0%, transparent 65%)",
        }} />

      <div className="relative mx-auto max-w-6xl px-5 py-20 w-full">
        <div className="flex flex-col items-center gap-16 lg:flex-row lg:items-center">

          {/* left — copy */}
          <div className="flex-1 text-center lg:text-left">
            {/* badge */}
            <M.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, ease }}
              className="inline-flex items-center gap-2 rounded-full px-4 py-1.5 mb-6"
              style={{
                background: "rgba(99,102,241,0.1)",
                border: "1px solid rgba(99,102,241,0.25)",
              }}>
              <Sparkles className="h-3.5 w-3.5 text-indigo-400" />
              <span className="text-[12px] font-bold text-indigo-300">
                AI-Powered Meeting Intelligence
              </span>
            </M.div>

            {/* headline */}
            <M.h1
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.65, ease, delay: 0.1 }}
              className="text-5xl font-black leading-[1.08] tracking-tight text-white md:text-6xl lg:text-7xl"
            >
              Turn meetings
              <br />
              <span style={{
                background: "linear-gradient(135deg, #a5b4fc 0%, #67e8f9 50%, #6ee7b7 100%)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                backgroundClip: "text",
              }}>
                into action.
              </span>
            </M.h1>

            <M.p
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, ease, delay: 0.22 }}
              className="mt-6 max-w-lg text-[16px] leading-relaxed text-slate-400 mx-auto lg:mx-0"
            >
              MeetTrack transcribes your recordings, extracts decisions and action items,
              and delivers structured intelligence — automatically.
            </M.p>

            {/* CTAs */}
            <M.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, ease, delay: 0.34 }}
              className="mt-8 flex flex-wrap items-center gap-3 justify-center lg:justify-start"
            >
              <M.div whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.97 }}>
                <Link to="/auth"
                  className="inline-flex items-center gap-2 rounded-2xl px-6 py-3.5
                             text-[14px] font-bold text-white"
                  style={{
                    background: "linear-gradient(135deg, #4338ca 0%, #0e7490 100%)",
                    boxShadow: "0 4px 28px rgba(67,56,202,0.45), 0 1px 0 rgba(255,255,255,0.1) inset",
                  }}>
                  Start for free
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </M.div>

              <M.div whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}>
                <Link to="/about"
                  className="inline-flex items-center gap-2 rounded-2xl px-6 py-3.5
                             text-[14px] font-semibold text-slate-400 hover:text-slate-200 transition-colors"
                  style={{ border: "1px solid rgba(255,255,255,0.08)" }}>
                  See how it works
                </Link>
              </M.div>
            </M.div>

            {/* stat row */}
            <M.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.7, duration: 0.6 }}
              className="mt-10 flex flex-wrap gap-6 justify-center lg:justify-start"
            >
              {[
                { val: 500, suffix: "+", label: "Meetings analysed" },
                { val: 98,  suffix: "%", label: "Accuracy rate"     },
                { val: 10,  suffix: "x", label: "Faster than manual"},
              ].map((s, i) => (
                <div key={i} className="text-center lg:text-left">
                  <p className="text-2xl font-black text-white">
                    <Counter to={s.val} suffix={s.suffix} />
                  </p>
                  <p className="text-[11px] text-slate-600 mt-0.5">{s.label}</p>
                </div>
              ))}
            </M.div>
          </div>

          {/* right — 3D card */}
          <div className="flex-1 w-full max-w-md">
            <TiltCard />
          </div>
        </div>
      </div>

      {/* scroll indicator */}
      <M.div
        animate={{ y: [0, 8, 0] }}
        transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
        className="absolute bottom-8 left-1/2 -translate-x-1/2 flex flex-col items-center gap-1"
      >
        <div className="h-8 w-5 rounded-full flex items-start justify-center pt-1.5"
          style={{ border: "1px solid rgba(255,255,255,0.12)" }}>
          <M.div className="h-1.5 w-1 rounded-full bg-slate-500"
            animate={{ y: [0, 10, 0] }}
            transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }} />
        </div>
      </M.div>
    </section>
  );
}

/* ═══════════════════════════════════════════════════════════
   HOW IT WORKS
═══════════════════════════════════════════════════════════ */
const STEPS = [
  { n: "01", icon: Mic2,     title: "Upload Recording",    desc: "Drop your .mp3 or .wav file — or paste a transcript directly.",          color: "#a78bfa" },
  { n: "02", icon: Brain,    title: "AI Processes It",     desc: "Whisper transcribes speech. Gemini extracts decisions and tasks.",        color: "#22d3ee" },
  { n: "03", icon: Zap,      title: "Get Structured Output", desc: "Summary, decisions, and action items — ready to share in seconds.",    color: "#34d399" },
];

function HowItWorks() {
  return (
    <section className="relative py-28 overflow-hidden">
      <div className="pointer-events-none absolute inset-0"
        style={{ background: "radial-gradient(ellipse 60% 40% at 50% 50%, rgba(6,182,212,0.06) 0%, transparent 70%)" }} />

      <div className="relative mx-auto max-w-6xl px-5">
        <M.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.55, ease }}
          className="text-center mb-16"
        >
          <p className="text-[11px] font-black uppercase tracking-[0.18em] text-cyan-500 mb-3">
            How it works
          </p>
          <h2 className="text-4xl font-black text-white tracking-tight">
            Three steps to clarity
          </h2>
        </M.div>

        <div className="relative flex flex-col gap-6 md:flex-row md:gap-4">
          {/* connector line */}
          <div className="hidden md:block absolute top-12 left-[16.66%] right-[16.66%] h-px"
            style={{ background: "linear-gradient(90deg, transparent, rgba(99,102,241,0.3), rgba(6,182,212,0.3), transparent)" }} />

          {STEPS.map((s, i) => {
            const Icon = s.icon;
            return (
              <M.div key={i}
                initial={{ opacity: 0, y: 30 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, ease, delay: i * 0.12 }}
                className="flex-1 flex flex-col items-center text-center"
              >
                {/* icon circle */}
                <M.div
                  whileHover={{ scale: 1.1, rotate: 5 }}
                  transition={{ duration: 0.3 }}
                  className="relative flex h-20 w-20 items-center justify-center rounded-2xl mb-5"
                  style={{
                    background: `linear-gradient(145deg, ${s.color}22, rgba(7,9,15,0.8))`,
                    border: `1px solid ${s.color}33`,
                    boxShadow: `0 8px 32px ${s.color}18`,
                  }}>
                  <Icon className="h-8 w-8" style={{ color: s.color }} />
                  <span className="absolute -top-2 -right-2 text-[10px] font-black rounded-full h-5 w-5
                                   flex items-center justify-center"
                    style={{ background: s.color + "22", color: s.color, border: `1px solid ${s.color}44` }}>
                    {s.n.slice(1)}
                  </span>
                </M.div>

                <h3 className="text-[15px] font-bold text-slate-100 mb-2">{s.title}</h3>
                <p className="text-sm text-slate-500 leading-relaxed max-w-[220px]">{s.desc}</p>
              </M.div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

/* ═══════════════════════════════════════════════════════════
   FEATURES
═══════════════════════════════════════════════════════════ */
const FEATURES = [
  {
    icon: Mic2,
    title: "Audio Transcription",
    desc: "Whisper AI converts any meeting recording into accurate, speaker-labelled text in seconds.",
    color: "#a78bfa",
    grad: "rgba(139,92,246,0.08)",
  },
  {
    icon: Brain,
    title: "Gemini Intelligence",
    desc: "Gemini 2.0 extracts summaries, implicit decisions, and action items with confidence scores.",
    color: "#22d3ee",
    grad: "rgba(6,182,212,0.08)",
  },
  {
    icon: Shield,
    title: "Structured & Reliable",
    desc: "Strict JSON output, fallback handling, and idempotent n8n webhooks — production-grade from day one.",
    color: "#34d399",
    grad: "rgba(16,185,129,0.08)",
  },
];

function Features() {
  return (
    <section className="py-24">
      <div className="mx-auto max-w-6xl px-5">
        <M.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.55, ease }}
          className="text-center mb-14"
        >
          <p className="text-[11px] font-black uppercase tracking-[0.18em] text-indigo-400 mb-3">
            Features
          </p>
          <h2 className="text-4xl font-black text-white tracking-tight">
            Built for real teams
          </h2>
        </M.div>

        <div className="grid gap-5 md:grid-cols-3">
          {FEATURES.map((f, i) => {
            const Icon = f.icon;
            return (
              <M.div key={i}
                initial={{ opacity: 0, y: 28 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, ease, delay: i * 0.1 }}
                whileHover={{ y: -6, boxShadow: `0 20px 48px rgba(0,0,0,0.5)` }}
                className="relative overflow-hidden rounded-3xl p-7 transition-all duration-250"
                style={{
                  background: `linear-gradient(145deg, ${f.grad} 0%, rgba(7,9,15,0.8) 100%)`,
                  border: `1px solid ${f.color}18`,
                  boxShadow: "0 4px 20px rgba(0,0,0,0.3)",
                }}>

                {/* corner glow */}
                <div className="pointer-events-none absolute -right-8 -top-8 h-32 w-32 rounded-full"
                  style={{ background: `radial-gradient(circle, ${f.color}15 0%, transparent 65%)`, filter: "blur(16px)" }} />

                <div className="flex h-11 w-11 items-center justify-center rounded-2xl mb-5"
                  style={{ background: f.color + "18", border: `1px solid ${f.color}28` }}>
                  <Icon className="h-5 w-5" style={{ color: f.color }} />
                </div>

                <h3 className="text-[15px] font-bold text-slate-100 mb-2">{f.title}</h3>
                <p className="text-sm text-slate-500 leading-relaxed">{f.desc}</p>
              </M.div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

/* ═══════════════════════════════════════════════════════════
   CTA BANNER
═══════════════════════════════════════════════════════════ */
function CTABanner() {
  return (
    <section className="py-24">
      <div className="mx-auto max-w-4xl px-5">
        <M.div
          initial={{ opacity: 0, scale: 0.96 }}
          whileInView={{ opacity: 1, scale: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6, ease }}
          className="relative overflow-hidden rounded-3xl px-8 py-16 text-center"
          style={{
            background: "linear-gradient(135deg, rgba(67,56,202,0.5) 0%, rgba(14,116,144,0.4) 50%, rgba(5,150,105,0.3) 100%)",
            border: "1px solid rgba(99,102,241,0.25)",
            boxShadow: "0 24px 80px rgba(67,56,202,0.2)",
          }}
        >
          <Particles count={16} />

          <div className="pointer-events-none absolute inset-0"
            style={{ background: "radial-gradient(ellipse 70% 60% at 50% 50%, rgba(99,102,241,0.15) 0%, transparent 70%)" }} />

          <M.div
            animate={{ rotate: [0, 360] }}
            transition={{ duration: 20, repeat: Infinity, ease: "linear" }}
            className="relative mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl"
            style={{
              background: "linear-gradient(135deg, #4338ca, #0e7490)",
              boxShadow: "0 8px 32px rgba(67,56,202,0.5)",
            }}>
            <Sparkles className="h-7 w-7 text-white" />
          </M.div>

          <h2 className="relative text-4xl font-black text-white tracking-tight mb-4">
            Ready to transform your meetings?
          </h2>
          <p className="relative text-slate-300 mb-8 max-w-md mx-auto">
            Join teams already using MeetTrack to turn conversations into clear, actionable outcomes.
          </p>

          <M.div whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.97 }} className="inline-block">
            <Link to="/auth"
              className="inline-flex items-center gap-2 rounded-2xl px-8 py-4
                         text-[15px] font-bold text-white"
              style={{
                background: "rgba(255,255,255,0.12)",
                border: "1px solid rgba(255,255,255,0.2)",
                backdropFilter: "blur(8px)",
                boxShadow: "0 4px 20px rgba(0,0,0,0.3)",
              }}>
              Get started free
              <ArrowRight className="h-4 w-4" />
            </Link>
          </M.div>
        </M.div>
      </div>
    </section>
  );
}

/* ═══════════════════════════════════════════════════════════
   MAIN EXPORT
═══════════════════════════════════════════════════════════ */
export default function LandingPage() {
  return (
    <div style={{ background: "#07090f" }}>
      <Hero />
      <HowItWorks />
      <Features />
      <CTABanner />

      {/* footer */}
      <footer className="border-t py-8 text-center text-[12px] text-slate-700"
        style={{ borderColor: "rgba(255,255,255,0.05)" }}>
        © 2026 MeetTrack · Built with Whisper + Gemini AI
      </footer>
    </div>
  );
}
