/**
 * merchant-proxy.js
 *
 * Proxies localhost:3001 → localhost:3000 (pure Node built-ins, no deps).
 * MetaMask treats them as separate browser origins so different wallets
 * can be connected to each port simultaneously.
 *
 * WebSockets (Next.js HMR) are also proxied so hot-reload works on :3001.
 */

const http = require("http");
const net  = require("net");

const TARGET = 3000;
const PORT   = 3001;

// ── HTTP proxy ────────────────────────────────────────────────────────────────
const server = http.createServer((req, res) => {
  const opts = {
    hostname : "127.0.0.1",
    port     : TARGET,
    path     : req.url,
    method   : req.method,
    headers  : { ...req.headers, host: `localhost:${TARGET}` },
  };

  const proxy = http.request(opts, (upstream) => {
    res.writeHead(upstream.statusCode, upstream.headers);
    upstream.pipe(res, { end: true });
  });

  proxy.on("error", () => res.end());
  req.pipe(proxy, { end: true });
});

// ── WebSocket proxy (Next.js HMR / hot-reload) ────────────────────────────────
server.on("upgrade", (req, clientSocket, head) => {
  const conn = net.connect(TARGET, "127.0.0.1", () => {
    // Re-send the upgrade request to the real server
    const headers = Object.entries(req.headers)
      .map(([k, v]) => `${k}: ${v}`)
      .join("\r\n");
    conn.write(
      `GET ${req.url} HTTP/1.1\r\n${headers}\r\nhost: localhost:${TARGET}\r\n\r\n`
    );
    if (head && head.length) conn.write(head);
    conn.pipe(clientSocket);
    clientSocket.pipe(conn);
  });

  conn.on("error", () => clientSocket.destroy());
  clientSocket.on("error", () => conn.destroy());
});

// ── Start ─────────────────────────────────────────────────────────────────────
server.listen(PORT, () => {
  console.log("");
  console.log("  🏪  Merchant proxy ready");
  console.log(`  →   localhost:${PORT}  proxies to  localhost:${TARGET}`);
  console.log(`  →   Open: http://localhost:${PORT}/merchant`);
  console.log("");
});
