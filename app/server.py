"""app/server.py: serves the replay page and the narrated matches.

  python -m app.server            then open http://localhost:8000
  PORT=8080 python -m app.server  another port (Azure Container Apps sets PORT)

It serves the page (app/web/) and the match files (data/*.json). It calls no model: the judges'
site replays matches that were narrated beforehand, so testing it costs nothing.

/api/tracking?seed=N gives the 1 Hz positions of the ball and all 22 players for match seed N
(only seeds of the matches in data/),
made again from the seed by the generator (it is deterministic), for the "All players" view.
"""
import gzip
import json
import os
from functools import lru_cache
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB, DATA = ROOT / "app" / "web", ROOT / "data"


@lru_cache(maxsize=4)
def tracking(seed: int) -> bytes:
    """Compact tracking for one seed, gzip-compressed JSON.

    players: the 22 players in a fixed order. officials: referee, two assistants, fourth official.
    frames: one per second; each frame is [ball x, ball y, x, y for each player, x, y for each
    official], in decimetres (whole numbers) to keep it small. Officials can be just off the pitch.
    possession: one letter per second, h or a: the team on the ball.
    through: every through ball, with the second just before the pass (the frame to judge offside at).
    """
    import bisect
    import math
    from sixth.generate import generate_match, next_team
    from sixth.roster import CLUBS, PLAYERS
    match = generate_match(seed)
    rows, events = match["physical_log"], match["event_log"]
    order = [p["player_id"] for p in rows[0]["players"]]
    from sixth.generate import ball_path, ball_touches
    _, flights = ball_path(events)
    sent_off = {e["player_id"]: e["match_clock_s"] for e in events if e["type"] == "foul" and e.get("card") == "red"}
    from sixth.formations import team_sheet
    sheet = team_sheet(match)
    players = [{"id": pid, "name": PLAYERS.get(pid, pid), "team": "home" if pid[0] == "h" else "away",
                "number": sheet[pid]["number"], "position": sheet[pid]["position"], "goalkeeper": pid[1:] == "01",
                "sent_off_s": sent_off.get(pid)}
               for pid in order]
    officials = [{"id": o["official_id"], "role": o["role"]} for o in rows[0].get("officials", [])]
    frames = []
    for r in rows:
        by_id = {p["player_id"]: p for p in r["players"]}
        f = [round(r["ball"]["x_m"] * 10), round(r["ball"]["y_m"] * 10)]
        for pid in order:
            f += [round(by_id[pid]["x_m"] * 10), round(by_id[pid]["y_m"] * 10)]
        for o in r.get("officials", []):
            f += [round(o["x_m"] * 10), round(o["y_m"] * 10)]
        frames.append(f)
    times, after, team = [], [], "home"
    for e in events:
        team = next_team(e, team)
        times.append(e["match_clock_s"])
        after.append(team)
    possession = "".join(
        (after[i] if (i := bisect.bisect_right(times, ts) - 1) >= 0 else "home")[0] for ts in range(len(rows)))
    offside_for = {e["related_event_id"] for e in events if e["type"] == "offside"}
    through = []
    for e in events:
        if e["type"] == "pass" and e.get("pass_type") == "through":
            outcome = "offside" if e["event_id"] in offside_for else ("complete" if e["outcome"] == "success" else "intercepted")
            through.append({"event_id": e["event_id"], "t": e["match_clock_s"], "frame": int(math.floor(e["match_clock_s"])),
                            "team": e["team_id"], "passer": PLAYERS.get(e["player_id"], e["player_id"]),
                            "receiver": PLAYERS.get(e["receiver_id"], e["receiver_id"]),
                            "receiver_slot": order.index(e["receiver_id"]), "outcome": outcome,
                            "end": [e["end_x_m"], e["end_y_m"]]})
    from sixth import formations as F
    shape = F.analyse(match)                      # per team, per 15-minute block, without / with the ball
    expected = {name: {"out": F.expected_label(name, False), "in": F.expected_label(name, True)}
                for name in F.TEMPLATES}
    body = {"seed": seed, "hz": 1, "unit": "dm", "clubs": CLUBS, "players": players, "officials": officials,
            "frames": frames, "possession": possession, "through": through,
            "shape": shape, "expected_shape": expected,
            # v2: the ball in the air, [start s, end s, peak m, height at the end m]
            "flights": [[round(a, 1), round(b, 1), round(c, 1), round(d, 1)] for a, b, c, d in flights],
            # 2026-10-27: every touch of the ball at its exact time, [t, x m, y m, player slot or -1],
            # so the page can move the ball and the players between the 1 Hz frames (app/web/motion.js).
            "touches": ball_touches(events, order),
            "movement": movement(rows, order), "movement_fields": MOVEMENT_FIELDS, "movement_benchmarks": BENCHMARKS,
            "note": "Modelled positions: formations that move with the ball, runs timed to the passes, "
                    "and officials positioned as referees are taught to be."}
    return gzip.compress(json.dumps(body, separators=(",", ":")).encode(), compresslevel=6)


