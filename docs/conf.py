"""Sphinx configuration for the Secure Contact Management API."""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Autodoc imports application modules. Safe documentation-only values prevent
# settings validation from requiring a developer's real `.env` file.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")
os.environ.setdefault(
    "JWT_SECRET_KEY", "documentation-only-secret-key-longer-than-32-characters"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")

project = "Secure Contact Management API"
author = "Repository maintainer"
release = "4.0.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
html_theme = "alabaster"
html_static_path = ["_static"]

autodoc_member_order = "bysource"
autodoc_typehints = "description"
autodoc_preserve_defaults = True
# Sphinx 9's new dynamic importer reloads third-party Pydantic models during
# introspection. The stable class-based backend avoids mutating those models.
autodoc_use_legacy_class_based = True
