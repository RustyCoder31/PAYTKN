"use client";
import { useEffect, useState } from "react";
import { useAccount, useReadContract, useBalance } from "wagmi";
import { ConnectButton } from "@rainbow-me/rainbowkit";
import { StatCard } from "@/components/StatCard";
import { api } from "@/lib/api";
import { CONTRACT_ADDRESSES, ERC20_ABI, GATEWAY_ADDRESS } from "@/lib/web3";

type Tab = "overview" | "orders" | "products" | "subscriptions" | "staking" | "integration";

const TIER_CONFIG = [
  { name: "Bronze",   min: 0,      color: "text-orange-400", bg: "border-orange-500/30 bg-orange-500/5",  feeDiscount: 0,  cashbackBoost: 0,  icon: "🥉" },
  { name: "Silver",   min: 10000,  color: "text-gray-300",   bg: "border-gray-400/30   bg-gray-400/5",    feeDiscount: 10, cashbackBoost: 10, icon: "🥈" },
  { name: "Gold",     min: 50000,  color: "text-yellow-400", bg: "border-yellow-500/30 bg-yellow-500/5",  feeDiscount: 20, cashbackBoost: 20, icon: "🥇" },
  { name: "Platinum", min: 200000, color: "text-indigo-300", bg: "border-indigo-400/30  bg-indigo-400/5", feeDiscount: 30, cashbackBoost: 30, icon: "💎" },
];

const MOCK_ORDERS = [
  { id: "ORD-0041", product: "MacBook Pro 14\"",      customer: "0x1a2b…3c4d", currency: "ETH",   paid: "0.419 ETH",  paytkn: "1,298 PAYTKN", cashback: "9.74 PAYTKN",  time: "2h ago",  status: "confirmed",   type: "one-time"     },
  { id: "ORD-0040", product: "TechMart Pro",          customer: "0x5e6f…7a8b", currency: "USDC",  paid: "9.99 USDC",  paytkn: "9.99 PAYTKN",  cashback: "0.07 PAYTKN",  time: "5h ago",  status: "confirmed",   type: "subscription" },
  { id: "ORD-0039", product: "AirPods Pro 2nd Gen",   customer: "0x9c0d…1e2f", currency: "AVAX",  paid: "8.89 AVAX",  paytkn: "248 PAYTKN",   cashback: "1.86 PAYTKN",  time: "1d ago",  status: "confirmed",   type: "one-time"     },
  { id: "ORD-0038", product: "TechMart Business",     customer: "0x3a4b…5c6d", currency: "MATIC", paid: "41.6 MATIC", paytkn: "29.95 PAYTKN", cashback: "0.22 PAYTKN",  time: "1d ago",  status: "confirmed",   type: "subscription" },
  { id: "ORD-0037", product: "iPhone 15 Pro",         customer: "0xf1e2…d3c4", currency: "BNB",   paid: "1.72 BNB",   paytkn: "998 PAYTKN",   cashback: "7.49 PAYTKN",  time: "2d ago",  status: "confirmed",   type: "one-time"     },
  { id: "ORD-0036", product: "Sony WH-1000XM5",       customer: "0xb5a6…9788", currency: "USDC",  paid: "349 USDC",   paytkn: "347.3 PAYTKN", cashback: "2.60 PAYTKN",  time: "3d ago",  status: "pending",     type: "one-time"     },
];

const MOCK_SUBSCRIPTIONS = [
  { id: "SUB-001", plan: "TechMart Pro",      customer: "0x1a2b…3c4d", price: "$9.99/mo",  next: "May 26",  status: "active", renewals: 3, total_paid: "$29.97"  },
  { id: "SUB-002", plan: "TechMart Business", customer: "0x5e6f…7a8b", price: "$29.99/mo", next: "May 10",  status: "active", renewals: 1, total_paid: "$29.99"  },
  { id: "SUB-003", plan: "TechMart Annual",   customer: "0x9c0d…1e2f", price: "$79.99/yr", next: "Apr 2027",status: "active", renewals: 0, total_paid: "$79.99"  },
  { id: "SUB-004", plan: "TechMart Pro",      customer: "0xaabb…ccdd", price: "$9.99/mo",  next: "—",       status: "cancelled", renewals: 2, total_paid: "$19.98" },
];

