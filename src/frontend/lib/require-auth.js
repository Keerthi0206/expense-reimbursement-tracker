"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../lib/auth-context";
import Nav from "../components/Nav";

export default function RequireAuth({ roles, children }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.push("/login");
      return;
    }
    if (roles && !roles.includes(user.role)) {
      const fallback = user.role === "requester" ? "/requester" : user.role === "admin" ? "/admin" : "/reviewer";
      router.push(fallback);
    }
  }, [user, loading, roles, router]);

  if (loading || !user || (roles && !roles.includes(user.role))) {
    return <div className="center-shell">Loading…</div>;
  }

  return (
    <div className="shell">
      <Nav />
      <div className="page">{children}</div>
    </div>
  );
}
