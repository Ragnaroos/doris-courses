#!/usr/bin/env python3
"""Compare the images that the courses pull with the builds that were verified.

Usage (from the repository root):
    python3 tools/check_image_digests.py [--update]
    python3 tools/check_image_digests.py --offline [--root ROOT]

maintenance/images.md lists every image that the courses pull, by the exact tag
that the courses name, with the digest of the build that the last full run of the
courses used. The courses pull by tag, and a publisher can push a new build of the
same version under the same tag. This tool asks each image's registry, as an
anonymous client, which build the tag points to now: the digest of its
multi-platform index, as `docker pull` would get it. Nothing is downloaded. It
reports each image whose build changed, and each one that the registry no longer
has. Once the Labs that use the changed images have run with the new builds,
--update writes the new digests into the list; it also fills in the digest of a
row whose digest is `new`. Exits with status 1 when an image changed, is missing,
or could not be checked.

--offline needs no network, and CI runs it (with PyYAML installed). It checks that
the list is well formed, that it has every image that a Compose file or a
Dockerfile of the courses names (images that a course builds itself are not
pulled), and that wherever else the courses name a listed image, in a notebook,
a README, or a Python module, they name a tag that the list has. ROOT defaults to
this repository and must be a Git work tree; only files that Git tracks are read.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - depends on the local environment; only --offline needs it
    yaml = None

REPO = Path(__file__).resolve().parents[1]
RECORD = "maintenance/images.md"
ROW = re.compile(r"^\| `(?P<image>[^`]+)` \| (?P<used_by>.+?) \| (?P<digest>`sha256:[0-9a-f]{64}`|new) \|$")
IMAGE = re.compile(r"^(?:[a-z0-9.-]+(?::\d+)?/)?[a-z0-9._-]+(?:/[a-z0-9._-]+)*:[A-Za-z0-9_][A-Za-z0-9._-]*$")
COMPOSE_VARIABLE = re.compile(r"\$\{(\w+)(?::?-([^}]*))?\}")
ACCEPT = ", ".join((
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
))
TIMEOUT = 30


def read_record(root):
    """Return the rows of the image list as (line number, image, used by, digest or None)."""
    rows, problems = [], []
    lines = (root / RECORD).read_text(encoding="utf-8").splitlines()
    for number, line in enumerate(lines, start=1):
        if not line.startswith("| `"):
            continue
        match = ROW.match(line)
        if not match:
            problems.append(f"{RECORD}:{number}: a row must read | `image:tag` | used by | `sha256:<64 hex>` or new |")
            continue
        image, digest = match["image"], match["digest"].strip("`")
        if not IMAGE.match(image):
            problems.append(f"{RECORD}:{number}: {image} is not an image name with a tag")
        rows.append((number, image, match["used_by"], None if digest == "new" else digest))
    images = [image for _, image, _, _ in rows]
    for image in sorted({image for image in images if images.count(image) > 1}):
        problems.append(f"{RECORD}: {image} is listed more than once")
    if not rows:
        problems.append(f"{RECORD}: no images are listed")
    return rows, problems


def split_reference(image):
    """Split an image reference into its registry host, repository, and tag."""
    name, tag = image.rsplit(":", 1)
    first, _, rest = name.partition("/")
    if rest and ("." in first or ":" in first or first == "localhost"):
        return first, rest, tag
    return "registry-1.docker.io", name if "/" in name else f"library/{name}", tag


def anonymous_token(challenge, repository):
    """Get a pull token from the realm that a registry's Bearer challenge names."""
    scheme, _, parameters = challenge.partition(" ")
    if scheme.lower() != "bearer":
        raise RuntimeError(f"the registry asks for {challenge or 'an unknown kind of'} authentication")
    fields = dict(re.findall(r'(\w+)="([^"]*)"', parameters))
    fields.setdefault("scope", f"repository:{repository}:pull")
    query = urllib.parse.urlencode({key: fields[key] for key in ("service", "scope") if key in fields})
    with urllib.request.urlopen(f"{fields['realm']}?{query}", timeout=TIMEOUT) as response:
        body = json.load(response)
    return body.get("token") or body["access_token"]


def registry_digest(image):
    """Return the digest that the image's tag points to now, or None if the registry has no such tag."""
    host, repository, tag = split_reference(image)
    url = f"https://{host}/v2/{repository}/manifests/{tag}"
    headers = {"Accept": ACCEPT}
    digest = None
    for method in ("HEAD", "GET"):
        for attempt in range(3):
            request = urllib.request.Request(url, headers=headers, method=method)
            try:
                with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                    digest = response.headers.get("Docker-Content-Digest")
                    if digest or method == "HEAD":
                        break
                    # Without the header, the digest is the hash of the manifest as served.
                    return "sha256:" + hashlib.sha256(response.read()).hexdigest()
            except urllib.error.HTTPError as error:
                if error.code == 401 and "Authorization" not in headers:
                    headers["Authorization"] = "Bearer " + anonymous_token(
                        error.headers.get("WWW-Authenticate", ""), repository)
                    continue
                if error.code == 404:
                    return None
                raise
            except (urllib.error.URLError, TimeoutError):
                if attempt == 2:
                    raise
        if digest:
            return digest
    raise RuntimeError("the registry did not say which digest the tag points to")


