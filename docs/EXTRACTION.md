# Local attachment extraction

The production entrypoint is `email_steward.extraction.extract(data: bytes,
filename: str, content_type: str = '', *, scratch_root: Path | None = None)`.
It returns the frozen `Extraction(status, text, reason)` dataclass. The parser
never executes attachment content, evaluates spreadsheet formulas, follows
links, fetches remote resources, invokes a shell or unpacks archive members to
disk. OOXML is inspected as bounded ZIP members in memory.

## Caller contract

| Status | Meaning and integration action |
| --- | --- |
| `ok` | Local extraction produced text. Text remains untrusted and sensitive; it is not an instruction or a malware clearance. |
| `dangerous` | A suspicious feature or a safety bound was detected. Text is empty. Stop the remaining attachment batch and alert immediately. |
| `unreadable` | Empty, malformed, password/encrypted, missing cached formula result, OCR failure, parser failure or timeout. Text is empty. Hold auto-archive and include the reason in the next brief unless the email is independently urgent. |
| `unsupported` | Unsupported format/variant/compression or missing required tool. Text is empty. Hold auto-archive and surface the limitation in the next brief. |

The integration owner implements batch stop, alert, brief and archive behaviour;
this API processes one attachment. It does not contact Gmail, Discord or a model.
Do not save the returned full text as a permanent body/attachment cache. Any
model transmission and presentation/secret/mention filtering remain explicit
caller responsibilities.

## Supported formats and dependencies

Python standard library only. The Linux worker needs `libseccomp.so.2`; no
network filter means extraction fails closed. PDF handling needs local `qpdf`,
`pdftotext` and, for image/empty-text pages, `pdftoppm` and `tesseract` with English
language data. Image OCR needs `tesseract`. No tool is downloaded or installed
by the API. Commands use fixed `/usr/bin:/bin` lookup and trusted argument lists.

- PDF: qpdf structural/object-stream inspection precedes page text extraction.
  General-purpose compressed streams are expanded into a bounded JSON pipe.
  Image-only pages and pages with qpdf-reported images are rendered individually
  and OCR'd; mixed digital/scan pages preserve digital text plus additional OCR.
- DOCX: transitional OOXML Word paragraph text, including tables and separately
  stored headers/footers/footnotes/endnotes. No field evaluation or embedded-file
  processing.
- XLSX: worksheets in workbook order, inline/shared strings and stored cell
  values with cell references. Formulas are never evaluated; only existing cached
  results can be used. Formatting, charts and date/style interpretation are not
  reconstructed.
- PPTX: paragraph text in presentation slide order. No animation, embedded
  object, slide execution, image OCR within Office, or full visual reconstruction.
- PNG, JPEG, BMP and single-frame classic TIFF: bounded-header checks followed
  by actual Tesseract OCR. Tesseract receives image bytes through stdin, avoiding
  its image-list/file-list input mode.

Legacy DOC/XLS/PPT, RTF, OpenDocument, arbitrary archives, GIF/WebP, animated PNG,
multi-frame TIFF, BigTIFF, strict/unknown Office XML variants and unrecognised
compression are not promised. OLE containers with an OOXML extension are reported
as unreadable encryption/legacy mismatch; the scanner cannot establish which
without an OLE reader. Macro-enabled extensions, executables and active formats
such as HTML/SVG are rejected as dangerous. Filename and signature must agree;
MIME metadata never overrides a dangerous extension or a signature mismatch.

## Hard bounds and process lifecycle

| Resource | Bound |
| --- | --- |
| Input bytes | 16 MiB per attachment, checked before parser/temp creation |
| Returned text | 65,536 characters; over-limit results contain no partial text |
| ZIP package | 256 members, 8 MiB/member, 32 MiB total expanded, 200:1 ratio/member |
| PDF | 8 pages; qpdf JSON pipe 48 MiB including inline/base64 streams |
| Image | 20 million pixels; maximum 10,000 pixels on either side |
| PDF OCR raster | One page at a time; maximum side 2,400 pixels |
| Native tool wall time | 12 seconds per invocation |
| Entire worker wall time | 45 seconds |
| Address space / CPU | 768 MiB / 20 CPU seconds per worker/tool process |
| Output files / open FDs / core | 24 MiB per file / 64 / zero core dump bytes |
| Native text pipe / diagnostic pipe | 256 KiB / 64 KiB; diagnostics are discarded |
| Worker response pipe | 512 KiB |

