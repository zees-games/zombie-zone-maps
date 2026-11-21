"""Launcher: this script lives in gs-map-convert/adapters/zombie-zone-maps/completeness.py, the family's one converter repository."""
import os
import sys

_C = os.environ.get("GSBSP_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "gs-map-convert")
sys.path.insert(0, os.path.join(_C, "adapters"))
import adapter_launch  # noqa: E402
adapter_launch.run(globals(), "zombie-zone-maps", "completeness.py")
