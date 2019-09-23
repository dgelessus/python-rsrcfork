from . import dcmp0
from . import dcmp1
from . import dcmp2

from .common import DecompressError, CompressedApplicationHeaderInfo, CompressedHeaderInfo, CompressedSystemHeaderInfo

__all__ = [
	"DecompressError",
	"decompress",
]


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