def check_registries(root, fetch, update):
    rows, problems = read_record(root)
    for problem in problems:
        print(f"PROBLEM {problem}")
    if problems:
        return 1

    def ask(image):
        try:
            return fetch(image), None
        except Exception as error:  # report every image, whatever went wrong with one
            return None, f"{type(error).__name__}: {error}"

    with ThreadPoolExecutor(max_workers=6) as pool:
        answers = list(pool.map(ask, [image for _, image, _, _ in rows]))
    counts = {"same": 0, "changed": 0, "new": 0, "missing": 0, "error": 0}
    updates = {}
    for (number, image, used_by, recorded), (current, error) in zip(rows, answers):
        if error:
            counts["error"] += 1
            print(f"ERROR    {image}: {error}")
        elif current is None:
            counts["missing"] += 1
            print(f"MISSING  {image}: the registry has no such tag (used by {used_by})")
        elif recorded is None:
            counts["new"] += 1
            updates[number] = current
            print(f"NEW      {image}: the registry has {current}")
        elif current != recorded:
            counts["changed"] += 1
            updates[number] = current
            print(f"CHANGED  {image}: verified {recorded}, the registry now has {current} (used by {used_by})")
        else:
            counts["same"] += 1
    print(f"{len(rows)} image(s): " + ", ".join(f"{count} {name}" for name, count in counts.items()))
    if update and updates:
        path = root / RECORD
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        for number, digest in updates.items():
            line = lines[number - 1]
            cells = line.rstrip("\n").rsplit(" | ", 1)
            lines[number - 1] = f"{cells[0]} | `{digest}` |" + ("\n" if line.endswith("\n") else "")
        path.write_text("".join(lines), encoding="utf-8")
        print(f"Wrote {len(updates)} digest(s) to {RECORD}")
        return 1 if counts["missing"] or counts["error"] else 0
    return 0 if counts["same"] == len(rows) else 1


def tracked_files(root, directory):
    listing = subprocess.run(["git", "-C", str(root), "ls-files", "-z", directory], capture_output=True, check=True)
    return [root / name for name in listing.stdout.decode("utf-8").split("\0") if name]


def resolve(value):
    """Replace ${NAME:-default} in a Compose value with its default, as when NAME is not set."""
    return COMPOSE_VARIABLE.sub(lambda match: match.group(2) or "", value)


def pulled_images(path):
    """Return the images that a Compose file or a Dockerfile pulls."""
    text = path.read_text(encoding="utf-8")
    if path.name == "Dockerfile":
        return [resolve(image) for image in re.findall(r"^FROM\s+(?:--\S+\s+)*(\S+)", text, re.M)]

    class ComposeLoader(yaml.SafeLoader):
        """Reads Compose files with their !reset and !override merge tags."""

    ComposeLoader.add_multi_constructor("!", lambda loader, suffix, node: None)
    services = (yaml.load(text, Loader=ComposeLoader) or {}).get("services") or {}
    # A service that the course builds itself names the image that the build produces.
    return [resolve(service["image"]) for service in services.values()
            if isinstance(service, dict) and service.get("image") and "build" not in service]


def check_offline(root):
    if yaml is None:
        sys.exit("PyYAML is required for --offline: run this script with a course virtual environment, "
                 "or `python3 -m pip install -r tools/requirements.txt`.")
    rows, problems = read_record(root)
    listed = {image for _, image, _, _ in rows}
    files = tracked_files(root, "doris-course")
    for path in files:
        if path.name == "Dockerfile" or re.fullmatch(r"(?:docker-)?compose(?:\.[\w-]+)?\.ya?ml", path.name):
            for image in pulled_images(path):
                if image not in listed:
                    problems.append(f"{path.relative_to(root).as_posix()} pulls {image}, which {RECORD} does not list")
    tags = {}
    for image in listed:
        name, tag = image.rsplit(":", 1)
        tags.setdefault(name, set()).add(tag)
    if tags:
        # A listed repository followed by a tag that looks like a version, such as haproxy:3.0-alpine.
        # The tag ends with a letter or digit; a full stop after it ends a sentence.
        mention = re.compile(r"(?<![\w./-])(" + "|".join(map(re.escape, sorted(tags, key=len, reverse=True)))
                             + r"):([A-Za-z0-9][A-Za-z0-9_-]*\.(?:[A-Za-z0-9._-]*[A-Za-z0-9_]))(?![\w*-])(?!\.\w)")
        for path in files:
            data = path.read_bytes()
            if b"\0" in data[:8192]:
                continue  # binary
            for number, line in enumerate(data.decode("utf-8", errors="replace").splitlines(), start=1):
                for match in mention.finditer(line):
                    if match.group(2) not in tags[match.group(1)]:
                        problems.append(f"{path.relative_to(root).as_posix()}:{number} names {match.group(0)}, "
                                        f"which {RECORD} does not list")
    for problem in problems:
        print(f"PROBLEM {problem}")
    print(f"{len(rows)} image(s) listed, {len(problems)} problem(s)")
    return 1 if problems else 0


def main(argv=None, fetch=registry_digest):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--offline", action="store_true", help="check the list against the courses, without the network")
    parser.add_argument("--update", action="store_true", help="write the registries' digests into the list")
    parser.add_argument("--root", type=Path, default=REPO, help="the repository; this one by default")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if args.offline:
        if args.update:
            parser.error("--update needs the registries; leave out --offline")
        return check_offline(root)
    return check_registries(root, fetch, args.update)


if __name__ == "__main__":
    sys.exit(main())
