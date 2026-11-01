"""Tests for the 0.4.0 features: numbering, cross-references, captions, diagrams, new checks."""

import io
import unittest

import yaml
from pypdf import PdfReader
from reportlab.lib import colors

from engine.audit import audit_pdf
from engine.build.builder import build_document
from engine.build.parser import Callout, Diagram, Heading, Image, Table, parse
from engine.errors import ConfigError, ContentError
from engine.render.document import analyze
from engine.render.styles import MIN_CONTRAST, contrast_ratio, ensure_contrast
from engine.schemas.meta import parse_meta
from engine.tests.support import META, TempProject

FLOW = """~~~diagram
type: flow
id: fig-flow
caption: A small flow.
node a: Start | actor
node b: Decide | decision
node c: Done | ok
node d: Refused | deny
edge a -> b: go
edge b -> c: yes
edge b -> d: no
edge c -> a: again
~~~
"""

SEQUENCE = """~~~diagram
type: sequence
caption: A short exchange.
actor x: First
actor y: Second
msg x -> y: hello
reply y --> x: hi
step: A phase
msg x -> x: think
~~~
"""

LAYERS = """~~~diagram
type: layers
caption: Two layers.
layer: Top | The upper layer. | key
layer: Bottom | The lower layer. | ok
~~~
"""

DOC = (
    "# Alpha {#alpha}\n\nOBJECTIVES: First goal. || Second goal about [[fig-flow]].\n\n"
    "## Part one {#part-one}\n\nSee [[fig-flow]], [[tab-one]] and [[part-one]].\n\n"
    + FLOW + "\n" + SEQUENCE + "\n" + LAYERS + "\n"
    "TABLE: tab-one | The only table\n| A | B |\n|---|---|\n| 1 | 2 |\n\n"
    "PITFALL: A mistake. || Another.\n\nEXAMPLE: Worked.\n\n# Beta {.nonum}\n\nText.\n"
)


class ParserTests(unittest.TestCase):
    def test_heading_attributes(self):
        blocks = parse("# One {#one}\n\n## Two {#two .nonum}\n")
        self.assertEqual((blocks[0].ref_id, blocks[0].numbered), ("one", True))
        self.assertEqual((blocks[1].ref_id, blocks[1].numbered), ("two", False))
        self.assertEqual(blocks[1].text, "Two")

    def test_unknown_heading_attribute_is_rejected(self):
        with self.assertRaises(ContentError) as raised:
            parse("# One {#one .wide}\n")
        self.assertEqual(raised.exception.line, 1)

    def test_invalid_id_is_rejected(self):
        with self.assertRaises(ContentError):
            parse("# One {#One_X}\n")

    def test_table_caption_attaches_to_next_table(self):
        blocks = parse("TABLE: t-one | Caption text\n\n| A | B |\n|---|---|\n| 1 | 2 |\n")
        self.assertIsInstance(blocks[0], Table)
        self.assertEqual((blocks[0].ref_id, blocks[0].caption), ("t-one", "Caption text"))

    def test_table_caption_without_table_is_rejected(self):
        with self.assertRaises(ContentError):
            parse("TABLE: t-one | Caption\n\nJust text.\n")
        with self.assertRaises(ContentError):
            parse("TABLE: only-id\n\n| A |\n|---|\n| 1 |\n")

    def test_image_id_needs_caption(self):
        with self.assertRaises(ContentError):
            parse("IMG: a.png | alt text | | fig-a\n")
        image = parse("IMG: a.png | alt text | Cap | fig-a\n")[0]
        self.assertIsInstance(image, Image)
        self.assertEqual(image.ref_id, "fig-a")

    def test_new_callout_kinds(self):
        for kind in ("OBJECTIVES", "EXAMPLE", "PITFALL"):
            block = parse(f"{kind}: Some text.\n")[0]
            self.assertIsInstance(block, Callout)
            self.assertEqual(block.kind, kind)

    def test_diagram_blocks_parse(self):
        for source in (FLOW, SEQUENCE, LAYERS):
            block = parse(source)[0]
            self.assertIsInstance(block, Diagram)

    def test_diagram_errors_name_a_line(self):
        cases = {
            "type: flow\ncaption: c\nnode a: A\nedge a -> z: x": "unknown node",
            "type: flow\nnode a: A": "caption",
            "type: pie\ncaption: c": "type must be",
            "type: sequence\ncaption: c\nactor a: A": "2 to",
            "type: layers\ncaption: c": "1 to",
            "type: flow\ncaption: c\nnode a: A | shiny": "node kind",
            "type: flow\ncaption: c\nnode a: A\nwhat is this": "unknown diagram line",
            "type: flow\ncaption: c\ndirection: right\nnode a: A": "direction",
        }
        for body, expected in cases.items():
            with self.assertRaises(ContentError, msg=body) as raised:
                parse("~~~diagram\n" + body + "\n~~~\n")
            self.assertIn(expected, str(raised.exception))


