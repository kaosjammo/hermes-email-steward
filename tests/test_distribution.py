"""Real installed web contract and distribution member/content verification."""
from importlib import metadata
import os
from pathlib import Path
import sys
import tarfile
import tomllib
import zipfile

from packaging.requirements import Requirement
import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get("ES_REPAIR_SOURCE", ROOT))
UPSTREAM = Path(os.environ.get("HERMES_UPSTREAM", ROOT.parent))


def test_actual_installed_web_versions_satisfy_host_and_plugin_declarations():
    sys.path.insert(0, str(UPSTREAM))
    try:
        from pm.plugin_declarations import read_python_declaration
        declaration = read_python_declaration(SOURCE)
    finally:
        sys.path.remove(str(UPSTREAM))
    host = tomllib.loads((UPSTREAM / "pyproject.toml").read_text())["project"]["optional-dependencies"]["web"]
    for value in [*host, *declaration.install_requirements]:
        requirement = Requirement(value)
        assert requirement.specifier.contains(metadata.version(requirement.name)), value
    # These are actual imported package distributions, not metadata-only wheels.
    import fastapi, starlette, uvicorn, python_multipart
    assert fastapi.__version__ == metadata.version("fastapi")
    assert starlette.__version__ == metadata.version("starlette")
    assert uvicorn.__version__ == metadata.version("uvicorn")
    assert python_multipart.__version__ == metadata.version("python-multipart")


def test_built_distributions_include_native_inputs_and_linked_desktop_guide():
    directory = os.environ.get("ES_DISTRIBUTION_DIR")
    if not directory:
        pytest.skip("Set ES_DISTRIBUTION_DIR after package.sh for real artifact qualification")
    directory = Path(directory)
    for name in ("email-steward-plugin-0.1.0.tar.gz", "hermes_email_steward-0.1.0.tar.gz"):
        with tarfile.open(directory / name) as archive:
            members = {m.name.split("/", 1)[1]: m for m in archive.getmembers() if m.isfile() and "/" in m.name}
            for relative in ("plugin.yaml", "email_steward/gmail.py", "email_steward/plugin.py", "email_steward/gateways.py", "email_steward/outbound.py",
                             "desktop/plugin.js", "dashboard/plugin_api.py", "tests/desktop/README.md", "docs/FILE-INVENTORY.txt"):
                assert relative in members, (name, relative)
                assert archive.extractfile(members[relative]).read() == (SOURCE / relative).read_bytes()
    with zipfile.ZipFile(directory / "hermes_email_steward-0.1.0-py3-none-any.whl") as wheel:
        assert wheel.read("email_steward/gmail.py") == (SOURCE / "email_steward/gmail.py").read_bytes()
        assert "desktop/plugin.js" not in wheel.namelist()  # Wheel remains library-only.
