"use client";
import Link from "next/link";
import { useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { GATEWAY_RATE } from "@/lib/web3";

// ── Products — priced in ETH for testnet demo ────────────────────────────────
const PRODUCTS = [
  { id: 1, name: "MacBook Pro 14\"",       ethPrice: 0.005, category: "Laptops",     emoji: "💻", desc: "Apple M3 Pro · 18GB RAM · 512GB SSD",          stock: 12, featured: true  },
  { id: 2, name: "iPhone 15 Pro",           ethPrice: 0.003, category: "Phones",      emoji: "📱", desc: "Titanium · A17 Pro · 256GB",                   stock: 8,  featured: true  },
  { id: 3, name: "Sony WH-1000XM5",         ethPrice: 0.001, category: "Audio",       emoji: "🎧", desc: "Industry-leading noise cancellation",           stock: 24, featured: false },
  { id: 4, name: "iPad Pro 12.9\"",         ethPrice: 0.004, category: "Tablets",     emoji: "📲", desc: "M2 chip · Liquid Retina XDR display",          stock: 6,  featured: false },
  { id: 5, name: "Samsung 4K Monitor 27\"", ethPrice: 0.002, category: "Monitors",    emoji: "🖥️", desc: "144Hz · HDR600 · USB-C Hub",                   stock: 15, featured: false },
  { id: 6, name: "Mechanical Keyboard",     ethPrice: 0.001, category: "Accessories", emoji: "⌨️", desc: "Cherry MX Red · RGB · TKL layout",            stock: 40, featured: false },
  { id: 7, name: "Logitech MX Master 3S",   ethPrice: 0.001, category: "Accessories", emoji: "🖱️", desc: "8K DPI · Silent clicks · USB-C",               stock: 50, featured: false },
  { id: 8, name: "AirPods Pro 2nd Gen",     ethPrice: 0.001, category: "Audio",       emoji: "🎵", desc: "ANC · Spatial Audio · MagSafe case",           stock: 30, featured: false },
];

const SUBSCRIPTIONS = [
  { id: "sub_1", name: "TechMart Pro",      ethPrice: 0.001, period: "monthly", color: "border-blue-500/40 bg-blue-500/5",    features: ["Early access to deals", "5% extra cashback", "Free shipping", "Priority support"],                                                            paytkn_bonus: 3  },
  { id: "sub_2", name: "TechMart Business", ethPrice: 0.002, period: "monthly", color: "border-indigo-500/40 bg-indigo-500/5", features: ["All Pro benefits", "Bulk order discounts", "Dedicated account manager", "API access", "10% extra cashback"],                               paytkn_bonus: 6  },
  { id: "sub_3", name: "TechMart Annual",   ethPrice: 0.005, period: "yearly",  color: "border-purple-500/40 bg-purple-500/5", features: ["All Business benefits", "Free device insurance", "Extended warranty", "Exclusive events", "15% extra cashback"],                          paytkn_bonus: 15 },
];

const CATEGORIES = ["All", "Laptops", "Phones", "Tablets", "Audio", "Monitors", "Accessories"];

// How many PAYTKN merchant receives per product
function merchantPAYTKN(ethPrice: number) {
  return (ethPrice * 0.995 * GATEWAY_RATE).toFixed(2);
}

// ── Inner component (uses useSearchParams) ───────────────────────────────────
function StoreInner() {
  const params = useSearchParams();

  // Merchant address + name come from URL — set by merchant clicking "Share Store" at :3001
  const merchantAddr = params.get("merchant") ?? "";
  const merchantName = params.get("merchant_name") ?? "TechMart Store";
  const hasMerchant  = merchantAddr.startsWith("0x") && merchantAddr.length === 42;

  const [activeCategory, setActiveCategory] = useState("All");
  const [activeTab, setActiveTab]           = useState<"products" | "subscriptions">("products");

  const filtered = activeCategory === "All"
    ? PRODUCTS
    : PRODUCTS.filter(p => p.category === activeCategory);
  const featured = PRODUCTS.filter(p => p.featured);

  function checkoutLink(product: typeof PRODUCTS[0]) {
    const p = new URLSearchParams({
      product:       product.name,
      price:         product.ethPrice.toString(),
      eth_amount:    product.ethPrice.toString(),
      merchant:      merchantAddr,
      merchant_name: merchantName,
      description:   product.desc,
      emoji:         product.emoji,
      type:          "one-time",
    });
    return `/checkout?${p}`;
  }

  function subLink(sub: typeof SUBSCRIPTIONS[0]) {
    const p = new URLSearchParams({
      product:       sub.name,
      price:         sub.ethPrice.toString(),
      eth_amount:    sub.ethPrice.toString(),
      merchant:      merchantAddr,
      merchant_name: merchantName,
      description:   `${sub.period} subscription · +${sub.paytkn_bonus} PAYTKN/period`,
      emoji:         "🔄",
      type:          "subscription",
      period:        sub.period,
    });
    return `/checkout?${p}`;
  }

  return (
    <div className="space-y-6">

      {/* ── Merchant status banner ─────────────────────────────────────────── */}
      {!hasMerchant ? (
        <div className="bg-amber-900/25 border border-amber-700/40 rounded-2xl p-6 flex items-start gap-4">
          <span className="text-3xl">⚠️</span>
          <div className="flex-1">
            <p className="font-bold text-amber-300 text-lg">No merchant connected</p>
            <p className="text-amber-400/70 text-sm mt-1">
              The merchant needs to open <strong>localhost:3001/merchant</strong>, connect their wallet,
              then click <strong>"Share Store Link"</strong>. Open that link here to load the store with their address.
            </p>
            <div className="mt-3 flex items-center gap-3">
              <span className="text-xs text-amber-600 font-mono bg-amber-900/30 px-3 py-1.5 rounded-lg">
                localhost:3001 → /merchant → Share Store Link
              </span>
            </div>
          </div>
        </div>
      ) : (
        <div className="bg-emerald-900/20 border border-emerald-700/30 rounded-2xl px-5 py-3 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="w-2.5 h-2.5 rounded-full bg-green-400 animate-pulse" />
            <div>
              <span className="text-sm font-semibold text-white">Merchant connected: </span>
              <span className="text-sm text-emerald-300">{merchantName}</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs text-gray-400">{merchantAddr.slice(0, 10)}…{merchantAddr.slice(-6)}</span>
            <a href={`https://sepolia.basescan.org/address/${merchantAddr}`} target="_blank" rel="noopener noreferrer"
              className="text-xs text-blue-400 hover:text-blue-300">Basescan ↗</a>
          </div>
        </div>
      )}

      {/* ── Store header ───────────────────────────────────────────────────── */}
      <div className="bg-gradient-to-r from-gray-900 via-indigo-950/40 to-gray-900 border border-gray-800 rounded-2xl p-7">
        <div className="flex items-center gap-4 mb-3">
          <span className="text-5xl">🖥️</span>
          <div>
            <h1 className="text-3xl font-bold text-white">{merchantName}</h1>
            <p className="text-gray-400 mt-1">Pay with ETH · Merchant receives PAYTKN · RL agent cashback</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-3 mt-4">
          <span className="bg-green-500/15 border border-green-500/30 text-green-400 text-xs px-3 py-1.5 rounded-full">✓ PAYTKN Accepted</span>
          <span className="bg-indigo-500/15 border border-indigo-500/30 text-indigo-400 text-xs px-3 py-1.5 rounded-full">⚡ ETH → PAYTKN Gateway</span>
          <span className="bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 text-xs px-3 py-1.5 rounded-full">⛓️ Base Sepolia · Real On-Chain</span>
          <span className="bg-amber-500/15 border border-amber-500/30 text-amber-400 text-xs px-3 py-1.5 rounded-full">🔴 Testnet Demo Prices</span>
        </div>
      </div>

      {/* ── Featured ───────────────────────────────────────────────────────── */}
      <div>
        <h2 className="text-xl font-bold text-white mb-4">⭐ Featured</h2>
        <div className="grid md:grid-cols-2 gap-4">
          {featured.map(p => (
            <div key={p.id} className="bg-gray-900 border border-indigo-500/30 rounded-2xl p-6 flex gap-4 hover:border-indigo-500/60 transition-colors">
              <span className="text-5xl shrink-0">{p.emoji}</span>
              <div className="flex-1 min-w-0">
                <div className="font-bold text-white text-lg">{p.name}</div>
                <div className="text-gray-400 text-sm mt-1">{p.desc}</div>
                <div className="flex items-center justify-between mt-4 gap-3">
                  <div>
                    <div className="text-2xl font-bold text-white">{p.ethPrice} ETH</div>
                    <div className="text-xs text-emerald-400 mt-0.5">
                      Merchant gets ~{merchantPAYTKN(p.ethPrice)} PAYTKN
                    </div>
                  </div>
                  {hasMerchant ? (
                    <Link href={checkoutLink(p)}
                      className="shrink-0 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold px-5 py-2.5 rounded-xl text-sm transition-colors">
                      Pay with ETH →
                    </Link>
                  ) : (
                    <button disabled
                      className="shrink-0 bg-gray-700 text-gray-500 font-semibold px-5 py-2.5 rounded-xl text-sm cursor-not-allowed">
                      No Merchant
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Tab switcher ───────────────────────────────────────────────────── */}
      <div className="flex gap-1 bg-gray-900 border border-gray-800 rounded-xl p-1 w-fit">
        {(["products", "subscriptions"] as const).map(t => (
          <button key={t} onClick={() => setActiveTab(t)}
            className={`px-5 py-2.5 rounded-lg text-sm font-medium transition-colors capitalize ${
              activeTab === t ? "bg-indigo-600 text-white" : "text-gray-400 hover:text-white"}`}>
            {t === "products" ? "🛒 All Products" : "🔄 Subscriptions"}
          </button>
        ))}
      </div>

      {/* ── Products grid ──────────────────────────────────────────────────── */}
      {activeTab === "products" && (
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {CATEGORIES.map(c => (
              <button key={c} onClick={() => setActiveCategory(c)}
                className={`px-4 py-1.5 rounded-full text-sm font-medium transition-colors ${
                  activeCategory === c ? "bg-indigo-600 text-white" : "bg-gray-800 text-gray-400 hover:text-white"}`}>
                {c}
              </button>
            ))}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filtered.map(p => (
              <div key={p.id} className="bg-gray-900 border border-gray-800 rounded-2xl p-5 hover:border-gray-700 transition-colors flex flex-col">
                <div className="flex items-start justify-between gap-2 mb-2">
                  <span className="text-4xl">{p.emoji}</span>
                  <span className="text-xs text-indigo-400 font-medium bg-indigo-400/10 px-2 py-0.5 rounded-full">{p.category}</span>
                </div>
                <div className="font-bold text-white text-base flex-1">{p.name}</div>
                <div className="text-gray-400 text-sm mt-1">{p.desc}</div>
                <div className="text-xs text-gray-600 mt-1">{p.stock} in stock</div>

                {/* Price + PAYTKN preview */}
                <div className="mt-4 bg-gray-800/60 rounded-xl p-3">
                  <div className="flex justify-between items-center">
                    <span className="text-xl font-bold text-white">{p.ethPrice} ETH</span>
                    <span className="text-xs text-emerald-400">~{merchantPAYTKN(p.ethPrice)} PAYTKN →🏪</span>
                  </div>
                  <div className="text-xs text-indigo-400/60 mt-0.5">🤖 RL cashback minted to buyer</div>
                </div>

                {hasMerchant ? (
                  <Link href={checkoutLink(p)}
                    className="mt-3 block w-full bg-indigo-600 hover:bg-indigo-500 text-white font-semibold py-2.5 rounded-xl text-sm text-center transition-colors">
                    Pay {p.ethPrice} ETH →
                  </Link>
                ) : (
                  <button disabled
                    className="mt-3 w-full bg-gray-800 text-gray-600 font-semibold py-2.5 rounded-xl text-sm cursor-not-allowed">
                    Merchant not connected
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Subscriptions ──────────────────────────────────────────────────── */}
      {activeTab === "subscriptions" && (
        <div className="grid md:grid-cols-3 gap-6">
          {SUBSCRIPTIONS.map(sub => (
            <div key={sub.id} className={`rounded-2xl border p-6 flex flex-col ${sub.color}`}>
              <div className="text-sm text-gray-400 mb-1 capitalize">{sub.period}</div>
              <div className="text-xl font-bold text-white">{sub.name}</div>
              <div className="mt-3">
                <span className="text-3xl font-black text-white">{sub.ethPrice} ETH</span>
                <span className="text-gray-400 text-sm">/{sub.period === "yearly" ? "yr" : "mo"}</span>
              </div>
              <div className="text-xs text-emerald-400 mt-1">Merchant gets ~{merchantPAYTKN(sub.ethPrice)} PAYTKN/period</div>
              <ul className="mt-5 space-y-2 flex-1">
                {sub.features.map((f, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-gray-300">
                    <span className="text-green-400 mt-0.5 shrink-0">✓</span>{f}
                  </li>
                ))}
              </ul>
              {hasMerchant ? (
                <Link href={subLink(sub)}
                  className="mt-6 block w-full bg-indigo-600 hover:bg-indigo-500 text-white font-bold py-3 rounded-xl text-center text-sm transition-colors">
                  Subscribe — {sub.ethPrice} ETH
                </Link>
              ) : (
                <button disabled className="mt-6 w-full bg-gray-800 text-gray-600 font-bold py-3 rounded-xl text-sm cursor-not-allowed">
                  No Merchant Connected
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* ── Protocol footer ────────────────────────────────────────────────── */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <span className="text-2xl">⚡</span>
          <div>
            <div className="text-sm font-semibold text-white">Powered by PAYTKN Protocol</div>
            <div className="text-xs text-gray-400">ETH → PAYTKN via Gateway · RL agent cashback · Base Sepolia</div>
          </div>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
          <span className="text-gray-500">Gateway: 3000 PAYTKN/ETH</span>
          {hasMerchant && (
            <span className="font-mono text-gray-600">{merchantAddr.slice(0, 10)}…</span>
          )}
        </div>
      </div>

    </div>
  );
}

// ── Suspense wrapper (required for useSearchParams in Next.js app router) ────
export default function StorePage() {
  return (
    <Suspense fallback={
      <div className="min-h-[70vh] flex items-center justify-center">
        <div className="text-gray-500">Loading store…</div>
      </div>
    }>
      <StoreInner />
    </Suspense>
  );
}
