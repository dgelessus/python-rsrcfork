import struct

from . import dcmp0
from . import dcmp1
from . import dcmp2

from .common import DecompressError

__all__ = [
	"DecompressError",
	"decompress",
]

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
	
	def __init__(self, header_length: int, compression_type: int, decompressed_length: int, dcmp_id: int) -> None:
		super().__init__()
		
		self.header_length: int = header_length
		self.compression_type: int = compression_type
		self.decompressed_length: int = decompressed_length
		self.dcmp_id: int = dcmp_id


class CompressedApplicationHeaderInfo(CompressedHeaderInfo):
	def __init__(self, header_length: int, compression_type: int, decompressed_length: int, dcmp_id: int, working_buffer_fractional_size: int, expansion_buffer_size: int) -> None:
		super().__init__(header_length, compression_type, decompressed_length, dcmp_id)
		
		self.working_buffer_fractional_size: int = working_buffer_fractional_size
		self.expansion_buffer_size: int = expansion_buffer_size
	
	def __repr__(self):
		return f"{type(self).__qualname__}(header_length={self.header_length}, compression_type={self.compression_type:>04x}, decompressed_length={self.decompressed_length}, dcmp_id={self.dcmp_id}, working_buffer_fractional_size={self.working_buffer_fractional_size}, expansion_buffer_size={self.expansion_buffer_size})"


class CompressedSystemHeaderInfo(CompressedHeaderInfo):
	def __init__(self, header_length: int, compression_type: int, decompressed_length: int, dcmp_id: int, parameters: bytes) -> None:
		super().__init__(header_length, compression_type, decompressed_length, dcmp_id)
		
		self.parameters: bytes = parameters
	
	def __repr__(self):
		return f"{type(self).__qualname__}(header_length={self.header_length}, compression_type={self.compression_type:>04x}, decompressed_length={self.decompressed_length}, dcmp_id={self.dcmp_id}, parameters={self.parameters!r})"


def _decompress_application(data: bytes, header_info: CompressedApplicationHeaderInfo, *, debug: bool=False) -> bytes:
	if header_info.dcmp_id == 0:
		decompress_func = dcmp0.decompress
	elif header_info.dcmp_id == 1:
		decompress_func = dcmp1.decompress
	else:
		raise DecompressError(f"Unsupported 'dcmp' ID: {header_info.dcmp_id}, expected 0 or 1")
	
	return decompress_func(data, header_info.decompressed_length, debug=debug)


def _decompress_system(data: bytes, header_info: CompressedSystemHeaderInfo, *, debug: bool=False) -> bytes:
	if header_info.dcmp_id == 2:
		decompress_func = dcmp2.decompress
	else:
		raise DecompressError(f"Unsupported 'dcmp' ID: {header_info.dcmp_id}, expected 2")
	
	return decompress_func(data, header_info.decompressed_length, header_info.parameters, debug=debug)


def decompress(data: bytes, *, debug: bool=False) -> bytes:
	"""Decompress the given compressed resource data."""
	
	header_info = CompressedHeaderInfo.parse(data)
	
	if debug:
		print(f"Compressed resource data header: {header_info}")
	
	if isinstance(header_info, CompressedApplicationHeaderInfo):
		decompress_func = _decompress_application
	elif isinstance(header_info, CompressedSystemHeaderInfo):
		decompress_func = _decompress_system
	else:
		raise DecompressError(f"Unsupported compression type: 0x{header_info.compression_type:>04x}")
	
	decompressed = decompress_func(data[header_info.header_length:], header_info, debug=debug)
	if len(decompressed) != header_info.decompressed_length:
		raise DecompressError(f"Actual length of decompressed data ({len(decompressed)}) does not match length stored in resource ({header_info.decompressed_length})")
	return decompressed
