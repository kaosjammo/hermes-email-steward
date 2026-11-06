"""Host-loaded backend, independent of cwd or an editable package installation."""
import hashlib
import importlib.util
from pathlib import Path
import sys

# Hermes imports backend files by location without adding the plugin root to sys.path.
# Give this installed copy its own package namespace; never rebind host modules.
package_dir = Path(__file__).resolve().parents[1] / "email_steward"
namespace = "email_steward_backend_" + hashlib.sha256(str(package_dir).encode()).hexdigest()[:16]
if namespace not in sys.modules:
    spec = importlib.util.spec_from_file_location(namespace, package_dir / "__init__.py",
        submodule_search_locations=[str(package_dir)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[namespace] = module
    spec.loader.exec_module(module)
api = __import__(namespace + ".api", fromlist=["create_router"])
runtime = __import__(namespace + ".runtime", fromlist=["service_from_host"])
router = api.create_router(runtime.service_from_host)
