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

Sources of information about the resource fork data format, and the structure of common resource types:

* The Inside Macintosh book series, specifically the chapter "Resource Manager". These books are Apple's official reference material for the classic Macintosh platform. Over time, they have gone through many revisions and updates, and their structure has been changed multiple times. This is a (likely incomplete) list of the major revisions of Inside Macintosh and where they can be obtained online.

  * The earliest revisions consisted of two volumes, each a three-ring binder containing photocopied pages. The chapters were referred to as individual "manuals" and were essentially standalone - each one had its own title page, TOC, glossary, and page numbers. Various parts were still missing or not yet finalized, and updated pages were distributed regularly as part of the `Macintosh Software Supplement <https://macgui.com/news/article.php?t=447>`_.
  
    * bitsavers.org has scanned and OCRed PDFs of a late (November 1984) revision: `Volume I <http://bitsavers.org/pdf/apple/mac/Inside_Macintosh_Vol_1_1984.pdf>`_, `Volume II <http://bitsavers.org/pdf/apple/mac/Inside_Macintosh_Vol_2_1984.pdf>`_.
  
  * The Promotional Edition, released in early 1985, consisted of a single book (it was nicknamed the "phonebook" edition because of its paper quality). Although it was physically a single book, the contents were still structured into standalone "manuals" like in the ring binder version, and some parts were still missing or not finalized.
  
    * bitsavers.org has `a scanned and OCRed PDF <http://bitsavers.org/pdf/apple/mac/Inside_Macintosh_Promotional_Edition_1985.pdf>`_.
  
  * The published 1985 revision consisted of three volumes, available as three paperback books or a single hardcover book. They contained the finalized contents of the previous revisions, which documented the Macintosh 128k, Macintosh 512k, and Macintosh XL. Unlike the previous revisions, each volume had continuous page numbers and a full TOC and index, and volume III contained a complete glossary.
  
    * pagetable.com has a `blog post <http://www.pagetable.com/?p=50>`_ with `a scanned and OCRed PDF of the three paperback volumes <http://www.weihenstephan.org/~michaste/pagetable/mac/Inside_Macintosh.pdf>`_.
  
  * Additional volumes were published later to document newer Macintosh models. These served as incremental additions and did not fully supersede or replace any of the previous volumes.
  
    * Volume IV was published in 1986 and documented the Macintosh Plus and Macintosh 512k Enhanced.
    * Volume V was published in 1986 and documented the Macintosh II and Macintosh SE.
    * Volume VI was published in 1991 and documented System 7.0.
    * VintageApple.org has `scanned and OCRed PDFs of Volumes I through VI <https://vintageapple.org/inside_o/>`_.
  
  * After 1991, Inside Macintosh was restructured into over 20 volumes organized by topic, rather than chronologically by Macintosh model. These were published as books starting in 1992, and later also on CDs and online.
  
    * VintageApple.org has `rendered (not scanned) PDFs of 26 volumes and 7 X-Ref volumes <https://vintageapple.org/inside_r/>`_.
    
      * The Communications Toolbox and QuickDraw GX Programmers' Overview volumes appear to be missing.
    
    * Many volumes are still available in Apple's legacy developer documentation archive, in HTML and rendered (not scanned) PDF formats:
    
      * Two volumes appear on the website under Inside Macintosh, even though other sources don't consider them part of the Inside Macintosh series:
      
        * `Advanced Color Imaging on the Mac OS (HTML) <https://developer.apple.com/library/archive/documentation/mac/ACI/ACI-2.html>`_ (November 1996)
        * `Advanced Color Imaging Reference (HTML) <https://developer.apple.com/library/archive/documentation/mac/ACIReference/ACIReference-2.html>`_ (November 1996)
      
      * `Devices (HTML) <https://developer.apple.com/library/archive/documentation/mac/Devices/Devices-2.html>`_ (July 1996), `Devices (chapter PDFs) <https://developer.apple.com/library/archive/documentation/mac/pdf/Devices/pdf.html>`_ (1994)
      * `Files (HTML) <https://developer.apple.com/library/archive/documentation/mac/Files/Files-2.html>`_ (July 1996), `Files (chapter PDFs) <https://developer.apple.com/library/archive/documentation/mac/pdf/Files/pdf.html>`_ (1992)
      * `Imaging with QuickDraw (HTML) <https://developer.apple.com/library/archive/documentation/mac/QuickDraw/QuickDraw-2.html>`_ (July 1996), `Imaging with QuickDraw (single PDF) <https://developer.apple.com/library/archive/documentation/mac/pdf/ImagingWithQuickDraw.pdf>`_ (1994)
      * `Interapplication Communication (HTML) <https://developer.apple.com/library/archive/documentation/mac/IAC/IAC-2.html>`_ (July 1996), `Interapplication Communication (chapter PDFs) <https://developer.apple.com/library/archive/documentation/mac/pdf/Interapplication_Communication/pdf.html>`_ (1993)
      * `Macintosh Toolbox Essentials (HTML) <https://developer.apple.com/library/archive/documentation/mac/Toolbox/Toolbox-2.html>`_ (July 1996), `Macintosh Toolbox Essentials (single PDF) <https://developer.apple.com/library/archive/documentation/mac/pdf/MacintoshToolboxEssentials.pdf>`_ (1992)
      * `Memory (HTML) <https://developer.apple.com/library/archive/documentation/mac/Memory/Memory-2.html>`_ (July 1996), `Memory (chapter PDFs) <https://developer.apple.com/library/archive/documentation/mac/pdf/Memory/pdf.html>`_ (1992)
      * `More Macintosh Toolbox (HTML) <https://developer.apple.com/library/archive/documentation/mac/MoreToolbox/MoreToolbox-2.html>`_ (July 1996), `More Macintosh Toolbox (single PDF) <https://developer.apple.com/library/archive/documentation/mac/pdf/MoreMacintoshToolbox.pdf>`_ (1993)
      * `Networking (HTML) <https://developer.apple.com/library/archive/documentation/mac/Networking/Networking-2.html>`_ (July 1996), `Networking (chapter PDFs) <https://developer.apple.com/library/archive/documentation/mac/pdf/Networking/pdf.html>`_ (1994)
      * `Operating System Utilities (HTML) <https://developer.apple.com/library/archive/documentation/mac/OSUtilities/OSUtilities-2.html>`_ (July 1996), `Operating System Utilities (chapter PDFs) <https://developer.apple.com/library/archive/documentation/mac/pdf/Operating_System_Utilities/pdf.html>`_ (1994)
      * `PowerPC Numerics (HTML) <https://developer.apple.com/library/archive/documentation/mac/PPCNumerics/PPCNumerics-2.html>`_ (July 1996), `PowerPC Numerics (chapter PDFs) <https://developer.apple.com/library/archive/documentation/mac/pdf/PPC_Numerics.sit.hqx>`_ (1994)
      * `PowerPC System Software (HTML) <https://developer.apple.com/library/archive/documentation/mac/PPCSoftware/PPCSoftware-2.html>`_ (July 1996), `PowerPC System Software (chapter PDFs) <https://developer.apple.com/library/archive/documentation/mac/pdf/PPC_System_Software.sit.hqx>`_ (1994)
      * `Processes (HTML) <https://developer.apple.com/library/archive/documentation/mac/Processes/Processes-2.html>`_ (June 1996), `Processes (chapter PDFs) <https://developer.apple.com/library/archive/documentation/mac/pdf/Processes/pdf.html>`_ (1992)
      * `Sound (HTML) <https://developer.apple.com/library/archive/documentation/mac/Sound/Sound-2.html>`_ (July 1996), `Sound (chapter PDFs) <https://developer.apple.com/library/archive/documentation/mac/pdf/Sound/pdf.html>`_ (1994)
      * `Text (HTML) <https://developer.apple.com/library/archive/documentation/mac/Text/Text-2.html>`_ (July 1996), `Text (single PDF) <https://developer.apple.com/library/archive/documentation/mac/pdf/Text.pdf>`_ (1993)
      * The two AOCE volumes, Communications Toolbox, Human Interface Guidelines, Overview, seven QuickDraw GX volumes, two QuickTime volumes, and X-Ref are missing.
  
  * The Gryphel project (best known for the Mini vMac emulator) has `a list of physical book releases <https://www.gryphel.com/c/books/appledev.html>`_ of Inside Macintosh (and other Apple developer documentation), including ISBNs, publishers, dates, and Amazon links.

