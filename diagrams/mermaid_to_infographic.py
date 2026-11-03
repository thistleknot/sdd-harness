"""mermaid_to_infographic.py -- render a party flowchart (Mermaid in Markdown) as an infographic SVG.

Spec: no governing spec found. Basis: operator instruction 2026-10-08 ("generate an svg
based on an input markdown with mermaid"; the x axis is the role flow, left to right,
starting at the Leader; the y axis is the model lane with effort inside the lane; roles
sharing a model and effort are merged into one). Palette rule: diagrams/color-key.md.
Promote to a REQ before anything depends on this file.

Usage:
    python mermaid_to_infographic.py two.md three.md          # writes two.svg, three.svg
    python mermaid_to_infographic.py in.md -o out.svg --title "My party"

Layout
    x: role flow. The entry's first role is step 1 (leftmost); each further hop is the next
       column, so branching roles fan out to the right.
    y: model lanes, heavy on top and light at the bottom (hue). Inside each lane the effort
       rows run high at the top to low at the bottom (vibrancy).
    Squash rule: roles whose model AND effort are identical are merged into one node, because
    one context serves them and no handoff is needed. Any difference keeps them apart, so a
    binding with fewer distinct (model, effort) positions simply draws fewer, squashed roles.

Input contract: the first ```mermaid block containing nodes labelled
`Class<br/>model / effort<br/>description...` (effort is low|medium|high). Nodes without
`/ effort` (User request, STOP, tests) become entry/exit pills in the side gutters.
Edges: `A --> B`, `A -->|"text"| B`, `A <-->|"text"| B`, `A -. "text" .-> B`.
Optional comment lines (Mermaid ignores `%%`):
    %% slot heavy: openai/gpt-5.6-sol, openai/gpt-5.6-terra   (models filling that lane, any vendor)
    %% title: OpenRouter, any vendor on the same dial
"""
from __future__ import annotations

import argparse
import colorsys
import html
import re
import sys
import textwrap
from pathlib import Path

ANCHORS = [(0.0, 0), (0.5, 40), (1.0, 125)]  # slot position -> hue degrees (red, amber, green)
EFFORT = {"low": (35, 82), "medium": (65, 67), "high": (95, 52)}  # (saturation %, lightness %)
EFFORT_ROWS = ["high", "medium", "low"]  # top to bottom inside every lane
SLOTS = [("light", 0.0), ("mid", 0.5), ("heavy", 1.0)]
LANE_ORDER = [2, 1, 0]  # heavy on top, light at the bottom
SLOT_PATTERNS = [(0, r"haiku|mini|nano|lite"), (2, r"opus|fable|sol|tierra|gpt-6"), (1, r"sonnet|gpt-5|luna")]
NUMBER_WORDS = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five"}

NODE_W, COL_W, COL_GAP = 360, 400, 110
LEFT_W, TAB_W, EFFORT_W, RIGHT_W = 150, 200, 70, 150
HEADER_H, TITLE_H, LEGEND_H, PAD, LANE_GAP = 56, 120, 96, 28, 18
SUB_MIN, GHOST_H = 100, 110
AUX_W, AUX_H = 130, 54
STACK_GAP = 34  # gap between nodes sharing a cell; wide enough for an edge label (22px) to sit in it
FONT = "'Segoe UI', system-ui, -apple-system, sans-serif"

NODE = r'(\w+)(?:\[(?:"([^"]*)"|([^\]]*))\])?'
EDGE_RE = re.compile(
    rf'^\s*{NODE}\s*(?:(<-->|-->)(?:\|"?([^|"]*)"?\|)?|-\.\s*"?([^".]*?)"?\s*\.->)\s*{NODE}\s*$'
)


def hue_at(t: float) -> float:
    for (t0, h0), (t1, h1) in zip(ANCHORS, ANCHORS[1:]):
        if t0 <= t <= t1:
            return h0 + (h1 - h0) * (t - t0) / (t1 - t0)
    raise ValueError(f"slot position out of range: {t}")


