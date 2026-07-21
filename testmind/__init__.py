"""TestMind - Open-source intelligent testing AI platform."""

from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("testmind-ai")
except PackageNotFoundError:
    __version__ = "0.5.0"  # fallback for editable installs / source checkout