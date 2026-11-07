# GrabCAD for PartCAD

Serves GrabCAD's models as PartCAD parts, published as
`//pub/universe/grabcad/models`.

**Nothing is listed.** A model site's catalog is not something to enumerate,
so `pc list parts` of this package is empty, as is `pc list packages`. A part is
asked for by name, and found with `pc search parts`:

```shell
pc search parts -P //pub/universe/grabcad/models -k "cable clip"
pc inspect "//pub/universe/grabcad/models:nema-17-6"
```

**No geometry is vendored.** Every file is fetched from GrabCAD the first
time a part is built, and kept by PartCAD from then on.

**Nothing here is manufacturable.** The package says `manufacturable: false`,
and so does the plugin of what it serves: an upload to a model site says
nothing about whether, or how, it is made to be made.

Requires PartCAD 0.9.3 or newer: the first release whose repository plugins
may search their own catalog (`searchKinds`), resolve a parametrized name
themselves (`instanceKinds`), and log in (`pc login`). They are described under
"Repositories" and "Logging in" in PartCAD's plugin documentation.

## Names

A model is a part per file of it that PartCAD reads, and the name says which.
A model is named by the model's slug, as in `grabcad.com/library/nema-17-6`:

| Name | Is |
| --- | --- |
| `nema-17-6` | the model's best file |
| `nema-17-6;format=stl` | its best STL |
| `nema-17-6;file=<name>` | one file, by its name (`<name>#2` for the second of that name, in another folder) |