def hsl_hex(hue: float, sat: float, light: float) -> str:
    r, g, b = colorsys.hls_to_rgb(hue / 360, light / 100, sat / 100)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def palette(slot: int, effort: str) -> str:
    sat, light = EFFORT[effort]
    return hsl_hex(hue_at(SLOTS[slot][1]), sat, light)


def parse_directives(text: str) -> tuple[dict, str | None]:
    """Read `%% slot light|mid|heavy: model, model` and `%% title: text` comment lines.

    A declared slot wins over the name patterns, so any vendor's model can be slotted
    (the OpenRouter case): the same roles then work across whatever fills each lane.
    """
    slots: dict[int, list[str]] = {}
    title = None
    for line in text.splitlines():
        m = re.match(r"^\s*%%\s*slot\s+(light|mid|heavy)\s*:\s*(.+?)\s*$", line)
        if m:
            idx = [name for name, _ in SLOTS].index(m.group(1))
            slots.setdefault(idx, []).extend(s.strip() for s in m.group(2).split(",") if s.strip())
            continue
        m = re.match(r"^\s*%%\s*title\s*:\s*(.+?)\s*$", line)
        if m:
            title = m.group(1)
    return slots, title


def slot_of(model: str, declared: dict | None = None) -> int:
    if declared and model in declared:
        return declared[model]
    for idx, pattern in SLOT_PATTERNS:
        if re.search(pattern, model, re.I):
            return idx
    print(f"warning: model {model!r} matches no slot pattern; placed in mid", file=sys.stderr)
    return 1


def parse_label(node_id: str, label: str | None) -> dict:
    """Split a node label into class name, model, effort and description lines."""
    segs = [s.strip() for s in re.split(r"<br\s*/?>", label or node_id)]
    effort_match = re.match(r"^(.*?)\s*/\s*(low|medium|high)$", segs[1]) if len(segs) > 1 else None
    if effort_match:
        return {"id": node_id, "name": segs[0], "model": effort_match.group(1),
                "effort": effort_match.group(2), "desc": segs[2:]}
    return {"id": node_id, "name": " ".join(segs), "model": None, "effort": None, "desc": []}


def parse_block(block: str) -> tuple[dict, list]:
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    for line in block.splitlines():
        m = EDGE_RE.match(line)
        if not m:
            continue
        ends = []
        for idg, qg, pg in ((1, 2, 3), (7, 8, 9)):
            node_id, label = m.group(idg), m.group(qg) if m.group(qg) is not None else m.group(pg)
            if label is not None:
                nodes[node_id] = parse_label(node_id, label)
            ends.append(node_id)
        src, dst = ends
        if src == dst:
            continue  # self-loops carry no flow between nodes
        dotted = m.group(4) is None
        edges.append({"src": src, "dst": dst, "dotted": dotted,
                      "bidir": m.group(4) == "<-->",
                      "text": (m.group(6) if dotted else m.group(5)) or ""})
    for e in edges:
        for end in (e["src"], e["dst"]):
            if end not in nodes:
                raise ValueError(f"node {end!r} is used in an edge but never given a label")
    return nodes, edges


def parse_markdown(text: str) -> tuple[dict, list]:
    for block in re.findall(r"```mermaid\s*\n(.*?)```", text, re.S):
        nodes, edges = parse_block(block)
        if any(n["effort"] for n in nodes.values()):
            return nodes, edges
    raise ValueError("no mermaid block with 'model / effort' node labels found")


def merged_desc(members: list[dict]) -> list[str]:
    """Description lines for a merged node: one wrapped `Role: what it does` entry per member."""
    lines: list[str] = []
    for n in members:
        text = " ".join(n["desc"]).strip()
        who = re.sub(r"\s*\(.*?\)", "", n["name"]).strip()  # "Captain (orchestrator)" -> "Captain"
        lines += textwrap.wrap(f"{who}: {text}" if text else who, 54)
    return lines


