"""A pure Python, cross-platform library/tool for reading Macintosh resource data, as stored in resource forks and ``.rsrc`` files."""

# To release a new version:
# * Remove the .dev suffix from the version number in this file.
# * Update the changelog in the README.rst (rename the "next version" section to the correct version number).
# * Remove the ``dist`` directory (if it exists) to clean up any old release files.
# * Run ``python3 setup.py sdist bdist_wheel`` to build the release files.
# * Run ``python3 -m twine check dist/*`` to check the release files.
# * Fix any errors reported by the build and/or check steps.
# * Commit the changes to master.
# * Tag the release commit with the version number, prefixed with a "v" (e. g. version 1.2.3 is tagged as v1.2.3).
# * Fast-forward the release branch to the new release commit.
# * Push the master and release branches.
# * Upload the release files to PyPI using ``python3 -m twine upload dist/*``.
# * On the GitHub repo's Releases page, edit the new release tag and add the relevant changelog section from the README.rst. (Note: The README is in reStructuredText format, but GitHub's release notes use Markdown, so it may be necessary to adjust the markup syntax.)

# After releasing:
# * (optional) Remove the build and dist directories from the previous release as they are no longer needed.
# * Bump the version number in this file to the next version and add a .dev suffix.
# * Add a new empty section for the next version to the README.rst changelog.
# * Commit and push the changes to master.

__version__ = "1.6.0"

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
