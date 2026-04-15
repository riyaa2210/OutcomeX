import { motion as M, AnimatePresence } from "framer-motion";
import { useState, useEffect } from "react";
import {
  AlertCircle, BriefcaseBusiness, Check, Globe,
  LogOut, Mail, MapPin, Pencil, Plus, Save, User, X,
} from "lucide-react";
import useAuth from "../context/useAuth";
import { useNavigate } from "react-router-dom";

const ease = [0.25, 0.1, 0.25, 1];

/* ── field component ─────────────────────────────────────── */
function Field({ label, value, onChange, disabled, placeholder, type = "text", icon: Icon }) {
  return (
    <div>
      <label className="mb-1.5 flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-slate-500">
        {Icon && <Icon className="h-3.5 w-3.5" />}
        {label}
      </label>
      <input
        type={type}
        value={value}
        onChange={e => onChange(e.target.value)}
        disabled={disabled}
        placeholder={placeholder}
        className="w-full rounded-xl border px-4 py-2.5 text-sm font-medium outline-none transition-all"
        style={{
          background: disabled ? "#f8fafc" : "#fff",
          border: disabled ? "1px solid #e2e8f0" : "1px solid #c7d2fe",
          color: "#0f172a",
          boxShadow: disabled ? "none" : undefined,
        }}
        onFocus={e => { if (!disabled) { e.currentTarget.style.borderColor = "#6366f1"; e.currentTarget.style.boxShadow = "0 0 0 3px rgba(99,102,241,0.12)"; }}}
        onBlur={e  => { e.currentTarget.style.borderColor = disabled ? "#e2e8f0" : "#c7d2fe"; e.currentTarget.style.boxShadow = "none"; }}
      />
    </div>
  );
}

/* ── section wrapper ─────────────────────────────────────── */
function Section({ title, children }) {
  return (
    <div className="rounded-2xl bg-white p-6 shadow-sm"
      style={{ border: "1px solid #e2e8f0" }}>
      <h3 className="mb-5 text-sm font-black uppercase tracking-wider text-slate-400">
        {title}
      </h3>
      {children}
    </div>
  );
}

