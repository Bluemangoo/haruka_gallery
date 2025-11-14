from types import ModuleType
from importlib import util
import importlib
from pathlib import Path
import sys

target = Path("import_from_file_content.py").resolve()

fake_pkg_name = "haruka_gallery_script"

pkg_dir = target.parent

pkg = ModuleType(fake_pkg_name)
pkg.__path__ = [str(pkg_dir)]
sys.modules[fake_pkg_name] = pkg

spec = util.spec_from_file_location(f"{fake_pkg_name}.import_from_file", str(target))
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod

spec.loader.exec_module(mod)