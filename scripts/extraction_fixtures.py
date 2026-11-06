"""Generate inert synthetic fixtures; no real mail, downloads or office execution."""
from __future__ import annotations

import argparse
import io
from functools import lru_cache
from pathlib import Path
import re
import struct
import tempfile
import zlib
import zipfile
from xml.sax.saxutils import escape


MESSAGE = "PAYMENT DUE FRIDAY"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
R = "http://schemas.openxmlformats.org/package/2006/relationships"
O = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def office(kind: str, text: str = MESSAGE, *, replacement: bytes | None = None,
           extras: dict[str, bytes] | None = None) -> bytes:
    """Build real OOXML package structures, including relationships/content types."""
    text = escape(text)
    definitions = {
        "docx": ("word/document.xml", f'<w:document xmlns:w="{W}"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>',
                 "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"),
        "xlsx": ("xl/workbook.xml", f'<workbook xmlns="{S}" xmlns:r="{O}"><sheets><sheet name="Sheet 1" sheetId="1" r:id="rId1"/></sheets></workbook>',
                 "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"),
        "pptx": ("ppt/presentation.xml", f'<p:presentation xmlns:p="{P}" xmlns:r="{O}"><p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst></p:presentation>',
                 "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"),
    }
    main, xml, mime = definitions[kind]
    entries = {
        "_rels/.rels": f'<Relationships xmlns="{R}"><Relationship Id="rId1" Type="{O}/officeDocument" Target="{main}"/></Relationships>'.encode(),
        main: xml.encode(),
    }
    overrides = f'<Override PartName="/{main}" ContentType="{mime}"/>'
    if kind == "xlsx":
        entries["xl/_rels/workbook.xml.rels"] = f'<Relationships xmlns="{R}"><Relationship Id="rId1" Type="{O}/worksheet" Target="worksheets/sheet1.xml"/></Relationships>'.encode()
        entries["xl/worksheets/sheet1.xml"] = f'<worksheet xmlns="{S}"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>{text}</t></is></c><c r="B1"><v>42</v></c></row></sheetData></worksheet>'.encode()
        overrides += '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    if kind == "pptx":
        entries["ppt/_rels/presentation.xml.rels"] = f'<Relationships xmlns="{R}"><Relationship Id="rId1" Type="{O}/slide" Target="slides/slide1.xml"/></Relationships>'.encode()
        entries["ppt/slides/slide1.xml"] = f'<p:sld xmlns:p="{P}" xmlns:a="{A}"><p:cSld><p:spTree><p:sp><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>{text}</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>'.encode()
        overrides += '<Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
    entries["[Content_Types].xml"] = ('<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>' + overrides + '</Types>').encode()
    if replacement is not None:
        entries[main] = replacement
    entries.update(extras or {})
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return result.getvalue()


def _pdf_objects(objects: list[bytes]) -> bytes:
    result = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(result))
        result.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(result)
    result.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        result.extend(f"{offset:010} 00000 n \n".encode())
    result.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(result)


def pdf(text: str = MESSAGE, *, action: bool = False, scan: bool = False, mixed: bool = False) -> bytes:
    catalog = b"<< /Type /Catalog /Pages 2 0 R" + (b" /OpenAction 6 0 R" if action else b"") + b" >>"
    if scan:
        width, height, pixels = raster()
        content = b"q 612 0 0 792 0 0 cm /Im1 Do Q"
        resources = b"<< /XObject << /Im1 5 0 R >> >>"
        if mixed:
            resources = b"<< /XObject << /Im1 5 0 R >> /Font << /F1 6 0 R >> >>"
            content += b"\nBT /F1 20 Tf 36 750 Td (INVOICE) Tj ET"
        image = zlib.compress(pixels)
        fifth = f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} /ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode /Length {len(image)} >>\nstream\n".encode() + image + b"\nendstream"
    else:
        content = f"BT /F1 24 Tf 36 700 Td ({text}) Tj ET".encode()
        resources = b"<< /Font << /F1 5 0 R >> >>"
        fifth = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    objects = [catalog, b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources " + resources + b" /Contents 4 0 R >>",
               f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream", fifth]
    if mixed:
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    if action:
        # Compressed action source and escaped PDF name exercise structural scanning.
        js = zlib.compress(b"/* INERT fixture: do not execute */")
        objects += [b"<< /S /Java#53cript /JS 7 0 R >>",
                    f"<< /Filter /FlateDecode /Length {len(js)} >>\nstream\n".encode() + js + b"\nendstream"]
    return _pdf_objects(objects)


def _fixture_command(name: str, args: list[str], *, source_data: bytes) -> bytes:
    from email_steward.extraction import run_bounded
    DEFAULT_SCRATCH = Path(__file__).resolve().parents[1] / ".local/extraction"
    DEFAULT_SCRATCH.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix="fixture-", dir=DEFAULT_SCRATCH) as directory:
        workdir = Path(directory)
        source, target = workdir / "source.pdf", workdir / "target.pdf"
        source.write_bytes(source_data)
        argv = ["/usr/bin/" + name, *[arg.replace("{source}", str(source)).replace("{target}", str(target)) for arg in args]]
        code, output, errors = run_bounded(argv, cwd=workdir, timeout=12, output_limit=8 * 1024 * 1024)
        if code:
            raise RuntimeError(f"synthetic fixture tool {name} failed: {code}")
        return target.read_bytes() if target.exists() else output


