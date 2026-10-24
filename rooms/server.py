"""Tiny HTTP server on port 9000 so a room is a reachable target for the reachability probes."""
from http.server import BaseHTTPRequestHandler, HTTPServer


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


HTTPServer(("0.0.0.0", 9000), H).serve_forever()
