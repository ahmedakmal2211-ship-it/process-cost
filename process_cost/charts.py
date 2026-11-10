"""Text and SVG charts of cost per part vs batch size (log-log), stdlib only."""

from __future__ import annotations

import math
from xml.sax.saxutils import escape

from .breakeven import Line

Q_MIN, Q_MAX = 1.0, 10000.0
_SYMBOLS = "AB"
_COLOURS = ("#1f6fb4", "#c8402a")


def _q_at(frac: float) -> float:
    return 10 ** (math.log10(Q_MIN) + frac * (math.log10(Q_MAX) - math.log10(Q_MIN)))


def _y_range(lines: list[Line], samples: int = 200) -> tuple[float, float]:
    vals = [ln.per_part(_q_at(i / (samples - 1))) for ln in lines for i in range(samples)]
    lo, hi = min(vals), max(vals)
    if lo <= 0:
        lo = min(v for v in vals if v > 0) if any(v > 0 for v in vals) else 1e-6
    if hi / lo < 1.0001:
        lo, hi = lo / 1.1, hi * 1.1
    return lo, hi


def ascii_chart(lines: list[Line], q_star: float | None = None, width: int = 61, height: int = 16) -> str:
    """Log-log character plot. A/B mark the scenarios, * overlap, | the break-even."""
    lo, hi = _y_range(lines)
    llo, lhi = math.log10(lo), math.log10(hi)
    grid = [[" "] * width for _ in range(height)]

    if q_star is not None and Q_MIN <= q_star <= Q_MAX:
        col = round((math.log10(q_star) - math.log10(Q_MIN))
                    / (math.log10(Q_MAX) - math.log10(Q_MIN)) * (width - 1))
        for r in range(height):
            grid[r][col] = "|"

    for i, ln in enumerate(lines):
        sym = _SYMBOLS[i] if i < len(_SYMBOLS) else str(i + 1)
        for c in range(width):
            y = ln.per_part(_q_at(c / (width - 1)))
            if y <= 0:
                continue
            r = round((lhi - math.log10(y)) / (lhi - llo) * (height - 1))
            r = min(max(r, 0), height - 1)
            grid[r][c] = "*" if grid[r][c] in _SYMBOLS and grid[r][c] != sym else sym

    out = []
    for r in range(height):
        val = 10 ** (lhi - r / (height - 1) * (lhi - llo))
        label = f"{val:10.2f}" if r in (0, height // 2, height - 1) else " " * 10
        out.append(f"{label} |{''.join(grid[r])}".rstrip())
    out.append(" " * 11 + "+" + "-" * width)
    ticks = [" "] * (width + 8)
    for k in range(5):
        text = str(10**k)
        pos = round(k / 4 * (width - 1))
        for j, ch in enumerate(text):
            if pos + j < len(ticks):
                ticks[pos + j] = ch
    out.append(" " * 12 + "".join(ticks).rstrip())
    out.append(" " * 12 + "batch size Q (parts, log)   y: cost per part ($, log)")
    legend = "   ".join(f"{_SYMBOLS[i] if i < 2 else i + 1} = {ln.name}" for i, ln in enumerate(lines))
    extra = "   | = break-even" if q_star is not None and Q_MIN <= q_star <= Q_MAX else ""
    out.append(" " * 12 + legend + "   * = overlap" + extra)
    return "\n".join(out)


def _nice_ticks(lo: float, hi: float) -> list[float]:
    ticks = []
    for e in range(math.floor(math.log10(lo)) - 1, math.ceil(math.log10(hi)) + 1):
        for m in (1, 2, 5):
            v = m * 10**e
            if lo <= v <= hi:
                ticks.append(v)
    return ticks


def svg_chart(lines: list[Line], q_star: float | None = None, title: str = "Cost per part vs batch size") -> str:
    w, h = 720, 430
    x0, x1, y0, y1 = 80, 690, 50, 360
    lo, hi = _y_range(lines)
    llo, lhi = math.log10(lo), math.log10(hi)
    pad = 0.05 * (lhi - llo)
    llo, lhi = llo - pad, lhi + pad

    def px(q: float) -> float:
        return x0 + (math.log10(q) - math.log10(Q_MIN)) / (math.log10(Q_MAX) - math.log10(Q_MIN)) * (x1 - x0)

    def py(v: float) -> float:
        return y1 - (math.log10(v) - llo) / (lhi - llo) * (y1 - y0)

    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
         f'font-family="sans-serif" font-size="12">',
         f"<title>{escape(title)}</title>",
         f'<rect width="{w}" height="{h}" fill="#ffffff"/>',
         f'<text x="{w / 2:.0f}" y="28" text-anchor="middle" font-size="15">{escape(title)}</text>']
    for k in range(5):
        x = px(10**k)
        s.append(f'<line x1="{x:.1f}" y1="{y0}" x2="{x:.1f}" y2="{y1}" stroke="#e3e3e3"/>')
        s.append(f'<text x="{x:.1f}" y="{y1 + 18}" text-anchor="middle">{10**k}</text>')
    for v in _nice_ticks(10**llo, 10**lhi):
        y = py(v)
        s.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="#e3e3e3"/>')
        s.append(f'<text x="{x0 - 6}" y="{y + 4:.1f}" text-anchor="end">{v:g}</text>')
    s.append(f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" fill="none" stroke="#444"/>')
    s.append(f'<text x="{(x0 + x1) / 2:.0f}" y="{y1 + 40}" text-anchor="middle">'
             f"Batch size Q (parts, log scale)</text>")
    s.append(f'<text transform="translate(22 {(y0 + y1) / 2:.0f}) rotate(-90)" text-anchor="middle">'
             f"Cost per part ($, log scale)</text>")

    for i, ln in enumerate(lines):
        pts = " ".join(f"{px(q):.1f},{py(ln.per_part(q)):.1f}"
                       for q in (_q_at(j / 160) for j in range(161)))
        colour = _COLOURS[i % len(_COLOURS)]
        s.append(f'<polyline fill="none" stroke="{colour}" stroke-width="2" points="{pts}"/>')
        ly = y0 + 18 + 18 * i
        s.append(f'<line x1="{x1 - 200}" y1="{ly}" x2="{x1 - 175}" y2="{ly}" stroke="{colour}" stroke-width="2"/>')
        s.append(f'<text x="{x1 - 168}" y="{ly + 4}">{escape(ln.name)}</text>')

    if q_star is not None and Q_MIN <= q_star <= Q_MAX:
        x = px(q_star)
        s.append(f'<line x1="{x:.1f}" y1="{y0}" x2="{x:.1f}" y2="{y1}" stroke="#333" '
                 f'stroke-dasharray="5,4"/>')
        s.append(f'<text x="{x + 5:.1f}" y="{y1 - 8}">Q* = {q_star:.1f}</text>')
    s.append("</svg>")
    return "\n".join(s) + "\n"
