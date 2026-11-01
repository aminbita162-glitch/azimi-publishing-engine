"""Text description of diagrams (a ~~~diagram block in content.md).

The description is validated here and drawn by engine.render.diagram. Three kinds exist:

flow       boxes and arrows laid out in ranks (flows, pipelines, state lifecycles)
sequence   actors with lifelines and numbered messages
layers     stacked bands (architectures, trust levels)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from ..errors import ContentError

KINDS = ("flow", "sequence", "layers")
NODE_KINDS = ("process", "decision", "ok", "deny", "store", "actor", "state")
LAYER_KINDS = ("plain", "ok", "deny", "key")
MAX_NODES = 12
MAX_EDGES = 24
MAX_MESSAGES = 16
MAX_ACTORS = 5
MAX_LAYERS = 8
MAX_LABEL = 70

_ID = re.compile(r"^[a-z][a-z0-9_]{0,23}$")
_REF_ID = re.compile(r"^[a-z][a-z0-9-]{0,39}$")
_NODE = re.compile(r"^node\s+([a-z][a-z0-9_]*)\s*:\s*(.+)$")
_EDGE = re.compile(r"^edge\s+([a-z][a-z0-9_]*)\s*(->|\.\.>)\s*([a-z][a-z0-9_]*)\s*(?::\s*(.*))?$")
_ACTOR = re.compile(r"^actor\s+([a-z][a-z0-9_]*)\s*:\s*(.+)$")
_MESSAGE = re.compile(r"^(msg|reply)\s+([a-z][a-z0-9_]*)\s*(?:->|-->)\s*([a-z][a-z0-9_]*)\s*:\s*(.+)$")
_HTML = re.compile(r"</?[A-Za-z!]")


@dataclass(frozen=True)
class Node:
    id: str
    label: str
    kind: str


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    label: str
    dashed: bool


@dataclass(frozen=True)
class Message:
    source: str
    target: str
    label: str
    reply: bool


@dataclass(frozen=True)
class Step:
    label: str


@dataclass(frozen=True)
class Layer:
    name: str
    text: str
    kind: str


@dataclass(frozen=True)
class DiagramSpec:
    kind: str
    ref_id: Optional[str]
    caption: Optional[str]
    direction: str
    nodes: Tuple[Node, ...]
    edges: Tuple[Edge, ...]
    actors: Tuple[Node, ...]
    messages: Tuple[object, ...]
    layers: Tuple[Layer, ...]


def _text(value: str, line: int, what: str) -> str:
    value = value.strip()
    if not value:
        raise ContentError(f"diagram {what} is empty", line)
    if len(value) > 160 or (what != "caption" and len(value) > MAX_LABEL * 2):
        raise ContentError(f"diagram {what} is too long", line)
    if _HTML.search(value) or any(ord(ch) < 32 for ch in value):
        raise ContentError(f"diagram {what} contains unsupported characters", line)
    return value


def parse_diagram(body: List[str], first_line: int) -> DiagramSpec:
    """Validate the lines of a diagram block. first_line is the 1-based line of body[0]."""
    kind: Optional[str] = None
    ref_id: Optional[str] = None
    caption: Optional[str] = None
    direction = "down"
    nodes: List[Node] = []
    edges: List[Edge] = []
    actors: List[Node] = []
    messages: List[object] = []
    layers: List[Layer] = []

    for offset, raw in enumerate(body):
        line = first_line + offset
        text = raw.strip()
        if not text:
            continue
        if text.startswith("type:"):
            kind = text[5:].strip()
            if kind not in KINDS:
                raise ContentError("diagram type must be one of: " + ", ".join(KINDS), line)
        elif text.startswith("id:"):
            ref_id = text[3:].strip()
            if not _REF_ID.match(ref_id):
                raise ContentError("diagram id must be lowercase letters, digits and hyphens", line)
        elif text.startswith("caption:"):
            caption = _text(text[8:], line, "caption")
        elif text.startswith("direction:"):
            direction = text[10:].strip()
            if direction != "down":
                raise ContentError("diagram direction must be down", line)
        elif text.startswith("node "):
            match = _NODE.match(text)
            if not match:
                raise ContentError("node syntax is: node id: Label | kind", line)
            label, _, node_kind = match.group(2).partition("|")
            node_kind = node_kind.strip() or "process"
            if node_kind not in NODE_KINDS:
                raise ContentError("node kind must be one of: " + ", ".join(NODE_KINDS), line)
            nodes.append(Node(match.group(1), _text(label, line, "label"), node_kind))
        elif text.startswith("edge "):
            match = _EDGE.match(text)
            if not match:
                raise ContentError("edge syntax is: edge a -> b: label", line)
            label = _text(match.group(4), line, "label") if match.group(4) and match.group(4).strip() else ""
            edges.append(Edge(match.group(1), match.group(3), label, match.group(2) == "..>"))
        elif text.startswith("actor "):
            match = _ACTOR.match(text)
            if not match:
                raise ContentError("actor syntax is: actor id: Label", line)
            actors.append(Node(match.group(1), _text(match.group(2), line, "label"), "actor"))
        elif text.startswith(("msg ", "reply ")):
            match = _MESSAGE.match(text)
            if not match:
                raise ContentError("message syntax is: msg a -> b: text", line)
            messages.append(
                Message(match.group(2), match.group(3), _text(match.group(4), line, "label"), match.group(1) == "reply")
            )
        elif text.startswith("step:"):
            messages.append(Step(_text(text[5:], line, "label")))
        elif text.startswith("layer:"):
            parts = [part.strip() for part in text[6:].split("|")]
            if len(parts) not in (2, 3):
                raise ContentError("layer syntax is: layer: Name | description | kind", line)
            layer_kind = parts[2] if len(parts) == 3 else "plain"
            if layer_kind not in LAYER_KINDS:
                raise ContentError("layer kind must be one of: " + ", ".join(LAYER_KINDS), line)
            layers.append(Layer(_text(parts[0], line, "label"), _text(parts[1], line, "label"), layer_kind))
        else:
            raise ContentError("unknown diagram line", line)

    if kind is None:
        raise ContentError("a diagram needs a type: line", first_line)
    if caption is None:
        raise ContentError("a diagram needs a caption: line (it is also the text alternative)", first_line)

    if kind == "flow":
        if not nodes or edges is None:
            raise ContentError("a flow diagram needs nodes", first_line)
        if len(nodes) > MAX_NODES or len(edges) > MAX_EDGES:
            raise ContentError(f"a flow diagram allows {MAX_NODES} nodes and {MAX_EDGES} edges", first_line)
        known = {node.id for node in nodes}
        if len(known) != len(nodes):
            raise ContentError("node ids must be unique", first_line)
        for edge in edges:
            if edge.source not in known or edge.target not in known or edge.source == edge.target:
                raise ContentError(f"edge {edge.source} -> {edge.target} uses an unknown node", first_line)
        if actors or messages or layers:
            raise ContentError("a flow diagram cannot contain actors, messages or layers", first_line)
    elif kind == "sequence":
        if len(actors) < 2 or len(actors) > MAX_ACTORS:
            raise ContentError(f"a sequence diagram needs 2 to {MAX_ACTORS} actors", first_line)
        known = {actor.id for actor in actors}
        if len(known) != len(actors):
            raise ContentError("actor ids must be unique", first_line)
        if not messages or len(messages) > MAX_MESSAGES:
            raise ContentError(f"a sequence diagram needs 1 to {MAX_MESSAGES} messages", first_line)
        for message in messages:
            if isinstance(message, Message) and (message.source not in known or message.target not in known):
                raise ContentError(f"message {message.source} -> {message.target} uses an unknown actor", first_line)
        if nodes or edges or layers:
            raise ContentError("a sequence diagram cannot contain nodes, edges or layers", first_line)
    else:
        if not layers or len(layers) > MAX_LAYERS:
            raise ContentError(f"a layers diagram needs 1 to {MAX_LAYERS} layers", first_line)
        if nodes or edges or actors or messages:
            raise ContentError("a layers diagram can only contain layers", first_line)

    return DiagramSpec(
        kind=kind, ref_id=ref_id, caption=caption, direction=direction,
        nodes=tuple(nodes), edges=tuple(edges), actors=tuple(actors),
        messages=tuple(messages), layers=tuple(layers),
    )
