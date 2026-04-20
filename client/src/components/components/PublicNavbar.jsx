import { AnimatePresence, motion as M } from "framer-motion";
import { Menu, X } from "lucide-react";
import { useState, useEffect } from "react";
import { Link, NavLink } from "react-router-dom";
import BrandLogo from "./BrandLogo";

const LINKS = [
  { to: "/",        label: "Home"    },
  { to: "/about",   label: "About"   },
  { to: "/contact", label: "Contact" },
];

const ease = [0.25, 0.1, 0.25, 1];

export default function PublicNavbar() {
  const [open,     setOpen]     = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const fn = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", fn, { passive: true });
    return () => window.removeEventListener("scroll", fn);
  }, []);

  return (
    <M.header
      initial={{ y: -60, opacity: 0 }}
      animate={{ y: 0,   opacity: 1 }}
      transition={{ duration: 0.55, ease }}
      className="fixed top-0 left-0 right-0 z-50 transition-all duration-300"
      style={{
        background: scrolled ? "rgba(7,9,15,0.9)" : "rgba(7,9,15,0.4)",
        backdropFilter: "blur(16px)",
        borderBottom: scrolled ? "1px solid rgba(255,255,255,0.07)" : "1px solid transparent",
        boxShadow: scrolled ? "0 4px 24px rgba(0,0,0,0.4)" : "none",
      }}
    >
      <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-3.5">
        <BrandLogo />

        {/* desktop nav links */}
        <nav className="hidden items-center gap-1 md:flex">
          {LINKS.map(({ to, label }) => (
            <NavLink
              key={to}
              to={to}
              className="rounded-xl px-3.5 py-2 text-[13px] font-semibold transition-all duration-200"
              style={({ isActive }) => ({
                color: isActive ? "#fff" : "#64748b",
                background: isActive ? "rgba(255,255,255,0.07)" : "transparent",
              })}
            >
              {label}
            </NavLink>
          ))}
        </nav>

        {/* desktop CTAs */}
        <div className="hidden items-center gap-3 md:flex">
          <Link
            to="/auth"
            className="rounded-xl px-4 py-2 text-[13px] font-semibold transition-colors"
            style={{ color: "#64748b" }}
            onMouseEnter={e => { e.currentTarget.style.color = "#e2e8f0"; }}
            onMouseLeave={e => { e.currentTarget.style.color = "#64748b"; }}
          >
            Sign in
          </Link>
          <M.div whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}>
            <Link
              to="/auth"
              className="rounded-xl px-4 py-2 text-[13px] font-bold text-white"
              style={{
                background: "linear-gradient(135deg, #4338ca, #0e7490)",
                boxShadow: "0 2px 16px rgba(67,56,202,0.4)",
              }}
            >
              Get Started
            </Link>
          </M.div>
        </div>

        {/* mobile toggle */}
        <button
          onClick={() => setOpen(v => !v)}
          className="rounded-xl p-2 transition-colors md:hidden"
          style={{ color: "#64748b" }}
        >
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </div>

      {/* mobile menu */}
      <AnimatePresence>
        {open && (
          <M.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.28 }}
            className="overflow-hidden border-t md:hidden"
            style={{ borderColor: "rgba(255,255,255,0.06)", background: "rgba(7,9,15,0.96)" }}
          >
            <div className="flex flex-col gap-1 px-5 py-4">
              {LINKS.map(({ to, label }) => (
                <NavLink
                  key={to}
                  to={to}
                  onClick={() => setOpen(false)}
                  className="rounded-xl px-3 py-2.5 text-sm font-semibold transition-colors"
                  style={({ isActive }) => ({
                    color: isActive ? "#fff" : "#64748b",
                    background: isActive ? "rgba(255,255,255,0.06)" : "transparent",
                  })}
                >
                  {label}
                </NavLink>
              ))}
              <Link
                to="/auth"
                onClick={() => setOpen(false)}
                className="mt-2 rounded-xl px-3 py-2.5 text-center text-sm font-bold text-white"
                style={{ background: "linear-gradient(135deg, #4338ca, #0e7490)" }}
              >
                Get Started
              </Link>
            </div>
          </M.div>
        )}
      </AnimatePresence>
    </M.header>
  );
}
