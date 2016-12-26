"""A library for reading old Macintosh resource manager data, as found in resource forks or .rsrc files even on current Mac OS X/macOS systems.

This library only understands the resource file's general structure, i. e. the type codes, IDs, attributes, and data of the resources stored in the file. The data of individual resources is provided in raw bytes form and is not processed further - the format of this data is specific to each resource type.

Writing resource data is not supported at all.
"""

import collections
import collections.abc
import enum
import io
import os
import struct
import sys
import typing

__all__ = [
	"Resource",
	"ResourceAttrs",
	"ResourceFile",
	"ResourceFileAttrs",
	"open",
]

__version__ = "1.1.0"

# Translation table to replace ASCII non-printable characters with periods.
_TRANSLATE_NONPRINTABLES = {k: "." for k in [*range(0x20), 0x7f]}

# The formats of all following structures is as described in the Inside Macintosh book (see module docstring).
# Signedness and byte order of the integers is never stated explicitly in IM.
# All integers are big-endian, as this is the native byte order of the 68k and PowerPC processors used in old Macs.
# Almost all integers are non-negative byte counts or offsets, so it only makes sense for them to be unsigned. Sometimes the number -1 is used as a placeholder value, it should be considered equivalent to its two's complement value interpreted as unsigned (i. e. all bits set). The only exception is the resource ID field, which is signed.

# Resource file header, found at the start of the resource file.
# 4 bytes: Offset from beginning of resource file to resource data. Basically guaranteed to be 0x100.
# 4 bytes: Offset from beginning of resource file to resource map.
# 4 bytes: Length of resource data.
# 4 bytes: Length of resource map.
# 112 bytes: System-reserved data. In practice, this is usually all null bytes.
# 128 bytes: Application-specific data. In practice, this is usually all null bytes.
STRUCT_RESOURCE_HEADER = struct.Struct(">IIII112s128s")

# Header for a single resource data block, found immediately before the resource data itself.
# 4 bytes: Length of following resource data.
STRUCT_RESOURCE_DATA_HEADER = struct.Struct(">I")

# Header for the resource map, found immediately after the last resource data block. This position is also indicated in the header.
# 16 bytes: Reserved for copy of resource header (in memory). Should be 0 in the file.
# 4 bytes: Reserved for handle to next resource map to be searched (in memory). Should be 0 in file.
# 2 bytes: Reserved for file reference number (in memory). Should be 0 in file.
# 2 bytes: Resource file attributes. Combination of ResourceFileAttrs flags, see below.
# 2 bytes: Offset from beginning of resource map to type list.
# 2 bytes: Offset from beginning of resource map to resource name list.
STRUCT_RESOURCE_MAP_HEADER = struct.Struct(">16x4x2xHHH")

# Header for the type list, found immediately after the resource map header.
# 2 bytes: Number of resource types in the map minus 1.
STRUCT_RESOURCE_TYPE_LIST_HEADER = struct.Struct(">H")

# A single type in the type list.
# 4 bytes: Resource type. This is usually a 4-character ASCII mnemonic, but may be any 4 bytes.
# 2 bytes: Number of resources of this type in the map minus 1.
# 2 bytes: Offset from beginning of type list to reference list for resources of this type.
STRUCT_RESOURCE_TYPE = struct.Struct(">4sHH")

# A single resource reference in a reference list. (A reference list has no header, and neither does the list of reference lists.)
# 2 bytes: Resource ID.
# 2 bytes: Offset from beginning of resource name list to length of resource name, or -1 (0xffff) if none.
# 1 byte: Resource attributes. Combination of ResourceAttrs flags, see below. (Note: packed into 4 bytes together with the next 3 bytes.)
# 3 bytes: Offset from beginning of resource data to length of data for this resource. (Note: packed into 4 bytes together with the previous 1 byte.)
# 4 bytes: Reserved for handle to resource (in memory). Should be 0 in file.
STRUCT_RESOURCE_REFERENCE = struct.Struct(">hHI4x")

# Header for a resource name, found immediately before the name itself. (The name list has no header.)
# 1 byte: Length of following resource name.
STRUCT_RESOURCE_NAME_HEADER = struct.Struct(">B")

