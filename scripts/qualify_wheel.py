#!/usr/bin/env python3
"""Offline wheel install and real worker/parser smoke in a task-owned directory."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    target = root / "installed"
    subprocess.run([sys.executable, "-m", "pip", "install", "--no-deps", "--no-index", "--target",
                    str(target), str(args.wheel.resolve())], check=True)
    code = r'''
import io, json, sys, zipfile
from pathlib import Path
root, target = map(Path, sys.argv[1:])
sys.path.insert(0, str(target))
import email_steward
assert Path(email_steward.__file__).resolve().is_relative_to(target)
from email_steward.gmail import Attachment
from email_steward.security import Settings, Access
from email_steward.store import Store
from email_steward.service import Steward
from email_steward.synthetic import SyntheticGmail
from email_steward.worker import Worker
raw = io.BytesIO()
with zipfile.ZipFile(raw, 'w') as archive:
    archive.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    archive.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
    archive.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Please approve the synthetic renewal today. WHEEL_TRANSIENT_EXTRACT</w:t></w:r></w:p></w:body></w:document>')
data = raw.getvalue()
settings = Settings(home=root/'home', profile='synthetic-wheel', owner='owner', destination='private', private_confirmed=True, timezone='UTC')
provider = SyntheticGmail()
service = Steward(Store(settings.home/'state'), settings, lambda account: provider)
access = Access(settings.home, 'owner', 'synthetic-wheel')
service.connect(access, 'gmail-1', 'alex@example.test', 'Synthetic')
provider.add('synthetic-message', body='WHEEL_TRANSIENT_BODY', attachments=[Attachment('renewal.docx', '', len(data), lambda: data)])
Worker(service, None).tick(1000)
item = service.store.item('ax1')
assert item['attachment_status'] == 'ok', item
assert item['classification'] == 'needs_action', item
assert b'WHEEL_TRANSIENT_EXTRACT' not in service.store.path.read_bytes()
assert b'WHEEL_TRANSIENT_BODY' not in service.store.path.read_bytes()
assert list((service.store.root/'scratch').iterdir()) == []
print(json.dumps({'installed_package':str(Path(email_steward.__file__).resolve()), 'worker':'PASS', 'actual_docx_parser':'PASS', 'transient_body_and_extract':'PASS', 'live_services':'UNRUN'}))
'''
    result = subprocess.run([sys.executable, "-I", "-c", code, str(root), str(target)],
                            cwd=root, capture_output=True, text=True, timeout=60)
    (root / "smoke.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    (root / "RESULT.json").write_text(json.dumps(json.loads(result.stdout), indent=2) + "\n")
    print(result.stdout.strip())


if __name__ == "__main__":
    main()