const MOCK_PRODUCTS = [
  { id: 1, name: "MacBook Pro 14\"",      price: 1299, category: "Laptops",     stock: 12, emoji: "💻", sales: 8  },
  { id: 2, name: "iPhone 15 Pro",          price: 999,  category: "Phones",      stock: 8,  emoji: "📱", sales: 15 },
  { id: 3, name: "Sony WH-1000XM5",        price: 349,  category: "Audio",       stock: 24, emoji: "🎧", sales: 6  },
  { id: 4, name: "iPad Pro 12.9\"",        price: 1099, category: "Tablets",     stock: 6,  emoji: "📲", sales: 4  },
];

export default function MerchantDashboard() {
  const { address, isConnected } = useAccount();
  const [tab, setTab]           = useState<Tab>("overview");
  const [tierInfo, setTierInfo] = useState<any>(null);
  const [copied, setCopied]     = useState<string | null>(null);
  const [orderFilter, setOrderFilter] = useState<"all"|"one-time"|"subscription">("all");
  const [editProduct, setEditProduct] = useState<number | null>(null);
  const [port, setPort]         = useState<string | null>(null);

  useEffect(() => {
    setPort(window.location.port);
  }, []);

  useEffect(() => {
    if (address) api.merchantTier(address).then(setTierInfo).catch(() => {});
  }, [address]);

  // ── Port guard: merchant must run on :3001 for wallet isolation ──────────
  if (port !== null && port !== "3001") {
    return (
      <div className="min-h-[70vh] flex items-center justify-center px-4">
        <div className="text-center space-y-6 max-w-md">
          <div className="text-7xl">🏪</div>
          <div>
            <h1 className="text-2xl font-bold text-white mb-2">Wrong Port</h1>
            <p className="text-gray-400 text-sm leading-relaxed">
              The merchant dashboard must run on <strong className="text-white">localhost:3001</strong> so MetaMask
              treats it as a separate origin and lets you connect a different wallet from the user's.
            </p>
          </div>
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 text-left space-y-2">
            <p className="text-xs text-gray-500 font-mono">In your terminal:</p>
            <code className="text-xs text-emerald-400 font-mono block">npm run merchant</code>
            <p className="text-xs text-gray-500 font-mono mt-2">Then open:</p>
            <code className="text-xs text-indigo-400 font-mono block">http://localhost:3001/merchant</code>
          </div>
          <a
            href="http://localhost:3001/merchant"
            className="inline-flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white font-bold px-6 py-3 rounded-xl transition-colors"
          >
            Open at localhost:3001 →
          </a>
        </div>
      </div>
    );
  }

  // ── Real on-chain balances ───────────────────────────────────────────────
  const { data: ethBalance } = useBalance({ address, query: { refetchInterval: 8000 } });
  const { data: paytknBalance, refetch: refetchPAYTKN } = useReadContract({
    address: CONTRACT_ADDRESSES.token as `0x${string}`,
    abi: ERC20_ABI,
    functionName: "balanceOf",
    args: [address ?? "0x0000000000000000000000000000000000000000"],
    query: { enabled: !!address, refetchInterval: 8000 },
  });

  const tierIdx = tierInfo?.tier ?? 0;
  const tier    = TIER_CONFIG[tierIdx];
  const apiKey  = address ? `pk_live_${address.slice(2, 14).toLowerCase()}xxxx` : "pk_live_connect_wallet";
  const webhookUrl = address ? `https://api.paytkn.io/webhook/${address}` : "connect wallet";

  function copy(text: string, key: string) {
    navigator.clipboard.writeText(text);
    setCopied(key);
    setTimeout(() => setCopied(null), 2000);
  }

  const filteredOrders = orderFilter === "all" ? MOCK_ORDERS : MOCK_ORDERS.filter(o => o.type === orderFilter);

  const TABS: { key: Tab; label: string; icon: string }[] = [
    { key: "overview",       label: "Overview",      icon: "📊" },
    { key: "orders",         label: "Orders",        icon: "📦" },
    { key: "products",       label: "Products",      icon: "🛒" },
    { key: "subscriptions",  label: "Subscriptions", icon: "🔄" },
    { key: "staking",        label: "Staking",       icon: "🔒" },
    { key: "integration",    label: "Integration",   icon: "🔌" },
  ];

  if (!isConnected) {
    return (
      <div className="min-h-[70vh] flex items-center justify-center">
        <div className="text-center space-y-5 max-w-md">
          <div className="text-7xl">🏪</div>
          <h1 className="text-3xl font-bold text-white">Merchant Dashboard</h1>
          <p className="text-gray-400">Connect your merchant wallet to view orders, manage products, configure webhooks, and monitor your staking tier.</p>
          <ConnectButton />
        </div>
      </div>
    );
  }

  const paytknFormatted = paytknBalance ? (Number(paytknBalance) / 1e18).toFixed(4) : "—";
  const ethFormatted    = ethBalance    ? parseFloat(ethBalance.formatted).toFixed(5) : "—";

  // Store link — opens on port 3000 (user side) with this merchant's address
  const storeName = `TechMart Store`;
  const storeLink = `http://localhost:3000/store?merchant=${address}&merchant_name=${encodeURIComponent(storeName)}`;

  return (
    <div className="space-y-6">

      {/* ── Share Store Link — THE KEY DEMO BUTTON ───────────────────────── */}
      <div className="bg-gradient-to-r from-emerald-950/60 to-indigo-950/40 border-2 border-emerald-700/50 rounded-2xl p-6">
        <div className="flex items-center gap-3 mb-4">
          <span className="text-3xl">🔗</span>
          <div>
            <h2 className="text-lg font-bold text-white">Share Your Store</h2>
            <p className="text-sm text-emerald-400/80">Send this link to the user — they open it at <strong>localhost:3000</strong></p>
          </div>
        </div>

        {/* Store link box */}
        <div className="flex items-center gap-2 bg-gray-900 border border-emerald-700/40 rounded-xl px-4 py-3 mb-3">
          <code className="flex-1 text-xs text-emerald-300 font-mono truncate">{storeLink}</code>
          <button
            onClick={() => { navigator.clipboard.writeText(storeLink); setCopied("link"); setTimeout(() => setCopied(null), 2500); }}
            className="shrink-0 bg-emerald-700 hover:bg-emerald-600 text-white font-bold rounded-lg px-4 py-1.5 text-xs transition-colors"
          >
            {copied === "link" ? "✓ Copied!" : "Copy Link"}
          </button>
        </div>

        {/* Open directly */}
        <a
          href={storeLink}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold px-5 py-2.5 rounded-xl text-sm transition-colors"
        >
          🛍️ Open Store (localhost:3000) ↗
        </a>

        <p className="text-xs text-gray-500 mt-3">
          The store will show your wallet address as the merchant. When a customer pays,
          PAYTKN arrives in <strong className="text-white">this wallet</strong>.
        </p>
      </div>

      {/* ── Live wallet panel ────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">

        {/* Receive address */}
        <div className="md:col-span-2 bg-gray-900 border border-emerald-800/40 rounded-2xl p-5">
          <div className="flex items-center gap-2 mb-3">
            <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            <span className="text-xs text-green-400 font-medium uppercase tracking-widest">Your Wallet (Receives PAYTKN)</span>
          </div>
          <div className="flex items-center gap-2">
            <code className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 font-mono text-sm text-white break-all">
              {address}
            </code>
            <button
              onClick={() => { navigator.clipboard.writeText(address ?? ""); setCopied("addr"); setTimeout(() => setCopied(null), 2000); }}
              className="shrink-0 bg-emerald-700/40 hover:bg-emerald-600/50 border border-emerald-700/50 text-emerald-300 rounded-lg px-3 py-2.5 text-xs transition-colors"
            >
              {copied === "addr" ? "✓" : "Copy"}
            </button>
          </div>
        </div>

        {/* Live balances */}
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5 space-y-4">
          <div className="text-xs text-gray-500 uppercase tracking-widest font-medium">Live Balances</div>
          <div className="space-y-3">
            <div>
              <div className="flex justify-between items-baseline">
                <span className="text-xs text-gray-400">ETH</span>
                <span className="font-mono text-sm font-bold text-white">{ethFormatted} ETH</span>
              </div>
              <div className="h-0.5 bg-gray-800 mt-1 rounded" />
            </div>
            <div>
              <div className="flex justify-between items-baseline">
                <span className="text-xs text-gray-400">PAYTKN</span>
                <span className="font-mono text-sm font-bold text-emerald-400">{paytknFormatted} PAYTKN</span>
              </div>
              <div className="h-0.5 bg-gray-800 mt-1 rounded" />
            </div>
          </div>
          <div className="space-y-2">
            <button
              onClick={() => refetchPAYTKN()}
              className="w-full text-xs bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-400 rounded-lg py-2 transition-colors"
            >
              🔄 Refresh
            </button>
            <button
              onClick={async () => {
                try {
                  await (window as any).ethereum.request({
                    method: "wallet_watchAsset",
                    params: {
                      type: "ERC20",
                      options: { address: CONTRACT_ADDRESSES.token, symbol: "PAYTKN", decimals: 18 },
                    },
                  });
                } catch {}
              }}
              className="w-full text-xs bg-indigo-800/30 hover:bg-indigo-700/40 border border-indigo-700/40 text-indigo-300 rounded-lg py-2 transition-colors"
            >
              + Add PAYTKN to MetaMask
            </button>
            <a
              href={`https://sepolia.basescan.org/address/${address}`}
              target="_blank"
              rel="noopener noreferrer"
              className="w-full text-xs text-center block bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-400 rounded-lg py-2 transition-colors"
            >
              View on Basescan ↗
            </a>
          </div>
        </div>
      </div>

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Merchant Dashboard</h1>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-gray-400 font-mono text-sm">{address?.slice(0,10)}…{address?.slice(-6)}</span>
            <span className={`text-xs px-2 py-0.5 rounded-full border ${tier.bg} ${tier.color} font-semibold`}>{tier.icon} {tier.name}</span>
          </div>
        </div>
        <a href={storeLink} target="_blank" rel="noopener noreferrer"
          className="flex items-center gap-2 text-sm bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-xl transition-colors">
          🛍️ View Your Store ↗
        </a>
      </div>

      {/* Tabs */}
      <div className="overflow-x-auto">
        <div className="flex gap-1 bg-gray-900 border border-gray-800 rounded-xl p-1 w-max">
          {TABS.map(t => (
            <button key={t.key} onClick={() => setTab(t.key)}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${
                tab === t.key ? "bg-indigo-600 text-white" : "text-gray-400 hover:text-white"}`}>
              <span className="text-xs">{t.icon}</span>{t.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── OVERVIEW ── */}
      {tab === "overview" && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label="Revenue (30d)"    value="$2,841"        color="green"  icon="💰" sub="across all currencies" />
            <StatCard label="Orders"           value="47"            color="blue"   icon="📦" sub="this month" />
            <StatCard label="Active Subs"      value="3"             color="purple" icon="🔄" sub="subscriptions" />
            <StatCard label="Cashback Given"   value="284 PAYTKN"   color="indigo" icon="🎁" sub="to customers" />
          </div>

          <div className="grid md:grid-cols-2 gap-5">
            {/* Recent orders preview */}
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
              <div className="flex items-center justify-between mb-3">
                <h2 className="font-semibold text-white">Recent Orders</h2>
                <button onClick={() => setTab("orders")} className="text-xs text-indigo-400 hover:text-indigo-300">View all →</button>
              </div>
              <div className="space-y-2">
                {MOCK_ORDERS.slice(0, 4).map(o => (
                  <div key={o.id} className="flex items-center justify-between py-2 border-b border-gray-800 last:border-0">
                    <div>
                      <div className="text-sm text-white">{o.product}</div>
                      <div className="text-xs text-gray-500">{o.customer} · {o.currency} · {o.time}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm text-green-400">{o.paytkn}</div>
                      {o.type === "subscription" && <div className="text-xs text-blue-400">🔄 sub</div>}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Quick stats */}
            <div className="space-y-3">
              <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
                <div className="text-xs text-gray-500 mb-2">TOP PRODUCTS</div>
                {MOCK_PRODUCTS.slice(0,3).map(p => (
                  <div key={p.id} className="flex items-center justify-between py-2 border-b border-gray-800 last:border-0">
                    <div className="flex items-center gap-2">
                      <span>{p.emoji}</span>
                      <span className="text-sm text-white">{p.name}</span>
                    </div>
                    <div className="text-right">
                      <div className="text-sm text-white">${p.price}</div>
                      <div className="text-xs text-gray-500">{p.sales} sold</div>
                    </div>
                  </div>
                ))}
              </div>

              <div className={`rounded-xl border p-4 ${tier.bg} flex items-center gap-3`}>
                <span className="text-3xl">{tier.icon}</span>
                <div className="flex-1">
                  <div className={`font-bold ${tier.color}`}>{tier.name} Merchant</div>
                  <div className="text-xs text-gray-400">{tier.feeDiscount}% fee discount · +{tier.cashbackBoost}% user cashback</div>
                </div>
                <button onClick={() => setTab("staking")} className="text-xs text-indigo-400 hover:text-indigo-300">Upgrade →</button>
              </div>
            </div>
          </div>

          {/* Credentials quick access */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-3">
            <h2 className="font-semibold text-white">API Credentials</h2>
            {[
              { label: "API Key", value: apiKey, key: "key", color: "text-indigo-300" },
              { label: "Webhook URL", value: webhookUrl, key: "webhook", color: "text-green-400" },
            ].map(c => (
              <div key={c.key}>
                <div className="text-xs text-gray-500 mb-1">{c.label}</div>
                <div className="flex items-center gap-2 bg-gray-800 rounded-lg px-3 py-2">
                  <code className={`flex-1 text-sm font-mono truncate ${c.color}`}>{c.value}</code>
                  <button onClick={() => copy(c.value, c.key)}
                    className="text-xs text-gray-400 hover:text-white bg-gray-700 hover:bg-gray-600 px-2.5 py-1 rounded-md transition-colors">
                    {copied === c.key ? "✓" : "Copy"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── ORDERS ── */}
      {tab === "orders" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div className="flex gap-1">
              {(["all","one-time","subscription"] as const).map(f => (
                <button key={f} onClick={() => setOrderFilter(f)}
                  className={`px-3 py-1.5 rounded-full text-xs font-semibold capitalize transition-colors ${
                    orderFilter === f ? "bg-indigo-600 text-white" : "bg-gray-800 text-gray-400 hover:text-white"}`}>
                  {f === "one-time" ? "One-Time" : f === "subscription" ? "🔄 Subscriptions" : "All"}
                </button>
              ))}
            </div>
            <button className="text-xs text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 px-3 py-1.5 rounded-lg transition-colors">📥 Export CSV</button>
          </div>

          <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-left text-xs text-gray-500 uppercase tracking-wider">
                  <th className="px-5 py-3">Order</th>
                  <th className="px-5 py-3">Product</th>
                  <th className="px-5 py-3">Customer</th>
                  <th className="px-5 py-3">Paid In</th>
                  <th className="px-5 py-3">PAYTKN Received</th>
                  <th className="px-5 py-3">Cashback Given</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3">Time</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {filteredOrders.map(o => (
                  <tr key={o.id} className="hover:bg-gray-800/40 transition-colors">
                    <td className="px-5 py-3.5">
                      <div className="font-mono text-indigo-400 text-xs">{o.id}</div>
                      {o.type === "subscription" && <div className="text-xs text-blue-400 mt-0.5">🔄 recurring</div>}
                    </td>
                    <td className="px-5 py-3.5 text-white">{o.product}</td>
                    <td className="px-5 py-3.5 font-mono text-gray-400 text-xs">{o.customer}</td>
                    <td className="px-5 py-3.5">
                      <div className="text-white">{o.paid}</div>
                      <div className="text-xs text-gray-500">{o.currency}</div>
                    </td>
                    <td className="px-5 py-3.5 text-green-400 font-semibold">{o.paytkn}</td>
                    <td className="px-5 py-3.5 text-indigo-400">{o.cashback}</td>
                    <td className="px-5 py-3.5">
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                        o.status === "confirmed" ? "bg-green-500/15 text-green-400" : "bg-yellow-500/15 text-yellow-400"}`}>
                        {o.status}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-gray-500">{o.time}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── PRODUCTS ── */}
      {tab === "products" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-white">Your Products</h2>
            <button className="text-sm bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-xl transition-colors">+ Add Product</button>
          </div>

          <div className="grid md:grid-cols-2 gap-4">
            {MOCK_PRODUCTS.map(p => (
              <div key={p.id} className="bg-gray-900 border border-gray-800 rounded-xl p-5">
                {editProduct === p.id ? (
                  <div className="space-y-3">
                    <div className="text-sm font-semibold text-white mb-2">Edit Product</div>
                    <input defaultValue={p.name} className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500" placeholder="Product name" />
                    <div className="flex gap-2">
                      <input defaultValue={p.price} className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500" placeholder="Price USD" type="number" />
                      <input defaultValue={p.stock} className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500" placeholder="Stock" type="number" />
                    </div>
                    <div className="flex gap-2">
                      <button onClick={() => setEditProduct(null)} className="flex-1 border border-gray-700 text-gray-400 py-2 rounded-lg text-sm">Cancel</button>
                      <button onClick={() => setEditProduct(null)} className="flex-1 bg-indigo-600 text-white py-2 rounded-lg text-sm font-semibold">Save</button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="flex items-start gap-3">
                      <span className="text-4xl">{p.emoji}</span>
                      <div className="flex-1">
                        <div className="font-bold text-white">{p.name}</div>
                        <div className="text-xs text-gray-400">{p.category}</div>
                        <div className="flex gap-4 mt-2 text-sm">
                          <span className="text-white font-semibold">${p.price.toLocaleString()}</span>
                          <span className="text-gray-400">{p.stock} in stock</span>
                          <span className="text-green-400">{p.sales} sold</span>
                        </div>
                      </div>
                    </div>
                    <div className="flex gap-2 mt-4">
                      <button onClick={() => setEditProduct(p.id)} className="flex-1 text-xs border border-gray-700 text-gray-400 hover:text-white py-2 rounded-lg transition-colors">Edit</button>
                      <a href={`/store`} target="_blank" className="flex-1 text-xs border border-gray-700 text-gray-400 hover:text-white py-2 rounded-lg transition-colors text-center">View in Store</a>
                      <button className="flex-1 text-xs border border-red-500/30 text-red-400 hover:bg-red-500/10 py-2 rounded-lg transition-colors">Remove</button>
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── SUBSCRIPTIONS ── */}
      {tab === "subscriptions" && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label="Active Subs"      value="3"       color="green"  icon="🔄" />
            <StatCard label="MRR"              value="$49.97"  color="blue"   icon="💰" sub="monthly recurring" />
            <StatCard label="Churn Rate"       value="25%"     color="yellow" icon="📉" sub="1 cancelled" />
            <StatCard label="PAYTKN Bonuses"   value="350/mo"  color="indigo" icon="⚡" sub="distributed" />
          </div>

          <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-left text-xs text-gray-500 uppercase tracking-wider">
                  <th className="px-5 py-3">Sub ID</th>
                  <th className="px-5 py-3">Plan</th>
                  <th className="px-5 py-3">Customer</th>
                  <th className="px-5 py-3">Price</th>
                  <th className="px-5 py-3">Next Payment</th>
                  <th className="px-5 py-3">Renewals</th>
                  <th className="px-5 py-3">Total Paid</th>
                  <th className="px-5 py-3">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {MOCK_SUBSCRIPTIONS.map(s => (
                  <tr key={s.id} className="hover:bg-gray-800/40 transition-colors">
                    <td className="px-5 py-3.5 font-mono text-indigo-400 text-xs">{s.id}</td>
                    <td className="px-5 py-3.5 text-white font-medium">{s.plan}</td>
                    <td className="px-5 py-3.5 font-mono text-gray-400 text-xs">{s.customer}</td>
                    <td className="px-5 py-3.5 text-white">{s.price}</td>
                    <td className="px-5 py-3.5 text-gray-300">{s.next}</td>
                    <td className="px-5 py-3.5 text-gray-300">{s.renewals}×</td>
                    <td className="px-5 py-3.5 text-green-400">{s.total_paid}</td>
                    <td className="px-5 py-3.5">
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                        s.status === "active" ? "bg-green-500/15 text-green-400" : "bg-red-500/15 text-red-400"}`}>
                        {s.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── STAKING ── */}
      {tab === "staking" && (
        <div className="space-y-5">
          <div className={`rounded-2xl border p-6 ${tier.bg} flex items-center gap-5`}>
            <span className="text-6xl">{tier.icon}</span>
            <div className="flex-1">
              <div className={`text-2xl font-bold ${tier.color}`}>{tier.name} Merchant</div>
              <div className="text-gray-400 text-sm mt-1">
                Currently staking <span className="text-white font-semibold">{(tierInfo?.staked ?? 0).toLocaleString()} PAYTKN</span>
              </div>
              <div className="flex gap-6 mt-3 text-sm">
                <div><span className="text-gray-500">Fee Discount</span> <span className={`font-bold ${tier.color}`}>{tier.feeDiscount}%</span></div>
                <div><span className="text-gray-500">Customer Cashback Boost</span> <span className="text-indigo-400 font-bold">+{tier.cashbackBoost}%</span></div>
                <div><span className="text-gray-500">Staking APY</span> <span className="text-yellow-400 font-bold">≥2%</span></div>
              </div>
            </div>
          </div>

          <div className="grid md:grid-cols-4 gap-3">
            {TIER_CONFIG.map((t, i) => (
              <div key={i} className={`rounded-xl border p-4 ${t.bg} ${i === tierIdx ? "ring-2 ring-indigo-500" : ""}`}>
                <div className="text-2xl mb-2">{t.icon}</div>
                <div className={`font-bold text-sm ${t.color}`}>{t.name}</div>
                <div className="text-xs text-gray-500 mt-1">{t.min === 0 ? "Free" : `${t.min.toLocaleString()} PAYTKN`}</div>
                <div className="mt-2 text-xs space-y-0.5">
                  <div className="text-green-400">−{t.feeDiscount}% fees</div>
                  <div className="text-indigo-400">+{t.cashbackBoost}% cashback</div>
                </div>
                {i === tierIdx && <div className="mt-2 text-xs bg-indigo-600/40 text-indigo-300 rounded px-2 py-0.5 text-center">Current</div>}
              </div>
            ))}
          </div>

          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 max-w-sm space-y-3">
            <h2 className="font-semibold text-white">Stake More</h2>
            <input className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-indigo-500" placeholder="Amount (PAYTKN)" type="number" />
            <p className="text-xs text-yellow-500/80">⚠ 7-day minimum lock · Minimum 2% APY guaranteed</p>
            <button className="w-full bg-purple-700 hover:bg-purple-600 text-white font-bold py-3 rounded-xl transition-colors">Stake as Merchant</button>
          </div>
        </div>
      )}

      {/* ── INTEGRATION ── */}
      {tab === "integration" && (
        <div className="space-y-5">
          <div className="grid md:grid-cols-2 gap-4">
            {[
              { label: "API Key",      value: apiKey,      key: "key",     color: "text-indigo-300", desc: "Use in your server-side API calls" },
              { label: "Webhook URL",  value: webhookUrl,  key: "webhook", color: "text-green-400",  desc: "PAYTKN posts payment events here" },
            ].map(c => (
              <div key={c.key} className="bg-gray-900 border border-gray-800 rounded-xl p-5">
                <div className="text-xs text-gray-500 mb-1">{c.label}</div>
                <div className="flex items-center gap-2 bg-gray-800 rounded-lg px-3 py-2.5 mb-2">
                  <code className={`flex-1 text-sm font-mono truncate ${c.color}`}>{c.value}</code>
                  <button onClick={() => copy(c.value, c.key)}
                    className="text-xs text-gray-400 hover:text-white bg-gray-700 hover:bg-gray-600 px-2.5 py-1.5 rounded-md transition-colors">
                    {copied === c.key ? "✓ Copied" : "Copy"}
                  </button>
                </div>
                <p className="text-xs text-gray-500">{c.desc}</p>
              </div>
            ))}
          </div>

          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
            <h2 className="font-semibold text-white mb-3">Embed Checkout Button</h2>
            <pre className="bg-gray-950 rounded-xl p-4 text-xs font-mono text-indigo-200 overflow-x-auto leading-relaxed">{`<script src="https://cdn.paytkn.io/checkout.js"></script>
<button
  data-paytkn-key="${apiKey}"
  data-merchant="${address ?? '0xYOUR_ADDRESS'}"
  data-amount="29.99"
  data-currency="USD"
  data-description="Order #1042"
  data-type="one-time"
>Pay with Crypto</button>

<!-- For subscriptions: -->
<button
  data-paytkn-key="${apiKey}"
  data-merchant="${address ?? '0xYOUR_ADDRESS'}"
  data-amount="9.99"
  data-currency="USD"
  data-type="subscription"
  data-period="monthly"
  data-plan="Pro Plan"
>Subscribe</button>`}</pre>
          </div>

          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
            <h2 className="font-semibold text-white mb-3">Webhook Payload</h2>
            <pre className="bg-gray-950 rounded-xl p-4 text-xs font-mono text-green-300 overflow-x-auto leading-relaxed">{`POST ${webhookUrl}
Content-Type: application/json
X-PAYTKN-Signature: hmac_sha256_signature

{
  "event": "payment.success",
  "order_id": "ORD-0041",
  "type": "one-time",            // or "subscription"
  "product": "MacBook Pro 14\\"",
  "customer": "0x1a2b3c4d...",
  "paid_currency": "ETH",
  "paid_amount": "0.419",
  "converted_paytkn": 1298,
  "net_merchant_paytkn": 1168,
  "cashback_to_user": 9.74,
  "burn_paytkn": 25.96,
  "timestamp": 1745625600,

  // For subscriptions:
  "subscription_id": "SUB-001",
  "period": "monthly",
  "next_payment_date": "2026-05-26",
  "renewal_number": 3
}`}</pre>
          </div>
        </div>
      )}
    </div>
  );
}