def merge_roles(nodes: dict, edges: list, groups: list | None = None) -> tuple[dict, list]:
    """Merge roles that share the same model and effort into one node; drop edges between them.

    `groups` (lists of node ids) overrides that grouping: a diagram drawn from tiers.toml passes
    party.py's own groups, so party.py stays the only authority on what squashes.
    """
    members_of: dict[str, list[str]] = {}
    if groups is None:
        keyed: dict[tuple, list[str]] = {}
        for n in nodes.values():
            if n["effort"]:
                keyed.setdefault((n["model"], n["effort"]), []).append(n["id"])
        for ids in keyed.values():
            members_of.update({i: ids for i in ids})
    else:
        for ids in groups:
            ids = [i for i in ids if i in nodes and nodes[i]["effort"]]
            members_of.update({i: ids for i in ids})
    head_of: dict[str, str] = {}
    merged: dict[str, dict] = {}
    for nid, n in nodes.items():
        if not n["effort"]:
            head_of[nid] = nid
            merged[nid] = dict(n, members=[n["name"]])
            continue
        members = members_of[nid]
        head_of[nid] = members[0]
        if nid == members[0]:
            roles = [nodes[i] for i in members]
            node = dict(n, members=[r["name"] for r in roles])
            if len(roles) > 1:
                node["name"] = " + ".join(r["name"] for r in roles)
                node["desc"] = merged_desc(roles)
            merged[nid] = node
    out: list[dict] = []
    seen: set[tuple] = set()
    for e in edges:
        a, b = head_of[e["src"]], head_of[e["dst"]]
        if a == b:
            continue  # an edge inside a merged role is no longer a hand-off
        key = (a, b, e["text"], e["dotted"], e["bidir"])
        twin = (b, a, e["text"], e["dotted"], e["bidir"]) if e["bidir"] else None
        if key in seen or (twin and twin in seen):
            continue
        seen.add(key)
        out.append(dict(e, src=a, dst=b))
    return merged, out


def flow_columns(nodes: dict, edges: list) -> dict[str, int]:
    """Column per model node: the entry's first role is 0, each further hop adds one."""
    has_incoming = {e["dst"] for e in edges}
    entries = {n["id"] for n in nodes.values() if not n["effort"] and n["id"] not in has_incoming}
    starts = [e["dst"] for e in edges if e["src"] in entries and nodes[e["dst"]]["effort"]]
    if not starts:
        starts = [next(n["id"] for n in nodes.values() if n["effort"])]
    adjacent: dict[str, set] = {}
    for e in edges:
        adjacent.setdefault(e["src"], set()).add(e["dst"])
        adjacent.setdefault(e["dst"], set()).add(e["src"])
    depth = {s: 0 for s in starts}
    queue = list(starts)
    while queue:
        cur = queue.pop(0)
        for nxt in sorted(adjacent.get(cur, ())):
            if nxt not in depth and nodes[nxt]["effort"]:
                depth[nxt] = depth[cur] + 1
                queue.append(nxt)
    for n in nodes.values():
        if n["effort"]:
            depth.setdefault(n["id"], 0)  # a role the flow never reaches stays in step 1
    return depth


def node_height(n: dict) -> int:
    return 62 + 16 * len(n["desc"])


