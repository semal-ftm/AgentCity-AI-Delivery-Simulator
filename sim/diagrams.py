"""Architecture diagrams as SVG, generated from each agent's `diagram` description.

Basic structure required by the assignment:
    Input / Perception -> Decision Process -> Action -> Environment   (+ feedback)
plus the architecture-specific components (rules, internal state, goal, utility,
learning/feedback, subgoals, context) drawn above the decision process.
The dashboard and the report both use these same SVGs.
"""
from __future__ import annotations

from html import escape
from typing import List

KIND_COLOR = {"rules": "#ef476f", "state": "#f78c1f", "goal": "#e0a000", "utility": "#06a77d", "learning": "#118ab2",
              "subgoals": "#8e5cf7", "context": "#e0457b", "model": "#5b6b84"}
W, H = 900, 400
BOX_W, BOX_H = 176, 104


def _box(x, y, w, h, title, lines: List[str], fill, stroke, title_color="#1d2340") -> str:
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{fill}" stroke="{stroke}" stroke-width="2"/>',
           f'<text x="{x + w / 2}" y="{y + 24}" text-anchor="middle" font-size="14" font-weight="700" fill="{title_color}">{escape(title)}</text>']
    for i, ln in enumerate(lines):
        out.append(f'<text x="{x + w / 2}" y="{y + 46 + i * 17}" text-anchor="middle" font-size="12" fill="#3b4366">{escape(ln)}</text>')
    return "\n".join(out)


def _arrow(x1, y1, x2, y2, color="#3b4366", dashed=False) -> str:
    d = ' stroke-dasharray="6 5"' if dashed else ""
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="2.2" marker-end="url(#ah)"{d}/>'


def diagram_svg(meta: dict) -> str:
    d = meta["diagram"]
    color = meta["color"]
    y = 238
    xs = [24, 250, 476, 702]
    main = [("Input / Perception", d["perception"], "#eaf1ff", "#5b7cfa"),
            ("Decision process", d["decision"], "#fff", color),
            ("Action", d["action"], "#e7fbf3", "#06a77d"),
            ("Environment", d["environment"], "#f2f4f8", "#5b6b84")]
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="Nunito, Segoe UI, Arial, sans-serif">',
             '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
             '<path d="M0,0 L10,5 L0,10 z" fill="#3b4366"/></marker></defs>',
             f'<rect width="{W}" height="{H}" rx="18" fill="#fbfaf6"/>',
             f'<text x="24" y="34" font-size="19" font-weight="800" fill="#1d2340">{escape(meta["name"])}</text>',
             f'<text x="24" y="56" font-size="13" fill="#59617f">{escape(meta["architecture"])}</text>']
    for i, (t, lines, fill, stroke) in enumerate(main):
        parts.append(_box(xs[i], y, BOX_W, BOX_H, t, lines, fill, stroke))
        if i < 3:
            parts.append(_arrow(xs[i] + BOX_W + 4, y + BOX_H / 2, xs[i + 1] - 6, y + BOX_H / 2))
    extras = d.get("extra", [])
    n = len(extras)
    ew = 190 if n <= 2 else 172
    gap = 22
    total = n * ew + (n - 1) * gap
    cx = xs[1] + BOX_W / 2
    x0 = max(14, min(W - total - 14, cx - total / 2))
    for i, e in enumerate(extras):
        ex = x0 + i * (ew + gap)
        c = KIND_COLOR.get(e["kind"], "#5b6b84")
        parts.append(_box(ex, 78, ew, 30 + 18 * max(1, len(e["lines"])) + 8, e["label"], e["lines"], "#ffffff", c, c))
        parts.append(_arrow(ex + ew / 2, 78 + 30 + 18 * max(1, len(e["lines"])) + 10, cx + (ex + ew / 2 - cx) * 0.25, y - 6, c))
    fy = y + BOX_H + 30
    parts.append(f'<path d="M{xs[3] + BOX_W / 2},{y + BOX_H + 4} L{xs[3] + BOX_W / 2},{fy} L{xs[0] + BOX_W / 2},{fy} '
                 f'L{xs[0] + BOX_W / 2},{y + BOX_H + 8}" fill="none" stroke="#5b6b84" stroke-width="2" stroke-dasharray="6 5" marker-end="url(#ah)"/>')
    parts.append(f'<text x="{(xs[0] + xs[3] + BOX_W) / 2}" y="{fy - 7}" text-anchor="middle" font-size="12" fill="#59617f">'
                 f'feedback: {escape(d.get("feedback", "new percept"))}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def system_svg() -> str:
    """Overall system architecture of the simulator."""
    boxes = [
        (30, 90, "Scenario manager", ["3 situations (JSON)", "random training situations"], "#5b7cfa"),
        (30, 230, "Road network graph", ["56 nodes, 80 edges", "routes A-D = node paths"], "#5b7cfa"),
        (270, 90, "Traffic + weather sims", ["zone traffic, rain, flooding", "noise, red lights, incidents"], "#f78c1f"),
        (270, 230, "Route evaluation", ["edge-by-edge time,", "cost, safety, risk"], "#f78c1f"),
        (510, 160, "7 agents", ["perceive -> decide", "write their own trace"], "#e0457b"),
        (720, 90, "Delivery environment", ["executes route on graph", "reward (same for all)"], "#06a77d"),
        (720, 230, "Runner + metrics", ["6-phase timeline", "200-run evaluation"], "#06a77d"),
    ]
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 930 380" width="930" height="380" font-family="Nunito, Segoe UI, Arial, sans-serif">',
             '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
             '<path d="M0,0 L10,5 L0,10 z" fill="#3b4366"/></marker></defs>',
             '<rect width="930" height="380" rx="18" fill="#fbfaf6"/>',
             '<text x="30" y="40" font-size="19" font-weight="800" fill="#1d2340">Agent City - system architecture</text>',
             '<text x="30" y="62" font-size="13" fill="#59617f">Python engine + agents  ->  JSON API (server.py)  ->  browser: 2D canvas city, reasoning panel, charts</text>']
    for x, y, t, lines, c in boxes:
        parts.append(_box(x, y, 190, 96, t, lines, "#fff", c, c))
    for a, b in [((220, 138), (268, 138)), ((220, 278), (268, 278)), ((365, 186), (365, 228)), ((460, 278), (508, 220)),
                 ((460, 138), (508, 196)), ((700, 208), (718, 150)), ((815, 186), (815, 228)), ((700, 220), (718, 270))]:
        parts.append(_arrow(*a, *b))
    parts.append('<text x="465" y="350" text-anchor="middle" font-size="12" fill="#59617f">Browser asks /api/run -> receives the timeline the agent produced; '
                 'nothing in the UI is precomputed or scripted.</text></svg>')
    return "\n".join(parts)
