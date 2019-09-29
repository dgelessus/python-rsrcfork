import collections
import collections.abc
import enum
import io
import os
import struct
import types
import typing
import warnings

from . import compress

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

class InvalidResourceFileError(Exception):
	pass

class ResourceFileAttrs(enum.Flag):
	"""Resource file attribute flags. The descriptions for these flags are taken from comments on the map*Bit and map* enum constants in <CarbonCore/Resources.h>."""
	
	mapResourcesLocked = 1 << 15 # "Resources Locked" (undocumented, but available as a checkbox in ResEdit)
	_BIT_14 = 1 << 14
	_BIT_13 = 1 << 13
	_BIT_12 = 1 << 12
	_BIT_11 = 1 << 11
	_BIT_10 = 1 << 10
	_BIT_9 = 1 << 9
	mapPrinterDriverMultiFinderCompatible = 1 << 8 # "Printer Driver MultiFinder Compatible" (undocumented, but available as a checkbox in ResEdit)
	mapReadOnly = 1 << 7 # "is this file read-only?", "Resource file read-only"
	mapCompact = 1 << 6 # "Is a compact necessary?", "Compact resource file"
	mapChanged = 1 << 5 # "Is it necessary to write map?", "Write map out at update"
	_BIT_4 = 1 << 4
	_BIT_3 = 1 << 3
	_BIT_2 = 1 << 2
	_BIT_1 = 1 << 1
	_BIT_0 = 1 << 0

class ResourceAttrs(enum.Flag):
	"""Resource attribute flags. The descriptions for these flags are taken from comments on the res*Bit and res* enum constants in <CarbonCore/Resources.h>."""
	
	resSysRef = 1 << 7 # "reference to system/local reference" (only documented as resSysRefBit = 7 in <CarbonCore/Resources.h>
	resSysHeap = 1 << 6 # "In system/in application heap", "System or application heap?"
	resPurgeable = 1 << 5 # "Purgeable/not purgeable", "Purgeable resource?"
	resLocked = 1 << 4 # "Locked/not locked", "Load it in locked?"
	resProtected = 1 << 3 # "Protected/not protected", "Protected?"
	resPreload = 1 << 2 # "Read in at OpenResource?", "Load in on OpenResFile?"
	resChanged = 1 << 1 # "Existing resource changed since last update", "Resource changed?"
	resCompressed = 1 << 0 # "indicates that the resource data is compressed" (only documented in https://github.com/kreativekorp/ksfl/wiki/Macintosh-Resource-File-Format)

class Resource(object):
	"""A single resource from a resource file."""
	
	type: bytes
	id: int
	name: typing.Optional[bytes]
	attributes: ResourceAttrs
	data_raw: bytes
	_compressed_info: compress.common.CompressedHeaderInfo
	_data_decompressed: bytes
	
	def __init__(self, resource_type: bytes, resource_id: int, name: typing.Optional[bytes], attributes: ResourceAttrs, data_raw: bytes) -> None:
		"""Create a new resource with the given type code, ID, name, attributes, and data."""
		
		super().__init__()
		
		self.type = resource_type
		self.id = resource_id
		self.name = name
		self.attributes = attributes
		self.data_raw = data_raw
	
	def __repr__(self) -> str:
		try:
			data = self.data
		except compress.DecompressError:
			decompress_ok = False
			data = self.data_raw
		else:
			decompress_ok = True
		
		if len(data) > 32:
			data_repr = f"<{len(data)} bytes: {data[:32]}...>"
		else:
			data_repr = repr(data)
		
		if not decompress_ok:
			data_repr = f"<decompression failed - compressed data: {data_repr}>"
		
		return f"{type(self).__module__}.{type(self).__qualname__}(type={self.type}, id={self.id}, name={self.name}, attributes={self.attributes}, data={data_repr})"
	
	@property
	def resource_type(self) -> bytes:
		warnings.warn(DeprecationWarning("The resource_type attribute has been deprecated and will be removed in a future version. Please use the type attribute instead."))
		return self.type
	
	@property
	def resource_id(self) -> int:
		warnings.warn(DeprecationWarning("The resource_id attribute has been deprecated and will be removed in a future version. Please use the id attribute instead."))
		return self.id
	
	@property
	def compressed_info(self) -> typing.Optional[compress.common.CompressedHeaderInfo]:
		"""The compressed resource header information, or None if this resource is not compressed.
		
		Accessing this attribute may raise a DecompressError if the resource data is compressed and the header could not be parsed. To access the unparsed header data, use the data_raw attribute.
		"""
		
		if ResourceAttrs.resCompressed in self.attributes:
			try:
				return self._compressed_info
			except AttributeError:
				self._compressed_info = compress.common.CompressedHeaderInfo.parse(self.data_raw)
				return self._compressed_info
		else:
			return None
	
	@property
	def length_raw(self) -> int:
		"""The length of the raw resource data, which may be compressed.
		
		Accessing this attribute may be faster than computing len(self.data_raw) manually.
		"""
		
		return len(self.data_raw)
	
	@property
	def length(self) -> int:
		"""The length of the resource data. If the resource data is compressed, this is the length of the data after decompression.
		
		Accessing this attribute may be faster than computing len(self.data) manually.
		"""
		
		if self.compressed_info is not None:
			return self.compressed_info.decompressed_length
		else:
			return self.length_raw
	
	@property
	def data(self) -> bytes:
		"""The resource data, decompressed if necessary.
		
		Accessing this attribute may raise a DecompressError if the resource data is compressed and could not be decompressed. To access the compressed resource data, use the data_raw attribute.
		"""
		
		if self.compressed_info is not None:
			try:
				return self._data_decompressed
			except AttributeError:
				self._data_decompressed = compress.decompress_parsed(self.compressed_info, self.data_raw[self.compressed_info.header_length:])
				return self._data_decompressed
		else:
			return self.data_raw

