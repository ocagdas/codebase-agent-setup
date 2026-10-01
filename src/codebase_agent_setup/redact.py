"""Remove secrets from captured files.

There is no option to keep them. A capsule is meant to be copied between machines,
attached to an issue and committed by mistake, so the only safe default is that it
never contains a credential. Every removal is returned so the caller can print it
and the owner knows exactly what to restore by hand.
"""

import json
import re
from typing import NamedTuple

PLACEHOLDER = "<redacted-by-cbsetup>"


class RedactionError(ValueError):
    pass


class Removal(NamedTuple):
    location: str  # A JSON path ("servers[0].api_key") or "line N" for plain text.
    reason: str  # Which rule matched, so the owner can judge a false positive.


# Key names whose value is a credential. Matched case-insensitively on word-ish boundaries.
SECRET_KEY = re.compile(
    r"(?:^|[_.\-])(?:token|secret|password|passwd|credential|credentials|apikey|api_key|access_key|"
    r"secret_key|private_key|authorization|auth_token|session|cookie|pat)(?:$|[_.\-])"
    r"|^(?:authorization|token|secret|password|apikey|api_key|pat)$",
    re.IGNORECASE,
)
# A key that names where a secret lives rather than holding one.
POINTER_KEY = re.compile(r"(?:_env|_var|_file|_path|_command|_ref|_name)$", re.IGNORECASE)
# A value that only points at a secret: an environment variable name or an expansion.
POINTER_VALUE = re.compile(r"^(?:\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|[A-Z][A-Z0-9_]{2,}|~?[/.][^\s]*)$")
# Value shapes that are credentials wherever they appear.
SECRET_VALUE = (
    (re.compile(r"sk-[A-Za-z0-9_\-]{16,}"), "openai-style key"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{16,}"), "github token"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "github fine-grained token"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "aws access key id"),
    (re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"), "slack token"),
    (re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"), "jwt"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key block"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{12,}"), "bearer token"),
    (re.compile(r"glpat-[A-Za-z0-9_\-]{16,}"), "gitlab token"),
    (re.compile(r"(?i)\b[a-z0-9._%+\-]+:[^\s/@]{8,}@[a-z0-9.\-]+\.[a-z]{2,}"), "credentials in a url"),
)
# NAME=value / NAME: value lines in plain text.
ASSIGNMENT = re.compile(r"^(\s*(?:export\s+)?)([A-Za-z_][A-Za-z0-9_.\-]*)(\s*[:=]\s*)(.+?)(\s*)$")


def looks_like_pointer(value):
    return bool(POINTER_VALUE.match(value.strip()))


def scrub_value(value):
    """Replace any secret-shaped substring in value; return (new_value, reason or None)."""
    for pattern, reason in SECRET_VALUE:
        if pattern.search(value):
            return pattern.sub(PLACEHOLDER, value), reason
    return value, None


def redact_json(value, path=""):
    """Walk parsed JSON, redacting by key name and by value shape. Returns (value, removals)."""
    removals = []
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            where = f"{path}.{key}" if path else str(key)
            if (
                isinstance(item, str)
                and item
                and SECRET_KEY.search(str(key))
                and not POINTER_KEY.search(str(key))
                and not looks_like_pointer(item)
            ):
                result[key] = PLACEHOLDER
                removals.append(Removal(where, f"key name {key!r}"))
                continue
            result[key], nested = redact_json(item, where)
            removals.extend(nested)
        return result, removals
    if isinstance(value, list):
        result = []
        for index, item in enumerate(value):
            cleaned, nested = redact_json(item, f"{path}[{index}]")
            result.append(cleaned)
            removals.extend(nested)
        return result, removals
    if isinstance(value, str) and value:
        cleaned, reason = scrub_value(value)
        if reason:
            return cleaned, [Removal(path or "(root)", reason)]
    return value, removals


def redact_lines(source):
    """Line-oriented fallback for anything that is not valid JSON."""
    removals, lines = [], source.splitlines(keepends=True)
    for number, line in enumerate(lines, start=1):
        body = line.rstrip("\r\n")
        ending = line[len(body) :]
        match = ASSIGNMENT.match(body)
        if match and match[4] and SECRET_KEY.search(match[2]) and not POINTER_KEY.search(match[2]):
            if not looks_like_pointer(match[4]):
                lines[number - 1] = match[1] + match[2] + match[3] + PLACEHOLDER + match[5] + ending
                removals.append(Removal(f"line {number}", f"assignment to {match[2]!r}"))
                continue
        cleaned, reason = scrub_value(body)
        if reason:
            lines[number - 1] = cleaned + ending
            removals.append(Removal(f"line {number}", reason))
    return "".join(lines), removals


def text(source, name):
    """Redact one file's text. JSON is walked structurally; everything else line by line."""
    if name.endswith(".json"):
        try:
            parsed = json.loads(source)
        except ValueError:
            return redact_lines(source)
        cleaned, removals = redact_json(parsed)
        if not removals:
            return source, []  # Preserve the original formatting when nothing changed.
        return json.dumps(cleaned, indent=2, sort_keys=False) + "\n", removals
    return redact_lines(source)


def text_bytes(data, name):
    """Decode captured bytes as UTF-8 text, then redact. Binary files are never guessed at."""
    try:
        source = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise RedactionError(f"{name} is not UTF-8 text; a capsule carries only reviewable text files") from error
    if "\x00" in source:
        raise RedactionError(f"{name} contains NUL bytes; a capsule carries only reviewable text files")
    return text(source, name)
