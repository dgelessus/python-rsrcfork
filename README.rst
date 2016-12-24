``rsrcfork``
============

A pure Python library for reading Macintosh Toolbox or Carbon resource manager data, as found in resource forks or ``.rsrc`` files even on current Mac OS X/macOS systems.

Requirements
------------

Python 3.6 or later. No other libraries are required.

Features
--------

* Reading resources from data or resource forks (the latter only work on macOS of course)
* Reading data lazily with seeking, or sequentially without seeking
* Accessing resource data and attributes by their type code and ID, using a mapping-like interface
* REPL-friendly ``repr``\s that truncate long resource data so it doesn't fill the entire screen

Examples
--------

Simple example
``````````````

.. code-block:: python

	>>> import rsrcfork
	>>> rf = rsrcfork.open("/Users/Shared/Test.textClipping")
	>>> rf
	<rsrcfork.ResourceFile at 0x1046e6048, attributes ResourceFileAttrs.0, containing 4 resource types: [b'utxt', b'utf8', b'TEXT', b'drag']>
	>>> rf[b"TEXT"]
	<rsrcfork.ResourceFile._LazyResourceMap at 0x10470ed30 containing one resource: rsrcfork.Resource(resource_type=b'TEXT', resource_id=256, name=None, attributes=ResourceAttrs.0, data=b'Here is some text')>

Automatic selection of data/resource fork
`````````````````````````````````````````

.. code-block:: python

	>>> import rsrcfork
	>>> datarf = rsrcfork.open("/System/Library/Fonts/Monaco.dfont") # Resources in data fork
	>>> datarf._stream
	<_io.BufferedReader name='/System/Library/Fonts/Monaco.dfont'>
	>>> resourcerf = rsrcfork.open("/Users/Shared/Test.textClipping") # Resources in resource fork
	>>> resourcerf._stream
	<_io.BufferedReader name='/Users/Shared/Test.textClipping/..namedfork/rsrc'>

Limitations
-----------

This library only understands the resource file's general structure, i. e. the type codes, IDs, attributes, and data of the resources stored in the file. The data of individual resources is provided in raw bytes form and is not processed further - the format of this data is specific to each resource type.

Definitions of common resource types can be found inside Carbon and related frameworks in Apple's macOS SDKs as ``.r`` files, a format roughly similar to C struct definitions, which is used by the ``Rez`` and ``DeRez`` command-line tools to de/compile resource data. There doesn't seem to be an exact specification of this format, and most documentation on it is only available inside old manuals for MPW (Macintosh Programmer's Workshop) or similar development tools for old Mac systems. Some macOS text editors, such as BBEdit/TextWrangler and TextMate support syntax highlighting for ``.r`` files.

Writing resource data is not supported at all.

Further info on resource files
------------------------------

Sources of information about the resource fork data format, and the structure of common resource types:

* Inside Macintosh, Volume I, Chapter 5 "The Resource Manager". This book can probably be obtained in physical form somewhere, but the relevant chapter/book is also available in a few places online:
	* `Apple's legacy documentation`__
	* pagetable.com, a site that happened to have a copy of the book: `info blog post`__, `direct download`__
* `Wikipedia`__, of course
* The `Resource Fork`__ article on "Just Solve the File Format Problem" (despite the title, this is a decent site and not clickbait)
* The `KSFL`__ library (and `its wiki`__), written in Java, which supports reading and writing resource files
* Apple's macOS SDK, which is distributed with Xcode. The latest version of Xcode is available for free from the Mac App Store. Current and previous versions can be downloaded from `the Apple Developer download page`__. Accessing these downloads requires an Apple ID with (at least) a free developer program membership.
* Apple's MPW (Macintosh Programmer's Workshop) and related developer tools. These were previously available from Apple's FTP server at ftp://ftp.apple.com/, which is no longer functional. Because of this, these downloads are only available on mirror sites, such as http://staticky.com/mirrors/ftp.apple.com/.

If these links are no longer functional, some are archived in the `Internet Archive Wayback Machine`__ or `archive.is`__ aka `archive.fo`__.

__ https://developer.apple.com/legacy/library/documentation/mac/pdf/MoreMacintoshToolbox.pdf

__ http://www.pagetable.com/?p=50

__ http://www.weihenstephan.org/~michaste/pagetable/mac/Inside_Macintosh.pdf

__ https://en.wikipedia.org/wiki/Resource_fork

__ http://fileformats.archiveteam.org/wiki/Resource_Fork

__ https://github.com/kreativekorp/ksfl

__ https://github.com/kreativekorp/ksfl/wiki/Macintosh-Resource-File-Format

__ https://developer.apple.com/download/more/

__ https://archive.org/web/

__ http://archive.is/

__ https://archive.fo/
