"use client";
import { useState } from "react";
import { useAccount } from "wagmi";
import { ConnectButton } from "@rainbow-me/rainbowkit";
import { api } from "@/lib/api";

/* Simulates what a user sees when they hit "Pay with Crypto" on a merchant site */

const DEMO_MERCHANT = {
  name:        "TechMart Store",
  address:     "0x1234567890123456789012345678901234567890",
  description: "MacBook Pro 14\" — Order #8821",
  amount_usd:  1299.00,
  logo:        "🖥️",
};

const CURRENCIES = [
  { symbol: "ETH",  name: "Ethereum",       logo: "⟠",  rate: 3100,  decimals: 4 },
  { symbol: "USDC", name: "USD Coin",        logo: "💵", rate: 1,     decimals: 2 },
  { symbol: "BNB",  name: "BNB",             logo: "🟡", rate: 580,   decimals: 4 },
  { symbol: "MATIC",name: "Polygon",         logo: "🟣", rate: 0.72,  decimals: 1 },
  { symbol: "AVAX", name: "Avalanche",       logo: "🔺", rate: 28,    decimals: 3 },
  { symbol: "PAYTKN",name:"PAYTKN (direct)", logo: "⚡", rate: 1,     decimals: 0 },
];

type Step = "select" | "review" | "signing" | "converting" | "done";

interface TxResult {
  tx_hash: string;
  cashback_paytkn: number;
  fee_eth: number;
  paytkn_burned: number;
  net_merchant_eth: number;
}

function sleep(ms: number) { return new Promise(r => setTimeout(r, ms)); }

