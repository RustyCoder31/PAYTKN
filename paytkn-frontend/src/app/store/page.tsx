"use client";
import Link from "next/link";
import { useState } from "react";

const MERCHANT = {
  name: "TechMart Store",
  address: "0x1234567890123456789012345678901234567890",
  logo: "🖥️",
  description: "Premium tech products — pay with any crypto, earn PAYTKN cashback",
};

const PRODUCTS = [
  { id: 1, name: "MacBook Pro 14\"",      price: 1299, category: "Laptops",      emoji: "💻", desc: "Apple M3 Pro · 18GB RAM · 512GB SSD",           stock: 12, featured: true },
  { id: 2, name: "iPhone 15 Pro",          price: 999,  category: "Phones",       emoji: "📱", desc: "Titanium · A17 Pro · 256GB",                    stock: 8,  featured: true },
  { id: 3, name: "Sony WH-1000XM5",        price: 349,  category: "Audio",        emoji: "🎧", desc: "Industry-leading noise cancellation",            stock: 24, featured: false },
  { id: 4, name: "iPad Pro 12.9\"",        price: 1099, category: "Tablets",      emoji: "📲", desc: "M2 chip · Liquid Retina XDR display",           stock: 6,  featured: false },
  { id: 5, name: "Samsung 4K Monitor 27\"",price: 449,  category: "Monitors",     emoji: "🖥️", desc: "144Hz · HDR600 · USB-C Hub",                    stock: 15, featured: false },
  { id: 6, name: "Mechanical Keyboard",    price: 159,  category: "Accessories",  emoji: "⌨️", desc: "Cherry MX Red · RGB · TKL layout",             stock: 40, featured: false },
  { id: 7, name: "Logitech MX Master 3S",  price: 99,   category: "Accessories",  emoji: "🖱️", desc: "8K DPI · Silent clicks · USB-C",                stock: 50, featured: false },
  { id: 8, name: "AirPods Pro 2nd Gen",    price: 249,  category: "Audio",        emoji: "🎵", desc: "ANC · Spatial Audio · MagSafe case",            stock: 30, featured: false },
];

const SUBSCRIPTIONS = [
  {
    id: "sub_1", name: "TechMart Pro",      price: 9.99,  period: "monthly", color: "border-blue-500/40 bg-blue-500/5",
    features: ["Early access to deals", "5% extra cashback", "Free shipping", "Priority support"],
    paytkn_bonus: 50,
  },
  {
    id: "sub_2", name: "TechMart Business", price: 29.99, period: "monthly", color: "border-indigo-500/40 bg-indigo-500/5",
    features: ["All Pro benefits", "Bulk order discounts", "Dedicated account manager", "API access", "10% extra cashback"],
    paytkn_bonus: 200,
  },
  {
    id: "sub_3", name: "TechMart Annual",   price: 79.99, period: "yearly",  color: "border-purple-500/40 bg-purple-500/5",
    features: ["All Business benefits", "Free device insurance", "Extended warranty", "Exclusive events", "15% extra cashback"],
    paytkn_bonus: 500,
  },
];

const CATEGORIES = ["All", "Laptops", "Phones", "Tablets", "Audio", "Monitors", "Accessories"];