def layout(nodes: dict, edges: list, slots: dict | None = None) -> dict:
    """Place every node: flow depth picks the column, model slot picks the lane, effort the row."""
    model_nodes = [n for n in nodes.values() if n["effort"]]
    declared = {model: idx for idx, models in (slots or {}).items() for model in models}
    depth = flow_columns(nodes, edges)
    for n in model_nodes:
        n["slot"] = slot_of(n["model"], declared)
        n["col"] = depth[n["id"]]
        n["w"], n["h"] = NODE_W, node_height(n)
    n_cols = max(depth.values()) + 1
    bound = {n["slot"] for n in model_nodes} | {s for s, ms in (slots or {}).items() if ms}

    cells: dict[tuple, list] = {}
    for n in model_nodes:  # dict order is first appearance in the source
        cells.setdefault((n["slot"], n["effort"], n["col"]), []).append(n)

    def stack_height(members: list) -> float:
        return sum(n["h"] for n in members) + STACK_GAP * max(len(members) - 1, 0)

    sub_h = {}
    for s in range(3):
        for e in EFFORT_ROWS:
            tallest = max([stack_height(cells.get((s, e, c), [])) for c in range(n_cols)])
            sub_h[(s, e)] = max(tallest + 30, SUB_MIN)
    lane_h = {s: (sum(sub_h[(s, e)] for e in EFFORT_ROWS) if s in bound else GHOST_H) for s in range(3)}

    grid_x = PAD + LEFT_W + TAB_W
    grid_y = TITLE_H + HEADER_H
    lane_y, sub_y, y = {}, {}, grid_y
    for s in LANE_ORDER:
        lane_y[s] = y
        sy = y
        for e in EFFORT_ROWS:
            sub_y[(s, e)] = sy
            sy += sub_h[(s, e)]
        y += lane_h[s] + LANE_GAP
    grid_h = y - LANE_GAP - grid_y

    for (slot, effort, col), members in cells.items():
        cy = sub_y[(slot, effort)] + (sub_h[(slot, effort)] - stack_height(members)) / 2
        for n in members:
            n["x"] = grid_x + col * (COL_W + COL_GAP) + (COL_W - NODE_W) / 2
            n["y"] = cy
            cy += n["h"] + STACK_GAP

    grid_end = grid_x + n_cols * COL_W + (n_cols - 1) * COL_GAP
    band_end = grid_end + EFFORT_W
    incoming = {e["dst"] for e in edges}
    aux = [n for n in nodes.values() if not n["effort"]]
    for side in ("left", "right"):
        group = [n for n in aux if (n["id"] not in incoming) == (side == "left")]
        for n in group:
            n["w"], n["h"], n["col"] = max(AUX_W, len(n["name"]) * 7.6 + 40), AUX_H, side
            n["x"] = PAD if side == "left" else band_end + 24
            peers = [nodes[e["dst"] if e["src"] == n["id"] else e["src"]] for e in edges
                     if n["id"] in (e["src"], e["dst"])]
            peers = [p for p in peers if p["effort"]]
            n["y"] = (sum(p["y"] + p["h"] / 2 for p in peers) / len(peers) - AUX_H / 2) if peers else grid_y
        taken = grid_y
        for n in sorted(group, key=lambda k: k["y"]):
            n["y"] = max(n["y"], taken)
            taken = n["y"] + AUX_H + 16
    for n in nodes.values():
        n["cx"], n["cy"] = n["x"] + n["w"] / 2, n["y"] + n["h"] / 2
    right_w = max([n["w"] for n in aux if n["col"] == "right"], default=0)
    total_w = band_end + (24 + right_w if right_w else 0) + PAD
    total_h = grid_y + grid_h + LEGEND_H + PAD
    return {"grid_x": grid_x, "grid_y": grid_y, "grid_h": grid_h, "grid_end": grid_end, "band_end": band_end,
            "lane_y": lane_y, "lane_h": lane_h, "sub_y": sub_y, "sub_h": sub_h, "n_cols": n_cols,
            "bound": bound, "w": total_w, "h": total_h}


def pick_sides(a: dict, b: dict, nodes: dict) -> tuple[str, str, str]:
    dx = b["cx"] - a["cx"]
    if a["col"] == b["col"] and isinstance(a["col"], int) and abs(dx) < 60:
        lo, hi = sorted((a["cy"], b["cy"]))
        blocked = any(n is not a and n is not b and n["col"] == a["col"] and lo < n["cy"] < hi
                      for n in nodes.values())
        if blocked:
            return "R", "R", "loop"
        return ("B", "T", "v") if b["cy"] > a["cy"] else ("T", "B", "v")
    return ("R", "L", "h") if dx > 0 else ("L", "R", "h")


def detour(a: dict, b: dict, e: dict, nodes: dict, geo: dict | None) -> float:
    """Vertical bow (px) that carries a horizontal edge around any model node sitting on its path."""
    (x1, y1), (x2, y2) = e["p1"], e["p2"]
    blockers = []
    for n in nodes.values():
        if n is a or n is b or not isinstance(n["col"], int):
            continue  # entry and exit pills never block
        for i in range(1, 20):
            px, py = x1 + (x2 - x1) * i / 20, y1 + (y2 - y1) * i / 20
            if n["x"] - 8 <= px <= n["x"] + n["w"] + 8 and n["y"] - 8 <= py <= n["y"] + n["h"] + 8:
                blockers.append(n)
                break
    if not blockers:
        return 0.0
    reach = (max(n["h"] for n in blockers) / 2 + 40) * 1.35  # a cubic only reaches ~0.75 of its control offset
    top = min(n["y"] for n in blockers)
    bottom = max(n["y"] + n["h"] for n in blockers)
    room_above = top - geo["grid_y"] if geo else 1e9
    room_below = geo["grid_y"] + geo["grid_h"] - bottom if geo else 0
    return -reach if room_above >= room_below else reach


