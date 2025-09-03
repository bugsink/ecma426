import json

from .codec import encode, decode  # noqa: F401


def _strip_xssi_prefix(s: str) -> str:
    if s.startswith(")]}'") or s.startswith(")]}"):
        return s.split("\n", 1)[1]
    return s


def loads(s: str | bytes) -> dict:
    if isinstance(s, bytes):
        s = s.decode("utf-8")

    obj = json.loads(_strip_xssi_prefix(s))
    return decode(obj)
