import io
import struct
import typing


class DecompressError(Exception):
	"""Raised when resource data decompression fails, because the data is invalid or the compression type is not supported."""


# The signature of all compressed resource data, 0xa89f6572 in hex, or "®üer" in MacRoman.
COMPRESSED_SIGNATURE = b"\xa8\x9fer"
# The number of the "type 8" compression type. This type is used in the Finder, ResEdit, and some other system files.
COMPRESSED_TYPE_8 = 0x0801
# The number of the "type 9" compression type. This type is used in the System file and System 7.5's Installer.
COMPRESSED_TYPE_9 = 0x0901

# Common header for compressed resources of all types.
# 4 bytes: Signature (see above).
# 2 bytes: Length of the complete header (this common part and the type-specific part that follows it). (This meaning is just a guess - the field's value is always 0x0012, so there's no way to know for certain what it means.)
# 2 bytes: Compression type. Known so far: 0x0801 ("type 8") and 0x0901 ("type 9").
# 4 bytes: Length of the data after decompression.
# 6 bytes: Remainder of the header. The exact format varies depending on the compression type.
STRUCT_COMPRESSED_HEADER = struct.Struct(">4sHHI6s")

# Remainder of header for a "type 8" compressed resource.
# 1 byte: "Working buffer fractional size" - the ratio of the compressed data size to the uncompressed data size, times 256.
# 1 byte: "Expansion buffer size" - the maximum number of bytes that the data might grow during decompression.
# 2 bytes: The ID of the 'dcmp' resource that can decompress this resource. Currently only ID 0 is supported.
# 2 bytes: Reserved (always zero).
STRUCT_COMPRESSED_TYPE_8_HEADER = struct.Struct(">BBhH")

# Remainder of header for a "type 9" compressed resource.
# 2 bytes: The ID of the 'dcmp' resource that can decompress this resource. Currently only ID 2 is supported.
# 4 bytes: Decompressor-specific parameters.
STRUCT_COMPRESSED_TYPE_9_HEADER = struct.Struct(">h4s")


class CompressedHeaderInfo(object):
	@classmethod
	def parse_stream(cls, stream: typing.BinaryIO) -> "CompressedHeaderInfo":
		try:
			signature, header_length, compression_type, decompressed_length, remainder = STRUCT_COMPRESSED_HEADER.unpack(stream.read(STRUCT_COMPRESSED_HEADER.size))
		except struct.error:
			raise DecompressError(f"Invalid header")
		if signature != COMPRESSED_SIGNATURE:
			raise DecompressError(f"Invalid signature: {signature!r}, expected {COMPRESSED_SIGNATURE}")
		if header_length != 0x12:
			raise DecompressError(f"Unsupported header length: 0x{header_length:>04x}, expected 0x12")
		
		if compression_type == COMPRESSED_TYPE_8:
			working_buffer_fractional_size, expansion_buffer_size, dcmp_id, reserved = STRUCT_COMPRESSED_TYPE_8_HEADER.unpack(remainder)
			
			if reserved != 0:
				raise DecompressError(f"Reserved field should be 0, not 0x{reserved:>04x}")
			
			return CompressedType8HeaderInfo(header_length, compression_type, decompressed_length, dcmp_id, working_buffer_fractional_size, expansion_buffer_size)
		elif compression_type == COMPRESSED_TYPE_9:
			dcmp_id, parameters = STRUCT_COMPRESSED_TYPE_9_HEADER.unpack(remainder)
			
			return CompressedType9HeaderInfo(header_length, compression_type, decompressed_length, dcmp_id, parameters)
		else:
			raise DecompressError(f"Unsupported compression type: 0x{compression_type:>04x}")
	
	@classmethod
	def parse(cls, data: bytes) -> "CompressedHeaderInfo":
		return cls.parse_stream(io.BytesIO(data))
	
	header_length: int
	compression_type: int
	decompressed_length: int
	dcmp_id: int
	
	def __init__(self, header_length: int, compression_type: int, decompressed_length: int, dcmp_id: int) -> None:
		super().__init__()
		
		self.header_length = header_length
		self.compression_type = compression_type
		self.decompressed_length = decompressed_length
		self.dcmp_id = dcmp_id


class CompressedType8HeaderInfo(CompressedHeaderInfo):
	working_buffer_fractional_size: int
	expansion_buffer_size: int
	
	def __init__(self, header_length: int, compression_type: int, decompressed_length: int, dcmp_id: int, working_buffer_fractional_size: int, expansion_buffer_size: int) -> None:
		super().__init__(header_length, compression_type, decompressed_length, dcmp_id)
		
		self.working_buffer_fractional_size = working_buffer_fractional_size
		self.expansion_buffer_size = expansion_buffer_size
	
	def __repr__(self) -> str:
		return f"{type(self).__qualname__}(header_length={self.header_length}, compression_type=0x{self.compression_type:>04x}, decompressed_length={self.decompressed_length}, dcmp_id={self.dcmp_id}, working_buffer_fractional_size={self.working_buffer_fractional_size}, expansion_buffer_size={self.expansion_buffer_size})"