class ResourceFileAttrs(enum.Flag):
	"""Resource file attribute flags. The descriptions for these flags are taken from comments on the map*Bit and map* enum constants in <CarbonCore/Resources.h>."""
	
	mapReadOnly = 128 # "is this file read-only?", "Resource file read-only"
	mapCompact = 64 # "Is a compact necessary?", "Compact resource file"
	mapChanged = 32 # "Is it necessary to write map?", "Write map out at update"
	_UNKNOWN_16 = 16
	_UNKNOWN_8 = 8
	_UNKNOWN_4 = 4
	_UNKNOWN_2 = 2
	_UNKNWON_1 = 1

class ResourceAttrs(enum.Flag):
	"""Resource attribute flags. The descriptions for these flags are taken from comments on the res*Bit and res* enum constants in <CarbonCore/Resources.h>."""
	
	resSysRef = 128 # "reference to system/local reference" (only documented as resSysRefBit = 7 in <CarbonCore/Resources.h>
	resSysHeap = 64 # "In system/in application heap", "System or application heap?"
	resPurgeable = 32 # "Purgeable/not purgeable", "Purgeable resource?"
	resLocked = 16 # "Locked/not locked", "Load it in locked?"
	resProtected = 8 # "Protected/not protected", "Protected?"
	resPreload = 4 # "Read in at OpenResource?", "Load in on OpenResFile?"
	resChanged = 2 # "Existing resource changed since last update", "Resource changed?"
	resCompressed = 1 # "indicates that the resource data is compressed" (only documented in https://github.com/kreativekorp/ksfl/wiki/Macintosh-Resource-File-Format)

_REZ_ATTR_NAMES = {
	ResourceAttrs.resSysRef: None, # "Illegal or reserved attribute"
	ResourceAttrs.resSysHeap: "sysheap",
	ResourceAttrs.resPurgeable: "purgeable",
	ResourceAttrs.resLocked: "locked",
	ResourceAttrs.resProtected: "protected",
	ResourceAttrs.resPreload: "preload",
	ResourceAttrs.resChanged: None, # "Illegal or reserved attribute"
	ResourceAttrs.resCompressed: None, # "Extended Header resource attribute"
}

F = typing.TypeVar("F", bound=enum.Flag, covariant=True)
def _decompose_flags(value: F) -> typing.Sequence[F]:
	"""Decompose an enum.Flags instance into separate enum constants."""
	
	return [bit for bit in type(value) if bit in value]

class Resource(object):
	"""A single resource from a resource file."""
	
	__slots__ = ("resource_type", "resource_id", "name", "attributes", "data")
	
	def __init__(self, resource_type: bytes, resource_id: int, name: typing.Optional[bytes], attributes: ResourceAttrs, data: bytes):
		"""Create a new resource with the given type code, ID, name, attributes, and data."""
		
		super().__init__()
		
		self.resource_type: bytes = resource_type
		self.resource_id: int = resource_id
		self.name: typing.Optional[bytes] = name
		self.attributes: ResourceAttrs = attributes
		self.data: bytes = data
	
	def __repr__(self):
		if len(self.data) > 32:
			data = f"<{len(self.data)} bytes: {self.data[:32]}...>"
		else:
			data = repr(self.data)
		
		return f"{type(self).__module__}.{type(self).__qualname__}(resource_type={self.resource_type}, resource_id={self.resource_id}, name={self.name}, attributes={self.attributes}, data={data})"

