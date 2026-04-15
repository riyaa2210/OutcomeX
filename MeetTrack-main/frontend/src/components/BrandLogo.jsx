import { motion as M } from "framer-motion";
import { Link } from "react-router-dom";

export default function BrandLogo({ to = "/" }) {
  return (
    <Link to={to} className="inline-flex items-center gap-2.5 group">
      {/* animated icon mark */}
      <M.div
        whileHover={{ rotate: [0, -8, 8, 0], scale: 1.08 }}
        transition={{ duration: 0.5 }}
        className="relative flex h-8 w-8 items-center justify-center rounded-xl"
        style={{
          background: "linear-gradient(135deg, #4338ca, #0e7490)",
          boxShadow: "0 2px 12px rgba(67,56,202,0.4)",
        }}
      >
        {/* waveform bars */}
        <svg width="18" height="14" viewBox="0 0 18 14" fill="none">
          {[
            { x: 1,  h: 6,  y: 4  },
            { x: 4,  h: 10, y: 2  },
            { x: 7,  h: 14, y: 0  },
            { x: 10, h: 10, y: 2  },
            { x: 13, h: 6,  y: 4  },
            { x: 16, h: 4,  y: 5  },
          ].map((b, i) => (
            <M.rect
              key={i}
              x={b.x} y={b.y} width="1.5" height={b.h} rx="0.75"
              fill="white"
              animate={{ scaleY: [1, 0.5 + Math.random() * 0.8, 1] }}
              transition={{ duration: 1.2 + i * 0.15, repeat: Infinity, ease: "easeInOut", delay: i * 0.1 }}
              style={{ originY: "bottom", transformBox: "fill-box" }}
            />
          ))}
        </svg>
      </M.div>

      <span className="text-[15px] font-black tracking-tight text-slate-100
                       group-hover:text-white transition-colors">
        Meet<span style={{ color: "#818cf8" }}>Track</span>
      </span>
    </Link>
  );
}
