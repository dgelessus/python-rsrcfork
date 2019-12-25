``rsrcfork``
============

A pure Python, cross-platform library/tool for reading Macintosh resource data, as stored in resource forks and ``.rsrc`` files.

Resource forks were an important part of the Classic Mac OS, where they provided a standard way to store structured file data, metadata and application resources. This usage continued into Mac OS X (now called macOS) for backward compatibility, but over time resource forks became less commonly used in favor of simple data fork-only formats, application bundles, and extended attributes.

As of OS X 10.8 and the deprecation of the Carbon API, macOS no longer provides any officially supported APIs for using and manipulating resource data. Despite this, parts of macOS still support and use resource forks, for example to store custom file and folder icons set by the user.

Features
--------

* Pure Python, cross-platform - no native Mac APIs are used.
* Provides both a Python API and a command-line tool.
* Resource data can be read from either the resource fork or the data fork.

  * On Mac systems, the correct fork is selected automatically when reading a file. This allows reading both regular resource forks and resource data stored in data forks (as with ``.rsrc`` and similar files).
  * On non-Mac systems, resource forks are not available, so the data fork is always used.

* Compressed resources (supported by System 7 through Mac OS 9) are automatically decompressed.

  * Only the standard System 7.0 resource compression methods are supported. Resources that use non-standard decompressors cannot be decompressed.

* Object ``repr``\s are REPL-friendly: all relevant information is displayed, and long data is truncated to avoid filling up the screen by accident.

Requirements
------------

Python 3.6 or later. No other libraries are required.

Installation
------------

``rsrcfork`` is available `on PyPI <https://pypi.org/project/rsrcfork/>`_ and can be installed using ``pip``: 

.. code-block:: sh

    python3 -m pip install rsrcfork

Alternatively you can download the source code manually, and run this command in the source code directory to install it:

.. code-block:: sh

    python3 -m pip install .

Examples
--------

Simple example
^^^^^^^^^^^^^^

.. code-block:: python

    >>> import rsrcfork
    >>> rf = rsrcfork.open("/Users/Shared/Test.textClipping")
    >>> rf
    <rsrcfork.ResourceFile at 0x1046e6048, attributes ResourceFileAttrs.0, containing 4 resource types: [b'utxt', b'utf8', b'TEXT', b'drag']>
    >>> rf[b"TEXT"]
    <rsrcfork.ResourceFile._LazyResourceMap at 0x10470ed30 containing one resource: rsrcfork.Resource(type=b'TEXT', id=256, name=None, attributes=ResourceAttrs.0, data=b'Here is some text')>

Automatic selection of data/resource fork
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    >>> import rsrcfork
    >>> datarf = rsrcfork.open("/System/Library/Fonts/Monaco.dfont") # Resources in data fork
    >>> datarf._stream
    <_io.BufferedReader name='/System/Library/Fonts/Monaco.dfont'>
    >>> resourcerf = rsrcfork.open("/Users/Shared/Test.textClipping") # Resources in resource fork
    >>> resourcerf._stream
    <_io.BufferedReader name='/Users/Shared/Test.textClipping/..namedfork/rsrc'>

Command-line interface
^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: sh

    $ python3 -m rsrcfork /Users/Shared/Test.textClipping
    4 resource types:
    'utxt': 1 resources:
    (256): 34 bytes
    
    'utf8': 1 resources:
    (256): 17 bytes
    
    'TEXT': 1 resources:
    (256): 17 bytes
    
    'drag': 1 resources:
    (128): 64 bytes
    
    $ python3 -m rsrcfork /Users/Shared/Test.textClipping "'TEXT' (256)"
    Resource 'TEXT' (256): 17 bytes:
    00000000 48 65 72 65 20 69 73 20 73 6f 6d 65 20 74 65 78 |Here is some tex|
    00000010 74                                              |t|
    00000011

Limitations
-----------

This library only understands the resource file's general structure, i. e. the type codes, IDs, attributes, and data of the resources stored in the file. The data of individual resources is provided in raw bytes form and is not processed further - the format of this data is specific to each resource type.