def route_edges(nodes: dict, edges: list, geo: dict | None = None) -> None:
    """Choose a side for each edge end, then spread the anchors evenly along each side."""
    ports: dict[tuple, list] = {}
    for i, e in enumerate(edges):
        a, b = nodes[e["src"]], nodes[e["dst"]]
        s1, s2, kind = pick_sides(a, b, nodes)
        e["s1"], e["s2"], e["kind"] = s1, s2, kind
        ports.setdefault((a["id"], s1), []).append((i, "p1", b))
        ports.setdefault((b["id"], s2), []).append((i, "p2", a))
    for (node_id, side), items in ports.items():
        n = nodes[node_id]
        key = (lambda it: it[2]["cx"]) if side in "TB" else (lambda it: it[2]["cy"])
        items.sort(key=key)
        for idx, (ei, which, _) in enumerate(items):
            frac = (idx + 1) / (len(items) + 1)
            if side == "L":
                pt = (n["x"], n["y"] + n["h"] * frac)
            elif side == "R":
                pt = (n["x"] + n["w"], n["y"] + n["h"] * frac)
            elif side == "T":
                pt = (n["x"] + n["w"] * frac, n["y"])
            else:
                pt = (n["x"] + n["w"] * frac, n["y"] + n["h"])
            edges[ei][which] = pt
    for e in edges:
        e["bow"] = detour(nodes[e["src"]], nodes[e["dst"]], e, nodes, geo) if e["kind"] == "h" else 0.0


def edge_path(e: dict) -> tuple[str, tuple[float, float]]:
    (x1, y1), (x2, y2) = e["p1"], e["p2"]
    if e["kind"] == "loop":
        bulge = 55
        c1, c2 = (x1 + bulge, y1), (x2 + bulge, y2)
    elif e["kind"] == "v":
        k = max(30, abs(y2 - y1) * 0.5) * (1 if e["s1"] == "B" else -1)
        c1, c2 = (x1, y1 + k), (x2, y2 - k)
    else:
        k = max(50, abs(x2 - x1) * 0.45) * (1 if e["s1"] == "R" else -1)
        c1, c2 = (x1 + k, y1 + e["bow"]), (x2 - k, y2 + e["bow"])
    mid = ((x1 + 3 * c1[0] + 3 * c2[0] + x2) / 8, (y1 + 3 * c1[1] + 3 * c2[1] + y2) / 8)
    return f"M{x1:.1f},{y1:.1f} C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {x2:.1f},{y2:.1f}", mid


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def tab_font(model: str) -> int:
    """Largest font (11-18px) that keeps a model id inside the lane tab."""
    return max(11, min(18, int((TAB_W - 24) / (len(model) * 0.6))))


def title_font(name: str) -> int:
    """Largest font (13-20px) that keeps a (possibly merged) role name inside its node."""
    return max(13, min(20, int((NODE_W - 24) / (len(name) * 0.58))))


