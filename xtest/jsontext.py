"""Build JSON text that a Python dict cannot represent.

Conformance cases need duplicate member names, escaped spellings of names,
exact number literals, lone surrogates, and case variants placed at exact
positions. None of these survives ``json.dumps``. ``Obj`` keeps ordered,
possibly repeated members, ``Raw`` splices JSON text in verbatim, and ``text``
serializes a mix of them, dicts, lists, and scalars compactly.

Shared by the DSPX-5520 vector generator and the xtest cases that inject the
same constructs into real TDF manifests.
"""

import json
from typing import Any


class Raw(str):
    """JSON text spliced in verbatim."""


class Obj:
    """A JSON object as ordered (name, value) pairs. Names may repeat."""

    def __init__(self, *pairs: tuple[str, Any]) -> None:
        self.pairs = list(pairs)

    @classmethod
    def of(cls, value: dict[str, Any]) -> Obj:
        """A shallow ``Obj`` of a parsed JSON object, keeping member order."""
        return cls(*value.items())

    def plus(self, *pairs: tuple[str, Any]) -> Obj:
        return Obj(*self.pairs, *pairs)

    def without(self, *names: str) -> Obj:
        return Obj(*((k, v) for k, v in self.pairs if k not in names))

    def put(self, name: str, value: Any) -> Obj:
        """Replace the value of ``name`` in place."""
        assert any(k == name for k, _ in self.pairs), name
        return Obj(*((k, value if k == name else v) for k, v in self.pairs))

    def rename(self, name: str, new: str) -> Obj:
        assert any(k == name for k, _ in self.pairs), name
        return Obj(*((new if k == name else k, v) for k, v in self.pairs))

    def after(self, name: str, *pairs: tuple[str, Any]) -> Obj:
        """Insert ``pairs`` right after member ``name``."""
        out: list[tuple[str, Any]] = []
        for k, v in self.pairs:
            out.append((k, v))
            if k == name:
                out.extend(pairs)
        assert len(out) == len(self.pairs) + len(pairs), name
        return Obj(*out)


def text(value: Any) -> str:
    """Compact JSON text for ``value``; non-ASCII characters stay literal."""
    match value:
        case Raw():
            return str(value)
        case Obj():
            return "{" + ",".join(f"{_name(k)}:{text(v)}" for k, v in value.pairs) + "}"
        case dict():
            return text(Obj(*value.items()))
        case list():
            return "[" + ",".join(text(v) for v in value) + "]"
        case float():
            raise TypeError("spell numbers out with Raw")
        case _:
            return json.dumps(value, ensure_ascii=False)


def _name(name: str) -> str:
    return str(name) if isinstance(name, Raw) else json.dumps(name, ensure_ascii=False)


# JSON escapes are built from code points rather than spelled in source, so
# that no tool between an editor and the interpreter can decode them.
BACKSLASH = chr(0x5C)


def esc(*units: int) -> str:
    """JSON text of a backslash-u escape for each UTF-16 code unit."""
    return "".join(f"{BACKSLASH}u{unit:04x}" for unit in units)


def esc_non_ascii(s: str) -> str:
    """``s`` with every non-ASCII character as backslash-u escapes."""
    out = []
    for c in s:
        if ord(c) < 0x80:
            out.append(c)
            continue
        units = c.encode("utf-16-be")
        out.append(
            esc(*(int.from_bytes(units[i : i + 2]) for i in range(0, len(units), 2)))
        )
    return "".join(out)


def quoted(*parts: str) -> Raw:
    """A JSON string literal from already-escaped ``parts``."""
    return Raw('"' + "".join(parts) + '"')