Definitions of common resource types can be found inside Carbon and related frameworks in Apple's macOS SDKs as ``.r`` files, a format roughly similar to C struct definitions, which is used by the ``Rez`` and ``DeRez`` command-line tools to de/compile resource data. There doesn't seem to be an exact specification of this format, and most documentation on it is only available inside old manuals for MPW (Macintosh Programmer's Workshop) or similar development tools for old Mac systems. Some macOS text editors, such as BBEdit/TextWrangler and TextMate support syntax highlighting for ``.r`` files.

Writing resource data is not supported at all.

Further info on resource files
------------------------------

For technical info and documentation about resource files and resources, see the `"resource forks" section of the mac_file_format_docs repo <https://github.com/dgelessus/mac_file_format_docs/blob/master/README.md#resource-forks>`_.

Changelog
---------

Version 1.7.1 (next version)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

* Removed the old (non-subcommand-based) CLI syntax.
* Added filtering support to the ``list`` subcommand.

Version 1.7.0
^^^^^^^^^^^^^

* Added a ``raw-decompress`` subcommand to decompress compressed resource data stored in a standalone file rather than as a resource.
* Optimized lazy loading of ``Resource`` objects. Previously, resource data would be read from disk whenever a ``Resource`` object was looked up, even if the data itself is never used. Now the resource data is only loaded once the ``data`` (or ``data_raw``) attribute is accessed.

  * The same optimization applies to the ``name`` attribute, although this is unlikely to make a difference in practice.
  * As a result, it is no longer possible to construct ``Resource`` objects without a resource file. This was previously possible, but had no practical use.
* Fixed a small error in the ``'dcmp' (0)`` decompression implementation.

Version 1.6.0
^^^^^^^^^^^^^

* Added a new subcommand-based command-line syntax to the ``rsrcfork`` tool, similar to other CLI tools such as ``git`` or ``diskutil``.

  * This subcommand-based syntax is meant to replace the old CLI options, as the subcommand structure is easier to understand and more extensible in the future.
  * Currently there are three subcommands: ``list`` to list resources in a file, ``read`` to read/display resource data, and ``read-header`` to read a resource file's header data. These subcommands can be used to perform all operations that were also available with the old CLI syntax.
  * The old CLI syntax is still supported for now, but it will be removed soon.
  * The new syntax no longer supports reading CLI arguments from a file (using ``@args_file.txt``), abbreviating long options (e. g. ``--no-d`` instead of ``--no-decompress``), or the short option ``-f`` instead of ``--fork``. If you have a need for any of these features, please open an issue.

Version 1.5.0
^^^^^^^^^^^^^

* Added stream-based decompression methods to the ``rsrcfork.compress`` module.

  * The internal decompressor implementations have been refactored to use streams.
  * This allows for incremental decompression of compressed resource data. In practice this has no noticeable effect yet, because the main ``rsrcfork`` API doesn't support incremental reading of resource data.

* Fixed the command line tool always displaying an incorrect error "Cannot specify an explicit fork when reading from stdin" when using ``-`` (stdin) as the input file.

Version 1.4.0
^^^^^^^^^^^^^

* Added ``length`` and ``length_raw`` attributes to ``Resource``. These attributes are equivalent to the ``len`` of ``data`` and ``data_raw`` respectively, but may be faster to access.

  * Currently, the only optimized case is ``length`` for compressed resources, but more optimizations may be added in the future.

* Added a ``compressed_info`` attribute to ``Resource`` that provides access to the header information of compressed resources.
* Improved handling of compressed resources when listing resource files with the command line tool.

  * Metadata of compressed resources is now displayed even if no decompressor implementation is available (as long as the compressed data header can be parsed).
  * Performance has been improved - the data no longer needs to be fully decompressed to get its length, this information is now read from the header.
  * The ``'dcmp'`` ID used to decompress each resource is displayed.

* Fixed an incorrect ``options.packages`` in ``setup.cfg``, which made the library unusable except when installing from source using ``--editable``.
* Fixed ``ResourceFile.__enter__`` returning ``None``, which made it impossible to use ``ResourceFile`` properly in a ``with`` statement.
* Fixed various minor errors reported by type checking with ``mypy``.

Version 1.3.0.post1
^^^^^^^^^^^^^^^^^^^

* Fixed an incorrect ``options.packages`` in ``setup.cfg``, which made the library unusable except when installing from source using ``--editable``.

Version 1.2.0.post1
^^^^^^^^^^^^^^^^^^^

* Fixed an incorrect ``options.packages`` in ``setup.cfg``, which made the library unusable except when installing from source using ``--editable``.

Version 1.3.0
^^^^^^^^^^^^^

* Added a ``--group`` command line option to group resources in list format by type (the default), ID, or with no grouping.
* Added a ``dump-text`` output format to the command line tool. This format is identical to ``dump``, but instead of a hex dump, it outputs the resource data as text. The data is decoded as MacRoman and classic Mac newlines (``\r``) are translated. This is useful for examining resources that contain mostly plain text.
* Changed the command line tool to sort resources by type and ID, and added a ``--no-sort`` option to disable sorting and output resources in file order (which was the previous behavior).
* Renamed the ``rsrcfork.Resource`` attributes ``resource_type`` and ``resource_id`` to ``type`` and ``id``, respectively. The old names have been deprecated and will be removed in the future, but are still supported for now.
* Changed ``--format=dump`` output to match ``hexdump -C``'s format - spacing has been adjusted, and multiple subsequent identical lines are collapsed into a single ``*``.

Version 1.2.0
^^^^^^^^^^^^^

* Added support for compressed resources.

  * Compressed resource data is automatically decompressed, both in the Python API and on the command line.
  * This is technically a breaking change, since in previous versions the compressed resource data was returned directly. However, this change will not affect end users negatively, unless one has already implemented custom handling for compressed resources.
  * Currently, only the three standard System 7.0 compression formats (``'dcmp'`` IDs 0, 1, 2) are supported. Attempting to access a resource compressed in an unsupported format results in a ``DecompressError``.
  * To access the raw resource data as stored in the file, without automatic decompression, use the ``res.data_raw`` attribute (for the Python API), or the ``--no-decompress`` option (for the command-line interface). This can be used to read the resource data in its compressed form, even if the compression format is not supported.

* Improved automatic data/resource fork selection for files whose resource fork contains invalid data.

  * This fixes reading certain system files with resource data in their data fork (such as HIToolbox.rsrc in HIToolbox.framework, or .dfont fonts) on recent macOS versions (at least macOS 10.14, possibly earlier). Although these files have no resource fork, recent macOS versions will successfully open the resource fork and return garbage data for it. This behavior is now detected and handled by using the data fork instead.

* Replaced the ``rsrcfork`` parameter of ``rsrcfork.open``/``ResourceFork.open`` with a new ``fork`` parameter. ``fork`` accepts string values (like the command line ``--fork`` option) rather than ``rsrcfork``'s hard to understand ``None``/``True``/``False``.

  * The old ``rsrcfork`` parameter has been deprecated and will be removed in the future, but for now it still works as before.

* Added an explanatory message when a resource filter on the command line doesn't match any resources in the resource file. Previously there would either be no output or a confusing error, depending on the selected ``--format``.
* Changed resource type codes and names to be displayed in MacRoman instead of escaping all non-ASCII characters.
* Cleaned up the resource descriptions in listings and dumps to improve readability. Previously they included some redundant or unnecessary information - for example, each resource with no attributes set would be explicitly marked as "no attributes".
* Unified the formats of resource descriptions in listings and dumps, which were previously slightly different from each other.
* Improved error messages when attempting to read multiple resources using ``--format=hex`` or ``--format=raw``.
* Fixed reading from non-seekable streams not working for some resource files.
* Removed the ``allow_seek`` parameter of ``ResourceFork.__init__`` and the ``--read-mode`` command line option. They are no longer necessary, and were already practically useless before due to non-seekable stream reading being broken.

Version 1.1.3.post1
^^^^^^^^^^^^^^^^^^^

* Fixed a formatting error in the README.rst to allow upload to PyPI.

Version 1.1.3
^^^^^^^^^^^^^

**Note: This version is not available on PyPI, see version 1.1.3.post1 changelog for details.**

* Added a setuptools entry point for the command-line interface. This allows calling it using just ``rsrcfork`` instead of ``python3 -m rsrcfork``.
* Changed the default value of ``ResourceFork.__init__``'s ``close`` keyword argument from ``True`` to ``False``. This matches the behavior of classes like ``zipfile.ZipFile`` and ``tarfile.TarFile``.
* Fixed ``ResourceFork.open`` and ``ResourceFork.__init__`` not closing their streams in some cases.
* Refactored the single ``rsrcfork.py`` file into a package. This is an internal change and should have no effect on how the ``rsrcfork`` module is used.

Version 1.1.2
^^^^^^^^^^^^^

* Added support for the resource file attributes "Resources Locked" and "Printer Driver MultiFinder Compatible" from ResEdit.
* Added more dummy constants for resource attributes with unknown meaning, so that resource files containing such attributes can be loaded without errors.

Version 1.1.1
^^^^^^^^^^^^^

* Fixed overflow issue with empty resource files or empty resource type entries
* Changed ``_hexdump`` to behave more like ``hexdump -C``

Version 1.1.0
^^^^^^^^^^^^^

* Added a command-line interface - run ``python3 -m rsrcfork --help`` for more info

Version 1.0.0
^^^^^^^^^^^^^

* Initial version
