/**
 * Authentication Service
 * Handles all authentication-related API calls
 */

import api from "./api";

export const authService = {
  /**
   * Register a new user
   */
  async register(email, password, full_name = "", role = "employee") {
    const BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
    try {
      const response = await fetch(`${BASE}/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, full_name: full_name || "", role }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        // FastAPI 422 returns { detail: [...] } — extract readable message
        let msg = "Registration failed";
        if (data.detail) {
          if (typeof data.detail === "string") {
            msg = data.detail;
          } else if (Array.isArray(data.detail)) {
            msg = data.detail.map(e => `${e.loc?.join(".")}: ${e.msg}`).join(", ");
          }
        }
        throw new Error(msg);
      }
      return data;
    } catch (error) {
      throw new Error(error.message || "Registration failed");
    }
  },

  /**
   * Login user
   */
  async login(email, password) {
    const BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
    try {
      const formData = new FormData();
      formData.append("username", email); // FastAPI OAuth2 expects 'username'
      formData.append("password", password);

      const response = await fetch(`${BASE}/login`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        let msg = "Login failed";
        if (error.detail) {
          msg = typeof error.detail === "string" ? error.detail : JSON.stringify(error.detail);
        }
        throw new Error(msg);
      }

      const data = await response.json();
      // Store access token
      if (data.access_token) {
        localStorage.setItem("access_token", data.access_token);
      }
      return data;
    } catch (error) {
      throw new Error(error.message || "Login failed");
    }
  },

  /**
   * Logout user (clear local token)
   */
  logout() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("user");
  },

  /**
   * Get current user profile
   */
  async getUserProfile(userId) {
    try {
      const response = await api.get(`/profile/${userId}`);
      return response;
    } catch (error) {
      throw new Error(error.message || "Failed to get profile");
    }
  },

  /**
   * Update user profile
   */
  async updateProfile(userId, profileData) {
    try {
      const response = await api.put(`/profile/${userId}`, profileData);
      return response;
    } catch (error) {
      throw new Error(error.message || "Failed to update profile");
    }
  },

  /**
   * Get access token from storage
   */
  getAccessToken() {
    return localStorage.getItem("access_token");
  },

  /**
   * Store access token
   */
  setAccessToken(token) {
    localStorage.setItem("access_token", token);
  },

  /**
   * Check if user is authenticated
   */
  isAuthenticated() {
    return !!localStorage.getItem("access_token");
  },
};

export default authService;