* `Wikipedia <https://en.wikipedia.org/wiki/Resource_fork>`_, of course
* The `Resource Fork <http://fileformats.archiveteam.org/wiki/Resource_Fork>`_ article on "Just Solve the File Format Problem" (despite the title, this is a decent site and not clickbait)
* The `KSFL <https://github.com/kreativekorp/ksfl>`_ library (and `its wiki <https://github.com/kreativekorp/ksfl/wiki/Macintosh-Resource-File-Format>`_), written in Java, which supports reading and writing resource files
* Alysis Software Corporation's article on resource compression (found on `the company's website <http://www.alysis.us/arctechnology.htm>`_ and in `MacTech Magazine's online archive <http://preserve.mactech.com/articles/mactech/Vol.09/09.01/ResCompression/index.html>`_) has some information on the structure of certain kinds of compressed resources.
* Apple's macOS SDK, which is distributed with Xcode. The latest version of Xcode is available for free from the Mac App Store. Current and previous versions can be downloaded from `the Apple Developer download page <https://developer.apple.com/download/more/>`_. Accessing these downloads requires an Apple ID with (at least) a free developer program membership.
* Apple's MPW (Macintosh Programmer's Workshop) and related developer tools. These were previously available from Apple's FTP server at ftp://ftp.apple.com/, which is no longer functional. Because of this, these downloads are only available on mirror sites, such as http://staticky.com/mirrors/ftp.apple.com/.

If these links are no longer functional, some are archived in the `Internet Archive Wayback Machine <https://archive.org/web/>`_ or `archive.is <http://archive.is/>`_ aka `archive.fo <https://archive.fo/>`_.

Changelog
---------

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