class ResourceFile(collections.abc.Mapping):
	"""A resource file reader operating on a byte stream."""
	
	# noinspection PyProtectedMember
	class _LazyResourceMap(collections.abc.Mapping):
		"""Internal class: Lazy mapping of resource IDs to resource objects, returned when subscripting a ResourceFile."""
		
		def __init__(self, resfile: "ResourceFile", restype: bytes):
			"""Create a new _LazyResourceMap "containing" all resources in resfile that have the type code restype."""
			
			super().__init__()
			
			self._resfile: "ResourceFile" = resfile
			self._restype: bytes = restype
			self._submap: typing.Mapping[int, typing.Tuple[int, ResourceAttrs, int]] = self._resfile._references[self._restype]
		
		def __len__(self):
			"""Get the number of resources with this type code."""
			
			return len(self._submap)
		
		def __iter__(self):
			"""Iterate over the IDs of all resources with this type code."""
			
			return iter(self._submap)
		
		def __contains__(self, key: int):
			"""Check if a resource with the given ID exists for this type code."""
			
			return key in self._submap
		
		def __getitem__(self, key: int) -> Resource:
			"""Get a resource with the given ID for this type code."""
			
			name_offset, attributes, data_offset = self._submap[key]
			
			if name_offset == 0xffff:
				name = None
			elif self._resfile._allow_seek:
				self._resfile._stream.seek(self._resfile.map_offset + self._resfile.map_name_list_offset + name_offset)
				(name_length,) = self._resfile._stream_unpack(STRUCT_RESOURCE_NAME_HEADER)
				name = self._resfile._read(name_length)
			else:
				name = self._resfile._resource_names[name_offset]
			
			if self._resfile._allow_seek:
				self._resfile._stream.seek(self._resfile.data_offset + data_offset)
				(data_length,) = self._resfile._stream_unpack(STRUCT_RESOURCE_DATA_HEADER)
				data = self._resfile._read(data_length)
			else:
				data = self._resfile._resource_data[data_offset]
			
			return Resource(self._restype, key, name, attributes, data)
		
		def __repr__(self):
			if len(self) == 1:
				return f"<{type(self).__module__}.{type(self).__qualname__} at {id(self):#x} containing one resource: {next(iter(self.values()))}>"
			else:
				return f"<{type(self).__module__}.{type(self).__qualname__} at {id(self):#x} containing {len(self)} resources with IDs: {list(self)}>"
	
	@classmethod
	def open(cls, filename: typing.Union[str, bytes, os.PathLike], *, rsrcfork: typing.Optional[bool]=None, **kwargs) -> "ResourceFile":
		"""Open the file at the given path as a ResourceFile.
		
		If rsrcfork is not None, it is treated as boolean and controls whether the data or resource fork of the file should be opened. (On systems other than macOS, opening resource forks will not work of course, since they don't exist.)
		If rsrcfork is None, guess whether the data or resource fork should be opened. If the resource fork exists and is not empty, it is opened, otherwise the data fork is opened instead.
		"""
		
		f: typing.io.BinaryIO
		if rsrcfork is None:
			# Determine whether the file has a usable resource fork.
			try:
				# Try to open the resource fork.
				f = io.open(os.path.join(filename, "..namedfork", "rsrc"), "rb")
			except (FileNotFoundError, NotADirectoryError):
				# If the resource fork doesn't exist, fall back to the data fork.
				f = io.open(filename, "rb")
			else:
				# Resource fork exists, check if it actually contains anything.
				if f.read(1):
					# Resource fork contains data, seek back to start before using it.
					f.seek(0)
				else:
					# Resource fork contains no data, fall back to the data fork.
					f = io.open(filename, "rb")
		elif rsrcfork:
			# Force use of the resource fork.
			f = io.open(os.path.join(filename, "..namedfork", "rsrc"), "rb")
		else:
			# Force use of the data fork.
			f = io.open(filename, "rb")
		
		# Use the selected fork to build a ResourceFile.
		return cls(f, **kwargs)
	
	def __init__(self, stream: typing.io.BinaryIO, *, allow_seek: typing.Optional[bool]=None, close: bool=True):
		"""Create a ResourceFile wrapping the given byte stream.
		
		To read resource file data from a bytes object, wrap it in an io.BytesIO.
		
		allow_seek controls whether seeking should be used when reading the file. If allow_seek is None, stream.seekable() is called to determine whether seeking should be used.
		If seeking is used, only the file header, map header, resource types, and resource references are read into memory. Resource data and names are loaded on-demand when the respective resource is accessed.
		If seeking is not used, the entire stream is processed sequentially and read into memory, including all resource data and names. This may be necessary when the stream does not support seeking at all. Memory is usually not a concern, most resource files are not even a megabyte in size.
		
		close controls whether the stream should be closed when the ResourceFile's close method is called.
		"""
		
		super().__init__()
		
		self._close_stream: bool = close
		self._stream: typing.io.BinaryIO = stream
		
		self._allow_seek: bool
		if allow_seek is None:
			self._allow_seek = self._stream.seekable()
		else:
			self._allow_seek = allow_seek
		
		if self._allow_seek:
			self._pos = None
			self._init_seeking()
		else:
			self._pos: int = 0
			self._init_streaming()
	
	def _tell(self) -> int:
		"""Get the current position in the stream. This uses the stream's tell method if seeking is enabled, and an internal counter otherwise."""
		
		if self._allow_seek:
			return self._stream.tell()
		else:
			return self._pos
	
	def _read(self, count: int) -> bytes:
		"""Read count bytes from the stream. If seeking is disabled, this also increments the internal seek counter accordingly."""
		
		ret = self._stream.read(count)
		if not self._allow_seek:
			self._pos += len(ret)
		return ret
	
	def _stream_unpack(self, st: struct.Struct) -> typing.Tuple:
		"""Unpack data from the stream according to the struct st. The number of bytes to read is determined using st.size, so variable-sized structs cannot be used with this method."""
		
		return st.unpack(self._read(st.size))
	
	def _read_header(self):
		"""Read the resource file header, starting at the current stream position."""
		
		assert self._tell() == 0
		
		self.data_offset: int
		self.map_offset: int
		self.data_length: int
		self.map_length: int
		self.header_system_data: bytes
		self.header_application_data: bytes
		(
			self.data_offset,
			self.map_offset,
			self.data_length,
			self.map_length,
			self.header_system_data,
			self.header_application_data,
		) = self._stream_unpack(STRUCT_RESOURCE_HEADER)
		
		assert self._tell() == self.data_offset
	
	def _read_all_resource_data(self):
		"""Read all resource data blocks, starting at the current stream position, until self.map_offset is reached."""
		
		assert self._tell() == self.data_offset
		
		self._resource_data: typing.MutableMapping[int, bytes] = collections.OrderedDict()
		
		while self._tell() < self.map_offset:
			initial_pos = self._tell()
			(length,) = self._stream_unpack(STRUCT_RESOURCE_DATA_HEADER)
			assert self._tell() + length <= self.map_offset
			self._resource_data[initial_pos] = self._read(length)
		
		assert self._tell() == self.map_offset
	
	def _read_map_header(self):
		"""Read the map header, starting at the current stream position."""
		
		assert self._tell() == self.map_offset
		
		self.map_type_list_offset: int
		self.map_name_list_offset: int
		(
			_file_attributes,
			self.map_type_list_offset,
			self.map_name_list_offset,
		) = self._stream_unpack(STRUCT_RESOURCE_MAP_HEADER)
		
		self.file_attributes: ResourceFileAttrs = ResourceFileAttrs(_file_attributes)
	
	def _read_all_resource_types(self):
		"""Read all resource types, starting at the current stream position."""
		
		self._reference_counts: typing.MutableMapping[bytes, int] = collections.OrderedDict()
		
		(type_list_length_m1,) = self._stream_unpack(STRUCT_RESOURCE_TYPE_LIST_HEADER)
		
		for _ in range(type_list_length_m1 + 1):
			(
				resource_type,
				count_m1,
				reflist_offset,
			) = self._stream_unpack(STRUCT_RESOURCE_TYPE)
			self._reference_counts[resource_type] = count_m1 + 1
	
	def _read_all_references(self):
		"""Read all resource references, starting at the current stream position."""
		
		self._references: typing.MutableMapping[bytes, typing.MutableMapping[int, typing.Tuple[int, ResourceAttrs, int]]] = collections.OrderedDict()
		
		for resource_type, count in self._reference_counts.items():
			resmap: typing.MutableMapping[int, typing.Tuple[int, ResourceAttrs, int]] = collections.OrderedDict()
			self._references[resource_type] = resmap
			for _ in range(count):
				(
					resource_id,
					name_offset,
					attributes_and_data_offset,
				) = self._stream_unpack(STRUCT_RESOURCE_REFERENCE)
				
				attributes = attributes_and_data_offset >> 24
				data_offset = attributes_and_data_offset & ((1 << 24) - 1)
				
				resmap[resource_id] = (name_offset, ResourceAttrs(attributes), data_offset)
	
	def _read_all_resource_names(self):
		"""Read all resource names, starting at the current stream position, until the end of the map is reached."""
		
		self._resource_names: typing.MutableMapping[int, bytes] = collections.OrderedDict()
		
		while self._tell() < self.map_offset + self.map_length:
			initial_pos = self._tell()
			(length,) = self._stream_unpack(STRUCT_RESOURCE_NAME_HEADER)
			self._resource_names[initial_pos] = self._read(length)
	
	def _init_seeking(self):
		"""Initialize self with seeking enabled, by reading the header, map header, resource types, and references."""
		
		self._read_header()
		self._stream.seek(self.map_offset)
		self._read_map_header()
		self._read_all_resource_types()
		self._read_all_references()
	
	def _init_streaming(self):
		"""Initialize self with seeking disabled, by reading the entire file sequentially."""
		
		self._read_header()
		self._read_all_resource_data()
		
		assert self._tell() == self.map_offset
		
		self._read_map_header()
		
		assert self._tell() == self.map_offset + self.map_type_list_offset
		
		self._read_all_resource_types()
		self._read_all_references()
		
		assert self._tell() == self.map_offset + self.map_name_list_offset
		
		self._read_all_resource_names()
	
	def close(self):
		"""Close the underlying stream, unless this behavior was suppressed by passing close=False to the constructor. If seeking is enabled for this ResourceFile, resources can no longer be read after closing the stream. On the other hand, if seeking is disabled, closing the stream does not affect the ResourceFile."""
		
		if self._close_stream:
			self._stream.close()
	
	def __enter__(self):
		pass
	
	def __exit__(self, exc_type, exc_val, exc_tb):
		self.close()
	
	def __len__(self):
		"""Get the number of resource types in this ResourceFile."""
		
		return len(self._references)
	
	def __iter__(self):
		"""Iterate over all resource types in this ResourceFile."""
		
		return iter(self._references)
	
	def __contains__(self, key: bytes):
		"""Check whether this ResourceFile contains any resources of the given type."""
		
		return key in self._references
	
	def __getitem__(self, key: bytes) -> "ResourceFile._LazyResourceMap":
		"""Get a lazy mapping of all resources with the given type in this ResourceFile."""
		
		return ResourceFile._LazyResourceMap(self, key)
	
	def __repr__(self):
		return f"<{type(self).__module__}.{type(self).__qualname__} at {id(self):#x}, attributes {self.file_attributes}, containing {len(self)} resource types: {list(self)}>"