/* ── main page ───────────────────────────────────────────── */
export default function ProfilePage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const [editing,  setEditing]  = useState(false);
  const [saving,   setSaving]   = useState(false);
  const [loading,  setLoading]  = useState(true);
  const [success,  setSuccess]  = useState("");
  const [error,    setError]    = useState("");
  const [newSkill, setNewSkill] = useState("");

  const [profile, setProfile] = useState({
    fullName: "", email: "", phoneNumber: "", bio: "",
    jobTitle: "", department: "", employeeId: "", managerName: "",
    skills: [], location: "", workMode: "Office", timezone: "",
  });
  const [original, setOriginal] = useState(profile);

  useEffect(() => {
    if (!user?.id) { setLoading(false); return; }
    (async () => {
      try {
        const res = await fetch(`${import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"}/profile/${user.id}`, {
          headers: { Authorization: `Bearer ${localStorage.getItem("access_token")}` },
        });
        const d = res.ok ? await res.json() : user;
        const skills = Array.isArray(d.skills) ? d.skills
          : (typeof d.skills === "string" ? JSON.parse(d.skills || "[]") : []);
        setProfile({
          fullName: d.full_name || "", email: d.email || "",
          phoneNumber: d.phone_number || "", bio: d.bio || "",
          jobTitle: d.job_title || "", department: d.department || "",
          employeeId: d.employee_id || "", managerName: d.manager_name || "",
          skills, location: d.location || "",
          workMode: d.work_mode || "Office", timezone: d.timezone || "",
        });
      } catch { /* fallback already set */ }
      finally { setLoading(false); }
    })();
  }, [user?.id]);

  const set = k => v => setProfile(p => ({ ...p, [k]: v }));

  function addSkill() {
    const s = newSkill.trim();
    if (s && !profile.skills.includes(s)) {
      set("skills")([...profile.skills, s]);
      setNewSkill("");
    }
  }

  async function handleSave() {
    setSaving(true); setError(""); setSuccess("");
    try {
      const res = await fetch(`${import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"}/profile/${user.id}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
        },
        body: JSON.stringify({
          full_name: profile.fullName, phone_number: profile.phoneNumber || null,
          bio: profile.bio || null, job_title: profile.jobTitle || null,
          department: profile.department || null, employee_id: profile.employeeId || null,
          manager_name: profile.managerName || null, skills: profile.skills,
          location: profile.location || null, work_mode: profile.workMode || null,
          timezone: profile.timezone || null,
        }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || "Save failed");
      setSuccess("Profile saved successfully");
      setEditing(false);
      setTimeout(() => setSuccess(""), 3000);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="h-10 w-10 rounded-full border-4 border-indigo-200 border-t-indigo-600 animate-spin" />
      </div>
    );
  }

  const initials = profile.fullName
    ? profile.fullName.split(" ").map(w => w[0]).join("").toUpperCase().slice(0, 2)
    : (profile.email?.[0] || "?").toUpperCase();

  return (
    <M.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease }}
      className="mx-auto max-w-3xl space-y-5 pb-12"
    >
      {/* ── hero card ── */}
      <div className="relative overflow-hidden rounded-3xl bg-white shadow-md"
        style={{ border: "1px solid #e2e8f0" }}>

        {/* gradient banner */}
        <div className="h-28 w-full"
          style={{ background: "linear-gradient(135deg, #4338ca 0%, #0e7490 60%, #059669 100%)" }} />

        {/* avatar + name row */}
        <div className="px-7 pb-6">
          <div className="flex items-end justify-between -mt-10 mb-4">
            {/* avatar */}
            <div className="flex h-20 w-20 items-center justify-center rounded-2xl text-2xl font-black text-white shadow-lg"
              style={{
                background: "linear-gradient(135deg, #4338ca, #0e7490)",
                border: "4px solid #fff",
                boxShadow: "0 4px 20px rgba(67,56,202,0.3)",
              }}>
              {initials}
            </div>

            {/* action buttons */}
            <div className="flex items-center gap-2 mb-1">
              {editing ? (
                <>
                  <M.button
                    whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}
                    onClick={handleSave} disabled={saving}
                    className="flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-bold text-white"
                    style={{ background: "linear-gradient(135deg, #059669, #0d9488)", boxShadow: "0 2px 12px rgba(5,150,105,0.3)" }}
                  >
                    <Save className="h-4 w-4" />
                    {saving ? "Saving…" : "Save"}
                  </M.button>
                  <button onClick={() => { setProfile(original); setEditing(false); setError(""); }}
                    className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50 transition-colors">
                    <X className="h-4 w-4" />
                    Cancel
                  </button>
                </>
              ) : (
                <M.button
                  whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}
                  onClick={() => { setOriginal(profile); setEditing(true); }}
                  className="flex items-center gap-2 rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-2 text-sm font-bold text-indigo-700 hover:bg-indigo-100 transition-colors"
                >
                  <Pencil className="h-4 w-4" />
                  Edit Profile
                </M.button>
              )}

              {/* logout — always visible */}
              <M.button
                whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}
                onClick={() => { logout(); navigate("/"); }}
                className="flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-2 text-sm font-bold text-red-600 hover:bg-red-100 transition-colors"
              >
                <LogOut className="h-4 w-4" />
                Logout
              </M.button>
            </div>
          </div>

          <h1 className="text-xl font-black text-slate-900">
            {profile.fullName || "Your Name"}
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {profile.jobTitle && profile.department
              ? `${profile.jobTitle} · ${profile.department}`
              : profile.jobTitle || profile.email}
          </p>

          {/* quick meta row */}
          <div className="mt-3 flex flex-wrap gap-4">
            {profile.email && (
              <span className="flex items-center gap-1.5 text-xs text-slate-500">
                <Mail className="h-3.5 w-3.5 text-indigo-400" />
                {profile.email}
              </span>
            )}
            {profile.location && (
              <span className="flex items-center gap-1.5 text-xs text-slate-500">
                <MapPin className="h-3.5 w-3.5 text-indigo-400" />
                {profile.location}
              </span>
            )}
            {profile.workMode && (
              <span className="flex items-center gap-1.5 text-xs text-slate-500">
                <BriefcaseBusiness className="h-3.5 w-3.5 text-indigo-400" />
                {profile.workMode}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* ── alerts ── */}
      <AnimatePresence>
        {success && (
          <M.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            className="flex items-center gap-3 rounded-xl bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-700"
            style={{ border: "1px solid #a7f3d0" }}>
            <Check className="h-4 w-4" /> {success}
          </M.div>
        )}
        {error && (
          <M.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            className="flex items-center gap-3 rounded-xl bg-red-50 px-4 py-3 text-sm font-semibold text-red-700"
            style={{ border: "1px solid #fecaca" }}>
            <AlertCircle className="h-4 w-4" /> {error}
          </M.div>
        )}
      </AnimatePresence>

      {/* ── personal info ── */}
      <Section title="Personal Information">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Full Name"    icon={User}  value={profile.fullName}    onChange={set("fullName")}    disabled={!editing} placeholder="Jane Smith" />
          <Field label="Email"        icon={Mail}  value={profile.email}       onChange={() => {}}           disabled={true}     placeholder="you@company.com" />
          <Field label="Phone Number" icon={User}  value={profile.phoneNumber} onChange={set("phoneNumber")} disabled={!editing} placeholder="+1 (555) 000-0000" />
        </div>
        <div className="mt-4">
          <label className="mb-1.5 flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-slate-500">
            Bio
          </label>
          <textarea
            value={profile.bio}
            onChange={e => set("bio")(e.target.value)}
            disabled={!editing}
            placeholder="Tell us about yourself…"
            rows={3}
            className="w-full resize-none rounded-xl border px-4 py-2.5 text-sm font-medium outline-none transition-all"
            style={{
              background: editing ? "#fff" : "#f8fafc",
              border: editing ? "1px solid #c7d2fe" : "1px solid #e2e8f0",
              color: "#0f172a",
            }}
            onFocus={e => { if (editing) { e.currentTarget.style.borderColor = "#6366f1"; e.currentTarget.style.boxShadow = "0 0 0 3px rgba(99,102,241,0.12)"; }}}
            onBlur={e  => { e.currentTarget.style.borderColor = editing ? "#c7d2fe" : "#e2e8f0"; e.currentTarget.style.boxShadow = "none"; }}
          />
        </div>
      </Section>

      {/* ── professional details ── */}
      <Section title="Professional Details">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Job Title"    icon={BriefcaseBusiness} value={profile.jobTitle}    onChange={set("jobTitle")}    disabled={!editing} placeholder="Software Engineer" />
          <Field label="Department"   icon={BriefcaseBusiness} value={profile.department}  onChange={set("department")}  disabled={!editing} placeholder="Engineering" />
          <Field label="Employee ID"  icon={User}              value={profile.employeeId}  onChange={set("employeeId")}  disabled={!editing} placeholder="EMP-12345" />
          <Field label="Manager Name" icon={User}              value={profile.managerName} onChange={set("managerName")} disabled={!editing} placeholder="Manager's name" />
        </div>

        {/* skills */}
        <div className="mt-5 pt-5" style={{ borderTop: "1px solid #f1f5f9" }}>
          <p className="mb-3 text-xs font-black uppercase tracking-wider text-slate-400">
            Skills
          </p>
          {editing && (
            <div className="mb-3 flex gap-2">
              <input
                value={newSkill}
                onChange={e => setNewSkill(e.target.value)}
                onKeyDown={e => e.key === "Enter" && addSkill()}
                placeholder="Add a skill…"
                className="flex-1 rounded-xl border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm font-medium text-slate-800 outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
              />
              <button onClick={addSkill}
                className="flex items-center gap-1 rounded-xl bg-indigo-600 px-3 py-2 text-sm font-bold text-white hover:bg-indigo-700 transition-colors">
                <Plus className="h-4 w-4" />
              </button>
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            {profile.skills.map(s => (
              <span key={s}
                className="flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold"
                style={{ background: "#eef2ff", color: "#4338ca", border: "1px solid #c7d2fe" }}>
                {s}
                {editing && (
                  <button onClick={() => set("skills")(profile.skills.filter(x => x !== s))}
                    className="text-indigo-400 hover:text-indigo-700 transition-colors">
                    ×
                  </button>
                )}
              </span>
            ))}
            {profile.skills.length === 0 && (
              <p className="text-xs text-slate-400 italic">No skills added yet</p>
            )}
          </div>
        </div>
      </Section>

      {/* ── location & work ── */}
      <Section title="Location & Work">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Location" icon={MapPin} value={profile.location} onChange={set("location")} disabled={!editing} placeholder="City, Country" />
          <Field label="Timezone" icon={Globe}  value={profile.timezone} onChange={set("timezone")} disabled={!editing} placeholder="UTC, EST, IST…" />
          <div>
            <label className="mb-1.5 flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-slate-500">
              <BriefcaseBusiness className="h-3.5 w-3.5" />
              Work Mode
            </label>
            <select
              value={profile.workMode}
              onChange={e => set("workMode")(e.target.value)}
              disabled={!editing}
              className="w-full rounded-xl border px-4 py-2.5 text-sm font-medium outline-none transition-all"
              style={{
                background: editing ? "#fff" : "#f8fafc",
                border: editing ? "1px solid #c7d2fe" : "1px solid #e2e8f0",
                color: "#0f172a",
              }}
            >
              <option value="Office">🏢 Office</option>
              <option value="Hybrid">🔄 Hybrid</option>
              <option value="Remote">🏠 Remote</option>
            </select>
          </div>
        </div>
      </Section>
    </M.div>
  );
}
