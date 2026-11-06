#
# partcad-grabcad, 2026
#
# Licensed under Apache License, Version 2.0.
#
"""A PartCAD 'basic' repository plugin that serves GrabCAD Library models as parts.

Published as ``//pub/collection/grabcad/models``. Nothing is listed: a part is
asked for by the model's slug (the last part of grabcad.com/library/<slug>), and
is one file of that model.

    nema-17-stepper-motor-23                  the model's best file (see remote_models.FORMATS)
    nema-17-stepper-motor-23;format=stl       its best STL
    nema-17-stepper-motor-23;file=nema17.step one of its files, by name

GrabCAD has no public API. What this reads is the JSON its library's own pages
read, under /community/api/v1: a model's details, its files folder by folder,
and the library's search, which anyone may. Downloading a file takes a signed-in
GrabCAD account - its '_grabcad_session' cookie - given to the plugin as
GRABCAD_SESSION, or as the repository's 'session' parameter (see the README).

GrabCAD's CDN has been known to turn away clients that are not browsers. This
plugin says what it is in its User-Agent and does not pretend otherwise; when it
is turned away, it says so.

PartCAD runs this script once per key (via runpy) with the key in
``request["key"]``; the answer goes in ``output``. What the keys mean, and
everything else that is the same for every model site, is in remote_models.py.
"""

import importlib.util
import os
import re
import sys
import urllib.parse

# When this plugin's answers stopped meaning what they meant before. PartCAD
# keys everything it caches of this package on it, so raise it with any change
# to what is answered - here or in remote_models.py.
#
# v1: library models as parts, one per file, read through /community/api/v1; and 'login'.
# v2: a part's 'source' parameter, and the plugin's 'formats' and 'source' preferences;
#     'login' says what to do with nobody at the screen.
CACHE_VERSION = 2


def _shared():
    """remote_models.py, beside this script, under a name of this plugin's own."""
    name = "_partcad_grabcad_remote_models"
    if name not in sys.modules:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "remote_models.py")
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


rm = _shared()

WEB = "https://grabcad.com"
API = WEB + "/community/api/v1"
SESSION_COOKIE = "_grabcad_session"

# A model's files are in folders, and an assembly's parts can be spread over a
# few levels of them. A bound, so that a model with a great many cannot run on.
_MAX_FOLDERS = 40

# What a slug is: all a model is known by, and it can start with a dash.
_SLUG = re.compile(r"^[a-z0-9_-]{1,200}$", re.IGNORECASE)


def model_url(slug):
    return "%s/library/%s" % (WEB, slug)


