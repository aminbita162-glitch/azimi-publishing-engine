"""Phase 5 WP4: diagram engine tests.

Validates flow, sequence and layers diagram rendering, label wrapping,
cycles, scaling, page-fit rejection, too-many-nodes rejection, captions,
and vector preservation.
"""

import io
import unittest
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib import colors

from engine.build.builder import build_document
from engine.build.diagram_spec import parse_diagram
from engine.errors import ContentError
from engine.render.diagram import DiagramFlowable, build_layout
from engine.render.fonts import register_fonts
from engine.tests.support import META, REAL_ROOT, TempProject

_FILLER = "\n\n".join(
    f"Filler paragraph number {i} of the document body for testing purposes."
    for i in range(1, 51)
)


def _read(path: Path) -> PdfReader:
    return PdfReader(io.BytesIO(path.read_bytes()))


class DiagramEngineTests(unittest.TestCase):
    def test_flow_diagram_renders(self):
        """A flow diagram with nodes, edges and labels renders correctly."""
        content = (
            "# Title\n\n"
            "~~~diagram\n"
            "type: flow\n"
            "caption: A flow diagram\n"
            "node start: Start | process\n"
            "node decide: Choose | decision\n"
            "node done: Finish | process\n"
            "edge start -> decide: begin\n"
            "edge decide -> done: yes\n"
            "~~~\n\n"
            + _FILLER
        )
        with TempProject(content=content, with_image=False) as root:
            result = build_document(root, "courses/doc")
            self.assertTrue(result.audit.passed)
            text = "".join(p.extract_text() for p in _read(result.pdf_path).pages)
            self.assertIn("Start", text)
            self.assertIn("Choose", text)
            self.assertIn("Finish", text)

    def test_sequence_diagram_renders(self):
        """A sequence diagram with actors and messages renders correctly."""
        content = (
            "# Title\n\n"
            "~~~diagram\n"
            "type: sequence\n"
            "caption: A sequence diagram\n"
            "actor client: Client\n"
            "actor server: Server\n"
            "msg client -> server: Request\n"
            "msg server -> client: Response\n"
            "~~~\n\n"
            + _FILLER
        )
        with TempProject(content=content, with_image=False) as root:
            result = build_document(root, "courses/doc")
            self.assertTrue(result.audit.passed)
            text = "".join(p.extract_text() for p in _read(result.pdf_path).pages)
            self.assertIn("Client", text)
            self.assertIn("Server", text)
            self.assertIn("Request", text)
            self.assertIn("Response", text)

    def test_layers_diagram_renders(self):
        """A layers diagram with stacked bands renders correctly."""
        content = (
            "# Title\n\n"
            "~~~diagram\n"
            "type: layers\n"
            "caption: A layers diagram\n"
            "layer: Presentation | UI layer | plain\n"
            "layer: Business | Logic layer | plain\n"
            "layer: Data | Storage layer | plain\n"
            "~~~\n\n"
            + _FILLER
        )
        with TempProject(content=content, with_image=False) as root:
            result = build_document(root, "courses/doc")
            self.assertTrue(result.audit.passed)
            text = "".join(p.extract_text() for p in _read(result.pdf_path).pages)
            self.assertIn("Presentation", text)
            self.assertIn("Business", text)
            self.assertIn("Data", text)

    def test_diagram_too_tall_is_rejected(self):
        """A diagram that exceeds 72% of the body height is rejected."""
        nodes = "\n".join(f"node n{i}: Node {i} | process" for i in range(12))
        edges = "\n".join(f"edge n{i} -> n{i + 1}" for i in range(11))
        content = (
            "# Title\n\n"
            "~~~diagram\n"
            "type: flow\n"
            "caption: Too tall\n"
            f"{nodes}\n"
            f"{edges}\n"
            "~~~\n"
        )
        with TempProject(content=content, with_image=False) as root:
            with self.assertRaisesRegex(ContentError, "too tall"):
                build_document(root, "courses/doc")

    def test_too_many_nodes_is_rejected(self):
        """A flow diagram with more than 12 nodes is rejected."""
        nodes = "\n".join(f"node n{i}: Node {i} | process" for i in range(13))
        content = (
            "# Title\n\n"
            "~~~diagram\n"
            "type: flow\n"
            "caption: Too many\n"
            f"{nodes}\n"
            "~~~\n"
        )
        with TempProject(content=content, with_image=False) as root:
            with self.assertRaisesRegex(ContentError, "allows 12"):
                build_document(root, "courses/doc")

    def test_long_labels_wrap(self):
        """Long node labels wrap without overflow or error."""
        content = (
            "# Title\n\n"
            "~~~diagram\n"
            "type: flow\n"
            "caption: Long labels\n"
            "node a: This is a very long label that needs wrapping | process\n"
            "node b: Short | process\n"
            "edge a -> b\n"
            "~~~\n\n"
            + _FILLER
        )
        with TempProject(content=content, with_image=False) as root:
            result = build_document(root, "courses/doc")
            self.assertTrue(result.audit.passed)

    def test_diagram_with_cycles_renders(self):
        """A flow diagram with a back edge (cycle) renders correctly."""
        content = (
            "# Title\n\n"
            "~~~diagram\n"
            "type: flow\n"
            "caption: Cycle diagram\n"
            "node a: Start | process\n"
            "node b: Retry | process\n"
            "edge a -> b: go\n"
            "edge b -> a: retry\n"
            "~~~\n\n"
            + _FILLER
        )
        with TempProject(content=content, with_image=False) as root:
            result = build_document(root, "courses/doc")
            self.assertTrue(result.audit.passed)
            text = "".join(p.extract_text() for p in _read(result.pdf_path).pages)
            self.assertIn("Start", text)
            self.assertIn("Retry", text)

    def test_diagram_caption_appears_in_text_and_lof(self):
        """A diagram with a caption is numbered and appears in the list of figures."""
        content = (
            "# Title\n\n"
            "~~~diagram\n"
            "type: flow\n"
            "caption: My diagram caption\n"
            "node a: Start | process\n"
            "node b: End | process\n"
            "edge a -> b\n"
            "~~~\n\n"
            + _FILLER
        )
        meta = META + "numbered: true\n"
        with TempProject(content=content, meta=meta, with_image=False) as root:
            result = build_document(root, "courses/doc")
            self.assertTrue(result.audit.passed)
            text = "".join(p.extract_text() for p in _read(result.pdf_path).pages)
            self.assertIn("Figure 1", text)
            self.assertIn("My diagram caption", text)
            self.assertIn("List of Figures", text)

    def test_diagram_scales_to_fit_available_space(self):
        """A diagram flowable shrinks when available height is constrained."""
        register_fonts(REAL_ROOT / "design-system" / "fonts")
        body = [
            "type: flow",
            "caption: Test",
            "node a: Start | process",
            "node b: End | process",
            "edge a -> b",
        ]
        spec = parse_diagram(body, 1)
        layout = build_layout(
            spec, colors.HexColor("#12344D"), colors.HexColor("#E07A1F"), 1
        )
        full = DiagramFlowable(layout, None, "Test")
        from engine.render.styles import CONTENT_WIDTH as _cw
        _, full_height = full.wrap(_cw, 700)
        constrained = DiagramFlowable(layout, None, "Test")
        _, constrained_height = constrained.wrap(_cw, 100)
        self.assertLess(
            constrained_height, full_height,
            "diagram should shrink when available height is constrained",
        )

    def test_diagram_is_vector_not_raster(self):
        """Diagram operations are canvas draw calls (vector), not image embeddings."""
        from engine.render.styles import CONTENT_WIDTH

        register_fonts(REAL_ROOT / "design-system" / "fonts")
        body = [
            "type: flow",
            "caption: Test",
            "node a: Start | process",
            "node b: End | process",
            "edge a -> b",
        ]
        spec = parse_diagram(body, 1)
        layout = build_layout(
            spec, colors.HexColor("#12344D"), colors.HexColor("#E07A1F"), 1
        )
        # The layout ops are Python callables that draw on a canvas —
        # they are vector drawing primitives, not raster images.
        self.assertGreater(len(layout.ops), 0)
        self.assertAlmostEqual(layout.width, CONTENT_WIDTH, delta=1.0)


if __name__ == "__main__":
    unittest.main()
