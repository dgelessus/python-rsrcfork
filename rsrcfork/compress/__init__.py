from . import dcmp0
from . import dcmp1
from . import dcmp2

from .common import DecompressError, CompressedApplicationHeaderInfo, CompressedHeaderInfo, CompressedSystemHeaderInfo

__all__ = [
	"DecompressError",
	"decompress",
]


# Maps 'dcmp' IDs to their corresponding Python implementations.
# Each decompressor has the signature (header_info: CompressedHeaderInfo, data: bytes, *, debug: bool=False) -> bytes.
DECOMPRESSORS = {
	0: dcmp0.decompress,
	1: dcmp1.decompress,
	2: dcmp2.decompress,
}


def decompress_parsed(header_info: CompressedHeaderInfo, data: bytes, *, debug: bool=False) -> bytes:
	"""Decompress the given compressed resource data, whose header has already been removed and parsed into a CompressedHeaderInfo object."""
	
	try:
		decompress_func = DECOMPRESSORS[header_info.dcmp_id]
	except KeyError:
		raise DecompressError(f"Unsupported 'dcmp' ID: {header_info.dcmp_id}")
	
	decompressed = decompress_func(header_info, data, debug=debug)
	if len(decompressed) != header_info.decompressed_length:
		raise DecompressError(f"Actual length of decompressed data ({len(decompressed)}) does not match length stored in resource ({header_info.decompressed_length})")
	return decompressed


def decompress(data: bytes, *, debug: bool=False) -> bytes:
	"""Decompress the given compressed resource data."""
	
	header_info = CompressedHeaderInfo.parse(data)
	
	if debug:
		print(f"Compressed resource data header: {header_info}")
	
	return decompress_parsed(header_info, data[header_info.header_length:], debug=debug)
