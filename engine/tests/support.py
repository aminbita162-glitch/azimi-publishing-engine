"""Shared helpers for tests that build real documents."""

import shutil
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

REAL_ROOT = Path(__file__).resolve().parents[2]

META = (
    "title: Agentic Systems Foundations\n"
    "subtitle: Session 01\n"
    "author: Amin Azimi\n"
    "audience: Senior engineers\n"
    "language: en\n"
    "version: 1.0.0\n"
    "date: November 2026\n"
    "output_name: Sample_Session\n"
)

CONTENT = """# Foundations

Agentic systems combine **models**, *tools* and `control loops`.

## Core ideas

- First point
- Second point

1. Step one
2. Step two

NOTE: This is a note.

~~~python
def run(task):
    return task
~~~

IMG: assets/flow.png | Three boxes in a row | The pipeline

| Layer | Purpose |
|:------|--------:|
| A | One |
| B | Two |

WARNING: This is a warning.

PAGEBREAK

# Second chapter

Closing text.

## Details

More text.
"""


RIGHTS = """# Rights and License

Copyright (c) 2026 The Publisher. All rights reserved.

## What is permitted

- Reading and studying this document for personal learning.

## What is not permitted

- Copying or redistributing this document.
"""


def make_logo(path: Path) -> None:
    image = Image.new("RGBA", (1600, 480), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 40, 400, 440), 60, fill=(18, 52, 77, 255))
    draw.rectangle((460, 160, 1560, 230), fill=(18, 52, 77, 255))
    image.save(path)


def make_figure(path: Path) -> None:
    image = Image.new("RGB", (1400, 700), (244, 246, 248))
    draw = ImageDraw.Draw(image)
    for x in (100, 520, 940):
        draw.rounded_rectangle((x, 250, x + 360, 450), 24, fill=(18, 52, 77))
    image.save(path, dpi=(150, 150))


def make_project(base: Path, content: str = CONTENT, meta: str = META, with_image: bool = True) -> Path:
    """Create a self-contained project root with fonts, a brand and one document."""
    root = base / "project"
    shutil.copytree(REAL_ROOT / "design-system" / "fonts", root / "design-system" / "fonts")
    brand = root / "brand" / "default"
    brand.mkdir(parents=True)
    (brand / "brand.yaml").write_text(
        "display_name: Azimi Innovation Lab\nprimary_color: '#12344D'\naccent_color: '#E07A1F'\n",
        encoding="utf-8",
    )
    make_logo(brand / "logo.png")
    (brand / "rights.md").write_text(RIGHTS, encoding="utf-8")
    document = root / "courses" / "doc"
    (document / "assets").mkdir(parents=True)
    (document / "meta.yaml").write_text(meta, encoding="utf-8")
    (document / "content.md").write_text(content, encoding="utf-8")
    if with_image:
        make_figure(document / "assets" / "flow.png")
    return root


class TempProject:
    """Context helper: creates a project in a temporary directory."""

    def __init__(self, **kwargs):
        self._kwargs = kwargs
        self._tmp = tempfile.TemporaryDirectory()

    def __enter__(self) -> Path:
        return make_project(Path(self._tmp.name), **self._kwargs)

    def __exit__(self, *exc):
        self._tmp.cleanup()