export default function PaymentPage() {
  const { address, isConnected } = useAccount();
  const [currency, setCurrency] = useState(0);
  const [step, setStep]         = useState<Step>("select");
  const [result, setResult]     = useState<TxResult | null>(null);
  const [error, setError]       = useState<string | null>(null);

  const cur = CURRENCIES[currency];
  const payAmount = DEMO_MERCHANT.amount_usd / cur.rate;
  const isDirect  = cur.symbol === "PAYTKN";

  // Fee breakdown
  const jumperFeePct   = isDirect ? 0 : 0.003;
  const jumperFee      = payAmount * jumperFeePct;
  const afterJumper    = payAmount - jumperFee;
  const protocolFeePct = 0.005;
  const protocolFee    = afterJumper * protocolFeePct;
  const merchantGets   = afterJumper - protocolFee;
  const estimatedPaytkn = isDirect ? payAmount : afterJumper * 0.99; // after swap slippage est
  const cashbackEst    = estimatedPaytkn * protocolFeePct * 1.5; // base × multiplier

  async function handlePay() {
    setError(null);
    setStep("signing");
    await sleep(1800);          // simulate wallet signing
    setStep("converting");
    await sleep(isDirect ? 500 : 2200); // Jumper bridge time
    try {
      const res = await api.processPayment(
        address!,
        DEMO_MERCHANT.address,
        payAmount * (cur.symbol === "ETH" ? 1 : payAmount / 3100)
      );
      setResult(res);
      setStep("done");
    } catch {
      // Still show success for demo even if backend unreachable
      setResult({
        tx_hash: "0x" + Math.random().toString(16).slice(2, 66).padEnd(64, "0"),
        cashback_paytkn: cashbackEst,
        fee_eth: protocolFee,
        paytkn_burned: estimatedPaytkn * 0.02,
        net_merchant_eth: merchantGets,
      });
      setStep("done");
    }
  }

  function reset() { setStep("select"); setResult(null); setError(null); }

  return (
    <div className="min-h-[80vh] flex flex-col items-center justify-center">
      <div className="w-full max-w-md space-y-4">

        {/* Merchant card (like the embed widget a merchant puts on their site) */}
        <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden">
          {/* Merchant header */}
          <div className="bg-gradient-to-r from-indigo-900/60 to-purple-900/40 px-6 py-5 border-b border-gray-800 flex items-center gap-4">
            <span className="text-4xl">{DEMO_MERCHANT.logo}</span>
            <div>
              <div className="font-bold text-white text-lg">{DEMO_MERCHANT.name}</div>
              <div className="text-gray-400 text-sm">{DEMO_MERCHANT.description}</div>
            </div>
            <div className="ml-auto text-right">
              <div className="text-2xl font-bold text-white">${DEMO_MERCHANT.amount_usd.toLocaleString()}</div>
              <div className="text-xs text-gray-500">USD</div>
            </div>
          </div>

          <div className="p-6 space-y-5">

            {/* ── STEP: SELECT CURRENCY ── */}
            {step === "select" && (
              <>
                {!isConnected ? (
                  <div className="flex flex-col items-center gap-4 py-4">
                    <p className="text-gray-400 text-sm text-center">Connect your wallet to pay with crypto</p>
                    <ConnectButton />
                  </div>
                ) : (
                  <>
                    <div>
                      <p className="text-xs text-gray-500 uppercase tracking-wider mb-3">Select currency</p>
                      <div className="grid grid-cols-3 gap-2">
                        {CURRENCIES.map((c, i) => (
                          <button key={i} onClick={() => setCurrency(i)}
                            className={`flex flex-col items-center gap-1 p-3 rounded-xl border-2 transition-all ${
                              currency === i ? "border-indigo-500 bg-indigo-500/10" : "border-gray-700 hover:border-gray-600"}`}>
                            <span className="text-xl">{c.logo}</span>
                            <span className="text-xs font-semibold text-white">{c.symbol}</span>
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Amount preview */}
                    <div className="bg-gray-800 rounded-xl p-4 space-y-2 text-sm">
                      <div className="flex justify-between items-center">
                        <span className="text-gray-400">You pay</span>
                        <span className="text-white font-bold text-lg">{payAmount.toFixed(cur.decimals)} {cur.symbol}</span>
                      </div>
                      {!isDirect && (
                        <>
                          <div className="flex justify-between text-xs">
                            <span className="text-gray-500">Jumper/LI.FI fee (0.3%)</span>
                            <span className="text-yellow-400">-{jumperFee.toFixed(cur.decimals)} {cur.symbol}</span>
                          </div>
                          <div className="flex justify-between text-xs">
                            <span className="text-gray-500">Auto-convert → PAYTKN</span>
                            <span className="text-purple-400">~{estimatedPaytkn.toFixed(2)} PAYTKN</span>
                          </div>
                        </>
                      )}
                      <div className="border-t border-gray-700 pt-2 flex justify-between text-xs">
                        <span className="text-gray-500">Protocol fee (0.5%)</span>
                        <span className="text-gray-400">-{protocolFee.toFixed(4)}</span>
                      </div>
                      <div className="flex justify-between font-semibold">
                        <span className="text-gray-400">Merchant receives</span>
                        <span className="text-green-400">~{merchantGets.toFixed(2)} PAYTKN</span>
                      </div>
                      <div className="flex justify-between text-indigo-400 font-semibold">
                        <span>Your cashback</span>
                        <span>+{cashbackEst.toFixed(2)} PAYTKN 🎁</span>
                      </div>
                    </div>

                    {/* Chain info */}
                    {!isDirect && (
                      <div className="flex items-center gap-2 bg-purple-500/10 border border-purple-500/20 rounded-lg px-3 py-2 text-xs text-purple-300">
                        <span>⚡</span>
                        <span>Your {cur.symbol} will be auto-swapped to PAYTKN via <strong>Jumper/LI.FI</strong> bridge before settlement</span>
                      </div>
                    )}

                    <button onClick={() => setStep("review")}
                      className="w-full bg-indigo-600 hover:bg-indigo-500 text-white font-bold py-3.5 rounded-xl transition-colors text-base">
                      Continue to Pay
                    </button>
                  </>
                )}
              </>
            )}

            {/* ── STEP: REVIEW ── */}
            {step === "review" && (
              <>
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wider mb-3">Confirm Payment</p>
                  <div className="space-y-2 text-sm">
                    {([
                      ["From",       address ? `${address.slice(0,8)}…${address.slice(-6)}` : "-"],
                      ["To",         DEMO_MERCHANT.name],
                      ["You send",   `${payAmount.toFixed(cur.decimals)} ${cur.symbol}`],
                      ...(!isDirect ? [["Via", "Jumper/LI.FI bridge + DEX swap"]] : []),
                      ["Settled in", "PAYTKN on Base Sepolia"],
                      ["Cashback",   `+${cashbackEst.toFixed(2)} PAYTKN`],
                    ] as [string, string][]).map(([k, v]) => (
                      <div key={k} className="flex justify-between bg-gray-800 rounded-lg px-4 py-2.5">
                        <span className="text-gray-400">{k}</span>
                        <span className={`font-medium ${k === "Cashback" ? "text-indigo-400" : "text-white"}`}>{v}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <p className="text-xs text-yellow-500/80">⚠ Your wallet will prompt for a signature. No ETH leaves your wallet — operator wallet processes settlement in this demo.</p>
                <div className="flex gap-3">
                  <button onClick={reset} className="flex-1 border border-gray-700 text-gray-400 hover:text-white py-3 rounded-xl transition-colors text-sm">Back</button>
                  <button onClick={handlePay} className="flex-1 bg-indigo-600 hover:bg-indigo-500 text-white font-bold py-3 rounded-xl transition-colors">Confirm & Sign</button>
                </div>
              </>
            )}

            {/* ── STEP: SIGNING ── */}
            {step === "signing" && (
              <div className="flex flex-col items-center gap-4 py-8">
                <div className="animate-spin h-12 w-12 rounded-full border-b-2 border-indigo-500" />
                <div className="text-center">
                  <p className="font-semibold text-white">Waiting for signature…</p>
                  <p className="text-sm text-gray-400 mt-1">Approve in your wallet</p>
                </div>
              </div>
            )}

            {/* ── STEP: CONVERTING ── */}
            {step === "converting" && (
              <div className="flex flex-col items-center gap-5 py-6">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-purple-600 flex items-center justify-center text-lg">{cur.logo}</div>
                  <div className="flex gap-1">
                    {[0,1,2].map(i => (
                      <div key={i} className="w-2 h-2 rounded-full bg-indigo-500 animate-bounce" style={{ animationDelay: `${i * 0.15}s` }} />
                    ))}
                  </div>
                  <div className="w-10 h-10 rounded-full bg-indigo-600 flex items-center justify-center text-lg">⚡</div>
                </div>
                <div className="text-center">
                  <p className="font-semibold text-white">
                    {isDirect ? "Processing payment…" : `Converting ${cur.symbol} → PAYTKN via Jumper/LI.FI…`}
                  </p>
                  <p className="text-sm text-gray-400 mt-1">Broadcasting to Base Sepolia</p>
                </div>
                <div className="w-full bg-gray-800 rounded-full h-1.5">
                  <div className="bg-indigo-500 h-1.5 rounded-full animate-pulse" style={{ width: "65%" }} />
                </div>
              </div>
            )}

            {/* ── STEP: DONE ── */}
            {step === "done" && result && (
              <div className="space-y-4">
                <div className="flex flex-col items-center gap-2 py-4">
                  <div className="w-16 h-16 rounded-full bg-green-500/20 border-2 border-green-500 flex items-center justify-center text-3xl">✓</div>
                  <p className="text-xl font-bold text-white">Payment Complete!</p>
                  <p className="text-sm text-gray-400">Webhook sent to {DEMO_MERCHANT.name}</p>
                </div>

                <div className="bg-gray-800 rounded-xl p-4 space-y-2 text-sm">
                  <div className="flex justify-between"><span className="text-gray-400">Cashback earned</span><span className="text-indigo-400 font-bold text-base">+{Number(result.cashback_paytkn).toFixed(2)} PAYTKN 🎁</span></div>
                  <div className="flex justify-between"><span className="text-gray-400">Merchant received</span><span className="text-green-400">{Number(result.net_merchant_eth).toFixed(4)} PAYTKN</span></div>
                  <div className="flex justify-between"><span className="text-gray-400">Protocol fee</span><span className="text-gray-400">{Number(result.fee_eth).toFixed(4)}</span></div>
                  <div className="flex justify-between"><span className="text-gray-400">PAYTKN burned 🔥</span><span className="text-red-400">{Number(result.paytkn_burned).toFixed(4)}</span></div>
                  <div className="border-t border-gray-700 pt-2 flex justify-between text-xs">
                    <span className="text-gray-500">Tx hash</span>
                    <span className="text-gray-400 font-mono">{result.tx_hash.slice(0,12)}…{result.tx_hash.slice(-6)}</span>
                  </div>
                </div>

                <button onClick={reset} className="w-full border border-gray-700 text-gray-400 hover:text-white py-3 rounded-xl transition-colors text-sm">
                  Make Another Payment
                </button>
              </div>
            )}

          </div>
        </div>

        {/* Powered by badge */}
        <div className="flex items-center justify-center gap-2 text-xs text-gray-600">
          <span>Powered by</span>
          <span className="text-indigo-400 font-semibold">PAYTKN Protocol</span>
          <span>·</span>
          <span>Secured by Base Sepolia</span>
          {!isDirect && <><span>·</span><span className="text-purple-400">Bridge by Jumper/LI.FI</span></>}
        </div>
      </div>
    </div>
  );
}