# Premier League means per match by position (Biology of Sport, 2019/20 and 2020/21 seasons:
# high-speed running above 19.8 km/h, sprinting above 25.2 km/h). Only the distance is compared on
# the page: the zones there are FIFA's (20 and 25 km/h), close to but not the same as these.
BENCHMARKS = {"defender": {"distance_m": [9966, 515], "hsr_m": [697, 275], "sprint_m": [151, 95], "top_mps": [9.63, 0.35]},
              "midfielder": {"distance_m": [11594, 622], "hsr_m": [992, 205], "sprint_m": [158, 80], "top_mps": [9.37, 0.43]},
              "forward": {"distance_m": [10710, 573], "hsr_m": [941, 182], "sprint_m": [202, 84], "top_mps": [9.83, 0.32]}}


# Speed zones in km/h, as in FIFA's World Cup physical reports (2026-10-26):
# walking 0-7, jogging 7-15, running 15-20, high-speed running 20-25, sprinting over 25.
ZONES_KMH = (7.0, 15.0, 20.0, 25.0)
MOVEMENT_FIELDS = ["distance_m", "walk_m", "jog_m", "run_m", "hsr_m", "sprint_m", "sprints", "top_kmh_x10"]


def movement(rows, order) -> dict:
    """Running per player, cumulative at the end of each minute (MOVEMENT_FIELDS): distance, the
    metres in each speed zone, sprints (a run of seconds over 25 km/h counts once) and top speed
    (km/h x 10). Speed is the distance moved in one second of the 1 Hz tracking."""
    import math
    acc = {pid: [0.0] * 8 for pid in order}
    out = {pid: [] for pid in order}
    prev, fast = {}, {pid: False for pid in order}
    for ts, r in enumerate(rows):
        for p in r["players"]:
            pid = p["player_id"]
            q = prev.get(pid)
            if q:
                v = math.hypot(p["x_m"] - q[0], p["y_m"] - q[1])
                kmh = v * 3.6
                a = acc[pid]
                a[0] += v
                zone = sum(kmh > z for z in ZONES_KMH)        # 0 walking ... 4 sprinting
                a[1 + zone] += v
                if zone == 4:
                    if not fast[pid]:
                        a[6] += 1
                    fast[pid] = True
                else:
                    fast[pid] = False
                a[7] = max(a[7], kmh)
            prev[pid] = (p["x_m"], p["y_m"])
        if ts % 60 == 0 or ts == len(rows) - 1:
            for pid in order:
                a = acc[pid]
                out[pid].append([round(a[0]), round(a[1]), round(a[2]), round(a[3]), round(a[4]), round(a[5]),
                                 int(a[6]), round(a[7] * 10)])
    return out


@lru_cache(maxsize=8)
def _seeds_of(files: tuple) -> frozenset:
    out = set()
    for name, _mtime in files:
        try:
            seed = json.loads((DATA / name).read_text(encoding="utf-8")).get("seed")
        except (OSError, ValueError):
            seed = None
        if not isinstance(seed, int):   # no seed field: take it from the name, match-<seed>-<kind>.json
            part = name.split("-")[1] if name.count("-") >= 1 else ""
            seed = int(part) if part.isdigit() else None
        if seed is not None:
            out.add(seed)
    return frozenset(out)


def published_seeds() -> frozenset:
    """Seeds of the narrated matches in data/. Added 2026-10-27: tracking is made only for these,
    so a stranger cannot make the server generate matches for any seed (CPU and memory)."""
    files = tuple(sorted((p.name, p.stat().st_mtime) for p in DATA.glob("match-*.json")))
    return _seeds_of(files)


def matches() -> list[str]:
    """Narrated matches, the Foundry ones first, newest first."""
    files = sorted(DATA.glob("match-*.json"), key=lambda p: ("foundry" not in p.name, -p.stat().st_mtime))
    return [p.name for p in files]


class Handler(SimpleHTTPRequestHandler):
    # The page's own fonts (app/web/fonts) and scripts: set the types, so no system table is needed.
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".woff2": "font/woff2", ".js": "text/javascript"}

    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(WEB), **k)

    def log_message(self, fmt, *args):
        pass

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def _json(self, code: int, obj) -> None:
        body = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/matches":
            body = json.dumps(matches()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/tracking":
            from urllib.parse import parse_qs
            raw = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "").get("seed", [""])[0]
            if not raw.isdigit() or int(raw) > 1_000_000:
                self.send_error(400, "seed must be a whole number")
                return
            if int(raw) not in published_seeds():
                self.send_error(404, "no published match has this seed")
                return
            body = tracking(int(raw))
            if "gzip" in self.headers.get("Accept-Encoding", ""):
                self.send_response(200)
                self.send_header("Content-Encoding", "gzip")
            else:
                body = gzip.decompress(body)
                self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/healthz":
            body = b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(body)
            return
        if path.startswith("/data/"):
            name = Path(path[len("/data/"):]).name           # no folders: no path tricks
            f = DATA / name
            if f.suffix == ".json" and f.is_file():
                body = f.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_error(404)
            return
        super().do_GET()


class Server(ThreadingHTTPServer):
    """The HTTP server. A browser that leaves before its answer arrives (a reload, a closed tab, a
    new request that replaces an old one) is normal: it is not logged as an error (2026-10-26)."""
    daemon_threads = True

    def handle_error(self, request, client_address):
        import sys
        if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
            return
        super().handle_error(request, client_address)


def main():
    port = int(os.environ.get("PORT", "8000"))
    srv = Server(("0.0.0.0", port), Handler)
    print(f"Sixth Official: http://localhost:{port}  ({len(matches())} matches)", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
