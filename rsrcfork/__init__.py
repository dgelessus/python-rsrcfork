"""A pure Python, cross-platform library/tool for reading Macintosh resource data, as stored in resource forks and ``.rsrc`` files."""

__version__ = "1.3.0.post1"

__all__ = [
	"Resource",
	"ResourceAttrs",
	"ResourceFile",
	"ResourceFileAttrs",
	"compress",
	"open",
]

from . import api, compress
from .api import Resource, ResourceAttrs, ResourceFile, ResourceFileAttrs

# noinspection PyShadowingBuiltins
open = ResourceFile.open