class GrabCAD(rm.Site):
    NAME = "grabcad"
    TITLE = "GrabCAD"
    URL = WEB + "/library"
    DESC = "Models in the GrabCAD Library, a part per file, by the model's slug. Nothing is listed; search instead."
    VERSION = CACHE_VERSION
    LOGIN_INSTRUCTIONS = (
        "Reading a model and searching GrabCAD need no login; downloading any of its files does. GrabCAD has no API "
        "keys: what is needed is the '_grabcad_session' cookie of grabcad.com, from a browser signed in to GrabCAD: "
        "the browser's developer tools show it, under Application (or Storage) > Cookies."
    )

    def __init__(self, request=None):
        super().__init__(request)
        session = rm.credential(self.request, "session", "GRABCAD_SESSION")
        # The cookie's value, or a whole Cookie header pasted from a browser.
        self.cookie = session if "=" in session else ("%s=%s" % (SESSION_COOKIE, session) if session else "")

    def valid_id(self, model_id):
        return bool(_SLUG.match(model_id))

    CREDENTIALS = {"session": "GRABCAD_SESSION"}

    def credentials_from(self, captured):
        # The cookie's value, which is what the parameter holds.
        return {"session": str(captured.get("session") or "").strip()}

    @staticmethod
    def _cookie(session):
        return session if "=" in session else "%s=%s" % (SESSION_COOKIE, session)

    # -- logging in --

    def whoami(self, credentials):
        session = credentials.get("session")
        if not session:
            return None
        # The library's own question: who is this? A visitor is answered 204.
        status, me = self.http.probe(
            API + "/members/me", "who the GrabCAD session is", headers={"Cookie": self._cookie(session)}
        )
        if status in (204, 401, 403):
            return None
        member = (me or {}).get("member") if isinstance(me, dict) else None
        if status != 200 or not isinstance(member, dict):
            raise rm.SiteError("grabcad: asking who the session is answered HTTP %d" % status)
        return member.get("name") or member.get("cached_slug") or "a GrabCAD member"

    def login_spec(self):
        # Every visitor has a session cookie, signed in or not, so the cookie
        # alone says nothing: the capture waits until the library's 'who am I'
        # answers the browser's own session with somebody.
        return {
            "url": "https://grabcad.com/login",
            "title": "GrabCAD",
            "capture": [{"name": "session", "cookie": {"url": "https://grabcad.com/", "name": SESSION_COOKIE}}],
            "done_when": {"fetch": {"url": API + "/members/me", "status": 200}},
            "guide": [
                {
                    "url": "https://grabcad.com/login*",
                    "selector": "input[type=email], input[name*=email], input[type=text]",
                    "text": "Sign in to GrabCAD",
                },
                {
                    "url": "https://grabcad.com/*",
                    "selector": "a[href*='/login']",
                    "text": "Sign in to GrabCAD",
                },
            ],
        }

    def usable(self, file):
        return bool(self.cookie)

    def model(self, model_id):
        slug = model_id.lower()
        quoted = urllib.parse.quote(slug, safe="")
        details = self.http.json("%s/models/%s?extended=true" % (API, quoted), "model %s" % slug)
        if not isinstance(details, dict) or not details.get("cached_slug"):
            raise rm.NotFound("grabcad: model %s: not found" % slug)
        return rm.Model(
            slug,
            title=details.get("name"),
            url=model_url(slug),
            author=(details.get("author") or {}).get("name"),
            files=self._files(slug),
        )

    def _files(self, slug):
        """Every file of a model, folder by folder, as the library's own files tab reads them."""
        quoted = urllib.parse.quote(slug, safe="")
        files, queue, seen, names = [], [None], set(), {}
        while queue and len(seen) < _MAX_FOLDERS:
            folder = queue.pop(0)
            url = "%s/models/%s/files" % (API, quoted)
            if folder is not None:
                url += "?" + urllib.parse.urlencode({"folder_id": folder})
            answer = self.http.json(url, "the files of model %s" % slug)
            seen.add(folder)
            if not isinstance(answer, dict):
                break
            for entry in answer.get("files") or []:
                name = (entry or {}).get("name")
                link = (entry or {}).get("download_url")
                if not name or not link or not self._is_api_link(link):
                    continue
                # A name is what a file is asked for by, so two of the same
                # name in different folders are told apart by a count.
                names[name] = names.get(name, 0) + 1
                key = name if names[name] == 1 else "%s#%d" % (name, names[name])
                files.append(rm.File(key, name, system=entry.get("system"), download_url=link))
            for sub in answer.get("folders") or []:
                sub_id = (sub or {}).get("id")
                if sub_id is not None and sub_id not in seen:
                    queue.append(sub_id)
        return files

    @staticmethod
    def _is_api_link(link):
        """Only the API's own download links are asked for, with the user's sign-in."""
        parts = urllib.parse.urlsplit(link)
        return (
            parts.scheme == "https"
            and parts.netloc == "grabcad.com"
            and parts.path.startswith("/community/api/v1/models/")
        )

    def download(self, model, file):
        what = "%s of model %s" % (file.name, model.id)
        if not self.cookie:
            raise rm.NeedsCredentials(
                "grabcad: %s takes a signed-in GrabCAD account: set GRABCAD_SESSION to the "
                "'%s' cookie of a signed-in browser, or the 'session' parameter of the repository "
                "(see the README)" % (what, SESSION_COOKIE)
            )
        headers = {"Cookie": self.cookie}
        answer = self.http.json(file.extra["download_url"], what, headers=headers, ttl=0)
        link = answer.get("url") if isinstance(answer, dict) else None
        if not link:
            raise rm.SiteError("grabcad: %s was not handed over" % what)
        same_site = urllib.parse.urlsplit(link).netloc in ("grabcad.com", "")
        data = self.http.download(urllib.parse.urljoin(WEB, link), what, headers=headers if same_site else None)
        if rm.is_zip(data) and not file.name.lower().endswith(".zip"):
            member = rm.read_zip_member(data, file.name)
            if member is not None:
                return member
        return data

    def search(self, text, limit):
        # The library's search, as its own page asks it. Undocumented: the
        # answer is checked against the words asked for (see below).
        answer = self.http.json(
            API + "/models",
            "a search for '%s'" % text,
            data={"query": text, "page": 1, "per_page": limit},
            ttl=600,
        )
        words = [w for w in re.split(r"\W+", text.lower()) if w]
        models = []
        hits = answer.get("models") if isinstance(answer, dict) else None
        for hit in hits or []:
            if not isinstance(hit, dict):
                continue
            slug = str(hit.get("cached_slug") or "").lower()
            if not slug:
                continue
            title = hit.get("name") or slug
            # Were the query not what the library searched by, this would be
            # its most downloaded models, whatever was asked. A hit that has
            # none of the words in its name or slug is not trusted as one.
            haystack = (title + " " + slug).lower()
            if words and not any(w in haystack for w in words):
                continue
            models.append(
                rm.Model(slug, title=title, url=model_url(slug), author=(hit.get("author") or {}).get("name"))
            )
        return models


def get(key):
    return rm.serve(GrabCAD(globals().get("request")), key)


# Last, so that everything above is defined when PartCAD runs this.
if __name__ == "get":
    output = {"result": get(request["key"])}  # noqa: F821 - injected by the runtime
elif __name__ == "login":
    output = {"result": rm.login(GrabCAD(globals().get("request")), globals().get("partcad_login"))}
else:
    output = {}
