"use client";
import Link from "next/link";
import { ConnectButton } from "@rainbow-me/rainbowkit";
import { usePathname } from "next/navigation";

const links = [
  { href: "/",          label: "Protocol",  icon: "⚡" },
  { href: "/store",     label: "Store",     icon: "🛍️" },
  { href: "/dashboard", label: "My Account",icon: "👤" },
  { href: "/merchant",  label: "Merchant",  icon: "🏪" },
  { href: "/agent",        label: "RL Agent",     icon: "🤖" },
  { href: "/economy",      label: "Simulator",    icon: "📡" },
  { href: "/machinations", label: "Token Flow",   icon: "🔀" },
];

export function Navbar() {
  const path = usePathname();
  const isCheckout = path === "/checkout";

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
              {links.map(l => (
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
