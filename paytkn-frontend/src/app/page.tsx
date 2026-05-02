"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Dashboard } from "@/components/Dashboard";

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    // On the merchant port, redirect root → /merchant automatically
    if (window.location.port === "3001") {
      router.replace("/merchant");
    }
  }, [router]);

  // On port 3001 this will flash briefly before redirect — acceptable
  if (typeof window !== "undefined" && window.location.port === "3001") {
    return (
      <div className="min-h-[70vh] flex items-center justify-center">
        <div className="text-gray-500 text-sm">Redirecting to merchant dashboard…</div>
      </div>
    );
  }

  return <Dashboard />;
}
