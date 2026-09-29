"""Just enough SVG to draw three figures, and deliberately no more.

What is missing is the point. There is no nice-number tick algorithm, no domain
inference, and no text-measurement engine: tick arrays are literals in the
figure code and gutters are generous. A charting library has to guess what the
caller meant; three hand-laid figures do not, and every guess we skip is a
class of bug we do not have to debug in a file nobody looks at twice a year.

Two rules are enforced by the shapes here rather than by discipline:

- :meth:`Canvas.text` takes a *class* (``ink`` or ``muted``), not a color. Text
  therefore cannot wear a series color, because the signature gives you no way
  to ask for one.
- Every coordinate goes through :func:`n`. A 1e-16 wobble in a scale
  computation cannot change a committed byte, so regenerating the figures on a
  different CPU produces no diff.

Colors are emitted as ``var(--s1)`` and friends, resolved by the stylesheet
:func:`document` writes. That is what lets one geometry pass serve both themes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

#: Text roles. Deliberately not a color -- see the module docstring.
InkClass = Literal["ink", "muted"]

#: Line roles, resolved by the stylesheet.
LineClass = Literal["grid", "axis", "ref", "rule"]

_FONT = 'ui-sans-serif, -apple-system, "Segoe UI", Roboto, Helvetica, sans-serif'


def n(v: float) -> str:
    """Format a coordinate to a stable two decimals, with ``-0`` normalized.

    Float formatting is the whole reason the committed SVGs do not churn.
    """
    s = f"{v:.2f}"
    if s.startswith("-") and float(s) == 0.0:
        return s[1:]
    return s


def esc(s: str) -> str:
    """XML-escape text content.

    Not theoretical: figure 2's legend reads ``p_adj_slower > 0.95``.
    """
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


@dataclass(frozen=True, slots=True)
class Theme:
    """One resolved set of colors. Two instances exist: :data:`LIGHT`, :data:`DARK`."""

    surface: str
    ink: str
    muted: str
    grid: str
    #: Categorical slots 1-3, in fixed order. Never cycled, never reordered:
    #: a figure's fourth series does not exist, it becomes a second panel.
    series: tuple[str, str, str]


#: Validated under ``--pairs all``: worst CVD dE 9.2, worst normal-vision dE 24.0.
#: ``#1baf7a`` sits at 2.74:1 on this surface, so anything drawn in it must also
#: carry a visible direct label.
LIGHT = Theme(
    surface="#fcfcfb",
    ink="#0b0b0b",
    muted="#52514e",
    grid="#dedcd4",
    series=("#2a78d6", "#eb6834", "#1baf7a"),
)

#: The same three hues re-stepped for the dark surface, not a second palette.
#: Validated under ``--pairs all``: every check passes, contrast included.
DARK = Theme(
    surface="#1a1a19",
    ink="#ffffff",
    muted="#c3c2b7",
    grid="#3b3a37",
    series=("#3987e5", "#d95926", "#199e70"),
)


def series(slot: int) -> str:
    """Return the CSS variable for categorical slot ``slot`` (0-based)."""
    if not 0 <= slot <= 2:
        raise ValueError(f"categorical slot must be 0..2, got {slot}")
    return f"var(--s{slot + 1})"


@dataclass(frozen=True, slots=True)
class Scale:
    """Maps a data value onto a pixel coordinate, linearly or in log space."""

    lo: float
    hi: float
    px0: float
    px1: float
    log: bool = False

    def at(self, v: float) -> float:
        if self.log:
            span = math.log(self.hi) - math.log(self.lo)
            t = (math.log(v) - math.log(self.lo)) / span
        else:
            t = (v - self.lo) / (self.hi - self.lo)
        return self.px0 + t * (self.px1 - self.px0)


@dataclass(frozen=True, slots=True)
class Panel:
    """A plot area. A figure with two of these has two y-axes and no dual axis."""

    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h


@dataclass(frozen=True, slots=True)
class Band:
    """Equal-width categorical slots across a pixel range."""

    count: int
    px0: float
    px1: float
    #: Fraction of each step left empty, so adjacent groups do not touch.
    pad: float = 0.34

    @property
    def step(self) -> float:
        return (self.px1 - self.px0) / self.count

    def center(self, i: int) -> float:
        return self.px0 + self.step * (i + 0.5)

    def slot(self, i: int, k: int, of: int, *, gap: float = 2.0) -> tuple[float, float]:
        """Return ``(x, width)`` for column ``k`` of ``of`` inside group ``i``.

        ``gap`` is the surface gap between adjacent columns, which is what keeps
        two touching fills from reading as one shape.
        """
        inner = self.step * (1.0 - self.pad)
        width = (inner - gap * (of - 1)) / of
        left = self.center(i) - inner / 2.0
        return left + k * (width + gap), width


class Canvas:
    """Accumulates SVG fragments. The whole mark vocabulary is its methods."""

    def __init__(self) -> None:
        self.parts: list[str] = []

    def render(self) -> str:
        return "\n".join(self.parts)

    def rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        fill: str,
        rx: float = 0.0,
        opacity: float = 1.0,
    ) -> None:
        radius = f' rx="{n(rx)}"' if rx else ""
        alpha = f' opacity="{n(opacity)}"' if opacity != 1.0 else ""
        self.parts.append(
            f'<rect x="{n(x)}" y="{n(y)}" width="{n(w)}" height="{n(h)}"'
            f'{radius} fill="{fill}"{alpha}/>'
        )

    def column(self, x: float, y_base: float, y_top: float, w: float, *, fill: str):
        """A column rounded at the data end only.

        ``rect rx=4`` would round the baseline too, which reads as a floating
        lozenge rather than a quantity standing on an axis.
        """
        h = y_base - y_top
        if h < 1.5:
            # Keep a near-zero quantity visible; the direct label carries the
            # real value. A bar that renders as nothing reads as missing data.
            h = 1.5
            y_top = y_base - h
        r = min(4.0, w / 2.0, h)
        self.parts.append(
            f'<path d="M{n(x)},{n(y_base)} L{n(x)},{n(y_top + r)}'
            f" Q{n(x)},{n(y_top)} {n(x + r)},{n(y_top)}"
            f" L{n(x + w - r)},{n(y_top)}"
            f" Q{n(x + w)},{n(y_top)} {n(x + w)},{n(y_top + r)}"
            f' L{n(x + w)},{n(y_base)} Z" fill="{fill}"/>'
        )

    def polyline(self, points: list[tuple[float, float]], *, stroke: str) -> None:
        pts = " ".join(f"{n(px)},{n(py)}" for px, py in points)
        self.parts.append(
            f'<polyline points="{pts}" fill="none" stroke="{stroke}"'
            ' stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
        )

    def dot(self, cx: float, cy: float, *, fill: str, r: float = 4.5) -> None:
        """A marker with a 2px surface ring, so overlapping marks stay countable."""
        self.parts.append(
            f'<circle cx="{n(cx)}" cy="{n(cy)}" r="{n(r)}" fill="{fill}"'
            ' stroke="var(--surface)" stroke-width="2"/>'
        )

    def rule(
        self, x1: float, y1: float, x2: float, y2: float, *, cls: LineClass
    ) -> None:
        self.parts.append(
            f'<line x1="{n(x1)}" y1="{n(y1)}" x2="{n(x2)}" y2="{n(y2)}" class="{cls}"/>'
        )

    def stroke(
        self, x1: float, y1: float, x2: float, y2: float, *, stroke: str, width: float
    ) -> None:
        """A colored 2px-class line. Used for series marks, never for text."""
        self.parts.append(
            f'<line x1="{n(x1)}" y1="{n(y1)}" x2="{n(x2)}" y2="{n(y2)}"'
            f' stroke="{stroke}" stroke-width="{n(width)}" stroke-linecap="round"/>'
        )

    def text(
        self,
        x: float,
        y: float,
        s: str,
        *,
        cls: InkClass = "ink",
        size: float = 12.0,
        anchor: str = "start",
        weight: str = "normal",
    ) -> None:
        bold = ' font-weight="600"' if weight == "bold" else ""
        self.parts.append(
            f'<text x="{n(x)}" y="{n(y)}" class="{cls}" font-size="{n(size)}"'
            f' text-anchor="{anchor}"{bold}>{esc(s)}</text>'
        )


def y_axis(
    c: Canvas,
    panel: Panel,
    scale: Scale,
    ticks: list[float],
    labels: list[str],
) -> None:
    """Horizontal gridlines with left-hand labels. Grid stays recessive."""
    for value, label in zip(ticks, labels, strict=True):
        y = scale.at(value)
        c.rule(panel.x, y, panel.right, y, cls="grid")
        c.text(panel.x - 10, y + 4, label, cls="muted", size=11, anchor="end")


def x_ticks(c: Canvas, panel: Panel, positions: list[float], labels: list[str]) -> None:
    """Category labels under a panel, with no tick marks -- the gap is enough."""
    for x, label in zip(positions, labels, strict=True):
        c.text(x, panel.bottom + 20, label, cls="muted", size=11, anchor="middle")


def legend(c: Canvas, x: float, y: float, entries: list[tuple[int, str]]) -> None:
    """A legend row. Present whenever a panel carries two or more series."""
    cursor = x
    for slot, label in entries:
        c.rect(cursor, y - 8, 10, 10, fill=series(slot), rx=2)
        c.text(cursor + 16, y, label, cls="muted", size=11)
        cursor += 26 + 6.4 * len(label)


def _vars(t: Theme) -> str:
    return (
        f"--surface:{t.surface};--ink:{t.ink};--muted:{t.muted};--grid:{t.grid};"
        f"--s1:{t.series[0]};--s2:{t.series[1]};--s3:{t.series[2]}"
    )


def document(width: float, height: float, body: str, *, title: str, desc: str) -> str:
    """Wrap a canvas in a themed, self-contained SVG document.

    The first thing drawn is an opaque surface covering the whole viewBox. On
    GitHub this file is served as an image in an isolated document, so its
    ``prefers-color-scheme`` follows the *operating system* rather than the
    GitHub theme toggle, and Safari ignores the query outright. Painting the
    surface means the worst case is a light card on a dark page -- bright, but
    never a figure rendered in ink that matches its background.
    """
    style = (
        f"svg{{{_vars(LIGHT)}}}"
        f"@media (prefers-color-scheme:dark){{svg{{{_vars(DARK)}}}}}"
        f"text{{font-family:{_FONT};}}"
        ".ink{fill:var(--ink);}"
        ".muted{fill:var(--muted);}"
        ".grid{stroke:var(--grid);stroke-width:1;}"
        ".axis{stroke:var(--muted);stroke-width:1;}"
        ".ref{stroke:var(--muted);stroke-width:1;stroke-dasharray:4 3;}"
        ".rule{stroke:var(--muted);stroke-width:1;}"
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{n(width)}"'
        f' height="{n(height)}" viewBox="0 0 {n(width)} {n(height)}"'
        f' role="img" aria-labelledby="t d">\n'
        f'<title id="t">{esc(title)}</title>\n'
        f'<desc id="d">{esc(desc)}</desc>\n'
        f"<style>{style}</style>\n"
        f'<rect width="{n(width)}" height="{n(height)}" rx="8"'
        f' fill="var(--surface)"/>\n'
        f"{body}\n"
        f"</svg>\n"
    )