open = ResourceFile.open

# The following internal functions are only used by the main function.

def _bytes_unescape(string: str) -> bytes:
	"""Convert a string containing ASCII characters and hex escapes to a bytestring.
	
	(We implement our own unescaping mechanism here to not depend on any of Python's string/bytes escape syntax.)
	"""
	
	out = []
	it = iter(string)
	n = 0
	for char in it:
		if char == "\\":
			try:
				esc = next(it)
				if esc in "\\\'\"":
					out.append(esc)
				elif esc == "x":
					x1, x2 = next(it), next(it)
					out.append(int(x1+x2, 16))
				else:
					raise ValueError(f"Unknown escape character: {esc}")
			except StopIteration:
				raise ValueError("End of string in escape sequence")
		else:
			out.append(ord(char))
		n += 1
	
	return bytes(out)

def _bytes_escape(bs: bytes, *, quote: str=None) -> str:
	"""Convert a bytestring to a string, with non-ASCII bytes hex-escaped.
	
	(We implement our own escaping mechanism here to not depend on Python's str or bytes repr.)
	"""
	
	out = []
	for byte in bs:
		c = chr(byte)
		if c in {quote, "\\"}:
			out.append(f"\\{c}")
		elif 0x20 <= byte < 0x7f:
			out.append(c)
		else:
			out.append(f"\\x{byte:02x}")
	
	return "".join(out)

