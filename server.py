#!/usr/bin/env python3
"""Карта + общие отметки «закрыто». Запуск: SURF_PASS=пароль python3 server.py [порт]
Отдаёт эту папку и API /api/closed (GET открыт, POST только с паролем)."""
import hmac, json, os, sys, threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = HERE  # index.html лежит рядом с server.py
DB = os.path.join(HERE, "closed.json")
NOTES = os.path.join(HERE, "notes.json")
PASS = os.environ.get("SURF_PASS", "")
lock = threading.Lock()


def load(path=DB):
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=SITE, **k)

    def _json(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def _auth(self):
        return hmac.compare_digest(self.headers.get("X-Pass", ""), PASS)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/closed":
            return self._json(200, load())
        if path == "/api/notes":
            if not self._auth():
                return self._json(403, {"error": "bad password"})
            return self._json(200, sorted(load(NOTES).values(), key=lambda n: -n["t"]))
        super().do_GET()

    def _save(self, path, db):
        tmp = path + ".tmp"
        json.dump(db, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
        os.replace(tmp, path)

    def _notes_post(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n > 20000:
                raise ValueError
            d = json.loads(self.rfile.read(n))
            if d["op"] == "del":
                note_id, note = d["id"], None
            else:
                x = d["note"]
                note_id = x["id"]
                note = {"id": note_id, "t": float(x["t"]), "text": x["text"],
                        "lat": x.get("lat"), "lon": x.get("lon")}
                if not isinstance(note["text"], str) or len(note["text"]) > 5000:
                    raise ValueError
                if any(v is not None and not isinstance(v, (int, float)) for v in (note["lat"], note["lon"])):
                    raise ValueError
            if not isinstance(note_id, str) or not 0 < len(note_id) <= 64:
                raise ValueError
        except (ValueError, KeyError, TypeError):
            return self._json(400, {"error": "bad request"})
        with lock:
            db = load(NOTES)
            if note is None:
                db.pop(note_id, None)
            elif note_id in db or len(db) < 5000:
                db[note_id] = note
            else:
                return self._json(400, {"error": "too many notes"})
            self._save(NOTES, db)
        self._json(200, {"ok": True})

    def do_POST(self):
        if self.path not in ("/api/closed", "/api/notes"):
            return self._json(404, {})
        if not self._auth():
            return self._json(403, {"error": "bad password"})
        if self.path == "/api/notes":
            return self._notes_post()
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n > 2000:
                raise ValueError
            d = json.loads(self.rfile.read(n))
            key, flag = d["key"], bool(d["closed"])
            if not isinstance(key, str) or not 0 < len(key) <= 200:
                raise ValueError
        except (ValueError, KeyError, TypeError):
            return self._json(400, {"error": "bad request"})
        with lock:
            db = load()
            if flag:
                db[key] = True
            else:
                db.pop(key, None)
            self._save(DB, db)
        self._json(200, db)


if __name__ == "__main__":
    if not PASS:
        sys.exit("Задайте пароль: SURF_PASS=... python3 server.py")
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    print(f"http://0.0.0.0:{port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