Both may be given, and must then agree; a third, `source`, and the plugin's
own `formats` are under [Parameters](#parameters). "Best" is by format, in
this order unless `formats` says otherwise, and among files of one format the first the site lists:

| Format | Read as PartCAD part type | Extensions |
| --- | --- | --- |
| `step` | `step` | `.step`, `.stp` |
| `brep` | `brep` | `.brep`, `.brp` |
| `3mf` | `3mf` | `.3mf` |
| `stl` | `stl` | `.stl` |
| `obj` | `obj` | `.obj` |
| `glb` | `gltf` | `.glb` |
| `scad` | `scad` | `.scad` |

An exact boundary representation beats a mesh of it, and 3MF knows its units
where STL does not. A `.gltf` is not served, since the buffers it names beside
itself do not come with it; an OpenSCAD source is last, because on a model site
it is usually the customizable source of the meshes beside it. A file in any
other format - IGES, SolidWorks, Fusion, a picture - is not a part. A name
that asks for one, or for a file the model has not got, is not found, and the
plugin says why.

These names are resolved by the plugin rather than by PartCAD applying the
parameters to a base part, because another file is another `path` and maybe
another `type`. `pc info` of a part shows the `file` and `format` it resolved
to, which is what to write to pin it: the best file of a model can change when
its designer uploads another.

## Search

`pc search parts -k <words>` asks GrabCAD's own search, and answers with
names of the form above - one per file, so a hit is everything needed to fetch
its geometry. Two files that differ only in their extension (`clip.step`,
`clip.stl`) are one part in two formats, and only the better is named; a model
with no file PartCAD reads is not a hit. `--limit` caps the hits (20 by
default); the plugin asks the site for three times as many models, and reads
their file lists a few at a time until it has enough.

A search is never cached by PartCAD; the plugin keeps what the site answered for
ten minutes.

## Logging in

```shell
pc login //pub/universe/grabcad:grabcad_repo
```

checks the session the plugin has by asking the library whom it belongs to
(`/community/api/v1/members/me`, which answers a visitor with nothing), and
keeps it if GrabCAD still takes it. Otherwise it opens your default browser, in
PartCAD's own profile with PartCAD's extension in it, on GrabCAD's sign-in. Sign
in there. Every visitor has a `_grabcad_session` cookie, signed in or not, so
the extension waits until the same question, asked from the browser with its
own session, answers with somebody - and then takes the cookie and closes the
window. It is saved in your `~/.partcad/config.yaml` as your override of the
repository's `session` parameter. `pc login --check ...` only checks it.

## Credentials, by hand

GrabCAD has no public API. What this reads is the JSON its library's own pages
read, under `/community/api/v1`: a model's details, its files folder by folder,
and the library's search, which anyone may. Downloading a file takes a signed-in
GrabCAD account - its `_grabcad_session` cookie. Copy the cookie's value from a
browser signed in to grabcad.com (or the whole `Cookie` header), and give it to
the plugin either way, never in a package:

```shell
export GRABCAD_SESSION=...        # read by the plugin; see the note on Docker below
```

```yaml
# ~/.partcad/config.yaml
parameters:
  "//pub/universe/grabcad:grabcad_repo":
    session: "..."
```

A session lasts as long as GrabCAD keeps it: when downloads start to say the
sign-in is wanted again, copy a new one. The cookie is sent to `grabcad.com`,
and to nothing else.

Reading models and searching need no session, so a part can be named, and
`pc info` of it answered, without one; only building it fetches the file.

**Docker.** PartCAD runs a plugin in its Python sandbox, and the `docker` sandbox
does not carry PartCAD's environment into its container, so an environment
variable does not reach the plugin there. The repository parameter does, being
part of what PartCAD hands the plugin; use that, or `pythonSandbox: venv`.

## Parameters

The plugin's parameters, declared in `partcad.yaml`, are a default for every
GrabCAD part:

| Parameter | Default | What it is |
| --- | --- | --- |
| `formats` | all, in the order above | The formats to take a model in, best first, separated by commas. A format left out is not taken - `stl,3mf` is meshes only - unless a part asks for it by its own `format` or `file`. |
| `source` | `auto` | Which of a model's files: GrabCAD has no preview meshes of its own, so `auto` and `original` are the same here and `preview` finds nothing. |
| `session` | empty | The `_grabcad_session` cookie of a browser signed in to GrabCAD. Downloading a file needs it; reading a model and searching do not. GrabCAD has no API keys. `GRABCAD_SESSION` gives it too. |

They are yours to set without touching this package - every one of them, the
credentials included, and the OAuth or API-key settings beside them:

- in your own `~/.partcad/config.yaml`, by the plugin's name, which is where
  `pc login` keeps the credentials:

  ```yaml
  parameters:
    "//pub/universe/grabcad:grabcad_repo":
      formats: stl,3mf
  ```

- or, for anything but the credentials, in a package of your own, as an enrich
  of the plugin and a package it serves - `//grabcad_meshes:<model>` in a
  package at the root:

  ```yaml
  repositories:
    meshes_repo:
      type: enrich
      source: //pub/universe/grabcad:grabcad_repo
      with:
        formats: stl,3mf
  dependencies:
    grabcad_meshes:
      type: external
      plugin: :meshes_repo
  ```

A part's own `file`, `format` and `source` override them for that part - in its
name (`nema-17-stepper-motor-23;format=stl`), or in the `with` of an enrich of the part:

```yaml
parts:
  clip:
    type: enrich
    source: //pub/universe/grabcad/models:nema-17-stepper-motor-23
    with:
      format: stl
```

PartCAD keys what it caches of this package on your overrides of the plugin's
parameters, so a change to one - logging in, too - takes effect at once. An
environment variable is not seen there: after setting one, `pc update`
refreshes what was cached without it.

## Logging in with nobody at the screen

An AI agent, or a script, logs in without a browser:

```shell
pc login --agent //pub/universe/grabcad:grabcad_repo
pc login --agent --set session=... //pub/universe/grabcad:grabcad_repo
```

The first prints what a person would do in the browser instead of opening one -
where to sign in, what to copy, and the command that hands it over - and exits
with status 3. It says where in a signed-in browser the session cookie is. The second hands over what the person found; the
plugin checks it with GrabCAD before PartCAD keeps it. `pc mcp`'s `login`
tool works the same way.

## Status

Run against the live site with PartCAD: model details, file lists (folders
included) and search all answer this plugin, and `pc search parts -k "nema 17"`
names STEP and STL files of the models it finds. Downloading was not run, for
want of a session: the plugin asks the file's API link with the cookie, expects
`{"url": ...}` back - where the file is, on GrabCAD's own host - and fetches it
from there with the cookie.

GrabCAD's CDN has been known to turn away clients that are not browsers. This
plugin says what it is in its User-Agent (`PartCAD-grabcad`) and does not pretend
otherwise; should GrabCAD turn it away, it says so, and that is where it stops.

The search is undocumented, so its answer is checked: a model that has none of
the words asked for in its name is not taken as a hit, which is what would
happen were the query not what the library searched by.

PartCAD does not read IGES, and a great many GrabCAD models are STEP and IGES,
or SolidWorks only. Those with an IGES file and no STEP are not parts here yet.

`pc login` was run against the live site in a real (headed) Chrome with
PartCAD's extension: GrabCAD's sign-in page loads, the e-mail field is
spotlighted with the guide's pointer, and the extension waits, as it should,
for `/members/me` to answer for a signed-in member before it takes the
session cookie. Signing in itself was not done, for want of an account.

## Layout

| Path | Purpose |
| --- | --- |
| `partcad.yaml` | `//pub/universe/grabcad`; the `models` external dependency and the `grabcad_repo` repository that serves it. |
| `grabcad_repo.py` | The repository plugin: how GrabCAD is asked. |
| `remote_models.py` | What every model-site plugin shares, byte for byte: the names, the formats, HTTP and its cache, the keys PartCAD asks. The same file is in every model-site plugin (partcad-repo-thingiverse, -makerworld, -grabcad, -printables, -cults3d and -sketchfab); `remote_models.sha256` is its digest, and a test fails when the two disagree - change it in all of them. |
| `test_*.py` | The tests. Nothing in them touches the network. |

```shell
python -m pytest
```

When what the plugin answers changes - here or in `remote_models.py` - raise
`CACHE_VERSION` in `grabcad_repo.py`: PartCAD keys everything it caches of this
package on it.

## Caching

PartCAD keeps every answer the plugin gives, files included, under its own
cache, apart from a search. The plugin keeps what GrabCAD answered under
`~/.cache/partcad-grabcad/` (or `$PARTCAD_GRABCAD_CACHE`): a model's details for
a day, a search for ten minutes, and a request that came to nothing for a while
too, so that a refused or throttled run is not repeated in full by the next one
- a 404 for a day, anything else for five minutes. Delete the directory to start
over.

Every request says what it is: `User-Agent: Mozilla/5.0 (compatible;
PartCAD-grabcad/<version>; +https://github.com/partcad/partcad-repo-grabcad)`.

## Licensing

The code here is Apache-2.0 (`LICENSE`). GrabCAD Library models are offered under GrabCAD's terms of use rather than a licence per model; read them before you use one for anything but your own work. GrabCAD's terms of use
are at <https://grabcad.com/terms>.
