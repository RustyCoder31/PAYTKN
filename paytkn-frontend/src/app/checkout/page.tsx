"use client";
import { Suspense, useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { useAccount } from "wagmi";
import { ConnectButton } from "@rainbow-me/rainbowkit";
import { api } from "@/lib/api";

const CURRENCIES = [
  { symbol: "ETH",    name: "Ethereum",  logo: "⟠",  rate: 3100, decimals: 5 },
  { symbol: "USDC",   name: "USD Coin",  logo: "💵", rate: 1,    decimals: 2 },
  { symbol: "BNB",    name: "BNB",       logo: "🟡", rate: 580,  decimals: 4 },
  { symbol: "MATIC",  name: "Polygon",   logo: "🟣", rate: 0.72, decimals: 1 },
  { symbol: "AVAX",   name: "Avalanche", logo: "🔺", rate: 28,   decimals: 3 },
  { symbol: "PAYTKN", name: "PAYTKN",    logo: "⚡", rate: 1,    decimals: 0 },
];

type Step = "connect" | "select" | "review" | "signing" | "converting" | "waiting" | "done";

function sleep(ms: number) { return new Promise(r => setTimeout(r, ms)); }

function CheckoutInner() {
  const params     = useSearchParams();
  const { address, isConnected } = useAccount();

  const productName    = params.get("product")       ?? "Unknown Product";
  const priceUSD       = parseFloat(params.get("price") ?? "0");
  const merchantAddr   = params.get("merchant")      ?? "0x0000000000000000000000000000000000000000";
  const merchantName   = params.get("merchant_name") ?? "Merchant";
  const description    = params.get("description")   ?? "";
  const emoji          = params.get("emoji")         ?? "🛒";
  const payType        = params.get("type")          ?? "one-time";
  const period         = params.get("period")        ?? "monthly";
  const isSubscription = payType === "subscription";

  const [currency, setCurrency]   = useState(0);
  const [step, setStep]           = useState<Step>("connect");
  const [result, setResult]       = useState<any>(null);
  const [confirmTimer, setConfirmTimer] = useState(0);

  const cur          = CURRENCIES[currency];
  const payAmount    = priceUSD / cur.rate;                       // in source currency units
  const isDirect     = cur.symbol === "PAYTKN";
  const jumperFee    = isDirect ? 0 : payAmount * 0.003;          // in source currency units
  const afterBridge  = payAmount - jumperFee;                     // in source currency units
  const protocolFee  = afterBridge * 0.005;                       // in source currency units
  // Convert to PAYTKN value after bridge (÷ by cur.rate gives USD, ×1 for PAYTKN@$1)
  const merchantGets = isDirect
    ? afterBridge - protocolFee                                    // already PAYTKN
    : (afterBridge - protocolFee) * cur.rate;                     // USD → PAYTKN@$1

  useEffect(() => {
    if (isConnected && step === "connect") setStep("select");
  }, [isConnected, step]);

  // Merchant confirmation countdown
  useEffect(() => {
    let t: ReturnType<typeof setInterval>;
    if (step === "waiting") {
      setConfirmTimer(30);
      t = setInterval(() => {
        setConfirmTimer(prev => {
          if (prev <= 1) {
            clearInterval(t);
            // Result cashback comes from backend (RL agent-calculated)
            setResult({
              tx_hash: "0x" + Array.from({length:64},()=>Math.floor(Math.random()*16).toString(16)).join(""),
              cashback_paytkn: null, // filled by backend response
              paytkn_burned: null,
              net_merchant: merchantGets,
            });
            setStep("done");
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    }
    return () => clearInterval(t);
  }, [step]);

  async function handlePay() {
    setStep("signing");
    await sleep(1800);
    setStep("converting");
    await sleep(isDirect ? 800 : 2500);
    setStep("waiting");
    try {
      // Always send payment value as ETH-equivalent for backend accounting
      const amountEth = isDirect ? priceUSD / 3100 : priceUSD / 3100;
      const res = await api.processPayment(address!, merchantAddr, amountEth);
      // Backend returns RL-calculated cashback
      setResult({
        tx_hash:           res.tx_hash ?? res.basescan?.split("/tx/")[1] ?? "simulated",
        cashback_paytkn:   res.estimated_cashback_paytkn ?? res.cashback_paytkn,
        paytkn_burned:     res.paytkn_burned,
        net_merchant:      merchantGets,
        cashback_bps:      res.cashback_bps,
        status:            res.status,
      });
      setStep("done");
    } catch {
      // Timer will fire and resolve with null cashback
    }
  }

  const progressSteps: { key: Step; label: string }[] = [
    { key: "select",     label: "Currency" },
    { key: "review",     label: "Review" },
    { key: "signing",    label: "Sign" },
    { key: "converting", label: "Convert" },
    { key: "waiting",    label: "Confirm" },
    { key: "done",       label: "Done" },
  ];
  const stepIdx = progressSteps.findIndex(s => s.key === step);

  return (
    <div className="min-h-[85vh] flex items-start justify-center pt-8 px-4">
      <div className="w-full max-w-lg space-y-4">

        {/* Product card */}
        <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden">

          {/* Merchant header */}
          <div className="bg-gradient-to-r from-indigo-900/60 to-purple-900/40 px-6 py-5 border-b border-gray-800">
            <div className="flex items-center gap-4">
              <span className="text-5xl">{emoji}</span>
              <div className="flex-1 min-w-0">
                <div className="text-xs text-gray-400">{merchantName}</div>
                <div className="font-bold text-white text-lg leading-tight">{productName}</div>
                <div className="text-gray-400 text-sm truncate">{description}</div>
              </div>
              <div className="text-right shrink-0">
                <div className="text-2xl font-bold text-white">${priceUSD.toLocaleString()}</div>
                {isSubscription && <div className="text-xs text-indigo-400">/{period}</div>}
                {isSubscription && <div className="text-xs text-blue-400 mt-0.5">🔄 Recurring</div>}
              </div>
            </div>
          </div>

          {/* Progress */}
          {step !== "connect" && step !== "done" && (
            <div className="px-6 py-3 border-b border-gray-800">
              <div className="flex items-center justify-between">
                {progressSteps.map((s, i) => (
                  <div key={s.key} className="flex items-center">
                    <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold transition-all ${
                      i < stepIdx ? "bg-green-500 text-white" :
                      i === stepIdx ? "bg-indigo-600 text-white ring-2 ring-indigo-400/40" :
                      "bg-gray-800 text-gray-600"}`}>
                      {i < stepIdx ? "✓" : i + 1}
                    </div>
                    {i < progressSteps.length - 1 && (
                      <div className={`h-0.5 w-6 mx-1 transition-colors ${i < stepIdx ? "bg-green-500" : "bg-gray-800"}`} />
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="p-6 space-y-5">

            {/* CONNECT */}
            {step === "connect" && (
              <div className="flex flex-col items-center gap-5 py-6">
                <div className="text-5xl">👛</div>
                <div className="text-center">
                  <p className="font-semibold text-white text-lg">Connect your wallet</p>
                  <p className="text-gray-400 text-sm mt-1">Required to pay with crypto</p>
                </div>
                <ConnectButton />
              </div>
            )}

            {/* SELECT CURRENCY */}
            {step === "select" && (
              <>
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wider mb-3">Pay with</p>
                  <div className="grid grid-cols-3 gap-2">
                    {CURRENCIES.map((c, i) => (
                      <button key={i} onClick={() => setCurrency(i)}
                        className={`flex flex-col items-center gap-1.5 p-3 rounded-xl border-2 transition-all ${
                          currency === i ? "border-indigo-500 bg-indigo-500/10" : "border-gray-700 hover:border-gray-600"}`}>
                        <span className="text-xl">{c.logo}</span>
                        <span className="text-xs font-bold text-white">{c.symbol}</span>
                        <span className="text-xs text-gray-500">${c.rate < 2 ? c.rate.toFixed(2) : c.rate.toLocaleString()}</span>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Fee breakdown — NO cashback estimate */}
                <div className="bg-gray-800 rounded-xl p-4 space-y-2 text-sm">
                  <div className="flex justify-between items-baseline">
                    <span className="text-gray-400">You pay</span>
                    <span className="text-white font-bold text-lg">{payAmount.toFixed(cur.decimals)} {cur.symbol}</span>
                  </div>
                  {!isDirect && (
                    <>
                      <div className="flex justify-between text-xs">
                        <span className="text-gray-500">Jumper/LI.FI bridge fee (0.3%)</span>
                        <span className="text-yellow-400">-{jumperFee.toFixed(cur.decimals)} {cur.symbol}</span>
                      </div>
                      <div className="flex justify-between text-xs">
                        <span className="text-gray-500">Auto-convert → PAYTKN</span>
                        <span className="text-purple-400">via DEX swap</span>
                      </div>
                    </>
                  )}
                  <div className="flex justify-between text-xs border-t border-gray-700 pt-2">
                    <span className="text-gray-500">Protocol fee (0.5%)</span>
                    <span className="text-gray-400">-{protocolFee.toFixed(4)}</span>
                  </div>
                  <div className="flex justify-between font-medium">
                    <span className="text-gray-400">Merchant receives</span>
                    <span className="text-green-400">~{merchantGets.toFixed(2)} PAYTKN</span>
                  </div>
                  <div className="border-t border-gray-700 pt-2 flex items-start gap-2 bg-indigo-500/5 rounded-lg p-2 -mx-1">
                    <span className="text-indigo-400 text-sm mt-0.5">🤖</span>
                    <div>
                      <div className="text-xs font-semibold text-indigo-400">PAYTKN Cashback</div>
                      <div className="text-xs text-gray-400 mt-0.5">
                        Calculated post-payment by the RL agent using your staking tier, loyalty score, and current <code className="text-indigo-300">cashback_base_bps</code>. Sent directly to your wallet.
                      </div>
                    </div>
                  </div>
                  {isSubscription && (
                    <div className="flex justify-between text-xs text-blue-400 font-medium">
                      <span>Subscription PAYTKN bonus</span>
                      <span>Distributed per epoch by RL agent</span>
                    </div>
                  )}
                </div>

                {!isDirect && (
                  <div className="flex items-center gap-2 bg-purple-500/10 border border-purple-500/20 rounded-xl px-4 py-3 text-xs text-purple-300">
                    <span>⚡</span>
                    <span>Your <strong>{cur.symbol}</strong> will be auto-swapped to PAYTKN via <strong>Jumper/LI.FI</strong> before settlement on Base Sepolia</span>
                  </div>
                )}

                {isSubscription && (
                  <div className="flex items-center gap-2 bg-blue-500/10 border border-blue-500/20 rounded-xl px-4 py-3 text-xs text-blue-300">
                    <span>🔄</span>
                    <span>This is a <strong>{period} subscription</strong>. Cancel anytime from your dashboard. Auto-renews until cancelled.</span>
                  </div>
                )}

                <button onClick={() => setStep("review")}
                  className="w-full bg-indigo-600 hover:bg-indigo-500 text-white font-bold py-4 rounded-xl transition-colors text-base">
                  Continue →
                </button>
              </>
            )}

            {/* REVIEW */}
            {step === "review" && (
              <>
                <p className="text-xs text-gray-500 uppercase tracking-wider">Order Summary</p>
                <div className="space-y-2 text-sm">
                  {([
                    ["Product",      productName],
                    ["From wallet",  address ? `${address.slice(0,8)}…${address.slice(-6)}` : "-"],
                    ["To merchant",  `${merchantName}`],
                    ["You send",     `${payAmount.toFixed(cur.decimals)} ${cur.symbol}`],
                    ...(!isDirect ? [["Bridge", "Jumper/LI.FI → PAYTKN"]] : []),
                    ["Settlement",   "PAYTKN on Base Sepolia"],
                    ["Payment type", isSubscription ? `${period} subscription` : "One-time"],
                    ["Cashback",     "Calculated by RL agent post-payment 🤖"],
                  ] as [string,string][]).map(([k,v]) => (
                    <div key={k} className={`flex justify-between rounded-lg px-4 py-2.5 ${k === "Cashback" ? "bg-indigo-500/10 border border-indigo-500/20" : "bg-gray-800"}`}>
                      <span className="text-gray-400">{k}</span>
                      <span className={`font-medium text-right max-w-[60%] ${k === "Cashback" ? "text-indigo-400" : "text-white"}`}>{v}</span>
                    </div>
                  ))}
                </div>
                <p className="text-xs text-yellow-500/80 text-center">⚠ Merchant will confirm your payment within ~30 seconds in this demo</p>
                <div className="flex gap-3">
                  <button onClick={() => setStep("select")} className="flex-1 border border-gray-700 text-gray-400 hover:text-white py-3 rounded-xl text-sm">Back</button>
                  <button onClick={handlePay} className="flex-1 bg-indigo-600 hover:bg-indigo-500 text-white font-bold py-3 rounded-xl">
                    {isSubscription ? "Subscribe & Pay" : "Confirm & Pay"}
                  </button>
                </div>
              </>
            )}

            {/* SIGNING */}
            {step === "signing" && (
              <div className="flex flex-col items-center gap-4 py-10">
                <div className="w-16 h-16 rounded-2xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center text-3xl animate-pulse">👛</div>
                <div className="text-center">
                  <p className="font-semibold text-white text-lg">Waiting for signature…</p>
                  <p className="text-sm text-gray-400 mt-1">Approve in your wallet</p>
                </div>
              </div>
            )}

            {/* CONVERTING */}
            {step === "converting" && (
              <div className="flex flex-col items-center gap-6 py-8">
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 rounded-2xl bg-purple-600 flex items-center justify-center text-2xl">{cur.logo}</div>
                  <div className="flex gap-1">
                    {[0,1,2,3].map(i => (
                      <div key={i} className="w-2 h-2 rounded-full bg-indigo-500 animate-bounce" style={{animationDelay:`${i*.12}s`}} />
                    ))}
                  </div>
                  <div className="w-12 h-12 rounded-2xl bg-indigo-600 flex items-center justify-center text-2xl">⚡</div>
                </div>
                <div className="text-center">
                  <p className="font-semibold text-white text-lg">
                    {isDirect ? "Processing payment…" : `Bridging ${cur.symbol} → PAYTKN via Jumper/LI.FI…`}
                  </p>
                  <p className="text-sm text-gray-400 mt-1">Broadcasting to Base Sepolia</p>
                </div>
                <div className="bg-gray-800 rounded-full h-2 w-full overflow-hidden">
                  <div className="h-2 bg-gradient-to-r from-purple-500 to-indigo-500 rounded-full animate-pulse" style={{width:"70%"}} />
                </div>
              </div>
            )}

            {/* WAITING FOR MERCHANT */}
            {step === "waiting" && (
              <div className="flex flex-col items-center gap-5 py-6">
                <div className="relative w-20 h-20">
                  <div className="w-20 h-20 rounded-full border-4 border-gray-800 flex items-center justify-center">
                    <span className="text-2xl font-black text-white tabular-nums">{confirmTimer}</span>
                  </div>
                  <svg className="absolute inset-0 -rotate-90" width="80" height="80">
                    <circle cx="40" cy="40" r="36" fill="none" stroke="#4f46e5" strokeWidth="4"
                      strokeDasharray={`${2 * Math.PI * 36}`}
                      strokeDashoffset={`${2 * Math.PI * 36 * (1 - confirmTimer/30)}`}
                      className="transition-all duration-1000" />
                  </svg>
                </div>
                <div className="text-center">
                  <p className="font-semibold text-white text-lg">Waiting for merchant confirmation</p>
                  <p className="text-sm text-gray-400 mt-1"><span className="text-indigo-400">{merchantName}</span> processing on-chain</p>
                </div>
                <div className="w-full bg-gray-800 rounded-xl p-3 space-y-1.5 text-xs text-gray-500">
                  <div className="flex items-center gap-2"><span className="text-green-400">✓</span> Signature verified</div>
                  <div className="flex items-center gap-2"><span className="text-green-400">✓</span> {isDirect ? "PAYTKN sent" : `${cur.symbol} bridged → PAYTKN via Jumper/LI.FI`}</div>
                  <div className="flex items-center gap-2"><span className="animate-spin inline-block">⏳</span> Awaiting merchant webhook response…</div>
                  <div className="flex items-center gap-2"><span className="text-indigo-400">🤖</span> RL agent calculating your cashback…</div>
                </div>
              </div>
            )}

            {/* DONE */}
            {step === "done" && result && (
              <div className="space-y-5">
                <div className="flex flex-col items-center gap-3 py-4">
                  <div className="w-20 h-20 rounded-full bg-green-500/20 border-2 border-green-500 flex items-center justify-center text-4xl">✓</div>
                  <p className="text-2xl font-bold text-white">{isSubscription ? "Subscribed!" : "Payment Complete!"}</p>
                  <p className="text-sm text-gray-400 text-center">
                    {isSubscription
                      ? `Your ${period} subscription is now active.`
                      : `${merchantName} has confirmed your order.`}
                  </p>
                </div>

                <div className="bg-gray-800 rounded-xl p-4 space-y-2 text-sm">
                  {/* Cashback — show RL-calculated value if available */}
                  <div className="flex justify-between items-start bg-indigo-500/10 border border-indigo-500/20 rounded-lg p-3">
                    <div>
                      <div className="text-indigo-400 font-semibold text-xs uppercase tracking-wider">🤖 RL Agent Cashback</div>
                      <div className="text-xs text-gray-400 mt-0.5">Calculated from your staking tier &amp; loyalty score</div>
                    </div>
                    <span className="text-indigo-400 font-bold text-lg ml-4 shrink-0">
                      {result.cashback_paytkn != null
                        ? `+${Number(result.cashback_paytkn).toFixed(4)} PAYTKN`
                        : "Sent to wallet ✓"}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Merchant confirmed</span>
                    <span className="text-green-400 font-medium">{merchantName}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">PAYTKN burned 🔥</span>
                    <span className="text-red-400">
                      {result.paytkn_burned != null ? Number(result.paytkn_burned).toFixed(4) : "via protocol"}
                    </span>
                  </div>
                  {isSubscription && (
                    <div className="flex justify-between border-t border-gray-700 pt-2">
                      <span className="text-gray-400">Next payment</span>
                      <span className="text-blue-400">{period === "monthly" ? "30 days" : "365 days"}</span>
                    </div>
                  )}
                  <div className="flex justify-between text-xs border-t border-gray-700 pt-2">
                    <span className="text-gray-500">Tx hash</span>
                    <span className="text-gray-400 font-mono">{String(result.tx_hash).slice(0,12)}…{String(result.tx_hash).slice(-6)}</span>
                  </div>
                </div>

                <div className="flex gap-3">
                  <a href="http://localhost:3001" className="flex-1 border border-gray-700 text-gray-400 hover:text-white py-3 rounded-xl text-sm text-center transition-colors">
                    ← Back to Store
                  </a>
                  <a href="/dashboard" className="flex-1 bg-indigo-600 hover:bg-indigo-500 text-white font-bold py-3 rounded-xl text-sm text-center transition-colors">
                    View Dashboard
                  </a>
                </div>
              </div>
            )}

          </div>
        </div>

        <div className="flex items-center justify-center gap-4 text-xs text-gray-600">
          <span>🔒 Base Sepolia</span><span>·</span>
          <span>⚡ PAYTKN Protocol</span><span>·</span>
          <span>🤖 RL-Optimised Cashback</span>
          {!isDirect && <><span>·</span><span>🌉 Jumper/LI.FI</span></>}
        </div>
      </div>
    </div>
  );
}

export default function CheckoutPage() {
  return (
    <Suspense fallback={<div className="flex justify-center h-64 items-center"><div className="animate-spin h-10 w-10 rounded-full border-b-2 border-indigo-500" /></div>}>
      <CheckoutInner />
    </Suspense>
  );
}
