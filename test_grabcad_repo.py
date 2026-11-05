#
# partcad-grabcad, 2026
#
# Licensed under Apache License, Version 2.0.
#
"""Tests of the GrabCAD plugin, with GrabCAD answered from a table.

The answers have the shape /community/api/v1 answers with - a model's details,
its files folder by folder, a download link's answer, the library's listing -
with values made up. Nothing here touches the network.
"""

import base64
import importlib.util
import json
import os
import runpy

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PLUGIN = os.path.join(_HERE, "grabcad_repo.py")
_SPEC = importlib.util.spec_from_file_location("grabcad_repo_under_test", _PLUGIN)
plugin = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(plugin)
rm = plugin.rm

API = "https://grabcad.com/community/api/v1"
SLUG = "nema-17-stepper-motor-23"


def _file(name, system, n):
    return {"name": name, "system": system, "download_url": "%s/models/%s/files/%d/download" % (API, SLUG, n)}


TABLE = {
    "%s/models/%s?extended=true"
    % (API, SLUG): (
        200,
        {"cached_slug": SLUG, "name": "NEMA 17 stepper motor", "author": {"name": "Bob", "cached_slug": "bob"}},
    ),
    "%s/models/%s/files"
    % (API, SLUG): (
        200,
        {
            "files": [
                _file("nema17.STEP", "STEP / IGES", 1),
                _file("nema17.igs", "STEP / IGES", 2),
                _file("nema17.SLDPRT", "SOLIDWORKS", 3),
                _file("render.jpg", "Rendering", 4),
                # A link that is not the API's own is never asked for.
                {"name": "elsewhere.stl", "download_url": "https://evil.example/elsewhere.stl"},
            ],
            "folders": [{"id": 42}],
        },
    ),
    "%s/models/%s/files?folder_id=42"
    % (API, SLUG): (
        200,
        {"files": [_file("nema17.stl", "STL", 5), _file("shaft.stl", "STL", 6)], "folders": [{"id": 42}]},
    ),
    "%s/models/%s/files/5/download" % (API, SLUG): (200, {"url": "https://grabcad.com/cads/files/5/nema17.stl"}),
    "https://grabcad.com/cads/files/5/nema17.stl": (200, b"solid nema17"),
}


class Wire:
    def __init__(self, table):
        self.table = dict(table)
        self.asked = []

    def __call__(self, url, headers=None, data=None, method=None, timeout=60):
        self.asked.append((url, dict(headers or {}), data))
        if url not in self.table:
            return rm.Response(404, {}, b"{}", url)
        status, body = self.table[url]
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        return rm.Response(status, {}, body, url)


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.setenv("PARTCAD_GRABCAD_CACHE", str(tmp_path))
    monkeypatch.delenv("GRABCAD_SESSION", raising=False)

    def make(session=""):
        made = plugin.GrabCAD({"parameters": {"session": session}})
        made.http.request = Wire(TABLE)
        return made

    return make


def test_a_model_is_its_best_file_from_any_folder(site):
    config = site("abc").get("objects/part/" + SLUG)
    assert config["type"] == "step"
    assert config["desc"] == "NEMA 17 stepper motor: nema17.STEP"
    assert config["url"] == "https://grabcad.com/library/" + SLUG
    assert config["author"] == "Bob"


def test_a_file_in_a_folder_is_named_by_its_name(site):
    assert site("abc").get("objects/part/%s;file=shaft.stl" % SLUG)["type"] == "stl"
    assert site("abc").get("objects/part/%s;format=stl" % SLUG)["desc"].endswith("nema17.stl")


def test_a_file_is_downloaded_with_the_session_and_only_from_grabcad(site):
    made = site("abc")
    config = made.get("objects/part/%s;file=nema17.stl" % SLUG)
    assert base64.b64decode(made.get("files/" + config["path"])) == b"solid nema17"
    downloads = [(url, headers.get("Cookie")) for url, headers, _ in made.http.request.asked if "download" in url]
    assert downloads == [("%s/models/%s/files/5/download" % (API, SLUG), "_grabcad_session=abc")]
    assert not any("evil.example" in url for url, _, _ in made.http.request.asked)


def test_a_whole_cookie_header_is_taken_as_it_is(site):
    assert site("_grabcad_session=abc; other=1").cookie == "_grabcad_session=abc; other=1"


def test_without_a_session_a_download_says_what_it_needs(site, capsys):
    made = site()
    config = made.get("objects/part/%s;file=nema17.stl" % SLUG)
    assert rm.serve(made, "files/" + config["path"]) is None
    assert "takes a signed-in GrabCAD account" in capsys.readouterr().err


def test_a_slug_that_cannot_be_one_costs_no_request(site, capsys):
    made = site()
    assert rm.serve(made, "objects/part/no spaces here") is None
    assert made.http.request.asked == []


def test_a_search_is_the_librarys_and_is_checked_against_the_words(site):
    made = site("abc")
    made.http.request.table[API + "/models"] = (
        200,
        {
            "models": [
                {"cached_slug": SLUG, "name": "NEMA 17 stepper motor", "author": {"name": "Bob"}},
                # Not about what was asked: a sort the query did not reach.
                {"cached_slug": "office-chair", "name": "Office chair"},
            ]
        },
    )
    hits = made.get("search/part?q=nema+17&limit=5")
    assert list(hits) == ["%s;file=nema17.STEP" % SLUG, "%s;file=shaft.stl" % SLUG]
    url, _, body = [a for a in made.http.request.asked if a[0] == API + "/models"][0]
    assert body == {"query": "nema 17", "page": 1, "per_page": 15}


def test_cloudfront_turning_it_away_is_said_plainly(site, capsys):
    made = site()
    made.http.request.table["%s/models/%s?extended=true" % (API, SLUG)] = (
        403,
        b"<H1>403 ERROR</H1>Request blocked. Generated by cloudfront (CloudFront)",
    )
    assert rm.serve(made, "objects/part/" + SLUG) is None
    assert "turned away by CloudFront" in capsys.readouterr().err


def test_partcad_runs_it_and_reads_the_answer_from_output():
    result = runpy.run_path(_PLUGIN, init_globals={"request": {"key": "meta", "parameters": {}}}, run_name="get")
    assert result["output"]["result"]["manufacturable"] is False


def test_the_shared_module_is_the_one_every_model_site_plugin_has():
    import hashlib

    with open(os.path.join(_HERE, "remote_models.py"), "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    with open(os.path.join(_HERE, "remote_models.sha256")) as f:
        assert digest == f.read().split()[0], "remote_models.py differs from the shared copy: update all five"


# --- logging in ----------------------------------------------------------------

ME = API + "/members/me"


def test_a_session_is_checked_by_asking_the_library_who_it_is(site):
    made = site()
    made.http.request.table[ME] = (200, {"member": {"cached_slug": "bob", "name": "Bob"}})
    assert made.whoami({"session": "abc"}) == "Bob"
    assert made.http.request.asked[-1][1] == {"Cookie": "_grabcad_session=abc"}
    made.http.request.table[ME] = (204, b"")
    assert made.whoami({"session": "visitor"}) is None


def test_a_visitors_session_is_not_taken_for_a_signed_in_one(site):
    """Every visitor has the cookie, so the capture waits for 'who am I' to answer somebody."""
    spec = site().login_spec()
    assert spec["capture"] == [
        {"name": "session", "cookie": {"url": "https://grabcad.com/", "name": "_grabcad_session"}}
    ]
    assert spec["done_when"] == {"fetch": {"url": ME, "status": 200}}
