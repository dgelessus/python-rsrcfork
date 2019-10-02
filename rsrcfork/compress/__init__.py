import io
import typing

from . import dcmp0
from . import dcmp1
from . import dcmp2

from .common import DecompressError, CompressedHeaderInfo

__all__ = [
	"CompressedHeaderInfo",
	"DecompressError",
	"decompress",
	"decompress_parsed",
	"decompress_stream",
	"decompress_stream_parsed",
]


# Maps 'dcmp' IDs to their corresponding Python implementations.
# Each decompressor has the signature (header_info: CompressedHeaderInfo, stream: typing.BinaryIO, *, debug: bool=False) -> typing.Iterator[bytes].
DECOMPRESSORS = {
	0: dcmp0.decompress_stream,
	1: dcmp1.decompress_stream,
	2: dcmp2.decompress_stream,
}


def decompress_stream_parsed(header_info: CompressedHeaderInfo, stream: typing.BinaryIO, *, debug: bool=False) -> typing.Iterator[bytes]:
	"""Decompress compressed resource data from a stream, whose header has already been read and parsed into a CompressedHeaderInfo object."""
	
	try:
		decompress_func = DECOMPRESSORS[header_info.dcmp_id]
	except KeyError:
		raise DecompressError(f"Unsupported 'dcmp' ID: {header_info.dcmp_id}")
	
	decompressed_length = 0
	for chunk in decompress_func(header_info, stream, debug=debug):
		decompressed_length += len(chunk)
		yield chunk
	
	if decompressed_length != header_info.decompressed_length:
		raise DecompressError(f"Actual length of decompressed data ({decompressed_length}) does not match length stored in resource ({header_info.decompressed_length})")

def decompress_parsed(header_info: CompressedHeaderInfo, data: bytes, *, debug: bool=False) -> bytes:
	"""Decompress the given compressed resource data, whose header has already been removed and parsed into a CompressedHeaderInfo object."""
	
	return b"".join(decompress_stream_parsed(header_info, io.BytesIO(data), debug=debug))

def decompress_stream(stream: typing.BinaryIO, *, debug: bool=False) -> typing.Iterator[bytes]:
	"""Decompress compressed resource data from a stream."""
	
	header_info = CompressedHeaderInfo.parse_stream(stream)
	
	if debug:
		print(f"Compressed resource data header: {header_info}")
	
	yield from decompress_stream_parsed(header_info, stream, debug=debug)

def decompress(data: bytes, *, debug: bool=False) -> bytes:
	"""Decompress the given compressed resource data."""
	
	return b"".join(decompress_stream(io.BytesIO(data), debug=debug))
