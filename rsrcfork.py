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
import typing

__all__ = [
	"Resource",
	"ResourceAttrs",
	"ResourceFile",
	"ResourceFileAttrs",
	"open",
]

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
	_UNKNWON_1 = 1

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
	def open(cls, filename: typing.Union[str, bytes, os.PathLike], *, rsrcfork: typing.Optional[bool]=None) -> "ResourceFile":
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
		return cls(f)
	
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
		
		if __debug__:
			if self.header_system_data != bytes(len(self.header_system_data)):
				print("Header system data is not all null bytes. This may be of interest.")
			
			if self.header_application_data != bytes(len(self.header_application_data)):
				print("Header application data is not all null bytes. This may be of interest.")
		
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