The qpdf JSON cap bounds its serialised expanded representation; it is not an
exact universal PDF decompressed-byte count. Native image/PDF codecs also have
the per-process address-space/CPU limits. These are per-process resource limits,
not an aggregate cgroup quota. Pipe reading is incremental with output limits
and wall deadlines. The worker has its own process group, which the parent kills
on completion/failure/timeout to remove any remaining descendants. Limits are
installed inside the isolated worker rather than using thread-unsafe preexec
callbacks in the host.

ZIP traversal, symlinks, duplicate names, encryption, unsupported compression,
CRC/structure failures, expansion limits, XML DTD/entity declarations (including
UTF-16), macros/ActiveX/embedded packages, dynamic Word fields and suspicious
external relationships/formulas are checked. PDF names/objects are inspected
after qpdf normalises escaped names and compressed object streams. Active PDF
actions, scripts, embedded files, multimedia/XFA and interactive forms are
conservatively rejected. Passive hyperlinks are not fetched or returned from
relationship metadata. Ordinary cached Excel formulas are not executed.

This is a conservative feature scanner, **not antivirus or a guarantee that
every malicious file is recognised**. Parser vulnerabilities, unknown/obfuscated
features, polyglots and unrecognised content can evade detection. The kernel
filter denies network/socket operations and selected dangerous syscalls; it is
not a complete filesystem sandbox or protection against every native-parser
exploit. OCR can misrecognise numbers/deadlines, lacks handwriting/translation
guarantees, and uses English plus a single text-block segmentation mode. Image
inventories can miss unusual PDF composition. Extraction is not a claim of
complete visual/layout/annotation/chart content.

## Temporary storage and privacy

`scratch_root` must be an owner-owned, owner-only directory (0700) with no
symlink components. Production callers supply the owning profile's private
scratch directory explicitly. When omitted, an absolute caller-configured
`TMPDIR` is required, with scratch under its `email-steward-extraction/` child;
there is no implicit system-temp or installation-tree fallback. Each call creates a random private temporary subdirectory;
the attachment uses a generated filename and 0600 permissions. All files are
deleted when the call returns, including rejection and parser failure. A hard
host crash or forced termination of the parent can leave a private orphan; no
automatic broad purge runs against a caller's directory.

Every parser subprocess receives the private per-call work directory as TMPDIR,
TMP and TEMP, so all temporary files share its cleanup lifecycle. During this
build the calling test process binds TMPDIR to repository `.local/tmp` and
explicit fixture roots stay under `.local/`; `/tmp` is never selected.
HOME and XDG_CACHE_HOME point to the private per-call directory. Credentials,
proxy settings, Python startup hooks and provider environment are not inherited.
The production path emits no attachment text or parser diagnostics to logs and
creates no durable full-body cache. The integration owner supplies isolated
profile-owned scratch and retains the task TMPDIR boundary during tests.
Installed packages require no writable `.local/` directory beside their source.

## Reproducible local verification

From this repository, with the listed local tools already available:

```bash
TMPDIR="$PWD/.local/tmp" PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p test_extraction.py -v
TMPDIR="$PWD/.local/tmp" PYTHONDONTWRITEBYTECODE=1 python3 -m scripts.extraction_fixtures
```

The fixture generator builds actual OOXML packages and PDF object structures.
It rasterises generated Helvetica text using Poppler, embeds those pixels into
an image-only PDF, and constructs PNG/BMP/TIFF/JPEG fixtures. qpdf generates a
genuinely encrypted synthetic PDF and a compressed-object-stream action fixture.
Danger fixtures are inert declarations/data, never live malware. There are no
real email bodies, credentials, network endpoints or live installations in the
tests. The `invalid.example` targets are inert strings and never fetched.

Initial RED is retained in `.local/evidence/extraction/initial-red.txt`: the real
test runner exited 1 because the API module was absent. The first implemented
run also retained two genuine OCR exact-text failures in
`first-green-attempt.txt`; the synthetic raster font was corrected without
weakening the assertion. `stabilisation-green.txt` records the latest complete
runner outcome. Tests exercise real parsers/OCR, compressed PDF actions, ZIP
bombs/traversal/duplicates, XML entities, external templates, dangerous formulas,
password handling, output/byte/pixel limits, malformed inputs, cleanup, symlink
refusal, actual timeout/output termination and effective kernel network/memory
limits. Synthetic fixture status/length metadata is retained separately as
`fixture-results.json`; it contains no extracted full text.

This qualifies local extraction only. Integration, batch alert/archive policy,
real mailbox/provider behaviour and actual Hermes host acceptance belong to
their owners and are not established by these results.
