"""Deterministic vector diagrams drawn from a DiagramSpec.

A diagram is laid out with plain arithmetic (no randomness, no clock), drawn with
ReportLab canvas primitives and set in the bundled fonts, so it stays sharp at any
zoom and identical on every machine.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import Flowable, Paragraph

from ..build.diagram_spec import DiagramSpec, Message, Step
from ..errors import ContentError
from .fonts import check_glyphs
from .styles import CONTENT_HEIGHT, CONTENT_WIDTH, MUTED, RULE, TEXT, WARNING, mix_with_white

NODE_FONT = 10.0
EDGE_FONT = 9.0
MIN_DIAGRAM_SCALE = 0.85
MAX_DIAGRAM_HEIGHT = CONTENT_HEIGHT * 0.72
DIAGRAM_SPACE_AFTER = 12.0
CAPTION_GAP = 6.0

OK_STROKE = colors.HexColor("#1E7B3A")
OK_FILL = colors.HexColor("#E6F4EA")
DENY_FILL = colors.HexColor("#FDECEA")
ARROW = colors.HexColor("#3E4C5E")

Op = Callable[[object], None]


@dataclass
class _Layout:
    width: float
    height: float
    ops: List[Op]


def _lines(text: str, font: str, size: float, width: float) -> List[str]:
    return simpleSplit(text, font, size, max(width, 20.0)) or [text]


def _arrowhead(canvas, x: float, y: float, dx: float, dy: float, color) -> None:
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    size = 6.0
    left = (x - ux * size - uy * size * 0.45, y - uy * size + ux * size * 0.45)
    right = (x - ux * size + uy * size * 0.45, y - uy * size - ux * size * 0.45)
    canvas.setFillColor(color)
    path = canvas.beginPath()
    path.moveTo(x, y)
    path.lineTo(*left)
    path.lineTo(*right)
    path.close()
    canvas.drawPath(path, stroke=0, fill=1)


def _centered(canvas, lines: Sequence[str], font: str, size: float, color, cx: float, cy: float) -> None:
    leading = size * 1.2
    canvas.setFont(font, size)
    canvas.setFillColor(color)
    top = cy + (len(lines) * leading) / 2.0 - size * 0.82
    for index, text in enumerate(lines):
        canvas.drawCentredString(cx, top - index * leading, text)


def _label_tag(canvas, text: str, cx: float, cy: float, size: float = EDGE_FONT) -> None:
    width = pdfmetrics.stringWidth(text, "Body", size) + 6
    canvas.setFillColor(colors.white)
    canvas.rect(cx - width / 2, cy - size * 0.5 - 1.5, width, size + 3, stroke=0, fill=1)
    canvas.setFillColor(TEXT)
    canvas.setFont("Body", size)
    canvas.drawCentredString(cx, cy - size * 0.32, text)


def _node_style(kind: str, primary, accent):
    if kind == "decision":
        return mix_with_white(accent, 0.85), accent, 1.6, TEXT
    if kind == "ok":
        return OK_FILL, OK_STROKE, 1.4, TEXT
    if kind == "deny":
        return DENY_FILL, WARNING, 1.4, TEXT
    if kind == "store":
        return colors.HexColor("#EEF1F5"), MUTED, 1.2, TEXT
    if kind == "actor":
        return primary, primary, 1.0, colors.white
    return colors.white, primary, 1.2, TEXT


# ---------------------------------------------------------------- flow


def _ranks(spec: DiagramSpec) -> Tuple[Dict[str, int], List[Tuple[str, str]]]:
    """Longest-path ranks over the forward edges; returns (rank, back_edges)."""
    order = [node.id for node in spec.nodes]
    out: Dict[str, List[str]] = {node_id: [] for node_id in order}
    for edge in spec.edges:
        out[edge.source].append(edge.target)
    state: Dict[str, int] = {}
    back: List[Tuple[str, str]] = []

    def visit(node_id: str) -> None:
        state[node_id] = 1
        for target in out[node_id]:
            if state.get(target) == 1:
                back.append((node_id, target))
            elif target not in state:
                visit(target)
        state[node_id] = 2

    for node_id in order:
        if node_id not in state:
            visit(node_id)
    back_set = set(back)
    forward = [(e.source, e.target) for e in spec.edges if (e.source, e.target) not in back_set]
    rank = {node_id: 0 for node_id in order}
    for _ in range(len(order)):
        changed = False
        for source, target in forward:
            if rank[target] < rank[source] + 1:
                rank[target] = rank[source] + 1
                changed = True
        if not changed:
            break
    return rank, back


DUMMY_WIDTH = 16.0
ROW_GAP = 15 * mm
NODE_GAP = 9 * mm
DUMMY_GAP = 5 * mm


@dataclass
class _Item:
    key: str
    width: float
    height: float
    rank: int
    real: bool
    x: float = 0.0
    y: float = 0.0


def _flow_layout(spec: DiagramSpec, primary, accent, line: int) -> _Layout:
    """Layered layout: ranks from the longest path, long edges routed through waypoints, x by relaxation."""
    rank, back = _ranks(spec)
    back_set = set(back)
    count = max(rank.values()) + 1
    nodes = {node.id: node for node in spec.nodes}

    # oriented edges always point from a lower rank to a higher one
    chains: List[Tuple[int, str, str, bool, List[str]]] = []
    for index, edge in enumerate(spec.edges):
        reversed_edge = (edge.source, edge.target) in back_set
        upper, lower = (edge.target, edge.source) if reversed_edge else (edge.source, edge.target)
        waypoints = [f"~{index}.{r}" for r in range(rank[upper] + 1, rank[lower])]
        chains.append((index, upper, lower, reversed_edge, waypoints))

    items: Dict[str, _Item] = {}
    rows: List[List[str]] = [[] for _ in range(count)]
    for node in spec.nodes:
        rows[rank[node.id]].append(node.id)
    for index, upper, lower, _rev, waypoints in chains:
        for offset, key in enumerate(waypoints):
            r = rank[upper] + 1 + offset
            rows[r].append(key)
            items[key] = _Item(key, DUMMY_WIDTH, 0.0, r, False)

    # node size: the width is shared by all real nodes
    most = 1
    narrowest = 64 * mm
    for row in rows:
        real = [k for k in row if k in nodes]
        dummies = len(row) - len(real)
        if not real:
            continue
        gaps = sum(NODE_GAP if (a in nodes and b in nodes) else DUMMY_GAP for a, b in zip(row, row[1:]))
        available = CONTENT_WIDTH - dummies * DUMMY_WIDTH - gaps
        narrowest = min(narrowest, available / len(real))
        most = max(most, len(real))
    node_w = narrowest
    if node_w < 30 * mm:
        raise ContentError("too many nodes in one rank; split the diagram", line)
    wrapped_labels: Dict[str, List[str]] = {}
    for node in spec.nodes:
        font = "Body-Bold" if node.kind == "actor" else "Body"
        wrapped_labels[node.id] = _lines(node.label, font, NODE_FONT, node_w - 14)
        items[node.id] = _Item(
            node.id, node_w, max(30.0, len(wrapped_labels[node.id]) * NODE_FONT * 1.2 + 16), rank[node.id], True
        )

    # order inside each rank: barycenter sweeps, keeping the ordering with the fewest crossings
    above: Dict[str, List[str]] = {key: [] for key in items}
    below: Dict[str, List[str]] = {key: [] for key in items}
    links: List[Tuple[str, str]] = []
    for _index, upper, lower, _rev, waypoints in chains:
        path = [upper] + waypoints + [lower]
        for first, second in zip(path, path[1:]):
            above[second].append(first)
            below[first].append(second)
            links.append((first, second))

    def crossings(layout: List[List[str]]) -> int:
        slot = {key: i for row in layout for i, key in enumerate(row)}
        total = 0
        for r in range(count - 1):
            pairs = sorted((slot[a], slot[b]) for a, b in links if items[a].rank == r)
            for i in range(len(pairs)):
                for j in range(i + 1, len(pairs)):
                    if pairs[i][0] < pairs[j][0] and pairs[i][1] > pairs[j][1]:
                        total += 1
        return total

    best = [list(row) for row in rows]
    best_score = crossings(best)
    current = [list(row) for row in rows]
    for sweep in range(6):
        downward = sweep % 2 == 0
        indices = range(1, count) if downward else range(count - 2, -1, -1)
        for r in indices:
            slot = {key: i for row in current for i, key in enumerate(row)}
            neighbours = above if downward else below
            keyed = []
            for position, key in enumerate(current[r]):
                around = [slot[o] for o in neighbours[key]]
                keyed.append((sum(around) / len(around) if around else float(position), position, key))
            current[r] = [key for _, _, key in sorted(keyed)]
        score = crossings(current)
        if score < best_score:
            best, best_score = [list(row) for row in current], score
    rows[:] = best

    def gap_between(a: str, b: str) -> float:
        return NODE_GAP if (items[a].real and items[b].real) else DUMMY_GAP

    def place(row: List[str], desired: List[float]) -> None:
        centers: List[float] = []
        for i, key in enumerate(row):
            c = desired[i]
            if i > 0:
                prev = row[i - 1]
                c = max(c, centers[-1] + (items[prev].width + items[key].width) / 2 + gap_between(prev, key))
            centers.append(c)
        for i in range(len(row) - 1, -1, -1):
            limit = CONTENT_WIDTH - items[row[i]].width / 2
            if i < len(row) - 1:
                nxt = row[i + 1]
                limit = min(limit, centers[i + 1] - (items[row[i]].width + items[nxt].width) / 2 - gap_between(row[i], nxt))
            centers[i] = min(centers[i], limit)
        for i, key in enumerate(row):
            floor = items[key].width / 2
            if i > 0:
                prev = row[i - 1]
                floor = max(floor, centers[i - 1] + (items[prev].width + items[key].width) / 2 + gap_between(prev, key))
            centers[i] = max(centers[i], floor)
            items[key].x = centers[i]

    for row in rows:
        total = sum(items[k].width for k in row) + sum(gap_between(a, b) for a, b in zip(row, row[1:]))
        cursor = (CONTENT_WIDTH - total) / 2
        desired = []
        for key in row:
            desired.append(cursor + items[key].width / 2)
            cursor += items[key].width + (gap_between(key, row[row.index(key) + 1]) if row.index(key) + 1 < len(row) else 0)
        place(row, desired)
    sweeps = [("down", range(1, count)), ("up", range(count - 2, -1, -1)), ("down", range(1, count))]
    for direction, sequence in sweeps:
        for r in sequence:
            neighbours = above if direction == "down" else below
            desired = []
            for key in rows[r]:
                others = [items[o].x for o in neighbours[key]]
                desired.append(sum(others) / len(others) if others else items[key].x)
            place(rows[r], desired)

    low = min(item.x - item.width / 2 for item in items.values())
    high = max(item.x + item.width / 2 for item in items.values())
    shift = (CONTENT_WIDTH - (high - low)) / 2 - low
    for item in items.values():
        item.x += shift

    row_heights = [max([items[k].height for k in row] + [14.0]) for row in rows]
    row_centers: List[float] = []
    cursor = 0.0
    for r in range(count):
        row_centers.append(cursor + row_heights[r] / 2)
        cursor += row_heights[r] + ROW_GAP
    height = cursor - ROW_GAP
    if height > MAX_DIAGRAM_HEIGHT:
        raise ContentError("diagram is too tall; split it into two diagrams", line)
    for item in items.values():
        item.y = row_centers[item.rank]

    # attachment points: spread the edges that meet one side of a node
    bottoms: Dict[str, List[Tuple[float, int]]] = {key: [] for key in items}
    tops: Dict[str, List[Tuple[float, int]]] = {key: [] for key in items}
    for index, upper, lower, _rev, waypoints in chains:
        path = [upper] + waypoints + [lower]
        bottoms[upper].append((items[path[1]].x, index))
        tops[lower].append((items[path[-2]].x, index))
    port_bottom: Dict[Tuple[str, int], float] = {}
    port_top: Dict[Tuple[str, int], float] = {}
    for key, entries in bottoms.items():
        entries.sort()
        for i, (_x, index) in enumerate(entries):
            item = items[key]
            port_bottom[(key, index)] = item.x - item.width * 0.32 + item.width * 0.64 * (i + 0.5) / len(entries) if item.real else item.x
    for key, entries in tops.items():
        entries.sort()
        for i, (_x, index) in enumerate(entries):
            item = items[key]
            port_top[(key, index)] = item.x - item.width * 0.32 + item.width * 0.64 * (i + 0.5) / len(entries) if item.real else item.x

    ops: List[Op] = []

    def to_y(y: float) -> float:
        return height - y

    for index, upper, lower, reversed_edge, waypoints in chains:
        edge = spec.edges[index]
        points: List[Tuple[float, float]] = [
            (port_bottom[(upper, index)], to_y(items[upper].y + (items[upper].height / 2 if items[upper].real else 0)))
        ]
        for key in waypoints:
            points.append((items[key].x, to_y(items[key].y)))
        points.append(
            (port_top[(lower, index)], to_y(items[lower].y - (items[lower].height / 2 if items[lower].real else 0)))
        )
        if reversed_edge:
            points.reverse()

        def draw_edge(canvas, edge=edge, points=points, edge_reversed=reversed_edge):
            canvas.setStrokeColor(ARROW)
            canvas.setLineWidth(1.1)
            if edge.dashed:
                canvas.setDash(4, 3)
            path = canvas.beginPath()
            path.moveTo(*points[0])
            for point in points[1:]:
                path.lineTo(*point)
            canvas.drawPath(path, stroke=1, fill=0)
            canvas.setDash()
            (x1, y1), (x2, y2) = points[-2], points[-1]
            _arrowhead(canvas, x2, y2, x2 - x1, y2 - y1, ARROW)
            if edge.label:
                (ax, ay), (bx, by) = points[0], points[1]
                if edge_reversed:
                    (ax, ay), (bx, by) = points[-1], points[-2]
                _label_tag(canvas, edge.label, ax + (bx - ax) * 0.4, ay + (by - ay) * 0.4)

        ops.append(draw_edge)

    for node in spec.nodes:
        item = items[node.id]
        fill, stroke, stroke_width, text_color = _node_style(node.kind, primary, accent)
        wrapped = wrapped_labels[node.id]

        def draw_node(canvas, node=node, item=item, fill=fill, stroke=stroke, stroke_width=stroke_width,
                      text_color=text_color, wrapped=wrapped):
            canvas.setFillColor(fill)
            canvas.setStrokeColor(stroke)
            canvas.setLineWidth(stroke_width)
            radius = item.height / 2 if node.kind == "state" else 5
            bottom = to_y(item.y) - item.height / 2
            canvas.roundRect(item.x - item.width / 2, bottom, item.width, item.height, radius, stroke=1, fill=1)
            if node.kind == "store":
                canvas.setLineWidth(3)
                canvas.line(item.x - item.width / 2 + 4, bottom + item.height - 1.5,
                            item.x + item.width / 2 - 4, bottom + item.height - 1.5)
            _centered(canvas, wrapped, "Body-Bold" if node.kind == "actor" else "Body", NODE_FONT,
                      text_color, item.x, to_y(item.y))

        ops.append(draw_node)

    return _Layout(CONTENT_WIDTH, height, ops)


# ---------------------------------------------------------------- sequence


def _sequence_layout(spec: DiagramSpec, primary, accent, line: int) -> _Layout:
    count = len(spec.actors)
    column = CONTENT_WIDTH / count
    centers = {actor.id: (index + 0.5) * column for index, actor in enumerate(spec.actors)}
    head_w = min(column - 8, 42 * mm)
    head_lines = {
        actor.id: _lines(actor.label, "Body-Bold", NODE_FONT, head_w - 12) for actor in spec.actors
    }
    head_h = max(len(v) for v in head_lines.values()) * NODE_FONT * 1.2 + 14

    rows: List[Tuple[object, List[str], float]] = []
    number = 0
    for item in spec.messages:
        if isinstance(item, Step):
            rows.append((item, [item.label], 26.0))
            continue
        number += 1
        assert isinstance(item, Message)
        span = abs(centers[item.target] - centers[item.source])
        if item.source != item.target:
            width = max(span - 12, 96.0)
        else:
            x = centers[item.source]
            room = x - 26 if x > CONTENT_WIDTH * 0.6 else CONTENT_WIDTH - x - 26
            width = max(90.0, min(190.0, room))
        wrapped = _lines(f"{number}. {item.label}", "Body", EDGE_FONT, width)
        rows.append((item, wrapped, len(wrapped) * EDGE_FONT * 1.2 + 17))
    body_h = sum(row[2] for row in rows) + 10
    height = head_h + 10 + body_h
    if height > MAX_DIAGRAM_HEIGHT:
        raise ContentError("diagram is too tall; split it into two diagrams", line)

    ops: List[Op] = []

    def draw_lifelines(canvas):
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(1)
        canvas.setDash(3, 3)
        for actor in spec.actors:
            x = centers[actor.id]
            canvas.line(x, height - head_h, x, 0)
        canvas.setDash()

    ops.append(draw_lifelines)

    y = head_h + 10
    for item, wrapped, row_h in rows:
        if isinstance(item, Step):
            def draw_step(canvas, y=y, row_h=row_h, item=item):
                top = height - y
                canvas.setFillColor(mix_with_white(accent, 0.86))
                canvas.rect(0, top - row_h + 6, CONTENT_WIDTH, row_h - 10, stroke=0, fill=1)
                canvas.setFillColor(TEXT)
                canvas.setFont("Body-Bold", EDGE_FONT)
                canvas.drawCentredString(CONTENT_WIDTH / 2, top - row_h / 2 - 1, item.label)
            ops.append(draw_step)
        else:
            def draw_message(canvas, y=y, row_h=row_h, item=item, wrapped=wrapped):
                x1, x2 = centers[item.source], centers[item.target]
                axis = height - y - row_h + 7
                canvas.setStrokeColor(ARROW)
                canvas.setLineWidth(1.1)
                canvas.setDash(4, 3) if item.reply else canvas.setDash()
                if x1 == x2:
                    side = -1 if x1 > CONTENT_WIDTH * 0.6 else 1
                    canvas.line(x1, axis + 8, x1 + side * 16, axis + 8)
                    canvas.line(x1 + side * 16, axis + 8, x1 + side * 16, axis)
                    canvas.setDash()
                    canvas.line(x1 + side * 16, axis, x1 + side * 1, axis)
                    _arrowhead(canvas, x1 + side * 1, axis, -side, 0, ARROW)
                    text_x, align = x1 + side * 22, ("left" if side == 1 else "right")
                else:
                    canvas.line(x1, axis, x2, axis)
                    canvas.setDash()
                    direction = 1 if x2 > x1 else -1
                    _arrowhead(canvas, x2, axis, direction, 0, ARROW)
                    text_x, align = (x1 + x2) / 2, "center"
                canvas.setFillColor(TEXT)
                canvas.setFont("Body", EDGE_FONT)
                top_text = axis + 4 + (len(wrapped) - 1) * EDGE_FONT * 1.2
                for index, text in enumerate(wrapped):
                    baseline = top_text - index * EDGE_FONT * 1.2
                    if align == "center":
                        width = pdfmetrics.stringWidth(text, "Body", EDGE_FONT) + 4
                        canvas.setFillColor(colors.white)
                        canvas.rect(text_x - width / 2, baseline - 2, width, EDGE_FONT + 2, stroke=0, fill=1)
                        canvas.setFillColor(TEXT)
                        canvas.drawCentredString(text_x, baseline, text)
                    elif align == "right":
                        canvas.drawRightString(text_x, baseline, text)
                    else:
                        canvas.drawString(text_x, baseline, text)
            ops.append(draw_message)
        y += row_h

    for actor in spec.actors:
        cx = centers[actor.id]

        def draw_head(canvas, actor=actor, cx=cx):
            canvas.setFillColor(primary)
            canvas.setStrokeColor(primary)
            canvas.roundRect(cx - head_w / 2, height - head_h, head_w, head_h, 5, stroke=0, fill=1)
            _centered(canvas, head_lines[actor.id], "Body-Bold", NODE_FONT, colors.white, cx, height - head_h / 2)

        ops.append(draw_head)

    return _Layout(CONTENT_WIDTH, height, ops)


# ---------------------------------------------------------------- layers


def _layers_layout(spec: DiagramSpec, primary, accent, line: int) -> _Layout:
    name_w = 42 * mm
    gap = 4.0
    rows = []
    for layer in spec.layers:
        name_lines = _lines(layer.name, "Body-Bold", NODE_FONT, name_w - 14)
        text_lines = _lines(layer.text, "Body", NODE_FONT, CONTENT_WIDTH - name_w - 20)
        h = max(34.0, max(len(name_lines), len(text_lines)) * NODE_FONT * 1.25 + 16)
        rows.append((layer, name_lines, text_lines, h))
    height = sum(row[3] for row in rows) + gap * (len(rows) - 1)
    if height > MAX_DIAGRAM_HEIGHT:
        raise ContentError("diagram is too tall; split it into two diagrams", line)

    ops: List[Op] = []
    y = 0.0
    for layer, name_lines, text_lines, h in rows:
        def draw_layer(canvas, layer=layer, name_lines=name_lines, text_lines=text_lines, h=h, y=y):
            if layer.kind == "key":
                name_fill, name_color, edge = primary, colors.white, primary
            elif layer.kind == "ok":
                name_fill, name_color, edge = OK_STROKE, colors.white, OK_STROKE
            elif layer.kind == "deny":
                name_fill, name_color, edge = WARNING, colors.white, WARNING
            else:
                name_fill, name_color, edge = mix_with_white(primary, 0.88), TEXT, primary
            bottom = height - y - h
            canvas.setFillColor(name_fill)
            canvas.setStrokeColor(edge)
            canvas.setLineWidth(1.0)
            canvas.roundRect(0, bottom, name_w, h, 5, stroke=1, fill=1)
            canvas.setFillColor(colors.white)
            canvas.roundRect(name_w + gap, bottom, CONTENT_WIDTH - name_w - gap, h, 5, stroke=1, fill=1)
            _centered(canvas, name_lines, "Body-Bold", NODE_FONT, name_color, name_w / 2, bottom + h / 2)
            canvas.setFont("Body", NODE_FONT)
            canvas.setFillColor(TEXT)
            leading = NODE_FONT * 1.25
            top = bottom + h / 2 + (len(text_lines) * leading) / 2 - NODE_FONT * 0.85
            for index, text in enumerate(text_lines):
                canvas.drawString(name_w + gap + 10, top - index * leading, text)

        ops.append(draw_layer)
        y += h + gap

    return _Layout(CONTENT_WIDTH, height, ops)


# ---------------------------------------------------------------- flowable


def _all_text(spec: DiagramSpec) -> List[str]:
    texts = [n.label for n in spec.nodes] + [e.label for e in spec.edges if e.label]
    texts += [a.label for a in spec.actors]
    for item in spec.messages:
        texts.append(item.label)  # type: ignore[attr-defined]
    for layer in spec.layers:
        texts += [layer.name, layer.text]
    if spec.caption:
        texts.append(spec.caption)
    return texts


def build_layout(spec: DiagramSpec, primary, accent, line: int) -> _Layout:
    for text in _all_text(spec):
        check_glyphs(text, "Body", line)
    if spec.kind == "flow":
        return _flow_layout(spec, primary, accent, line)
    if spec.kind == "sequence":
        return _sequence_layout(spec, primary, accent, line)
    return _layers_layout(spec, primary, accent, line)


class DiagramFlowable(Flowable):
    """A vector diagram with an optional caption; it shrinks a little to use the space that is left."""

    def __init__(self, layout: _Layout, caption: Optional[Paragraph], alt: str) -> None:
        super().__init__()
        self._layout = layout
        self._caption = caption
        self.alt = alt
        self._scale = 1.0
        self._caption_height = 0.0
        self.hAlign = "CENTER"

    def wrap(self, available_width, available_height):
        self._caption_height = 0.0
        gap = 0.0
        if self._caption is not None:
            _, self._caption_height = self._caption.wrap(available_width, available_height)
            gap = CAPTION_GAP
        self._reserved = DIAGRAM_SPACE_AFTER + self._caption_height + gap
        room = available_height - self._reserved
        height = self._layout.height
        scale = 1.0
        if room < height:
            scale = max(MIN_DIAGRAM_SCALE, room / height) if room > 0 else MIN_DIAGRAM_SCALE
        self._scale = scale
        self._box_width = available_width
        return available_width, height * scale + self._reserved

    def draw(self):
        canvas = self.canv
        scale = self._scale
        left = (self._box_width - self._layout.width * scale) / 2
        bottom = self._reserved - DIAGRAM_SPACE_AFTER + (CAPTION_GAP if self._caption is not None else 0.0)
        bottom = DIAGRAM_SPACE_AFTER + self._caption_height + (CAPTION_GAP if self._caption is not None else 0.0)
        canvas.saveState()
        canvas.translate(left, bottom)
        canvas.scale(scale, scale)
        for op in self._layout.ops:
            canvas.saveState()
            op(canvas)
            canvas.restoreState()
        canvas.restoreState()
        if self._caption is not None:
            self._caption.drawOn(canvas, 0, DIAGRAM_SPACE_AFTER)
