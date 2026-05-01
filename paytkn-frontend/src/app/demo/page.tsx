"use client";
import { useState, useEffect, useCallback } from "react";
import { useAccount, useBalance, useReadContract } from "wagmi";
import { ConnectButton } from "@rainbow-me/rainbowkit";
import { formatEther, isAddress } from "viem";
import { api } from "@/lib/api";
import { CONTRACT_ADDRESSES, ERC20_ABI, DEMO_MERCHANT, OPERATOR_ADDRESS } from "@/lib/web3";

// ── Types ─────────────────────────────────────────────────────────────────────
interface PayResult {
  tx_hash: string;
  cashback_paytkn: number;
  fee_eth: number;
  basescan: string;
  merchant_eth_received: number;
}

// ── Constants ─────────────────────────────────────────────────────────────────
const PAYTKN_ADDR = CONTRACT_ADDRESSES.token as `0x${string}`;
const AMOUNT_PRESETS = [0.001, 0.005, 0.01, 0.05];
const PRODUCTS = [
  { name: "Coffee ☕",         price: 0.001 },
  { name: "Lunch 🍔",          price: 0.003 },
  { name: "Hoodie 👕",         price: 0.01  },
  { name: "Custom amount",      price: 0     },
];

// ── Helper ────────────────────────────────────────────────────────────────────
function fmt(wei: bigint | undefined, decimals = 5) {
  if (wei === undefined) return "—";
  return parseFloat(formatEther(wei)).toFixed(decimals);
}
function fmtPAYTKN(raw: bigint | undefined) {
  if (raw === undefined) return "—";
  return (Number(raw) / 1e18).toFixed(4);
}
function shortAddr(a: string) {
  return a ? `${a.slice(0, 6)}…${a.slice(-4)}` : "";
}

