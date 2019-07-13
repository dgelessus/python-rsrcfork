"""A library for reading old Macintosh resource manager data, as found in resource forks or .rsrc files even on current Mac OS X/macOS systems.

This library only understands the resource file's general structure, i. e. the type codes, IDs, attributes, and data of the resources stored in the file. The data of individual resources is provided in raw bytes form and is not processed further - the format of this data is specific to each resource type.

Writing resource data is not supported at all.
"""

__version__ = "1.1.3.post1"

__all__ = [
	"Resource",
	"ResourceAttrs",
	"ResourceFile",
	"ResourceFileAttrs",
	"open",
]

from . import api
from .api import Resource, ResourceAttrs, ResourceFile, ResourceFileAttrs

# noinspection PyShadowingBuiltins
open = ResourceFile.open
