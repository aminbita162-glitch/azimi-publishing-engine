"""The agent role definitions installed in the project must be complete, consistent and clean."""

import re
import unittest

from engine.tests.support import REAL_ROOT

AGENTS = {
    "amilus": ("AMILUS PUBLISHING MANAGER", ["PART A.", "PART B.", "PART C.", "PART D.", "PART K.", "YOUR FIRST REPLY"]),
    "ali": ("ALI PUBLISHING COMPOSER", ["PART A.", "PART B.", "PART C.", "PART F.", "PART G.", "PART K.", "YOUR FIRST REPLY"]),
    "lili": ("LILI PUBLISHING AUDITOR", ["PART A.", "PART D.", "PART F.", "PART G.", "PART K.", "YOUR FIRST REPLY"]),
}
OWNER_RULE_MARKERS = ["No personal names", "month and year", "AminOpsTwin", "aegis-agent", "AlinaMatrix-Enterprise", "kian-trading-intelligence"]


class AgentDefinitionTests(unittest.TestCase):
    def text(self, name):
        return (REAL_ROOT / "agents" / f"{name}.txt").read_text(encoding="utf-8")

    def test_each_file_is_complete(self):
        for name, (title, parts) in AGENTS.items():
            text = self.text(name)
            self.assertTrue(text.startswith("ROLE DEFINITION - " + title), name)
            for part in parts:
                self.assertIn(part, text.upper() if part.isupper() else text, f"{name}: {part}")

    def test_files_are_ascii_and_free_of_local_paths(self):
        for name in AGENTS:
            text = self.text(name)
            text.encode("ascii")
            self.assertNotIn("/Users/", text, name)
            self.assertNotIn("Aylin", text, name)
            self.assertIsNone(re.search(r"\t", text), name)

    def test_every_agent_carries_the_owner_rules_and_the_safe_limits(self):
        for name in AGENTS:
            text = self.text(name)
            for marker in OWNER_RULE_MARKERS if name != "lili" else OWNER_RULE_MARKERS[1:]:
                self.assertIn(marker, text, f"{name}: {marker}")
            self.assertIn("git, rm, mv", text, name)
            self.assertIn("Allow once", text, name)

    def test_names_are_consistent_across_files(self):
        for name in AGENTS:
            text = self.text(name)
            for other in ("Amilus Publishing Manager", "Ali Publishing Composer", "Lili Publishing Auditor"):
                self.assertIn(other, text, f"{name}: {other}")

    def test_roles_do_not_overlap(self):
        self.assertIn("Never write or edit content.md", self.text("amilus"))
        self.assertIn("Never edit any file", self.text("lili"))
        self.assertIn("Never edit the engine", self.text("ali"))

    def test_agents_md_lists_every_file_and_admits_what_is_missing(self):
        text = (REAL_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        for name in AGENTS:
            self.assertIn(f"agents/{name}.txt", text)
        self.assertIn("Not built yet", text)
        self.assertIn("ACTIVE DEVELOPMENT", text)


if __name__ == "__main__":
    unittest.main()