// ── Balance card ──────────────────────────────────────────────────────────────
function BalanceRow({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="flex justify-between items-center py-2 border-b border-white/5 last:border-0">
      <span className="text-sm text-gray-400">{label}</span>
      <span className={`font-mono text-sm font-semibold ${highlight ? "text-green-400" : "text-white"}`}>
        {value}
      </span>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// Main page
// ═════════════════════════════════════════════════════════════════════════════
export default function DemoPage() {
  const { address, isConnected } = useAccount();

  // ── Merchant address state ───────────────────────────────────────────────
  const [merchantAddr, setMerchantAddr] = useState(DEMO_MERCHANT);
  const [merchantInput, setMerchantInput] = useState(DEMO_MERCHANT);
  const merchantValid = isAddress(merchantInput);

  // ── Payment form ─────────────────────────────────────────────────────────
  const [product, setProduct]     = useState(0);
  const [amount, setAmount]       = useState(0.005);
  const [customAmt, setCustomAmt] = useState("0.005");

  const payAmount = PRODUCTS[product].price > 0 ? PRODUCTS[product].price : parseFloat(customAmt) || 0;

  // ── Status ───────────────────────────────────────────────────────────────
  const [status, setStatus] = useState<"idle" | "sending" | "done" | "error">("idle");
  const [result, setResult] = useState<PayResult | null>(null);
  const [error, setError]   = useState("");

  // ── ETH balances ─────────────────────────────────────────────────────────
  const { data: userETH,     refetch: reU }  = useBalance({ address });
  const { data: merchantETH, refetch: reM }  = useBalance({ address: merchantAddr as `0x${string}` });
  const { data: operatorETH, refetch: reOp } = useBalance({ address: OPERATOR_ADDRESS as `0x${string}` });

  // ── PAYTKN balances ───────────────────────────────────────────────────────
  const { data: userPAYTKN,     refetch: rePU } = useReadContract({
    address: PAYTKN_ADDR, abi: ERC20_ABI, functionName: "balanceOf",
    args: [address ?? "0x0000000000000000000000000000000000000000"],
    query: { enabled: !!address },
  });
  const { data: merchantPAYTKN, refetch: rePM } = useReadContract({
    address: PAYTKN_ADDR, abi: ERC20_ABI, functionName: "balanceOf",
    args: [merchantAddr as `0x${string}`],
    query: { enabled: merchantValid },
  });

  // Snapshot before payment for delta display
  const [snapUserETH,     setSnapUserETH]     = useState<bigint | undefined>();
  const [snapMerchantETH, setSnapMerchantETH] = useState<bigint | undefined>();
  const [snapUserPAY,     setSnapUserPAY]     = useState<bigint | undefined>();

  // Refresh all balances
  const refetchAll = useCallback(() => {
    reU(); reM(); reOp(); rePU(); rePM();
  }, [reU, reM, reOp, rePU, rePM]);

  // Poll every 4s while sending
  useEffect(() => {
    if (status !== "sending") return;
    const t = setInterval(refetchAll, 4000);
    return () => clearInterval(t);
  }, [status, refetchAll]);

  // ── Pay handler ───────────────────────────────────────────────────────────
  async function handlePay() {
    if (!address || !merchantValid || payAmount <= 0) return;
    setStatus("sending");
    setResult(null);
    setError("");
    // Snapshot before
    setSnapUserETH(userETH?.value);
    setSnapMerchantETH(merchantETH?.value);
    setSnapUserPAY(userPAYTKN as bigint | undefined);

    try {
      const res = await api.processPayment(address, merchantAddr, payAmount);
      const merchantReceived = payAmount * 0.995; // 99.5% after 0.5% fee
      setResult({
        tx_hash:               res.tx_hash ?? "",
        cashback_paytkn:       res.cashback_paytkn ?? res.estimated_cashback_paytkn ?? 0,
        fee_eth:               res.fee_eth ?? payAmount * 0.005,
        basescan:              res.basescan ?? `https://sepolia.basescan.org/tx/${res.tx_hash}`,
        merchant_eth_received: merchantReceived,
      });
      setStatus("done");
      // Refetch a few times to capture on-chain finality
      setTimeout(refetchAll, 2000);
      setTimeout(refetchAll, 6000);
      setTimeout(refetchAll, 12000);
    } catch (e: any) {
      setError(e?.message ?? "Payment failed — check backend is running");
      setStatus("error");
    }
  }

  function resetDemo() {
    setStatus("idle");
    setResult(null);
    setError("");
    refetchAll();
  }

  // Apply merchant address when user confirms
  function applyMerchant() {
    if (merchantValid) setMerchantAddr(merchantInput);
  }

  // ── Deltas ────────────────────────────────────────────────────────────────
  const deltaUserPAY = userPAYTKN !== undefined && snapUserPAY !== undefined
    ? Number(userPAYTKN as bigint) - Number(snapUserPAY)
    : null;
  const deltaMerchETH = merchantETH?.value !== undefined && snapMerchantETH !== undefined
    ? merchantETH.value - snapMerchantETH
    : null;

  // ── Operator ETH warning ──────────────────────────────────────────────────
  const operatorLow = operatorETH && operatorETH.value < BigInt("5000000000000000"); // < 0.005 ETH

  // ─────────────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-gray-950 text-white">

      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="border-b border-gray-800 bg-gradient-to-r from-indigo-950/60 via-gray-900 to-emerald-950/40 px-6 py-8">
        <div className="max-w-6xl mx-auto">
          <div className="flex items-center gap-3 mb-2">
            <span className="w-3 h-3 rounded-full bg-green-400 animate-pulse" />
            <span className="text-xs text-green-400 font-mono uppercase tracking-widest">Live on Base Sepolia</span>
          </div>
          <h1 className="text-3xl font-black text-white tracking-tight">⚡ PAYTKN Live Demo</h1>
          <p className="text-gray-400 mt-1 text-sm max-w-xl">
            Real on-chain payment — merchant receives ETH, user receives PAYTKN cashback.
            Powered by the deployed Treasury contract on Base Sepolia (Chain ID 84532).
          </p>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-4 py-8 space-y-6">

        {/* ── Operator warning ──────────────────────────────────────────── */}
        {operatorLow && (
          <div className="bg-amber-900/30 border border-amber-700/50 rounded-xl px-5 py-3 flex items-center gap-3">
            <span className="text-xl">⚠️</span>
            <div>
              <p className="text-amber-300 font-semibold text-sm">Backend wallet is low on test ETH</p>
              <p className="text-amber-400/70 text-xs mt-0.5">
                Operator: {shortAddr(OPERATOR_ADDRESS)} — balance: {fmt(operatorETH?.value, 4)} ETH.
                Send Base Sepolia ETH to this address so the backend can relay payments.
              </p>
            </div>
          </div>
        )}

        {/* ── Two wallet panels + payment ───────────────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

          {/* ── USER WALLET ─────────────────────────────────────────────── */}
          <div className="bg-gray-900 border border-indigo-800/40 rounded-2xl overflow-hidden">
            <div className="bg-gradient-to-br from-indigo-900/60 to-indigo-800/20 px-5 py-4 border-b border-indigo-800/30">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-lg">👤</span>
                <span className="font-bold text-indigo-200 text-sm uppercase tracking-widest">User Wallet</span>
              </div>
              <p className="text-xs text-indigo-400/70">Receives PAYTKN cashback from each payment</p>
            </div>

            <div className="p-5 space-y-4">
              {!isConnected ? (
                <div className="flex flex-col items-center gap-3 py-4">
                  <div className="text-4xl">🔗</div>
                  <p className="text-sm text-gray-400 text-center">Connect your MetaMask wallet<br/>to act as the paying customer</p>
                  <ConnectButton />
                </div>
              ) : (
                <>
                  <div className="bg-gray-800/60 rounded-lg px-3 py-2">
                    <p className="text-xs text-gray-500 mb-0.5">Address</p>
                    <p className="font-mono text-xs text-indigo-300 break-all">{address}</p>
                  </div>

                  <div className="space-y-0">
                    <BalanceRow label="ETH Balance" value={`${fmt(userETH?.value, 5)} ETH`} />
                    <BalanceRow
                      label="PAYTKN Balance"
                      value={`${fmtPAYTKN(userPAYTKN as bigint | undefined)} PAYTKN`}
                      highlight={(userPAYTKN as bigint ?? 0n) > 0n}
                    />
                    {deltaUserPAY !== null && deltaUserPAY > 0 && (
                      <div className="mt-2 flex items-center gap-2 bg-green-900/30 border border-green-700/40 rounded-lg px-3 py-2">
                        <span className="text-green-400 text-lg">✨</span>
                        <div>
                          <p className="text-green-400 text-xs font-semibold">Cashback received!</p>
                          <p className="text-green-300 font-mono text-sm">+{(deltaUserPAY / 1e18).toFixed(6)} PAYTKN</p>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Import PAYTKN to MetaMask button */}
                  <button
                    onClick={async () => {
                      try {
                        await (window as any).ethereum.request({
                          method: "wallet_watchAsset",
                          params: {
                            type: "ERC20",
                            options: {
                              address: PAYTKN_ADDR,
                              symbol: "PAYTKN",
                              decimals: 18,
                            },
                          },
                        });
                      } catch {}
                    }}
                    className="w-full text-xs bg-indigo-800/30 hover:bg-indigo-700/40 border border-indigo-700/40 text-indigo-300 rounded-lg py-2 transition-colors"
                  >
                    + Add PAYTKN to MetaMask
                  </button>

                  <div className="flex justify-end">
                    <ConnectButton accountStatus="address" chainStatus="icon" showBalance={false} />
                  </div>
                </>
              )}
            </div>
          </div>

          {/* ── PAYMENT TERMINAL ────────────────────────────────────────── */}
          <div className="bg-gray-900 border border-gray-700/50 rounded-2xl overflow-hidden">
            <div className="bg-gradient-to-br from-gray-800/80 to-gray-900 px-5 py-4 border-b border-gray-700/40">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-lg">💳</span>
                <span className="font-bold text-gray-100 text-sm uppercase tracking-widest">Payment Terminal</span>
              </div>
              <p className="text-xs text-gray-400">Backend relays on-chain — no gas from your wallet</p>
            </div>

            <div className="p-5 space-y-4">

              {/* Product selector */}
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Product</p>
                <div className="grid grid-cols-2 gap-2">
                  {PRODUCTS.map((p, i) => (
                    <button key={i} onClick={() => setProduct(i)}
                      className={`text-left px-3 py-2.5 rounded-xl border text-sm transition-all ${
                        product === i
                          ? "border-indigo-500 bg-indigo-500/15 text-white"
                          : "border-gray-700 hover:border-gray-600 text-gray-400"
                      }`}>
                      <div className="font-medium">{p.name}</div>
                      {p.price > 0 && <div className="text-xs text-gray-500 mt-0.5">{p.price} ETH</div>}
                    </button>
                  ))}
                </div>
              </div>

              {/* Custom amount if selected */}
              {product === 3 && (
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Amount (ETH)</p>
                  <div className="flex gap-2">
                    {AMOUNT_PRESETS.map(a => (
                      <button key={a} onClick={() => setCustomAmt(String(a))}
                        className={`flex-1 text-xs py-1.5 rounded-lg border transition-colors ${
                          customAmt === String(a)
                            ? "border-indigo-500 bg-indigo-500/15 text-white"
                            : "border-gray-700 text-gray-400 hover:border-gray-600"
                        }`}>
                        {a}
                      </button>
                    ))}
                  </div>
                  <input
                    value={customAmt}
                    onChange={e => setCustomAmt(e.target.value)}
                    placeholder="0.001"
                    className="w-full mt-2 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-indigo-500"
                  />
                </div>
              )}

              {/* Fee breakdown */}
              {payAmount > 0 && (
                <div className="bg-gray-800/60 rounded-xl p-3 space-y-1.5 text-xs">
                  <div className="flex justify-between text-gray-400">
                    <span>Payment amount</span>
                    <span className="font-mono text-white">{payAmount.toFixed(5)} ETH</span>
                  </div>
                  <div className="flex justify-between text-gray-400">
                    <span>Protocol fee (0.5%)</span>
                    <span className="font-mono text-red-400">−{(payAmount * 0.005).toFixed(6)} ETH</span>
                  </div>
                  <div className="flex justify-between text-gray-400">
                    <span>Merchant receives (ETH)</span>
                    <span className="font-mono text-emerald-400">{(payAmount * 0.995).toFixed(6)} ETH</span>
                  </div>
                  <div className="flex justify-between text-gray-400 border-t border-gray-700 pt-1.5 mt-1.5">
                    <span>Your PAYTKN cashback</span>
                    <span className="font-mono text-indigo-400">~{(payAmount * 0.005).toFixed(4)} PAYTKN</span>
                  </div>
                </div>
              )}

              {/* Result / Status area */}
              {status === "done" && result && (
                <div className="bg-green-900/25 border border-green-700/40 rounded-xl p-4 space-y-3">
                  <div className="flex items-center gap-2">
                    <span className="text-green-400 text-xl">✅</span>
                    <span className="font-semibold text-green-300">Transaction Confirmed!</span>
                  </div>
                  <div className="space-y-1.5 text-xs">
                    <div className="flex justify-between text-gray-400">
                      <span>Merchant received</span>
                      <span className="font-mono text-emerald-400">+{result.merchant_eth_received.toFixed(6)} ETH</span>
                    </div>
                    <div className="flex justify-between text-gray-400">
                      <span>Your cashback</span>
                      <span className="font-mono text-indigo-400">+{result.cashback_paytkn.toFixed(4)} PAYTKN</span>
                    </div>
                  </div>
                  <a
                    href={result.basescan}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 transition-colors"
                  >
                    <span className="font-mono">{shortAddr(result.tx_hash)}</span>
                    <span>→ View on Basescan ↗</span>
                  </a>
                  <button onClick={resetDemo}
                    className="w-full text-xs bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-300 rounded-lg py-2 transition-colors mt-1">
                    Make another payment
                  </button>
                </div>
              )}

              {status === "error" && (
                <div className="bg-red-900/25 border border-red-700/40 rounded-xl px-4 py-3">
                  <p className="text-red-400 text-sm font-medium">Payment failed</p>
                  <p className="text-red-300/70 text-xs mt-1 break-words">{error}</p>
                  <button onClick={resetDemo} className="mt-2 text-xs text-gray-400 underline">Try again</button>
                </div>
              )}

              {/* Pay button */}
              {status !== "done" && (
                <button
                  onClick={handlePay}
                  disabled={!isConnected || !merchantValid || payAmount <= 0 || status === "sending"}
                  className={`w-full py-3.5 rounded-xl font-bold text-sm tracking-wide transition-all ${
                    status === "sending"
                      ? "bg-indigo-800/60 text-indigo-300 cursor-wait"
                      : !isConnected || !merchantValid || payAmount <= 0
                      ? "bg-gray-800 text-gray-600 cursor-not-allowed"
                      : "bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-900/50"
                  }`}
                >
                  {status === "sending" ? (
                    <span className="flex items-center justify-center gap-2">
                      <span className="w-4 h-4 border-2 border-indigo-400/40 border-t-indigo-400 rounded-full animate-spin" />
                      Processing on-chain…
                    </span>
                  ) : !isConnected ? (
                    "Connect wallet first"
                  ) : !merchantValid ? (
                    "Enter valid merchant address"
                  ) : (
                    `⚡ Pay ${payAmount.toFixed(4)} ETH on Base Sepolia`
                  )}
                </button>
              )}

              {/* Network info */}
              <div className="flex items-center justify-center gap-1.5 text-xs text-gray-600">
                <span className="w-2 h-2 rounded-full bg-green-500/60" />
                Base Sepolia · Chain 84532 · Treasury {CONTRACT_ADDRESSES.treasury.slice(0, 6)}…
              </div>
            </div>
          </div>

          {/* ── MERCHANT WALLET ──────────────────────────────────────────── */}
          <div className="bg-gray-900 border border-emerald-800/40 rounded-2xl overflow-hidden">
            <div className="bg-gradient-to-br from-emerald-900/50 to-emerald-800/20 px-5 py-4 border-b border-emerald-800/30">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-lg">🏪</span>
                <span className="font-bold text-emerald-200 text-sm uppercase tracking-widest">Merchant Wallet</span>
              </div>
              <p className="text-xs text-emerald-400/70">Receives 99.5% of payment as ETH</p>
            </div>

            <div className="p-5 space-y-4">
              {/* Merchant address input */}
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Merchant address</p>
                <div className="flex gap-2">
                  <input
                    value={merchantInput}
                    onChange={e => setMerchantInput(e.target.value)}
                    placeholder="0x…"
                    className={`flex-1 bg-gray-800 border rounded-lg px-3 py-2 text-xs font-mono focus:outline-none transition-colors ${
                      merchantValid
                        ? "border-emerald-700/60 focus:border-emerald-500 text-white"
                        : "border-red-700/50 focus:border-red-500 text-red-300"
                    }`}
                  />
                  <button
                    onClick={applyMerchant}
                    disabled={!merchantValid}
                    className="px-3 py-2 bg-emerald-700/40 hover:bg-emerald-600/50 disabled:opacity-40 border border-emerald-700/50 text-emerald-300 rounded-lg text-xs transition-colors"
                  >
                    Set
                  </button>
                </div>
                {!merchantValid && merchantInput.length > 2 && (
                  <p className="text-red-400 text-xs mt-1">Invalid Ethereum address</p>
                )}
                {merchantAddr === DEMO_MERCHANT && (
                  <p className="text-emerald-600 text-xs mt-1">Using demo operator address</p>
                )}
              </div>

              {/* Merchant balances */}
              <div className="space-y-0">
                <BalanceRow label="ETH Balance" value={`${fmt(merchantETH?.value, 6)} ETH`} highlight={(merchantETH?.value ?? 0n) > 0n} />
                <BalanceRow label="PAYTKN Balance" value={`${fmtPAYTKN(merchantPAYTKN as bigint | undefined)} PAYTKN`} />
              </div>

              {/* ETH received delta */}
              {deltaMerchETH !== null && deltaMerchETH > 0n && (
                <div className="flex items-center gap-2 bg-emerald-900/30 border border-emerald-700/40 rounded-lg px-3 py-2">
                  <span className="text-emerald-400 text-lg">💰</span>
                  <div>
                    <p className="text-emerald-400 text-xs font-semibold">ETH received on-chain!</p>
                    <p className="text-emerald-300 font-mono text-sm">+{fmt(deltaMerchETH, 8)} ETH</p>
                  </div>
                </div>
              )}

              {/* Tip: use another MetaMask account */}
              <div className="bg-emerald-900/15 border border-emerald-800/30 rounded-lg px-3 py-3">
                <p className="text-xs text-emerald-400 font-semibold mb-1">💡 For a live demo</p>
                <p className="text-xs text-gray-400 leading-relaxed">
                  Enter a second MetaMask account as the merchant address. After paying, switch to that account in MetaMask to see the ETH arrive in real time.
                </p>
              </div>

              {/* Refresh */}
              <button
                onClick={refetchAll}
                className="w-full text-xs bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-400 rounded-lg py-2 transition-colors"
              >
                🔄 Refresh balances
              </button>
            </div>
          </div>
        </div>

        {/* ── How it works ──────────────────────────────────────────────────── */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          {[
            { step: "1", icon: "🔗", title: "Connect Wallet", desc: "User connects MetaMask on Base Sepolia" },
            { step: "2", icon: "🏪", title: "Set Merchant", desc: "Enter any wallet address to receive payment" },
            { step: "3", icon: "⚡", title: "Pay On-Chain", desc: "Backend relays tx via Treasury contract" },
            { step: "4", icon: "✨", title: "Instant Settlement", desc: "Merchant gets ETH, user gets PAYTKN cashback" },
          ].map(s => (
            <div key={s.step} className="bg-gray-900/60 border border-gray-800 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-2">
                <span className="w-5 h-5 rounded-full bg-indigo-700 text-xs font-bold flex items-center justify-center">{s.step}</span>
                <span className="text-lg">{s.icon}</span>
              </div>
              <p className="font-semibold text-sm text-white">{s.title}</p>
              <p className="text-xs text-gray-400 mt-0.5">{s.desc}</p>
            </div>
          ))}
        </div>

        {/* ── Testnet setup guide ───────────────────────────────────────────── */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

          {/* Get test ETH */}
          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5">
            <h3 className="font-bold text-white flex items-center gap-2 mb-4">
              <span className="text-lg">🚰</span> Get Base Sepolia Test ETH
            </h3>
            <div className="space-y-3">
              {[
                {
                  name: "Coinbase Faucet",
                  url: "https://www.coinbase.com/faucets/base-ethereum-sepolia-faucet",
                  desc: "Official — requires Coinbase login",
                  badge: "Recommended",
                },
                {
                  name: "QuickNode Faucet",
                  url: "https://faucet.quicknode.com/base/sepolia",
                  desc: "Up to 0.1 ETH per day",
                  badge: "",
                },
                {
                  name: "Alchemy Faucet",
                  url: "https://www.alchemy.com/faucets/base-sepolia",
                  desc: "Up to 0.5 ETH — requires Alchemy account",
                  badge: "High Amount",
                },
              ].map(f => (
                <a key={f.name} href={f.url} target="_blank" rel="noopener noreferrer"
                  className="flex items-center justify-between bg-gray-800/60 hover:bg-gray-800 border border-gray-700/50 hover:border-indigo-700/40 rounded-xl px-4 py-3 transition-all group">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-white group-hover:text-indigo-300 transition-colors">{f.name}</span>
                      {f.badge && (
                        <span className="text-xs bg-indigo-700/50 text-indigo-300 px-1.5 py-0.5 rounded">{f.badge}</span>
                      )}
                    </div>
                    <p className="text-xs text-gray-400 mt-0.5">{f.desc}</p>
                  </div>
                  <span className="text-gray-500 group-hover:text-indigo-400 transition-colors">↗</span>
                </a>
              ))}
              <div className="bg-amber-900/20 border border-amber-800/30 rounded-lg px-3 py-2">
                <p className="text-xs text-amber-400 font-medium">⚠️ Also fund the backend wallet</p>
                <p className="text-xs text-gray-400 mt-0.5">Send some Base Sepolia ETH to:</p>
                <p className="font-mono text-xs text-white mt-1 break-all">{OPERATOR_ADDRESS}</p>
                <p className="text-xs text-gray-500 mt-0.5">This relays payments on-chain (needs ETH for gas + payment amount)</p>
              </div>
            </div>
          </div>

          {/* MetaMask setup */}
          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5">
            <h3 className="font-bold text-white flex items-center gap-2 mb-4">
              <span className="text-lg">🦊</span> MetaMask Setup for Demo
            </h3>
            <div className="space-y-3">
              <div className="space-y-2 text-sm">
                {[
                  { step: "1", text: 'Open MetaMask → Networks → "Add Network"' },
                  { step: "2", text: "Network Name: Base Sepolia" },
                  { step: "3", text: "RPC URL: https://sepolia.base.org" },
                  { step: "4", text: "Chain ID: 84532" },
                  { step: "5", text: "Currency: ETH  |  Explorer: sepolia.basescan.org" },
                  { step: "6", text: 'Click "Add PAYTKN to MetaMask" button in User Wallet panel above' },
                ].map(s => (
                  <div key={s.step} className="flex gap-3 items-start">
                    <span className="w-5 h-5 rounded-full bg-gray-700 text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">{s.step}</span>
                    <span className="text-gray-400 text-xs leading-relaxed">{s.text}</span>
                  </div>
                ))}
              </div>

              <div className="bg-gray-800/60 rounded-xl p-3 space-y-2 mt-3">
                <p className="text-xs text-gray-500 uppercase tracking-wider">Contract addresses</p>
                {[
                  { label: "PAYTKN Token", addr: CONTRACT_ADDRESSES.token },
                  { label: "Treasury", addr: CONTRACT_ADDRESSES.treasury },
                  { label: "Staking", addr: CONTRACT_ADDRESSES.staking },
                ].map(c => (
                  <div key={c.label} className="flex justify-between items-center">
                    <span className="text-xs text-gray-400">{c.label}</span>
                    <a
                      href={`https://sepolia.basescan.org/address/${c.addr}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-mono text-xs text-indigo-400 hover:text-indigo-300"
                    >
                      {shortAddr(c.addr)} ↗
                    </a>
                  </div>
                ))}
              </div>

              {/* Second wallet tip */}
              <div className="bg-emerald-900/15 border border-emerald-800/30 rounded-lg px-3 py-3 mt-2">
                <p className="text-xs text-emerald-400 font-semibold mb-1">🎯 Two-wallet demo tip</p>
                <p className="text-xs text-gray-400 leading-relaxed">
                  In MetaMask click the account icon → "Add account" to create a second wallet. Use that address as the Merchant above. After paying, switch to account 2 to see the ETH arrive.
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* ── Operator wallet status ────────────────────────────────────────── */}
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5">
          <h3 className="font-bold text-white flex items-center gap-2 mb-3">
            <span className="text-lg">🤖</span> Backend Operator Wallet
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <p className="text-xs text-gray-500 mb-1">Address (has OPERATOR_ROLE)</p>
              <a
                href={`https://sepolia.basescan.org/address/${OPERATOR_ADDRESS}`}
                target="_blank"
                rel="noopener noreferrer"
                className="font-mono text-xs text-indigo-400 hover:text-indigo-300 break-all"
              >
                {OPERATOR_ADDRESS} ↗
              </a>
            </div>
            <div>
              <p className="text-xs text-gray-500 mb-1">ETH Balance</p>
              <p className={`font-mono text-sm font-bold ${operatorLow ? "text-amber-400" : "text-white"}`}>
                {fmt(operatorETH?.value, 6)} ETH
                {operatorLow && <span className="text-amber-400 text-xs ml-2">⚠️ Low</span>}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-500 mb-1">Role</p>
              <span className="text-xs bg-green-800/40 text-green-400 border border-green-700/40 px-2 py-0.5 rounded">
                OPERATOR_ROLE ✓
              </span>
            </div>
          </div>
          <p className="text-xs text-gray-500 mt-3">
            The backend relays every payment through this wallet. It needs sufficient ETH to cover gas (≈0.0001 ETH/tx) plus the payment amount. Add test funds via the faucets above.
          </p>
        </div>

      </div>
    </div>
  );
}
