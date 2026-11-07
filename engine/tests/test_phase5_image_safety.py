"""Phase 5 WP2: image safety and quality tests.

Validates file existence, sandboxed path resolution, permitted formats,
decode failures, corrupt/truncated files, huge dimensions, EXIF rotation,
transparency, and aspect-ratio handling for the image rendering pipeline.
"""

import io
import os
import unittest
from pathlib import Path

from PIL import Image as PILImage

from engine.build.builder import build_document
from engine.build.parser import parse
from engine.errors import ContentError
from engine.tests.support import META, REAL_ROOT, TempProject, make_figure


class ImageSafetyTests(unittest.TestCase):
    """End-to-end image safety tests through the full build pipeline."""

    def test_corrupt_image_is_rejected(self):
        """A truncated PNG file is rejected with a clear ContentError."""
        content = "# Title\n\nIMG: assets/broken.png | Alt text | Caption\n"
        with TempProject(content=content, with_image=False) as root:
            assets = root / "courses" / "doc" / "assets"
            make_figure(assets / "broken.png")
            raw = (assets / "broken.png").read_bytes()
            (assets / "broken.png").write_bytes(raw[:50])
            with self.assertRaisesRegex(ContentError, "image cannot be read"):
                build_document(root, "courses/doc")

    def test_huge_image_is_rejected(self):
        """An image exceeding MAX_PIXELS (40 million) is rejected."""
        content = "# Title\n\nIMG: assets/huge.png | Alt text | Caption\n"
        with TempProject(content=content, with_image=False) as root:
            assets = root / "courses" / "doc" / "assets"
            big = PILImage.new("L", (6325, 6325), 128)
            big.save(assets / "huge.png")
            with self.assertRaisesRegex(ContentError, "image is too large"):
                build_document(root, "courses/doc")

    def test_transparent_png_renders_without_error(self):
        """An RGBA image with alpha channel renders and passes the audit."""
        content = "# Title\n\nIMG: assets/transparent.png | Transparent diagram | Caption\n"
        with TempProject(content=content, with_image=False) as root:
            assets = root / "courses" / "doc" / "assets"
            img = PILImage.new("RGBA", (800, 400), (0, 0, 0, 0))
            img.save(assets / "transparent.png")
            result = build_document(root, "courses/doc")
            self.assertTrue(result.audit.passed)

    def test_jpeg_image_is_accepted(self):
        """A JPEG image is a permitted format and renders correctly."""
        content = "# Title\n\nIMG: assets/photo.jpg | A photo | Caption\n"
        with TempProject(content=content, with_image=False) as root:
            assets = root / "courses" / "doc" / "assets"
            img = PILImage.new("RGB", (800, 400), (100, 150, 200))
            img.save(assets / "photo.jpg", quality=85)
            result = build_document(root, "courses/doc")
            self.assertTrue(result.audit.passed)

    def test_symlink_image_is_rejected(self):
        """A symlinked image path is rejected by the path-confined resolver."""
        content = "# Title\n\nIMG: assets/linked.png | Alt | Caption\n"
        with TempProject(content=content, with_image=False) as root:
            assets = root / "courses" / "doc" / "assets"
            make_figure(assets / "real.png")
            os.symlink(assets / "real.png", assets / "linked.png")
            with self.assertRaisesRegex(ContentError, "image path is not allowed"):
                build_document(root, "courses/doc")

    def test_exif_rotated_image_displays_in_intended_orientation(self):
        """An image with EXIF orientation is transposed before size calculation."""
        from engine.render.document import _figure_size
        from engine.build.parser import Image as ImageBlock

        with TempProject(with_image=False) as root:
            assets = root / "courses" / "doc" / "assets"
            img = PILImage.new("RGB", (1200, 600), (255, 100, 50))
            exif = img.getexif()
            exif[0x0112] = 6  # 90° CW → portrait
            img.save(assets / "rotated.jpg", exif=exif.tobytes(), dpi=(150, 150))
            block = ImageBlock(
                line=1, path="assets/rotated.jpg", alt="test", caption=None
            )
            source, width, height = _figure_size(block, root / "courses" / "doc")
            self.assertGreater(
                height, width,
                "EXIF-rotated image should display in its intended (portrait) orientation",
            )

    def test_exif_rotated_image_builds_and_passes_audit(self):
        """An EXIF-rotated JPEG builds successfully and the audit passes."""
        content = "# Title\n\nIMG: assets/rotated.jpg | Rotated | Caption\n"
        with TempProject(content=content, with_image=False) as root:
            assets = root / "courses" / "doc" / "assets"
            img = PILImage.new("RGB", (1200, 600), (255, 100, 50))
            exif = img.getexif()
            exif[0x0112] = 6
            img.save(assets / "rotated.jpg", exif=exif.tobytes(), dpi=(150, 150))
            result = build_document(root, "courses/doc")
            self.assertTrue(result.audit.passed)

    def test_image_with_id_requires_caption(self):
        """The parser rejects an image with an id but no caption."""
        with self.assertRaisesRegex(ContentError, "image with an id needs a caption"):
            parse("IMG: assets/a.png | alt |  | myid\n")

    def test_image_with_id_and_caption_is_accepted(self):
        """The parser accepts an image with an id when a caption is present."""
        block = parse("IMG: assets/a.png | alt | caption | myid\n")[0]
        self.assertEqual(block.ref_id, "myid")
        self.assertEqual(block.caption, "caption")

    def test_aspect_ratio_is_preserved(self):
        """The rendered image preserves the source aspect ratio."""
        from engine.render.document import _scaled_size

        width, height = _scaled_size(800, 400, 150, 400, 200)
        self.assertAlmostEqual(width / height, 2.0, places=1)

    def test_non_png_jpeg_format_is_rejected(self):
        """GIF and SVG are not permitted image formats."""
        for ext in (".gif", ".svg", ".webp", ".bmp"):
            with self.subTest(ext=ext):
                with self.assertRaisesRegex(ContentError, "image must be PNG or JPEG"):
                    parse(f"IMG: assets/a{ext} | alt\n")


if __name__ == "__main__":
    unittest.main()
