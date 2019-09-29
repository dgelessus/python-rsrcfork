import struct
import typing


class DecompressError(Exception):
	"""Raised when resource data decompression fails, because the data is invalid or the compression type is not supported."""


# The signature of all compressed resource data, 0xa89f6572 in hex, or "®üer" in MacRoman.
COMPRESSED_SIGNATURE = b"\xa8\x9fer"
# The compression type commonly used for application resources.
COMPRESSED_TYPE_APPLICATION = 0x0801
# The compression type commonly used for System file resources.
COMPRESSED_TYPE_SYSTEM = 0x0901

# Common header for compressed resources of all types.
# 4 bytes: Signature (see above).
# 2 bytes: Length of the complete header (this common part and the type-specific part that follows it). (This meaning is just a guess - the field's value is always 0x0012, so there's no way to know for certain what it means.)
# 2 bytes: Compression type. Known so far: 0x0901 is used in the System file's resources. 0x0801 is used in other files' resources.
# 4 bytes: Length of the data after decompression.
# 6 bytes: Remainder of the header. The exact format varies depending on the compression type.
STRUCT_COMPRESSED_HEADER = struct.Struct(">4sHHI6s")

# Remainder of header for an "application" compressed resource.
# 1 byte: "Working buffer fractional size" - the ratio of the compressed data size to the uncompressed data size, times 256.
# 1 byte: "Expansion buffer size" - the maximum number of bytes that the data might grow during decompression.
# 2 bytes: The ID of the 'dcmp' resource that can decompress this resource. Currently only ID 0 is supported.
# 2 bytes: Reserved (always zero).
STRUCT_COMPRESSED_APPLICATION_HEADER = struct.Struct(">BBhH")

# Remainder of header for a "system" compressed resource.
# 2 bytes: The ID of the 'dcmp' resource that can decompress this resource. Currently only ID 2 is supported.
# 4 bytes: Decompressor-specific parameters.
STRUCT_COMPRESSED_SYSTEM_HEADER = struct.Struct(">h4s")


class CompressedHeaderInfo(object):
	@classmethod
	def parse(cls, data: bytes) -> "CompressedHeaderInfo":
		try:
			signature, header_length, compression_type, decompressed_length, remainder = STRUCT_COMPRESSED_HEADER.unpack_from(data)
		except struct.error:
			raise DecompressError(f"Invalid header")
		if signature != COMPRESSED_SIGNATURE:
			raise DecompressError(f"Invalid signature: {signature!r}, expected {COMPRESSED_SIGNATURE}")
		if header_length != 0x12:
			raise DecompressError(f"Unsupported header length: 0x{header_length:>04x}, expected 0x12")
		
		if compression_type == COMPRESSED_TYPE_APPLICATION:
			working_buffer_fractional_size, expansion_buffer_size, dcmp_id, reserved = STRUCT_COMPRESSED_APPLICATION_HEADER.unpack(remainder)
			
			if reserved != 0:
				raise DecompressError(f"Reserved field should be 0, not 0x{reserved:>04x}")
			
			return CompressedApplicationHeaderInfo(header_length, compression_type, decompressed_length, dcmp_id, working_buffer_fractional_size, expansion_buffer_size)
		elif compression_type == COMPRESSED_TYPE_SYSTEM:
			dcmp_id, parameters = STRUCT_COMPRESSED_SYSTEM_HEADER.unpack(remainder)
			
			return CompressedSystemHeaderInfo(header_length, compression_type, decompressed_length, dcmp_id, parameters)
		else:
			raise DecompressError(f"Unsupported compression type: 0x{compression_type:>04x}")
	
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


class CompressedApplicationHeaderInfo(CompressedHeaderInfo):
	working_buffer_fractional_size: int
	expansion_buffer_size: int
	
	def __init__(self, header_length: int, compression_type: int, decompressed_length: int, dcmp_id: int, working_buffer_fractional_size: int, expansion_buffer_size: int) -> None:
		super().__init__(header_length, compression_type, decompressed_length, dcmp_id)
		
		self.working_buffer_fractional_size = working_buffer_fractional_size
		self.expansion_buffer_size = expansion_buffer_size
	
	def __repr__(self) -> str:
		return f"{type(self).__qualname__}(header_length={self.header_length}, compression_type=0x{self.compression_type:>04x}, decompressed_length={self.decompressed_length}, dcmp_id={self.dcmp_id}, working_buffer_fractional_size={self.working_buffer_fractional_size}, expansion_buffer_size={self.expansion_buffer_size})"


class CompressedSystemHeaderInfo(CompressedHeaderInfo):
	parameters: bytes
	
	def __init__(self, header_length: int, compression_type: int, decompressed_length: int, dcmp_id: int, parameters: bytes) -> None:
		super().__init__(header_length, compression_type, decompressed_length, dcmp_id)
		
		self.parameters = parameters
	
	def __repr__(self) -> str:
		return f"{type(self).__qualname__}(header_length={self.header_length}, compression_type=0x{self.compression_type:>04x}, decompressed_length={self.decompressed_length}, dcmp_id={self.dcmp_id}, parameters={self.parameters!r})"


def _read_variable_length_integer(data: bytes, position: int) -> typing.Tuple[int, int]:
	"""Read a variable-length integer starting at the given position in the data, and return the integer as well as the number of bytes consumed.
	
	This variable-length integer format is used by the 0xfe codes in the compression formats used by 'dcmp' (0) and 'dcmp' (1).
	"""
	
	assert len(data) > position
	if data[position] == 0xff:
		assert len(data) > position + 4
		return int.from_bytes(data[position+1:position+5], "big", signed=True), 5
	elif data[position] >= 0x80:
		assert len(data) > position + 1
		data_modified = bytes([(data[position] - 0xc0) & 0xff, data[position+1]])
		return int.from_bytes(data_modified, "big", signed=True), 2
	else:
		return int.from_bytes(data[position:position+1], "big", signed=True), 1