def _filter_resources(rf: ResourceFile, filters: typing.Sequence[str]) -> typing.Sequence[Resource]:
	matching = collections.OrderedDict()
	
	for filter in filters:
		if len(filter) == 4:
			try:
				resources = rf[filter.encode("ascii")]
			except KeyError:
				continue
			
			for res in resources.values():
				matching[res.resource_type, res.resource_id] = res
		elif filter[0] == filter[-1] == "'":
			try:
				resources = rf[_bytes_unescape(filter[1:-1])]
			except KeyError:
				continue
			
			for res in resources.values():
				matching[res.resource_type, res.resource_id] = res
		else:
			pos = filter.find("'", 1)
			if pos == -1:
				raise ValueError(f"Invalid filter {filter!r}: Resource type must be single-quoted")
			elif filter[pos + 1] != " ":
				raise ValueError(f"Invalid filter {filter!r}: Resource type and ID must be separated by a space")
			
			restype, resid = filter[:pos + 1], filter[pos + 2:]
			
			if not restype[0] == restype[-1] == "'":
				raise ValueError(
					f"Invalid filter {filter!r}: Resource type is not a single-quoted type identifier: {restype!r}")
			restype = _bytes_unescape(restype[1:-1])
			
			if len(restype) != 4:
				raise ValueError(
					f"Invalid filter {filter!r}: Type identifier must be 4 bytes after replacing escapes, got {len(restype)} bytes: {restype!r}")
			
			if resid[0] != "(" or resid[-1] != ")":
				raise ValueError(f"Invalid filter {filter!r}: Resource ID must be parenthesized")
			resid = resid[1:-1]
			
			try:
				resources = rf[restype]
			except KeyError:
				continue
			
			if resid[0] == resid[-1] == '"':
				name = _bytes_unescape(resid[1:-1])
				
				for res in resources.values():
					if res.name == name:
						matching[res.resource_type, res.resource_id] = res
						break
			elif ":" in resid:
				if resid.count(":") > 1:
					raise ValueError(f"Invalid filter {filter!r}: Too many colons in ID range expression: {resid!r}")
				start, end = resid.split(":")
				start, end = int(start), int(end)
				
				for res in resources.values():
					if start <= res.resource_id <= end:
						matching[res.resource_type, res.resource_id] = res
			else:
				resid = int(resid)
				try:
					res = resources[resid]
				except KeyError:
					continue
				matching[res.resource_type, res.resource_id] = res
	
	return list(matching.values())

