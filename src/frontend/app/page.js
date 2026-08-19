"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../lib/auth-context";
import LoadingState from "../components/LoadingState";

export default function Home() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.push("/login");
    } else if (user.role === "admin") {
      router.push("/admin");
    } else if (user.role === "reviewer") {
      router.push("/reviewer");
    } else {
      router.push("/requester");
    }
  }, [user, loading, router]);

  return <div className="center-shell"><LoadingState /></div>;
}
