"use client";

import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { api } from "./api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    const token = typeof window !== "undefined" ? localStorage.getItem("cdf_token") : null;
    if (!token) {
      setLoading(false);
      return;
    }
    api
      .me()
      .then(setUser)
      .catch(() => {
        localStorage.removeItem("cdf_token");
      })
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(
    async (email, password) => {
      const data = await api.login(email, password);
      localStorage.setItem("cdf_token", data.access_token);
      setUser(data.user);
      if (data.user.role === "admin") {
        router.push("/admin");
      } else if (data.user.role === "reviewer") {
        router.push("/reviewer");
      } else {
        router.push("/requester");
      }
      return data.user;
    },
    [router]
  );

  const logout = useCallback(() => {
    localStorage.removeItem("cdf_token");
    setUser(null);
    router.push("/login");
  }, [router]);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