def _hexdump(data: bytes):
	for i in range(0, len(data), 16):
		line = data[i:i + 16]
		line_hex = " ".join(f"{byte:02x}" for byte in line)
		line_char = line.decode("MacRoman").translate(_TRANSLATE_NONPRINTABLES)
		print(f"{i:08x} {line_hex:<{16*2+15}} |{line_char:<16}|")

def _raw_hexdump(data: bytes):
	for i in range(0, len(data), 16):
		print(" ".join(f"{byte:02x}" for byte in data[i:i + 16]))

def main(args: typing.Sequence[str]):
	import argparse
	import textwrap
	
	ap = argparse.ArgumentParser(
		add_help=False,
		fromfile_prefix_chars="@",
		formatter_class=argparse.RawDescriptionHelpFormatter, description=textwrap.dedent("""
		Read and display resources from a file's resource or data fork.
		
		When specifying resource filters, each one may be of one of the
		following forms:
		
		An unquoted type name (without escapes): TYPE
		A quoted type name: 'TYPE'
		A quoted type name and an ID: 'TYPE' (42)
		A quoted type name and an ID range: 'TYPE' (24:42)
		A quoted type name and a resource name: 'TYPE' ("foobar")
		
		When multiple filters are specified, all resources matching any of them
		are displayed.
		"""),
	)
	
	ap.add_argument("--help", action="help", help="Display this help message and exit")
	ap.add_argument("--version", action="version", version=__version__, help="Display version information and exit")
	ap.add_argument("-a", "--all", action="store_true", help="When no filters are given, show all resources in full, instead of an overview")
	ap.add_argument("-f", "--fork", choices=["auto", "data", "rsrc"], default="auto", help="The fork from which to read the resource data, or auto to guess (default: %(default)s)")
	ap.add_argument("--format", choices=["dump", "hex", "raw", "derez"], default="dump", help="How to output the resources - human-readable info with hex dump (dump), data only as hex (hex), data only as raw bytes (raw), or like DeRez with no resource definitions (derez)")
	ap.add_argument("--header-system", action="store_true", help="Output system-reserved header data and nothing else")
	ap.add_argument("--header-application", action="store_true", help="Output application-specific header data and nothing else")
	ap.add_argument("--read-mode", choices=["auto", "stream", "seek"], default="auto", help="Whether to read the data sequentially (stream) or on-demand (seek), or auto to use seeking when possible (default: %(default)s)")
	
	ap.add_argument("file", help="The file to read, or - for stdin")
	ap.add_argument("filter", nargs="*", help="One or more filters to select which resources to display, or omit to show an overview of all resources")
	
	ns = ap.parse_args(args)
	
	ns.fork = {"auto": None, "data": False, "rsrc": True}[ns.fork]
	ns.read_mode = {"auto": None, "stream": False, "seek": True}[ns.read_mode]
	
	if ns.file == "-":
		if ns.fork is not None:
			print("Cannot specify an explicit fork when reading from stdin", file=sys.stderr)
			sys.exit(1)
		
		rf = ResourceFile(sys.stdin.buffer, allow_seek=ns.read_mode)
	else:
		rf = ResourceFile.open(ns.file, rsrcfork=ns.fork, allow_seek=ns.read_mode)
	
	with rf:
		if ns.header_system or ns.header_application:
			if ns.header_system:
				data = rf.header_system_data
			else:
				data = rf.header_application_data
			
			if ns.format == "dump":
				_hexdump(data)
			elif ns.format == "hex":
				_raw_hexdump(data)
			elif ns.format == "raw":
				sys.stdout.buffer.write(data)
			elif ns.format == "derez":
				print("Cannot output file header data in derez format", file=sys.stderr)
				sys.exit(1)
			else:
				raise ValueError(f"Unhandled output format: {ns.format}")
		elif ns.filter or ns.all:
			if ns.filter:
				resources = _filter_resources(rf, ns.filter)
			else:
				resources = []
				for reses in rf.values():
					resources.extend(reses.values())
			
			if ns.format in ("hex", "raw") and len(resources) != 1:
				print(f"Format {ns.format} only supports exactly one resource, but found {len(resources)}", file=sys.stderr)
				sys.exit(1)
			
			for res in resources:
				if ns.format == "dump":
					# Human-readable info and hex dump
					
					if res.name is None:
						name = "unnamed"
					else:
						name = _bytes_escape(res.name, quote='"')
						name = f'name "{name}"'
					
					attrs = _decompose_flags(res.attributes)
					if attrs:
						attrdesc = "attributes: " + " | ".join(attr.name for attr in attrs)
					else:
						attrdesc = "no attributes"
					
					restype = _bytes_escape(res.resource_type, quote="'")
					print(f"Resource '{restype}' ({res.resource_id}), {name}, {attrdesc}, {len(res.data)} bytes:")
					_hexdump(res.data)
					print()
				elif ns.format == "hex":
					# Data only as hex
					
					_raw_hexdump(res.data)
				elif ns.format == "raw":
					# Data only as raw bytes
					
					sys.stdout.buffer.write(res.data)
				elif ns.format == "derez":
					# Like DeRez with no resource definitions
					
					attrs = [_REZ_ATTR_NAMES[attr] for attr in _decompose_flags(res.attributes)]
					if None in attrs:
						attrs[:] = [f"${res.attributes.value:02X}"]
					
					parts = [str(res.resource_id)]
					
					if res.name is not None:
						name = _bytes_escape(res.name, quote='"')
						parts.append(f'"{name}"')
					
					parts += attrs
					
					restype = _bytes_escape(res.resource_type, quote="'")
					print(f"data '{restype}' ({', '.join(parts)}) {{")
					
					for i in range(0, len(res.data), 16):
						# Two-byte grouping is really annoying to implement.
						groups = []
						for j in range(0, 16, 2):
							if i+j >= len(res.data):
								break
							elif i+j+1 >= len(res.data):
								groups.append(f"{res.data[i+j]:02X}")
							else:
								groups.append(f"{res.data[i+j]:02X}{res.data[i+j+1]:02X}")
						
						s = f'$"{" ".join(groups)}"'
						comment = "/* " + res.data[i:i + 16].decode("MacRoman").translate(_TRANSLATE_NONPRINTABLES) + " */"
						print(f"\t{s:<54s}{comment}")
					
					print("};")
					print()
				else:
					raise ValueError(f"Unhandled output format: {ns.format}")
		else:
			if rf.header_system_data != bytes(len(rf.header_system_data)):
				print("Header system data:")
				_hexdump(rf.header_system_data)
			else:
				print("No header system data")
			
			if rf.header_application_data != bytes(len(rf.header_application_data)):
				print("Header application data:")
				_hexdump(rf.header_application_data)
			else:
				print("No header application data")
			
			attrs = _decompose_flags(rf.file_attributes)
			if attrs:
				print("File attributes: " + " | ".join(attr.name for attr in attrs))
			else:
				print("No file attributes")
			
			print(f"{len(rf)} resource types:")
			for typecode, resources in rf.items():
				restype = _bytes_escape(typecode, quote="'")
				print(f"'{restype}': {len(resources)} resources:")
				for resid, res in rf[typecode].items():
					if res.name is None:
						name = "unnamed"
					else:
						name = _bytes_escape(res.name, quote='"')
						name = f'name "{name}"'
					
					attrs = _decompose_flags(res.attributes)
					if attrs:
						attrdesc = " | ".join(attr.name for attr in attrs)
					else:
						attrdesc = "no attributes"
					
					print(f"({resid}), {name}, {attrdesc}, {len(res.data)} bytes")
				print()
	
	sys.exit(0)

if __name__ == "__main__":
	main(sys.argv[1:])
