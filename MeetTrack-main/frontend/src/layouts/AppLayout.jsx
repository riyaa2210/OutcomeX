import { History, LayoutDashboard, LogOut, User } from "lucide-react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import BrandLogo from "../components/BrandLogo";
import ThemeToggle from "../components/ThemeToggle";
import useAuth from "../context/useAuth";

const NAV = [
  { to: "/dashboard", label: "Dashboard", Icon: LayoutDashboard },
  { to: "/history",   label: "History",   Icon: History          },
  { to: "/profile",   label: "Profile",   Icon: User             },
];

export default function AppLayout() {
  const { logout, user } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="flex min-h-screen" style={{ background: "#07090f" }}>

      {/* ── sidebar ── */}
      <aside className="hidden w-[220px] flex-shrink-0 flex-col p-4 lg:flex"
        style={{
          borderRight: "1px solid rgba(255,255,255,0.045)",
          background: "rgba(9,12,22,0.85)",
          backdropFilter: "blur(16px)",
        }}>

        {/* brand row */}
        <div className="flex items-center justify-between gap-2 pb-4"
          style={{ borderBottom: "1px solid rgba(255,255,255,0.045)" }}>
          <BrandLogo to="/dashboard" />
          <ThemeToggle />
        </div>

        {/* user chip */}
        <div className="mt-4 rounded-xl px-3 py-2.5"
          style={{
            background: "rgba(99,102,241,0.07)",
            border: "1px solid rgba(99,102,241,0.14)",
          }}>
          <p className="text-[9px] font-black uppercase tracking-[0.14em] text-indigo-500 mb-0.5">
            Signed in as
          </p>
          <p className="text-[11px] font-medium text-slate-400 truncate">{user?.email}</p>
        </div>

        {/* nav */}
        <nav className="mt-4 flex-1 space-y-0.5">
          {NAV.map(({ to, label, Icon }) => (
            <NavLink key={to} to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] font-semibold
                 transition-all duration-200
                 ${isActive ? "text-white" : "text-slate-600 hover:text-slate-300"}`
              }
              style={({ isActive }) => isActive
                ? {
                    background: "linear-gradient(135deg, rgba(67,56,202,0.32), rgba(14,116,144,0.18))",
                    border: "1px solid rgba(99,102,241,0.22)",
                    boxShadow: "0 2px 14px rgba(67,56,202,0.18)",
                  }
                : { border: "1px solid transparent" }
              }
            >
              {({ isActive }) => (
                <>
                  <Icon className="h-4 w-4 flex-shrink-0"
                    style={{ color: isActive ? "#a5b4fc" : undefined }} />
                  {label}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* logout — always visible, styled prominently */}
        <div className="pt-3" style={{ borderTop: "1px solid rgba(255,255,255,0.05)" }}>
          <button
            onClick={() => { logout(); navigate("/"); }}
            className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left
                       text-[13px] font-bold transition-all duration-200"
            style={{
              background: "rgba(239,68,68,0.08)",
              border: "1px solid rgba(239,68,68,0.18)",
              color: "#f87171",
            }}
            onMouseEnter={e => { e.currentTarget.style.background = "rgba(239,68,68,0.15)"; e.currentTarget.style.color = "#fca5a5"; }}
            onMouseLeave={e => { e.currentTarget.style.background = "rgba(239,68,68,0.08)"; e.currentTarget.style.color = "#f87171"; }}
          >
            <LogOut className="h-4 w-4 flex-shrink-0" />
            Logout
          </button>
        </div>
      </aside>

      {/* ── main ── */}
      <main className="flex-1 overflow-auto p-5 lg:p-8">
        <Outlet />
      </main>
    </div>
  );
}
