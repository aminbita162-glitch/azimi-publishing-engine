"""Ticket file validation and the tickets installed in the project."""

import tempfile
import unittest
from pathlib import Path

from engine.cli import main
from engine.errors import ConfigError
from engine.tests.support import REAL_ROOT, TempProject
from engine.tools import TICKET_FIELDS, parse_ticket, validate_ticket

GOOD = (
    "TICKET-ID: T-DOC-001\n"
    "DOCUMENT: courses/doc\n"
    "VERSION: 1.0.0\n"
    "GOAL: Change one thing.\n"
    "  A second line of the goal.\n"
    "INPUTS: The existing content.\n"
    "ACCEPTANCE: Check passes.\n"
    "OWNER-DECISIONS: none\n"
)


def put(root: Path, name: str, text: str) -> str:
    folder = root / "tickets"
    folder.mkdir(exist_ok=True)
    (folder / name).write_text(text, encoding="utf-8")
    return f"tickets/{name}"


class TicketTests(unittest.TestCase):
    def test_parse_joins_continuation_lines(self):
        fields = parse_ticket(GOOD)
        self.assertEqual(fields["GOAL"], "Change one thing. A second line of the goal.")
        self.assertEqual(set(TICKET_FIELDS) - set(fields), set())

    def test_parse_rejects_bad_lines_and_repeated_fields(self):
        with self.assertRaises(ConfigError):
            parse_ticket("this is not a field\n")
        with self.assertRaises(ConfigError):
            parse_ticket("GOAL: a\nGOAL: b\n")

    def test_a_good_ticket_passes(self):
        with TempProject() as root:
            self.assertEqual(validate_ticket(root, put(root, "T-DOC-001.txt", GOOD)), [])
            self.assertEqual(main(["ticket", str(root / "tickets" / "T-DOC-001.txt")], root=root), 0)

    def test_problems_are_reported(self):
        cases = {
            "missing field ACCEPTANCE": GOOD.replace("ACCEPTANCE: Check passes.\n", ""),
            "TICKET-ID must look like": GOOD.replace("T-DOC-001", "TICKET1"),
            "VERSION must look like": GOOD.replace("1.0.0", "one"),
            "VERSION must equal": GOOD.replace("VERSION: 1.0.0", "VERSION: 9.0.0"),
            "DOCUMENT must be": GOOD.replace("courses/doc", "../outside"),
            "month and year only": GOOD.replace("none", "ship by 2026-11-05"),
            "unknown fields": GOOD + "EXTRA: value\n",
        }
        for expected, text in cases.items():
            with TempProject() as root:
                problems = validate_ticket(root, put(root, "T-DOC-001.txt", text))
                self.assertTrue(any(expected in p for p in problems), (expected, problems))

    def test_file_name_must_match_the_id_and_the_folder(self):
        with TempProject() as root:
            problems = validate_ticket(root, put(root, "T-DOC-002.txt", GOOD))
            self.assertTrue(any("file name must be" in p for p in problems))
            (root / "elsewhere").mkdir()
            (root / "elsewhere" / "T-DOC-001.txt").write_text(GOOD, encoding="utf-8")
            self.assertTrue(any("inside the tickets folder" in p for p in validate_ticket(root, "elsewhere/T-DOC-001.txt")))

    def test_non_ascii_and_missing_files(self):
        with TempProject() as root:
            self.assertTrue(any("ASCII" in p for p in validate_ticket(root, put(root, "T-DOC-001.txt", GOOD + "NOTE: café\n"))))
            with self.assertRaises(ConfigError):
                validate_ticket(root, "tickets/T-DOC-009.txt")
            self.assertEqual(main(["ticket", str(root / "tickets" / "T-DOC-001.txt")], root=root), 2)


class InstalledTicketTests(unittest.TestCase):
    def test_the_template_lists_every_required_field(self):
        text = (REAL_ROOT / "tickets" / "TEMPLATE.txt").read_text(encoding="utf-8")
        for field in TICKET_FIELDS:
            self.assertIn(field + ":", text)

    @unittest.skipUnless((REAL_ROOT / "courses" / "agentic-ai-masterclass" / "session-01" / "meta.yaml").is_file(), "needs the course folder")
    def test_the_first_ticket_is_valid(self):
        # Historical ticket targets v2.2.0, but current document is v2.4.0.
        # Preserve the record and assert strict rejection of version mismatch.
        ticket = parse_ticket((REAL_ROOT / "tickets" / "T-S01-001.txt").read_text(encoding="utf-8"))
        self.assertEqual(ticket["TICKET-ID"], "T-S01-001")
        self.assertEqual(ticket["VERSION"], "2.2.0")
        self.assertEqual(ticket["DOCUMENT"], "courses/agentic-ai-masterclass/session-01")
        self.assertEqual(validate_ticket(REAL_ROOT, "tickets/T-S01-001.txt"),
                         ["VERSION must equal the version in the meta.yaml of the document"])

    def test_agent_files_describe_the_ticket_files(self):
        for name in ("amilus", "ali", "lili"):
            text = (REAL_ROOT / "agents" / f"{name}.txt").read_text(encoding="utf-8")
            self.assertIn("PART L. TICKET FILES", text)
            self.assertIn("tickets/ID.txt", text)
            self.assertIn("never overwritten", text)


if __name__ == "__main__":
    unittest.main()