def render(nodes: dict, edges: list, title: str | None, slots: dict | None = None,
           groups: list | None = None) -> str:
    nodes, edges = merge_roles(nodes, edges, groups)
    geo = layout(nodes, edges, slots)
    route_edges(nodes, edges, geo)
    model_nodes = [n for n in nodes.values() if n["effort"]]
    models_by_slot = {}
    for s in range(3):
        listed = list((slots or {}).get(s, []))  # declared candidates keep their declared order
        used = sorted({n["model"] for n in model_nodes if n["slot"] == s} - set(listed))
        models_by_slot[s] = listed + used
    bound = geo["bound"]
    heading = title or f"{NUMBER_WORDS.get(len(bound), len(bound))} model tiers: the party on a dial"
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {geo["w"]:.0f} {geo["h"]:.0f}" '
           f'width="{geo["w"]:.0f}" height="{geo["h"]:.0f}" font-family="{FONT}">',
           '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" '
           'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#333"/></marker></defs>',
           '<rect width="100%" height="100%" fill="#ffffff"/>',
           f'<text x="{PAD}" y="52" font-size="30" font-weight="700" fill="#1a1a1a">{esc(heading)}</text>',
           f'<text x="{PAD}" y="80" font-size="15" fill="#555">x: role flow, left to right   '
           f'y: model lane, heavy on top (hue); effort inside the lane, high on top (vibrancy)</text>']

    gx, gy, gend, band_end = geo["grid_x"], geo["grid_y"], geo["grid_end"], geo["band_end"]
    band_x = gx - TAB_W
    tabs: list[str] = []  # lane tabs are drawn after the edges so an edge passes behind them
    for s in LANE_ORDER:
        ly, lh = geo["lane_y"][s], geo["lane_h"][s]
        name = SLOTS[s][0]
        if s in bound:
            hue = hue_at(SLOTS[s][1])
            out.append(f'<rect x="{band_x}" y="{ly}" width="{band_end - band_x}" height="{lh}" rx="14" '
                       f'fill="{hsl_hex(hue, 40, 96)}" stroke="{hsl_hex(hue, 65, 40)}" stroke-width="2.5"/>')
            for e in EFFORT_ROWS:  # effort rows: vibrancy stripes across the lane
                sy, sh = geo["sub_y"][(s, e)], geo["sub_h"][(s, e)]
                out.append(f'<rect x="{gx}" y="{sy + 5}" width="{gend - gx}" height="{sh - 10}" rx="9" '
                           f'fill="{palette(s, e)}" fill-opacity="0.28" stroke="{palette(s, e)}" stroke-width="1.5"/>')
                out.append(f'<text x="{band_end - 10}" y="{sy + sh / 2 + 4}" font-size="13" font-weight="600" '
                           f'text-anchor="end" fill="#555">{e}</text>')
            tabs.append(f'<rect x="{band_x}" y="{ly}" width="{TAB_W}" height="{lh}" rx="14" '
                        f'fill="{palette(s, "medium")}" stroke="{hsl_hex(hue, 65, 40)}" stroke-width="2.5"/>')
            models = models_by_slot[s]
            top = ly + lh / 2 - (len(models) * 24) / 2 - 6
            tabs.append(f'<text x="{band_x + TAB_W / 2}" y="{top - 6}" font-size="13" text-anchor="middle" '
                        f'fill="#222">{name} model</text>')
            for i, mname in enumerate(models):
                tabs.append(f'<text x="{band_x + TAB_W / 2}" y="{top + 20 + 24 * i}" font-size="{tab_font(mname)}" '
                            f'font-weight="700" text-anchor="middle" fill="#111">{esc(mname)}</text>')
        else:
            out.append(f'<rect x="{band_x}" y="{ly}" width="{band_end - band_x}" height="{lh}" rx="14" '
                       f'fill="none" stroke="#aaa" stroke-width="2" stroke-dasharray="8 6"/>')
            out.append(f'<text x="{band_x + TAB_W / 2}" y="{ly + lh / 2 + 5}" font-size="16" '
                       f'text-anchor="middle" fill="#888">no {name} model bound</text>')
            out.append(f'<text x="{(gx + gend) / 2}" y="{ly + lh / 2 + 5}" font-size="14" '
                       f'text-anchor="middle" fill="#999">the ceiling is the lane below</text>')
    for c in range(geo["n_cols"]):  # flow steps across the top
        cx = gx + c * (COL_W + COL_GAP)
        out.append(f'<rect x="{cx}" y="{gy - 44}" width="{COL_W}" height="34" rx="10" fill="#f1f1f1" '
                   f'stroke="#bbb" stroke-width="1.5"/>')
        out.append(f'<text x="{cx + 20}" y="{gy - 21}" font-size="17" font-weight="600" fill="#333">'
                   f'step {c + 1}</text>')
        if c < geo["n_cols"] - 1:
            out.append(f'<text x="{cx + COL_W + COL_GAP / 2}" y="{gy - 21}" font-size="20" '
                       f'text-anchor="middle" fill="#888">→</text>')

    for e in edges:  # edges under the nodes
        path, _ = edge_path(e)
        dash = ' stroke-dasharray="6 5"' if e["dotted"] else ""
        start = ' marker-start="url(#arrow)"' if e["bidir"] else ""
        out.append(f'<path d="{path}" fill="none" stroke="#333" stroke-width="1.8"{dash}{start} '
                   f'marker-end="url(#arrow)"/>')
    out.extend(tabs)

    for n in nodes.values():
        if n["effort"]:
            fill = palette(n["slot"], n["effort"])
            stroke = hsl_hex(hue_at(SLOTS[n["slot"]][1]), 70, 30)
            out.append(f'<rect x="{n["x"]:.1f}" y="{n["y"]:.1f}" width="{n["w"]}" height="{n["h"]}" rx="12" '
                       f'fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
            out.append(f'<text x="{n["cx"]:.1f}" y="{n["y"] + 26:.1f}" font-size="{title_font(n["name"])}" '
                       f'font-weight="700" text-anchor="middle" fill="#111">{esc(n["name"])}</text>')
            out.append(f'<text x="{n["cx"]:.1f}" y="{n["y"] + 47:.1f}" font-size="14" font-weight="600" '
                       f'text-anchor="middle" fill="#222">{esc(n["model"])} / {n["effort"]}</text>')
            for i, line in enumerate(n["desc"]):
                out.append(f'<text x="{n["cx"]:.1f}" y="{n["y"] + 66 + 16 * i:.1f}" font-size="12" '
                           f'text-anchor="middle" fill="#333">{esc(line)}</text>')
        else:
            out.append(f'<rect x="{n["x"]:.1f}" y="{n["y"]:.1f}" width="{n["w"]}" height="{n["h"]}" rx="27" '
                       f'fill="#2b2b2b" stroke="#111" stroke-width="2"/>')
            out.append(f'<text x="{n["cx"]:.1f}" y="{n["cy"] + 5:.1f}" font-size="13" font-weight="600" '
                       f'text-anchor="middle" fill="#fff">{esc(n["name"])}</text>')

    placed: list[tuple[float, float, float]] = []  # (x_center, y_center, width) of labels already drawn
    for e in edges:  # edge labels on top, nudged down until they stop overlapping
        if not e["text"]:
            continue
        _, (mx, my) = edge_path(e)
        w = len(e["text"]) * 6.6 + 16
        for _ in range(8):
            if not any(abs(mx - px) < (w + pw) / 2 and abs(my - py) < 24 for px, py, pw in placed):
                break
            my += 24
        placed.append((mx, my, w))
        out.append(f'<rect x="{mx - w / 2:.1f}" y="{my - 11:.1f}" width="{w:.1f}" height="22" rx="11" '
                   f'fill="#ffffff" fill-opacity="0.94" stroke="#bbb" stroke-width="1"/>')
        out.append(f'<text x="{mx:.1f}" y="{my + 4:.1f}" font-size="12" text-anchor="middle" '
                   f'fill="#222">{esc(e["text"])}</text>')

    ly = gy + geo["grid_h"] + 30  # legend: hue = model, vibrancy = effort
    out.append(f'<text x="{PAD}" y="{ly + 16}" font-size="13" font-weight="600" fill="#444">Color key</text>')
    lx = PAD + 100
    for s, (name, _) in enumerate(SLOTS):
        for effort in EFFORT_ROWS:
            out.append(f'<rect x="{lx}" y="{ly}" width="44" height="24" rx="5" fill="{palette(s, effort)}" '
                       f'stroke="#555" stroke-width="1"/>')
            lx += 48
        out.append(f'<text x="{lx + 2}" y="{ly + 17}" font-size="13" fill="#444">{name}</text>')
        lx += 70
    out.append(f'<text x="{lx + 10}" y="{ly + 17}" font-size="13" fill="#666">hue = model, '
               f'vibrancy = effort (high, medium, low)</text>')
    merged_groups = [n["members"] for n in model_nodes if len(n["members"]) > 1]
    if merged_groups:
        note = "; ".join(" + ".join(g) for g in merged_groups)
        out.append(f'<text x="{PAD}" y="{ly + 52}" font-size="13" fill="#666">Squashed roles (same model and '
                   f'effort, so no context handoff): {esc(note)}</text>')
    out.append("</svg>")
    return "\n".join(out)


ROLE_FACE = {  # how each party role is drawn: (name, description lines)
    "leader": ("Leader (the session)", ["devises the plan, writes the contract", "(signatures + Google docstrings),",
                                        "fixes low-level spec bugs", "(one clarification, then up)"]),
    "doer": ("Fighters (doers, coders)", ["a team: fill the bodies, run the check"]),
    "reader": ("Scout (reader)", ["read-only"]),
    "oracle": ("Oracle (wild card)", ["get-out-of-jail card:", "replans from the evidence"]),
}
PARTY_FLOW = [("leader", "doer", "file sets / bug reports"), ("leader", "reader", "reading / digest"),
              ("leader", "oracle", "stuck + evidence / better spec")]


def party_graph(party, binding: dict) -> tuple:
    """(nodes, edges, groups, slots) for a party resolved by party.py -- no Mermaid involved."""
    nodes = {"User": parse_label("User", "User request")}
    for r in party.roles:
        name, desc = ROLE_FACE[r.role]
        nodes[r.role] = {"id": r.role, "name": name, "model": r.model, "effort": r.effort, "desc": list(desc)}
    edges = [{"src": "User", "dst": "leader", "dotted": False, "bidir": False, "text": ""}]
    edges += [{"src": a, "dst": b, "dotted": False, "bidir": True, "text": t} for a, b, t in PARTY_FLOW
              if a in nodes and b in nodes]
    cands = binding.get("candidates", {})
    light = list(cands.get("light") or [binding["L0"]])
    mid = list(cands.get("mid") or [binding["L1"]])
    heavy = [m for m in (cands.get("heavy") or [binding["L3"]]) if m not in mid and m not in light]
    slots = {0: light, 1: mid}
    if heavy:                       # no heavy lane when the heavy tier is the mid model at high effort
        slots[2] = heavy
    return nodes, edges, party.groups, slots


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="*", type=Path, help="markdown files containing a mermaid flowchart")
    ap.add_argument("-o", "--out", type=Path, help="output path (single input only)")
    ap.add_argument("--title", help="override the heading")
    ap.add_argument("--party", metavar="HARNESS[:PROVIDER]",
                    help="draw straight from tiers.toml via party.py instead of reading Mermaid")
    ap.add_argument("--window", help="with --party: clamp the dial to lo:hi step indices, e.g. 0:2")
    args = ap.parse_args(argv)
    if args.party:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        import render_agents
        from party import parse_open_window, resolve_party
        harness, _, provider = args.party.partition(":")
        schema = render_agents.load_schema()
        party = resolve_party(schema, harness, provider or None, parse_open_window(args.window))
        nodes, edges, groups, slots = party_graph(party, schema["binding"][party.provider])
        dest = args.out or Path(__file__).resolve().parent / f"{harness}-{party.provider}.svg"
        dest.write_text(render(nodes, edges, args.title, slots, groups), encoding="utf-8")
        print(f"{args.party} -> {dest}  ({len(nodes)} nodes, {len(edges)} edges, groups {party.groups})")
        return 0
    if not args.inputs:
        ap.error("give markdown inputs or --party HARNESS[:PROVIDER]")
    if args.out and len(args.inputs) != 1:
        ap.error("-o needs exactly one input")
    for src in args.inputs:
        text = src.read_text(encoding="utf-8")
        nodes, edges = parse_markdown(text)
        slots, md_title = parse_directives(text)
        dest = args.out or src.with_suffix(".svg")
        dest.write_text(render(nodes, edges, args.title or md_title, slots), encoding="utf-8")
        print(f"{src.name} -> {dest}  ({len(nodes)} nodes, {len(edges)} edges)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