@lru_cache(maxsize=1)
def raster() -> tuple[int, int, bytes]:
    # Rasterise generated Helvetica text, ensuring the scanned PDF contains only an image.
    raw = _fixture_command("pdftoppm", ["-f", "1", "-l", "1", "-singlefile", "-scale-to", "1600", "-gray", "{source}"], source_data=pdf())
    header = re.match(rb"P5\s+(\d+)\s+(\d+)\s+255\s", raw)
    if header is None:
        raise RuntimeError("unexpected generated fixture PGM header")
    width, height = int(header[1]), int(header[2])
    pixels = raw[header.end():]
    if len(pixels) != width * height:
        raise RuntimeError("generated fixture PGM length mismatch")
    return width, height, pixels


def png() -> bytes:
    width, height, pixels = raster()
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    raw = b"".join(b"\0" + pixels[y * width:(y + 1) * width] for y in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def bmp() -> bytes:
    width, height, pixels = raster()
    rgb = bytearray(len(pixels) * 3)
    for channel in range(3):
        rgb[channel::3] = pixels
    stride = width * 3
    pad = b"\0" * (-stride % 4)
    body = b"".join(rgb[y * stride:(y + 1) * stride] + pad for y in reversed(range(height)))
    return (b"BM" + struct.pack("<IHHI", 54 + len(body), 0, 0, 54)
            + struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0, len(body), 2835, 2835, 0, 0) + body)


def tiff() -> bytes:
    width, height, pixels = raster()
    tags = [(256, 4, width), (257, 4, height), (258, 3, 8), (259, 3, 1),
            (262, 3, 1), (273, 4, 122), (277, 3, 1), (278, 4, height), (279, 4, len(pixels))]
    directory = b"".join(struct.pack("<HHII", tag, kind, 1, value) for tag, kind, value in tags)
    return b"II*\0" + struct.pack("<IH", 8, len(tags)) + directory + b"\0" * 4 + pixels


def fixtures() -> dict[str, bytes]:
    result = {"letter.pdf": pdf(), "letter.docx": office("docx"),
              "table.xlsx": office("xlsx"), "slides.pptx": office("pptx"),
              "scan.png": png(), "scan.pdf": pdf(scan=True), "mixed.pdf": pdf(scan=True, mixed=True),
              "scan.bmp": bmp(), "scan.tiff": tiff(),
              "scan.jpg": _fixture_command("pdftoppm", ["-f", "1", "-l", "1", "-singlefile", "-scale-to", "1600", "-jpeg", "{source}"], source_data=pdf()),
              "danger-action.pdf": pdf(action=True),
              "danger-macro.docx": office("docx", extras={"word/vbaProject.bin": b"INERT"}),
              "danger-traversal.docx": office("docx", extras={"../outside": b"INERT"}),
              "danger-entity.docx": office("docx", replacement=b'<!DOCTYPE a [<!ENTITY x "INERT">]><a>&x;</a>'),
              "danger-bomb.docx": office("docx", extras={"word/bomb.bin": b"0" * (5 * 1024 * 1024)}),
              "danger-link.docx": office("docx", extras={"word/_rels/document.xml.rels": f'<Relationships xmlns="{R}"><Relationship Id="rId9" Type="{O}/attachedTemplate" Target="https://invalid.example/template" TargetMode="External"/></Relationships>'.encode()}),
              "danger-formula.xlsx": office("xlsx", extras={"xl/worksheets/sheet1.xml": f'<worksheet xmlns="{S}"><sheetData><row><c><f>WEBSERVICE("https://invalid.example/")</f><v>0</v></c></row></sheetData></worksheet>'.encode()}),
              "protected.pdf": _fixture_command("qpdf", ["--encrypt", "synthetic-fixture-password", "synthetic-owner-password", "256", "--", "{source}", "{target}"], source_data=pdf())}
    result["danger-compressed-action.pdf"] = _fixture_command("qpdf", ["--object-streams=generate", "--stream-data=compress", "{source}", "{target}"], source_data=pdf(action=True))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", type=Path, help="Optional synthetic-fixture output directory")
    args = parser.parse_args()
    for name, data in fixtures().items():
        if args.write:
            args.write.mkdir(parents=True, exist_ok=True, mode=0o700)
            (args.write / name).write_bytes(data)
        print(f"{name}: {len(data)} bytes (synthetic)")


if __name__ == "__main__":
    main()