class CompressedType9HeaderInfo(CompressedHeaderInfo):
	parameters: bytes
	
	def __init__(self, header_length: int, compression_type: int, decompressed_length: int, dcmp_id: int, parameters: bytes) -> None:
		super().__init__(header_length, compression_type, decompressed_length, dcmp_id)
		
		self.parameters = parameters
	
	def __repr__(self) -> str:
		return f"{type(self).__qualname__}(header_length={self.header_length}, compression_type=0x{self.compression_type:>04x}, decompressed_length={self.decompressed_length}, dcmp_id={self.dcmp_id}, parameters={self.parameters!r})"


if typing.TYPE_CHECKING:
	class PeekableIO(typing.Protocol):
		"""Minimal protocol for binary IO streams that support the peek method.
		
		The peek method is supported by various standard Python binary IO streams, such as io.BufferedReader. If a stream does not natively support the peek method, it may be wrapped using the custom helper function make_peekable.
		"""
		
		def readable(self) -> bool: ...
		def read(self, size: typing.Optional[int] = ...) -> bytes: ...
		def peek(self, size: int = ...) -> bytes: ...


class _PeekableIOWrapper(object):
	"""Wrapper class to add peek support to an existing stream. Do not instantiate this class directly, use the make_peekable function instead.
	
	Python provides a standard io.BufferedReader class, which supports the peek method. However, according to its documentation, it only supports wrapping io.RawIOBase subclasses, and not streams which are already otherwise buffered.
	
	Warning: this class does not perform any buffering of its own, outside of what is required to make peek work. It is strongly recommended to only wrap streams that are already buffered or otherwise fast to read from. In particular, raw streams (io.RawIOBase subclasses) should be wrapped using io.BufferedReader instead.
	"""
	
	_wrapped: typing.BinaryIO
	_readahead: bytes
	
	def __init__(self, wrapped: typing.BinaryIO) -> None:
		super().__init__()
		
		self._wrapped = wrapped
		self._readahead = b""
	
	def readable(self) -> bool:
		return self._wrapped.readable()
	
	def read(self, size: typing.Optional[int] = None) -> bytes:
		if size is None or size < 0:
			ret = self._readahead + self._wrapped.read()
			self._readahead = b""
		elif size <= len(self._readahead):
			ret = self._readahead[:size]
			self._readahead = self._readahead[size:]
		else:
			ret = self._readahead + self._wrapped.read(size - len(self._readahead))
			self._readahead = b""
		
		return ret
	
	def peek(self, size: int = -1) -> bytes:
		if not self._readahead:
			self._readahead = self._wrapped.read(io.DEFAULT_BUFFER_SIZE if size < 0 else size)
		return self._readahead


def make_peekable(stream: typing.BinaryIO) -> "PeekableIO":
	"""Wrap an arbitrary binary IO stream so that it supports the peek method.
	
	The stream is wrapped as efficiently as possible (or not at all if it already supports the peek method). However, in the worst case a custom wrapper class needs to be used, which may not be particularly efficient and only supports a very minimal interface. The only methods that are guaranteed to exist on the returned stream are readable, read, and peek.
	"""
	
	if hasattr(stream, "peek"):
		# Stream is already peekable, nothing to be done.
		return typing.cast("PeekableIO", stream)
	elif isinstance(stream, io.RawIOBase):
		# Raw IO streams can be wrapped efficiently using BufferedReader.
		return io.BufferedReader(stream)
	else:
		# Other streams need to be wrapped using our custom wrapper class.
		return _PeekableIOWrapper(stream)


def read_exact(stream: typing.BinaryIO, byte_count: int) -> bytes:
	"""Read byte_count bytes from the stream and raise an exception if too few bytes are read (i. e. if EOF was hit prematurely)."""
	
	data = stream.read(byte_count)
	if len(data) != byte_count:
		raise DecompressError(f"Attempted to read {byte_count} bytes of data, but only got {len(data)} bytes")
	return data

def read_variable_length_integer(stream: typing.BinaryIO) -> int:
	"""Read a variable-length integer from the stream.
	
	This variable-length integer format is used by the 0xfe codes in the compression formats used by 'dcmp' (0) and 'dcmp' (1).
	"""
	
	head = read_exact(stream, 1)
	
	if head[0] == 0xff:
		return int.from_bytes(read_exact(stream, 4), "big", signed=True)
	elif head[0] >= 0x80:
		data_modified = bytes([(head[0] - 0xc0) & 0xff]) + read_exact(stream, 1)
		return int.from_bytes(data_modified, "big", signed=True)
	else:
		return int.from_bytes(head, "big", signed=True)
