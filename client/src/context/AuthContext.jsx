import { useMemo, useState } from "react";
import AuthContext from "./authContextObject";

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const cached = localStorage.getItem("meettrack-user");
    return cached ? JSON.parse(cached) : null;
  });

  const login = (email) => {
    const profile = { name: "MeetTrack User", email };
    localStorage.setItem("meettrack-user", JSON.stringify(profile));
    setUser(profile);
  };

  const logout = () => {
    localStorage.removeItem("meettrack-user");
    setUser(null);
  };

  const value = useMemo(() => ({ user, login, logout }), [user]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

