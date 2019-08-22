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
STRUCT_COMPRESSED_HEADER = struct.Struct(">4sHHI")

# Header continuation part for an "application" compressed resource.
# 1 byte: "Working buffer fractional size" - the ratio of the compressed data size to the uncompressed data size, times 256.
# 1 byte: "Expansion buffer size" - the maximum number of bytes that the data might grow during decompression.
# 2 bytes: The ID of the 'dcmp' resource that can decompress this resource. Currently only ID 0 is supported.
# 2 bytes: Reserved (always zero).
STRUCT_COMPRESSED_APPLICATION_HEADER = struct.Struct(">BBhH")

# Header continuation part for a "system" compressed resource.
# 2 bytes: The ID of the 'dcmp' resource that can decompress this resource. Currently only ID 2 is supported.
# 4 bytes: Decompressor-specific parameters.
STRUCT_COMPRESSED_SYSTEM_HEADER = struct.Struct(">h4s")


def _decompress_application(data: bytes, decompressed_length: int, *, debug: bool=False) -> bytes:
	working_buffer_fractional_size, expansion_buffer_size, dcmp_id, reserved = STRUCT_COMPRESSED_APPLICATION_HEADER.unpack_from(data)
	
	if debug:
		print(f"Working buffer fractional size: {working_buffer_fractional_size} (=> {len(data) * 256 / working_buffer_fractional_size})")
		print(f"Expansion buffer size: {expansion_buffer_size}")
	
	if dcmp_id == 0:
		decompress_func = dcmp0.decompress
	elif dcmp_id == 1:
		decompress_func = dcmp1.decompress
	else:
		raise DecompressError(f"Unsupported 'dcmp' ID: {dcmp_id}, expected 0 or 1")
	
	if reserved != 0:
		raise DecompressError(f"Reserved field should be 0, not 0x{reserved:>04x}")
	
	return decompress_func(data[STRUCT_COMPRESSED_APPLICATION_HEADER.size:], decompressed_length, debug=debug)


def _decompress_system(data: bytes, decompressed_length: int, *, debug: bool=False) -> bytes:
	dcmp_id, params = STRUCT_COMPRESSED_SYSTEM_HEADER.unpack_from(data)
	
	if dcmp_id == 2:
		decompress_func = dcmp2.decompress
	else:
		raise DecompressError(f"Unsupported 'dcmp' ID: {dcmp_id}, expected 2")
	
	return decompress_func(data[STRUCT_COMPRESSED_SYSTEM_HEADER.size:], decompressed_length, params, debug=debug)


def decompress(data: bytes, *, debug: bool=False) -> bytes:
	"""Decompress the given compressed resource data."""
	
	try:
		signature, header_length, compression_type, decompressed_length = STRUCT_COMPRESSED_HEADER.unpack_from(data)
	except struct.error:
		raise DecompressError(f"Invalid header")
	if signature != COMPRESSED_SIGNATURE:
		raise DecompressError(f"Invalid signature: {signature!r}, expected {COMPRESSED_SIGNATURE}")
	if header_length != 0x12:
		raise DecompressError(f"Unsupported header length: 0x{header_length:>04x}, expected 0x12")
	
	if compression_type == COMPRESSED_TYPE_APPLICATION:
		decompress_func = _decompress_application
	elif compression_type == COMPRESSED_TYPE_SYSTEM:
		decompress_func = _decompress_system
	else:
		raise DecompressError(f"Unsupported compression type: 0x{compression_type:>04x}")
	
	if debug:
		print(f"Decompressed length: {decompressed_length}")
	
	decompressed = decompress_func(data[STRUCT_COMPRESSED_HEADER.size:], decompressed_length, debug=debug)
	if len(decompressed) != decompressed_length:
		raise DecompressError(f"Actual length of decompressed data ({len(decompressed)}) does not match length stored in resource ({decompressed_length})")
	return decompressed
