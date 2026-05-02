"use client";
import Link from "next/link";
import { ConnectButton } from "@rainbow-me/rainbowkit";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

const USER_LINKS = [
  { href: "/",             label: "Protocol",   icon: "⚡" },
  { href: "/demo",         label: "Live Demo",  icon: "🔴" },
  { href: "/store",        label: "Store",      icon: "🛍️" },
  { href: "/dashboard",    label: "My Account", icon: "👤" },
  { href: "/agent",        label: "RL Agent",   icon: "🤖" },
  { href: "/economy",      label: "Simulator",  icon: "📡" },
  { href: "/machinations", label: "Token Flow", icon: "🔀" },
];

export function Navbar() {
  const path = usePathname();
  const isCheckout = path === "/checkout";
  const [isMerchantPort, setIsMerchantPort] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    setIsMerchantPort(window.location.port === "3001");
  }, []);

  // ── Port 3001: Merchant-only navbar ──────────────────────────────────────
  if (mounted && isMerchantPort) {
    return (
      <nav className="border-b border-emerald-900/60 bg-gray-900/95 backdrop-blur sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <div className="font-bold text-xl text-emerald-400 tracking-tight flex items-center gap-2">
              <span className="w-7 h-7 bg-emerald-700 rounded-lg flex items-center justify-center text-xs font-black text-white">P</span>
              PAYTKN
              <span className="text-xs font-normal text-emerald-700 border border-emerald-800 rounded px-1.5 py-0.5 ml-1">
                Merchant :3001
              </span>
            </div>
            <a
              href="http://localhost:3000"
              className="text-xs text-gray-600 hover:text-gray-400 flex items-center gap-1 transition-colors"
            >
              ← User App (localhost:3000)
            </a>
          </div>
          <ConnectButton />
        </div>
      </nav>
    );
  }

  // ── Port 3000: Full user-facing navbar ───────────────────────────────────
  return (
    <nav className="border-b border-gray-800 bg-gray-900/90 backdrop-blur sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
        <div className="flex items-center gap-8">
          <Link href="/" className="font-bold text-xl text-indigo-400 tracking-tight flex items-center gap-2">
            <span className="w-7 h-7 bg-indigo-600 rounded-lg flex items-center justify-center text-xs font-black">P</span>
            PAYTKN
          </Link>
          {!isCheckout && (
            <div className="hidden md:flex gap-1">
              {USER_LINKS.map(l => (
                <Link key={l.href} href={l.href}
                  className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-1.5
                    ${path === l.href || (l.href !== "/" && path.startsWith(l.href))
                      ? "bg-indigo-600 text-white"
                      : "text-gray-400 hover:text-white hover:bg-gray-800"}`}>
                  <span className="text-xs">{l.icon}</span>{l.label}
                </Link>
              ))}
            </div>
          )}
        </div>
        <ConnectButton />
      </div>
    </nav>
  );
}
