"""Serve the TechMart static store on port 3001."""
import http.server, socketserver, os

PORT = 3001
os.chdir(os.path.dirname(os.path.abspath(__file__)))

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[STORE] {self.address_string()} — {fmt % args}")

print(f"[STORE] TechMart running at http://localhost:{PORT}")
with socketserver.TCPServer(("", PORT), Handler) as httpd:
    httpd.serve_forever()