export default function StorePage() {
  const [activeCategory, setActiveCategory] = useState("All");
  const [activeTab, setActiveTab] = useState<"products" | "subscriptions">("products");

  const filtered = activeCategory === "All"
    ? PRODUCTS
    : PRODUCTS.filter(p => p.category === activeCategory);

  const featured = PRODUCTS.filter(p => p.featured);

  function checkoutLink(product: typeof PRODUCTS[0], type: "one-time" | "subscription" = "one-time") {
    const params = new URLSearchParams({
      product: product.name,
      price: product.price.toString(),
      merchant: MERCHANT.address,
      merchant_name: MERCHANT.name,
      description: product.desc,
      emoji: product.emoji,
      type,
    });
    return `/checkout?${params}`;
  }

  function subCheckoutLink(sub: typeof SUBSCRIPTIONS[0]) {
    const params = new URLSearchParams({
      product: sub.name,
      price: sub.price.toString(),
      merchant: MERCHANT.address,
      merchant_name: MERCHANT.name,
      description: `${sub.period} subscription · +${sub.paytkn_bonus} PAYTKN/period`,
      emoji: "🔄",
      type: "subscription",
      period: sub.period,
    });
    return `/checkout?${params}`;
  }

  return (
    <div className="space-y-8">
      {/* Store header */}
      <div className="bg-gradient-to-r from-gray-900 via-indigo-950/40 to-gray-900 border border-gray-800 rounded-2xl p-8">
        <div className="flex items-center gap-4 mb-3">
          <span className="text-5xl">{MERCHANT.logo}</span>
          <div>
            <h1 className="text-3xl font-bold text-white">{MERCHANT.name}</h1>
            <p className="text-gray-400 mt-1">{MERCHANT.description}</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-3 mt-4">
          <span className="bg-green-500/15 border border-green-500/30 text-green-400 text-xs px-3 py-1.5 rounded-full">✓ PAYTKN Accepted</span>
          <span className="bg-indigo-500/15 border border-indigo-500/30 text-indigo-400 text-xs px-3 py-1.5 rounded-full">⚡ Instant Cashback</span>
          <span className="bg-purple-500/15 border border-purple-500/30 text-purple-400 text-xs px-3 py-1.5 rounded-full">🔄 Subscriptions Available</span>
          <span className="bg-blue-500/15 border border-blue-500/30 text-blue-400 text-xs px-3 py-1.5 rounded-full">🌉 Jumper/LI.FI Bridge</span>
        </div>
      </div>

      {/* Featured */}
      <div>
        <h2 className="text-xl font-bold text-white mb-4">⭐ Featured</h2>
        <div className="grid md:grid-cols-2 gap-4">
          {featured.map(p => (
            <div key={p.id} className="bg-gray-900 border border-indigo-500/30 rounded-2xl p-6 flex gap-4 hover:border-indigo-500/60 transition-colors">
              <span className="text-5xl">{p.emoji}</span>
              <div className="flex-1">
                <div className="font-bold text-white text-lg">{p.name}</div>
                <div className="text-gray-400 text-sm mt-1">{p.desc}</div>
                <div className="flex items-center justify-between mt-3">
                  <span className="text-2xl font-bold text-white">${p.price.toLocaleString()}</span>
                  <Link href={checkoutLink(p)}
                    className="bg-indigo-600 hover:bg-indigo-500 text-white font-semibold px-5 py-2.5 rounded-xl text-sm transition-colors">
                    Pay with Crypto →
                  </Link>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Tab switcher */}
      <div className="flex gap-1 bg-gray-900 border border-gray-800 rounded-xl p-1 w-fit">
        {(["products", "subscriptions"] as const).map(t => (
          <button key={t} onClick={() => setActiveTab(t)}
            className={`px-5 py-2.5 rounded-lg text-sm font-medium transition-colors capitalize ${
              activeTab === t ? "bg-indigo-600 text-white" : "text-gray-400 hover:text-white"}`}>
            {t === "products" ? "🛒 Products" : "🔄 Subscriptions"}
          </button>
        ))}
      </div>

      {/* Products tab */}
      {activeTab === "products" && (
        <div className="space-y-4">
          {/* Category filter */}
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
                <div className="text-4xl mb-3">{p.emoji}</div>
                <div className="text-xs text-indigo-400 font-medium mb-1">{p.category}</div>
                <div className="font-bold text-white text-base flex-1">{p.name}</div>
                <div className="text-gray-400 text-sm mt-1">{p.desc}</div>
                <div className="text-xs text-gray-600 mt-1">{p.stock} in stock</div>
                <div className="flex items-center justify-between mt-4">
                  <span className="text-xl font-bold text-white">${p.price.toLocaleString()}</span>
                  <Link href={checkoutLink(p)}
                    className="bg-indigo-600 hover:bg-indigo-500 text-white font-semibold px-4 py-2 rounded-xl text-sm transition-colors">
                    Buy →
                  </Link>
                </div>
                <div className="text-xs text-indigo-400/70 mt-1 text-right">
                  🤖 RL cashback on payment
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Subscriptions tab */}
      {activeTab === "subscriptions" && (
        <div className="grid md:grid-cols-3 gap-6">
          {SUBSCRIPTIONS.map(sub => (
            <div key={sub.id} className={`rounded-2xl border p-6 flex flex-col ${sub.color}`}>
              <div className="text-sm text-gray-400 mb-1 capitalize">{sub.period}</div>
              <div className="text-xl font-bold text-white">{sub.name}</div>
              <div className="mt-3">
                <span className="text-4xl font-black text-white">${sub.price}</span>
                <span className="text-gray-400 text-sm">/{sub.period === "yearly" ? "yr" : "mo"}</span>
              </div>
              <div className="text-xs text-indigo-400 mt-1">+{sub.paytkn_bonus} PAYTKN per period</div>
              <ul className="mt-5 space-y-2 flex-1">
                {sub.features.map((f, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-gray-300">
                    <span className="text-green-400 mt-0.5">✓</span>{f}
                  </li>
                ))}
              </ul>
              <Link href={subCheckoutLink(sub)}
                className="mt-6 block w-full bg-indigo-600 hover:bg-indigo-500 text-white font-bold py-3 rounded-xl text-center text-sm transition-colors">
                Subscribe with Crypto
              </Link>
              <p className="text-xs text-gray-500 text-center mt-2">Auto-renews · Cancel anytime</p>
            </div>
          ))}
        </div>
      )}

      {/* PAYTKN merchant badge */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-2xl">⚡</span>
          <div>
            <div className="text-sm font-semibold text-white">Powered by PAYTKN Protocol</div>
            <div className="text-xs text-gray-400">All payments auto-converted via Jumper/LI.FI · Instant cashback on every purchase</div>
          </div>
        </div>
        <div className="text-xs text-gray-500 font-mono hidden md:block">
          {MERCHANT.address.slice(0, 10)}…{MERCHANT.address.slice(-6)}
        </div>
      </div>
    </div>
  );
}
