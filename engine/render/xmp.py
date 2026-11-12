"""XMP metadata for the finished PDF, written deterministically with pikepdf.

The packet states title, author, language, rights and producer. It makes no
conformance claim: there is no pdfaid or pdfuaid entry on purpose.
"""

from __future__ import annotations

import datetime
import io

import pikepdf

from ..brand import Brand
from ..schemas.meta import Meta


def apply_xmp(pdf: bytes, meta: Meta, brand: Brand, producer: str) -> bytes:
    """Return the PDF with an XMP packet and a matching Producer. Same input gives the same bytes."""
    stamp = datetime.datetime.fromtimestamp(meta.epoch, datetime.timezone.utc)
    year = meta.date.split()[-1]
    with pikepdf.open(io.BytesIO(pdf)) as document:
        with document.open_metadata(set_pikepdf_as_editor=False, update_docinfo=False) as xmp:
            xmp["dc:title"] = meta.title
            xmp["dc:creator"] = [meta.author]
            xmp["dc:description"] = meta.subtitle or meta.audience
            xmp["dc:language"] = [meta.language]
            xmp["dc:rights"] = f"Copyright (c) {year} {meta.author}. All rights reserved."
            xmp["pdf:Producer"] = producer
            if meta.keywords:
                xmp["pdf:Keywords"] = meta.keywords
            xmp["xmp:CreatorTool"] = "Azimi Publishing Engine"
            xmp["xmp:CreateDate"] = stamp.isoformat()
            xmp["xmp:ModifyDate"] = stamp.isoformat()
            xmp["xmp:MetadataDate"] = stamp.isoformat()
        document.docinfo["/Producer"] = producer
        out = io.BytesIO()
        document.save(out, deterministic_id=True, compress_streams=True, object_stream_mode=pikepdf.ObjectStreamMode.preserve)
    return out.getvalue()
