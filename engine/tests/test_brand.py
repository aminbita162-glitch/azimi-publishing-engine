import tempfile
import unittest
from pathlib import Path

from PIL import Image

from engine.brand import load_brand
from engine.errors import ConfigError, PathError

YAML = "display_name: Azimi Innovation Lab\nprimary_color: '#12344d'\naccent_color: '#E07A1F'\n"


def make_logo(path: Path, width=1200, height=400, mode="RGBA", fmt="PNG"):
    color = (10, 20, 30, 0) if mode == "RGBA" else (10, 20, 30)
    Image.new(mode, (width, height), color).save(path, format=fmt)


class BrandTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.folder = self.root / "azimi"
        self.folder.mkdir()
        (self.folder / "brand.yaml").write_text(YAML, encoding="utf-8")
        make_logo(self.folder / "logo.png")

    def tearDown(self):
        self._tmp.cleanup()

    def test_valid_brand(self):
        brand = load_brand(self.root, "azimi")
        self.assertEqual(brand.display_name, "Azimi Innovation Lab")
        self.assertEqual(brand.primary_color, "#12344D")
        self.assertEqual(brand.accent_color, "#E07A1F")
        self.assertEqual(brand.logo_size, (1200, 400))

    def test_tagline_is_optional(self):
        self.assertIsNone(load_brand(self.root, "azimi").tagline)
        (self.folder / "brand.yaml").write_text(YAML + "tagline: AI Architect | Systems\n", encoding="utf-8")
        self.assertEqual(load_brand(self.root, "azimi").tagline, "AI Architect | Systems")

    def test_invalid_tagline(self):
        for bad in ("''", "x" * 201, "5"):
            with self.subTest(bad=bad):
                (self.folder / "brand.yaml").write_text(YAML + f"tagline: {bad}\n", encoding="utf-8")
                with self.assertRaisesRegex(ConfigError, "tagline"):
                    load_brand(self.root, "azimi")

    def test_logo_too_narrow(self):
        make_logo(self.folder / "logo.png", width=999)
        with self.assertRaisesRegex(ConfigError, "at least 1000"):
            load_brand(self.root, "azimi")

    def test_logo_too_wide(self):
        make_logo(self.folder / "logo.png", width=8001, height=10)
        with self.assertRaisesRegex(ConfigError, "at most 8000"):
            load_brand(self.root, "azimi")

    def test_logo_must_be_transparent(self):
        make_logo(self.folder / "logo.png", mode="RGB")
        with self.assertRaisesRegex(ConfigError, "transparent"):
            load_brand(self.root, "azimi")

    def test_logo_must_be_png(self):
        make_logo(self.folder / "logo.png", mode="RGB", fmt="JPEG")
        with self.assertRaisesRegex(ConfigError, "not a PNG"):
            load_brand(self.root, "azimi")

    def test_logo_not_an_image(self):
        (self.folder / "logo.png").write_bytes(b"not an image")
        with self.assertRaisesRegex(ConfigError, "cannot be read"):
            load_brand(self.root, "azimi")

    def test_missing_logo(self):
        (self.folder / "logo.png").unlink()
        with self.assertRaisesRegex(ConfigError, "logo.png is missing"):
            load_brand(self.root, "azimi")

    def test_missing_config(self):
        (self.folder / "brand.yaml").unlink()
        with self.assertRaisesRegex(ConfigError, "brand.yaml"):
            load_brand(self.root, "azimi")

    def test_invalid_color(self):
        (self.folder / "brand.yaml").write_text(
            "display_name: X\nprimary_color: red\naccent_color: '#000000'\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(ConfigError, "primary_color"):
            load_brand(self.root, "azimi")

    def test_unknown_and_missing_keys(self):
        (self.folder / "brand.yaml").write_text("display_name: X\nextra: 1\n", encoding="utf-8")
        with self.assertRaisesRegex(ConfigError, "unknown keys"):
            load_brand(self.root, "azimi")
        (self.folder / "brand.yaml").write_text("display_name: X\n", encoding="utf-8")
        with self.assertRaisesRegex(ConfigError, "missing keys"):
            load_brand(self.root, "azimi")

    def test_unknown_brand(self):
        with self.assertRaisesRegex(ConfigError, "folder not found"):
            load_brand(self.root, "other")

    def test_invalid_brand_names(self):
        for bad in ("../azimi", "Azimi", "a/b", ""):
            with self.subTest(bad=bad):
                with self.assertRaises((ConfigError, PathError)):
                    load_brand(self.root, bad)


if __name__ == "__main__":
    unittest.main()
