import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import AuthContext from "./authContextObject";
import { authService } from "../services/authService";

const STORAGE_KEY_TOKEN   = "access_token";
const STORAGE_KEY_REFRESH = "refresh_token";
const STORAGE_KEY_USER    = "user";

const API = import.meta.env.VITE_API_URL || "https://meeting-outcome-tracker-backend.onrender.com";

export function AuthProvider({ children }) {
  const [user, setUser]       = useState(null);
  const [token, setToken]     = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);
  const refreshTimerRef       = useRef(null);

  // ── Proactive token refresh (14 min after login, access token is 15 min) ──
  const scheduleRefresh = useCallback((delayMs = 14 * 60 * 1000) => {
    clearTimeout(refreshTimerRef.current);
    refreshTimerRef.current = setTimeout(async () => {
      const refreshToken = localStorage.getItem(STORAGE_KEY_REFRESH);
      if (!refreshToken) return;
      try {
        const res = await fetch(`${API}/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (res.ok) {
          const data = await res.json();
          localStorage.setItem(STORAGE_KEY_TOKEN,   data.access_token);
          localStorage.setItem(STORAGE_KEY_REFRESH, data.refresh_token);
          setToken(data.access_token);
          scheduleRefresh(); // schedule next refresh
        }
      } catch (e) {
        console.warn("[Auth] Token refresh failed:", e);
      }
    }, delayMs);
  }, []);

  // Initialize auth state from storage
  useEffect(() => {
    try {
      const storedUser  = localStorage.getItem(STORAGE_KEY_USER);
      const storedToken = localStorage.getItem(STORAGE_KEY_TOKEN);
      if (storedUser && storedToken) {
        setUser(JSON.parse(storedUser));
        setToken(storedToken);
        scheduleRefresh();
      }
    } catch (err) {
      console.error("Failed to initialize auth:", err);
    } finally {
      setLoading(false);
    }
    return () => clearTimeout(refreshTimerRef.current);
  }, [scheduleRefresh]);

  const register = useCallback(async (email, password, fullName = "", role = "employee") => {
    try {
      setError(null);
      setLoading(true);
      const response = await authService.register(email, password, fullName, role);
      const userData = {
        id: response.id, email: response.email,
        full_name: response.full_name || "", name: response.full_name || email.split("@")[0],
        role: response.role,
      };
      localStorage.setItem(STORAGE_KEY_USER, JSON.stringify(userData));
      setUser(userData);
      return response;
    } catch (err) {
      setError(err.message || "Registration failed");
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const login = useCallback(async (email, password) => {
    try {
      setError(null);
      setLoading(true);
      const response = await authService.login(email, password);

      // Store both tokens
      localStorage.setItem(STORAGE_KEY_TOKEN,   response.access_token);
      if (response.refresh_token) {
        localStorage.setItem(STORAGE_KEY_REFRESH, response.refresh_token);
      }
      setToken(response.access_token);

      const userData = {
        id: response.user_id || 1,
        email: response.email,
        name: response.full_name || email.split("@")[0],
        full_name: response.full_name || "",
        role: response.role || "employee",
      };
      localStorage.setItem(STORAGE_KEY_USER, JSON.stringify(userData));
      setUser(userData);
      scheduleRefresh();
      return response;
    } catch (err) {
      setError(err.message || "Login failed");
      throw err;
    } finally {
      setLoading(false);
    }
  }, [scheduleRefresh]);

  const logout = useCallback(async () => {
    try {
      clearTimeout(refreshTimerRef.current);
      const refreshToken = localStorage.getItem(STORAGE_KEY_REFRESH);
      const accessToken  = localStorage.getItem(STORAGE_KEY_TOKEN);
      // Best-effort server-side logout
      if (refreshToken && accessToken) {
        fetch(`${API}/auth/logout`, {
          method: "POST",
          headers: {
            "Content-Type":  "application/json",
            "Authorization": `Bearer ${accessToken}`,
          },
          body: JSON.stringify({ refresh_token: refreshToken }),
        }).catch(() => {});
      }
    } finally {
      authService.logout();
      localStorage.removeItem(STORAGE_KEY_USER);
      localStorage.removeItem(STORAGE_KEY_REFRESH);
      setUser(null);
      setToken(null);
      setError(null);
    }
  }, []);

  const updateProfile = useCallback(async (profileData) => {
    try {
      setError(null);
      setLoading(true);
      if (!user) throw new Error("No user logged in");
      const response = await authService.updateProfile(user.id, profileData);
      const updatedUser = { ...user, ...response };
      localStorage.setItem(STORAGE_KEY_USER, JSON.stringify(updatedUser));
      setUser(updatedUser);
      return response;
    } catch (err) {
      setError(err.message || "Failed to update profile");
      throw err;
    } finally {
      setLoading(false);
    }
  }, [user]);

  const clearError = useCallback(() => setError(null), []);

  const value = useMemo(
    () => ({
      user, token, loading, error,
      login, logout, register, updateProfile, clearError,
      isAuthenticated: !!user,
    }),
    [user, token, loading, error, login, logout, register, updateProfile, clearError]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