class AnalysisTests(unittest.TestCase):
    def test_numbers_and_labels(self):
        analysis = analyze(parse(DOC), True)
        numbers = [analysis.headings[i] for i, b in enumerate(parse(DOC)) if isinstance(b, Heading)]
        self.assertEqual(numbers, ["1", "1.1", None])
        self.assertEqual(analysis.refs["alpha"], "Chapter 1")
        self.assertEqual(analysis.refs["part-one"], "Section 1.1")
        self.assertEqual(analysis.refs["fig-flow"], "Figure 1")
        self.assertEqual(analysis.refs["tab-one"], "Table 1")
        self.assertEqual(len(analysis.figure_entries), 3)

    def test_without_numbering_sections_are_quoted(self):
        analysis = analyze(parse("# Alpha {#alpha}\n"), False)
        self.assertEqual(analysis.refs["alpha"], '"Alpha"')

    def test_duplicate_ids_are_rejected(self):
        with self.assertRaises(ContentError):
            analyze(parse("# A {#same}\n\n# B {#same}\n"), True)
        with self.assertRaises(ContentError):
            analyze(parse("# B {#same}\n"), True, {"same": "x"})


class MetaTests(unittest.TestCase):
    def test_numbered_must_be_boolean(self):
        data = dict(yaml.safe_load(META), numbered="yes please")
        with self.assertRaises(ConfigError):
            parse_meta(data)
        self.assertTrue(parse_meta(dict(yaml.safe_load(META), numbered=True)).numbered)


class ContrastTests(unittest.TestCase):
    def test_ensure_contrast_reaches_the_minimum(self):
        orange = colors.HexColor("#E07A1F")
        self.assertLess(contrast_ratio(orange, colors.white), MIN_CONTRAST)
        self.assertGreaterEqual(contrast_ratio(ensure_contrast(orange), colors.white), MIN_CONTRAST)

    def test_dark_colors_are_unchanged(self):
        navy = colors.HexColor("#12344D")
        self.assertEqual(ensure_contrast(navy), navy)


class NumberedBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._project = TempProject(content=DOC, meta=META + "numbered: true\n", with_image=False)
        cls.root = cls._project.__enter__()
        cls.result = build_document(cls.root, "courses/doc")
        cls.reader = PdfReader(io.BytesIO(cls.result.pdf_path.read_bytes()))
        cls.text = "\n".join(page.extract_text() for page in cls.reader.pages)

    @classmethod
    def tearDownClass(cls):
        cls._project.__exit__(None, None, None)

    def check(self, check_id):
        return next(c for c in self.result.audit.checks if c.id == check_id)

    def test_headings_carry_numbers_and_references_resolve(self):
        self.assertIn("1.1 Part one", " ".join(self.text.split()))
        self.assertIn("Figure 1", self.text)
        self.assertTrue(self.check("A9").passed)
        self.assertTrue(self.check("A10").passed)
        self.assertTrue(self.check("A11").passed)
        self.assertTrue(self.check("A13").passed)

    def test_lists_of_figures_and_tables_are_present(self):
        self.assertIn("List of Figures", self.text)
        self.assertIn("List of Tables", self.text)
        self.assertIn("Table 1. The only table", self.text)

    def test_diagram_captions_are_numbered_in_order(self):
        compact = " ".join(self.text.split())
        for number, caption in ((1, "A small flow."), (2, "A short exchange."), (3, "Two layers.")):
            self.assertIn(f"Figure {number}. {caption}", compact)

    def test_unnumbered_chapter_has_no_number(self):
        self.assertNotIn("2 Beta", " ".join(self.text.split()))


class ReferenceErrorTests(unittest.TestCase):
    def build(self, content):
        with TempProject(content=content, meta=META + "numbered: true\n", with_image=False) as root:
            return build_document(root, "courses/doc")

    def test_unknown_reference_names_its_line(self):
        with self.assertRaises(ContentError) as raised:
            self.build("# One\n\nSee [[nowhere]].\n")
        self.assertEqual(raised.exception.line, 3)

    def test_heading_cannot_contain_a_reference(self):
        with self.assertRaises(ContentError):
            self.build("# One {#one}\n\n## About [[one]]\n")

    def test_tall_diagram_is_rejected(self):
        nodes = "\n".join(f"node n{i}: Step {i}" for i in range(12))
        edges = "\n".join(f"edge n{i} -> n{i + 1}" for i in range(11))
        with self.assertRaises(ContentError) as raised:
            self.build(f"# One\n\n~~~diagram\ntype: flow\ncaption: Tall.\n{nodes}\n{edges}\n~~~\n")
        self.assertIn("too tall", str(raised.exception))


class NewAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._project = TempProject()
        cls.root = cls._project.__enter__()
        cls.result = build_document(cls.root, "courses/doc")
        cls.pdf = cls.result.pdf_path.read_bytes()
        cls.meta = parse_meta(yaml.safe_load(META))

    @classmethod
    def tearDownClass(cls):
        cls._project.__exit__(None, None, None)

    def failed(self, **kwargs):
        report = audit_pdf(self.pdf, self.meta, self.result.audit.exempt_pages, **kwargs)
        return {c.id for c in report.checks if not c.passed}

    def test_low_contrast_fails(self):
        self.assertIn("A13", self.failed(contrast=[("pale text", 2.0)]))

    def test_low_image_resolution_fails(self):
        self.assertIn("A12", self.failed(min_image_dpi=90.0))
        self.assertNotIn("A12", self.failed(min_image_dpi=200.0))


if __name__ == "__main__":
    unittest.main()
