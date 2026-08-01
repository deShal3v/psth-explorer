#!/usr/bin/env python3
"""Threaded static server for the Neural Spiking Explorer.
Serves <file> from <file>.gz with Content-Encoding: gzip when present and the
client accepts gzip (so the 83 MB cube ships as ~12 MB). Everything else normal.
"""
import os, sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = sys.argv[2] if len(sys.argv) > 2 else "/home/ubuntu/b/site"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8099

class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=ROOT, **k)
    def end_headers(self):
        # never let the browser cache the app itself, or edits appear to do nothing;
        # the big .u8.gz data files keep their long cache (set in do_GET)
        p = self.path.split('?', 1)[0]
        if p.endswith(('.html', '.js')) or p.endswith('/') or p == '':
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
        super().end_headers()
    def do_GET(self):
        rel = self.path.split('?', 1)[0].lstrip('/')
        fpath = os.path.join(ROOT, rel)
        gz = fpath + '.gz'
        accepts = 'gzip' in self.headers.get('Accept-Encoding', '')
        if os.path.isfile(gz) and accepts:
            data = open(gz, 'rb').read()
            ctype = self.guess_type(fpath)
            self.send_response(200)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Encoding', 'gzip')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'public, max-age=86400')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(data)
            return
        return super().do_GET()
    def log_message(self, *a): pass

if __name__ == '__main__':
    print(f"serving {ROOT} on 127.0.0.1:{PORT} (gzip sidecars enabled)")
    ThreadingHTTPServer(('127.0.0.1', PORT), H).serve_forever()
