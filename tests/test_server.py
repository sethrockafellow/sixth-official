"""The judges' site: it lists the matches, serves them, and refuses paths outside data/."""
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from app import server


@pytest.fixture(scope="module")
def base():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def get(url):
    with urllib.request.urlopen(url) as r:
        return r.status, r.read()


def test_page_and_health(base):
    assert get(base + "/")[0] == 200
    assert get(base + "/healthz")[1] == b"ok"


def test_matches_listed_and_served(base):
    names = json.loads(get(base + "/api/matches")[1])
    for n in names:
        status, body = get(base + "/data/" + n)
        assert status == 200 and json.loads(body)["comments"]


def test_no_paths_outside_data(base):
    for bad in ("/data/..%2fsixth%2fschema.py", "/data/../README.md", "/data/x.py"):
        with pytest.raises(urllib.error.HTTPError):
            get(base + bad)


def test_tracking_for_a_seed(base):
    """The ball, 22 players and 4 officials, once a second; players inside the pitch."""
    d = json.loads(get(base + "/api/tracking?seed=4")[1])
    assert len(d["players"]) == 22 and len(d["officials"]) == 4 and len(d["frames"]) == 5401
    assert all(len(f) == 2 + 44 + 8 for f in d["frames"])
    xs = [v for f in d["frames"] for v in f[0:46:2]]
    ys = [v for f in d["frames"] for v in f[1:46:2]]
    assert 0 <= min(xs) and max(xs) <= 1050 and 0 <= min(ys) and max(ys) <= 680
    assert len(d["possession"]) == 5401 and set(d["possession"]) <= {"h", "a"}
    assert d["through"] and {b["outcome"] for b in d["through"]} <= {"complete", "offside", "intercepted"}


def test_tracking_refuses_a_bad_seed(base):
    for bad in ("/api/tracking", "/api/tracking?seed=abc", "/api/tracking?seed=-1"):
        with pytest.raises(urllib.error.HTTPError):
            get(base + bad)



def test_page_files_served_with_their_types(base):
    """The glossary, the open fonts and three.js (the player camera) are served with the right types."""
    for path, kind in (("/glossary.html", "text/html"), ("/cam.js", "text/javascript"),
                       ("/fonts/atkinson-hyperlegible-latin-400-normal.woff2", "font/woff2"),
                       ("/vendor/three.min.js", "text/javascript")):
        with urllib.request.urlopen(base + path) as r:
            assert r.status == 200 and r.headers["Content-Type"].startswith(kind), path


def test_touches_follow_the_events(base):
    """Every touch of the ball at its exact time (for the smooth replay): sorted, with valid players,
    and on the pitch."""
    d = json.loads(get(base + "/api/tracking?seed=4")[1])
    t = d["touches"]
    assert len(t) > 2000
    assert all(a[0] <= b[0] for a, b in zip(t, t[1:]))
    assert all(-1 <= k[3] < len(d["players"]) for k in t)
    assert all(0.0 <= k[1] <= 105.0 and 0.0 <= k[2] <= 68.0 for k in t)


def test_tracking_only_for_published_seeds(base):
    """Added 2026-10-27: a seed with no match in data/ gets 404, so the server makes no new match."""
    try:
        urllib.request.urlopen(base + "/api/tracking?seed=999")
        assert False, "seed 999 should be refused"
    except urllib.error.HTTPError as e:
        assert e.code == 404
