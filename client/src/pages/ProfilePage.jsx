import { motion as Motion } from "framer-motion";
import { useState } from "react";
import { BriefcaseBusiness, Camera, Globe, Mail, MapPin, User } from "lucide-react";
import { buttonHoverProps, fadeInProps, subtle } from "../lib/motionPresets";

export default function ProfilePage() {
  const [profile, setProfile] = useState({
    fullName: "John Doe",
    email: "john.doe@company.com",
    jobTitle: "Product Manager",
    department: "Engineering",
    location: "San Francisco, CA",
    timezone: "PST (UTC-8)",
  });

  const updateField = (key, value) => setProfile((prev) => ({ ...prev, [key]: value }));

  return (
    <Motion.div className="space-y-6" {...fadeInProps}>
      <Motion.section
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={subtle}
        className="overflow-hidden rounded-2xl border border-violet-500 bg-white shadow-md shadow-slate-200/50 dark:border-violet-600 dark:bg-slate-900/70 dark:shadow-black/40"
      >
        <div className="flex items-start justify-between bg-gradient-to-r from-indigo-600 to-violet-400 px-6 py-5 text-white">
          <div>
            <h1 className="text-4xl font-bold tracking-tight">Profile Information</h1>
            <p className="mt-1 text-violet-100">Your personal and professional details</p>
          </div>
          <Motion.button type="button" className="rounded-lg px-3 py-1.5 font-semibold text-white hover:bg-white/15" {...buttonHoverProps}>
            Edit
          </Motion.button>
        </div>

        <div className="grid gap-8 p-6 lg:grid-cols-[180px_1fr]">
          <div className="flex flex-col items-center">
            <span className="inline-flex rounded-full bg-violet-500 p-7 text-white">
              <User className="h-16 w-16" />
            </span>
            <Motion.button
              type="button"
              className="mt-4 inline-flex items-center gap-2 rounded-xl border border-violet-500 px-4 py-2 text-sm font-semibold text-violet-600 hover:bg-violet-50 dark:border-violet-400 dark:text-violet-300 dark:hover:bg-violet-950/50"
              {...buttonHoverProps}
            >
              <Camera className="h-4 w-4" />
              Change Photo
            </Motion.button>
          </div>

          <div className="grid gap-5 md:grid-cols-2">
            <ProfileField
              label="Full Name"
              icon={User}
              value={profile.fullName}
              onChange={(value) => updateField("fullName", value)}
            />
            <ProfileField
              label="Email"
              icon={Mail}
              value={profile.email}
              onChange={(value) => updateField("email", value)}
            />
            <ProfileField
              label="Job Title"
              icon={BriefcaseBusiness}
              value={profile.jobTitle}
              onChange={(value) => updateField("jobTitle", value)}
            />
            <ProfileField
              label="Department"
              icon={BriefcaseBusiness}
              value={profile.department}
              onChange={(value) => updateField("department", value)}
            />
            <ProfileField
              label="Location"
              icon={MapPin}
              value={profile.location}
              onChange={(value) => updateField("location", value)}
            />
            <ProfileField
              label="Timezone"
              icon={Globe}
              value={profile.timezone}
              onChange={(value) => updateField("timezone", value)}
            />
          </div>
        </div>
      </Motion.section>
    </Motion.div>
  );
}

function ProfileField({ label, icon, value, onChange }) {
  const FieldIcon = icon;
  return (
    <label className="block">
      <span className="mb-2 inline-flex items-center gap-2 text-sm font-semibold text-slate-700 dark:text-slate-300">
        <FieldIcon className="h-4 w-4 text-violet-600 dark:text-violet-400" />
        {label}
      </span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-xl border border-slate-100 bg-slate-50 px-4 py-3 text-slate-700 outline-none focus:border-violet-400 focus:bg-white dark:border-slate-700 dark:bg-slate-800/80 dark:text-slate-200 dark:focus:border-violet-500 dark:focus:bg-slate-800"
      />
    </label>
  );
}