class ResourceFile(typing.Mapping[bytes, typing.Mapping[int, Resource]], typing.ContextManager["ResourceFile"]):
	"""A resource file reader operating on a byte stream."""
	
	# noinspection PyProtectedMember
	class _LazyResourceMap(typing.Mapping[int, Resource]):
		"""Internal class: Lazy mapping of resource IDs to resource objects, returned when subscripting a ResourceFile."""
		
		_resfile: "ResourceFile"
		_restype: bytes
		_submap: typing.Mapping[int, typing.Tuple[int, ResourceAttrs, int]]
		
		def __init__(self, resfile: "ResourceFile", restype: bytes) -> None:
			"""Create a new _LazyResourceMap "containing" all resources in resfile that have the type code restype."""
			
			super().__init__()
			
			self._resfile = resfile
			self._restype = restype
			self._submap = self._resfile._references[self._restype]
		
		def __len__(self) -> int:
			"""Get the number of resources with this type code."""
			
			return len(self._submap)
		
		def __iter__(self) -> typing.Iterator[int]:
			"""Iterate over the IDs of all resources with this type code."""
			
			return iter(self._submap)
		
		def __contains__(self, key: object) -> bool:
			"""Check if a resource with the given ID exists for this type code."""
			
			return key in self._submap
		
		def __getitem__(self, key: int) -> Resource:
			"""Get a resource with the given ID for this type code."""
			
			name_offset, attributes, data_offset = self._submap[key]
			
			if name_offset == 0xffff:
				name = None
			else:
				self._resfile._stream.seek(self._resfile.map_offset + self._resfile.map_name_list_offset + name_offset)
				(name_length,) = self._resfile._stream_unpack(STRUCT_RESOURCE_NAME_HEADER)
				name = self._resfile._read_exact(name_length)
			
			self._resfile._stream.seek(self._resfile.data_offset + data_offset)
			(data_length,) = self._resfile._stream_unpack(STRUCT_RESOURCE_DATA_HEADER)
			data = self._resfile._read_exact(data_length)
			
			return Resource(self._restype, key, name, attributes, data)
		
		def __repr__(self) -> str:
			if len(self) == 1:
				return f"<{type(self).__module__}.{type(self).__qualname__} at {id(self):#x} containing one resource: {next(iter(self.values()))}>"
			else:
				return f"<{type(self).__module__}.{type(self).__qualname__} at {id(self):#x} containing {len(self)} resources with IDs: {list(self)}>"
	
	_close_stream: bool
	_stream: typing.BinaryIO
	
	data_offset: int
	map_offset: int
	data_length: int
	map_length: int
	header_system_data: bytes
	header_application_data: bytes
	
	map_type_list_offset: int
	map_name_list_offset: int
	file_attributes: ResourceFileAttrs
	
	_reference_counts: typing.MutableMapping[bytes, int]
	_references: typing.MutableMapping[bytes, typing.MutableMapping[int, typing.Tuple[int, ResourceAttrs, int]]]
	
	@classmethod
	def open(cls, filename: typing.Union[str, os.PathLike], *, fork: str="auto", **kwargs: typing.Any) -> "ResourceFile":
		"""Open the file at the given path as a ResourceFile.
		
		The fork parameter controls which fork of the file the resource data will be read from. It accepts the following values:
		
		* "auto" (the default): Automatically select the correct fork. The resource fork will be used if the file has one and it contains valid resource data. Otherwise the data fork will be used.
		* "rsrc": Force use of the resource fork and never fall back to the data fork. This will not work on systems other than macOS, because they do not support resource forks natively.
		* "data": Force use of the data fork, even if a resource fork is present.
		
		The rsrcfork parameter is deprecated and will be removed in the future. It has the same purpose as the fork parameter, but accepts different argument values: None stands for "auto", True stands for "rsrc", and False stands for "data". These argument values are less understandable than the string versions and are not easily extensible in the future, which is why the parameter has been deprecated.
		"""
		
		if "close" in kwargs:
			raise TypeError("ResourceFile.open does not support the 'close' keyword argument")
		
		kwargs["close"] = True
		
		if "rsrcfork" in kwargs:
			if fork != "auto":
				raise TypeError("The fork and rsrcfork parameters cannot be used together. Please use only the fork parameter; it replaces the deprecated rsrcfork parameter.")
			
			if kwargs["rsrcfork"] is None:
				fork = "auto"
			elif kwargs["rsrcfork"]:
				fork = "rsrc"
			else:
				fork = "data"
			warnings.warn(DeprecationWarning(f"The rsrcfork parameter has been deprecated and will be removed in a future version. Please use fork={fork!r} instead of rsrcfork={kwargs['rsrcfork']!r}."))
			del kwargs["rsrcfork"]
		
		if fork == "auto":
			# Determine whether the file has a usable resource fork.
			try:
				# Try to open the resource fork.
				f = open(os.path.join(filename, "..namedfork", "rsrc"), "rb")
			except (FileNotFoundError, NotADirectoryError):
				# If the resource fork doesn't exist, fall back to the data fork.
				return cls(open(filename, "rb"), **kwargs)
			else:
				# Resource fork exists, check if it actually contains valid resource data.
				# This check is necessary because opening ..namedfork/rsrc on files that don't actually have a resource fork can sometimes succeed, but the resulting stream will either be empty, or (as of macOS 10.14, and possibly earlier) contain garbage data.
				try:
					return cls(f, **kwargs)
				except InvalidResourceFileError:
					# Resource fork is empty or invalid, fall back to the data fork.
					f.close()
					return cls(open(filename, "rb"), **kwargs)
				except BaseException:
					f.close()
					raise
		elif fork == "rsrc":
			# Force use of the resource fork.
			return cls(open(os.path.join(filename, "..namedfork", "rsrc"), "rb"), **kwargs)
		elif fork == "data":
			# Force use of the data fork.
			return cls(open(filename, "rb"), **kwargs)
		else:
			raise ValueError(f"Unsupported value for the fork parameter: {fork!r}")
	
	def __init__(self, stream: typing.BinaryIO, *, close: bool=False) -> None:
		"""Create a ResourceFile wrapping the given byte stream.
		
		To read resource file data from a bytes object, wrap it in an io.BytesIO.
		
		If the stream is seekable, only the file header and resource map are read initially. Resource data and names are loaded on-demand when the respective resource is accessed. If the stream is not seekable, the entire stream data is read into memory (this is necessary because the resource map is stored at the end of the resource file).
		
		In practice, memory usage is usually not a concern when reading resource files. Even large resource files are only a few megabytes in size, and due to limitations in the format, resource files cannot be much larger than 16 MiB (except for special cases that are unlikely to occur in practice).
		
		close controls whether the stream should be closed when the ResourceFile's close method is called. By default this is False.
		"""
		
		super().__init__()
		
		self._close_stream = close
		if stream.seekable():
			self._stream = stream
		else:
			self._stream = io.BytesIO(stream.read())
		
		try:
			self._read_header()
			self._stream.seek(self.map_offset)
			self._read_map_header()
			self._read_all_resource_types()
			self._read_all_references()
		except BaseException:
			self.close()
			raise
	
	def _read_exact(self, byte_count: int) -> bytes:
		"""Read byte_count bytes from the stream and raise an exception if too few bytes are read (i. e. if EOF was hit prematurely)."""
		
		data = self._stream.read(byte_count)
		if len(data) != byte_count:
			raise InvalidResourceFileError(f"Attempted to read {byte_count} bytes of data, but only got {len(data)} bytes")
		return data
	
	def _stream_unpack(self, st: struct.Struct) -> tuple:
		"""Unpack data from the stream according to the struct st. The number of bytes to read is determined using st.size, so variable-sized structs cannot be used with this method."""
		
		try:
			return st.unpack(self._read_exact(st.size))
		except struct.error as e:
			raise InvalidResourceFileError(str(e))
	
	def _read_header(self) -> None:
		"""Read the resource file header, starting at the current stream position."""
		
		assert self._stream.tell() == 0
		
		(
			self.data_offset,
			self.map_offset,
			self.data_length,
			self.map_length,
			self.header_system_data,
			self.header_application_data,
		) = self._stream_unpack(STRUCT_RESOURCE_HEADER)
		
		if self._stream.tell() != self.data_offset:
			raise InvalidResourceFileError(f"The data offset ({self.data_offset}) should point exactly to the end of the file header ({self._stream.tell()})")
	
	def _read_map_header(self) -> None:
		"""Read the map header, starting at the current stream position."""
		
		assert self._stream.tell() == self.map_offset
		
		(
			_file_attributes,
			self.map_type_list_offset,
			self.map_name_list_offset,
		) = self._stream_unpack(STRUCT_RESOURCE_MAP_HEADER)
		
		self.file_attributes = ResourceFileAttrs(_file_attributes)
	
	def _read_all_resource_types(self) -> None:
		"""Read all resource types, starting at the current stream position."""
		
		self._reference_counts = collections.OrderedDict()
		
		(type_list_length_m1,) = self._stream_unpack(STRUCT_RESOURCE_TYPE_LIST_HEADER)
		type_list_length = (type_list_length_m1 + 1) % 0x10000
		
		for _ in range(type_list_length):
			(
				resource_type,
				count_m1,
				reflist_offset,
			) = self._stream_unpack(STRUCT_RESOURCE_TYPE)
			count = (count_m1 + 1) % 0x10000
			self._reference_counts[resource_type] = count
	
	def _read_all_references(self) -> None:
		"""Read all resource references, starting at the current stream position."""
		
		self._references = collections.OrderedDict()
		
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
	
	def close(self) -> None:
		"""Close this ResourceFile.
		
		If close=True was passed when this ResourceFile was created, the underlying stream's close method is called as well.
		"""
		
		if self._close_stream:
			self._stream.close()
	
	def __enter__(self) -> "ResourceFile":
		return self
	
	def __exit__(
		self,
		exc_type: typing.Optional[typing.Type[BaseException]],
		exc_val: typing.Optional[BaseException],
		exc_tb: typing.Optional[types.TracebackType]
	) -> typing.Optional[bool]:
		self.close()
		return None
	
	def __len__(self) -> int:
		"""Get the number of resource types in this ResourceFile."""
		
		return len(self._references)
	
	def __iter__(self) -> typing.Iterator[bytes]:
		"""Iterate over all resource types in this ResourceFile."""
		
		return iter(self._references)
	
	def __contains__(self, key: object) -> bool:
		"""Check whether this ResourceFile contains any resources of the given type."""
		
		return key in self._references
	
	def __getitem__(self, key: bytes) -> "ResourceFile._LazyResourceMap":
		"""Get a lazy mapping of all resources with the given type in this ResourceFile."""
		
		return ResourceFile._LazyResourceMap(self, key)
	
	def __repr__(self) -> str:
		return f"<{type(self).__module__}.{type(self).__qualname__} at {id(self):#x}, attributes {self.file_attributes}, containing {len(self)} resource types: {list(self)}>"
