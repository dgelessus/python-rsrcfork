import io
import typing

from . import dcmp0
from . import dcmp1
from . import dcmp2

from .common import DecompressError, CompressedHeaderInfo, CompressedType8HeaderInfo, CompressedType9HeaderInfo

__all__ = [
	"CompressedHeaderInfo",
	"CompressedType8HeaderInfo",
	"CompressedType9HeaderInfo",
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


def decompress_stream_parsed(header_info: CompressedHeaderInfo, stream: typing.BinaryIO, *, debug: bool = False) -> typing.Iterator[bytes]:
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


def decompress_parsed(header_info: CompressedHeaderInfo, data: bytes, *, debug: bool = False) -> bytes:
	"""Decompress the given compressed resource data, whose header has already been removed and parsed into a CompressedHeaderInfo object."""
	
	return b"".join(decompress_stream_parsed(header_info, io.BytesIO(data), debug=debug))


def decompress_stream(stream: typing.BinaryIO, *, debug: bool = False) -> typing.Iterator[bytes]:
	"""Decompress compressed resource data from a stream."""
	
	header_info = CompressedHeaderInfo.parse_stream(stream)
	
	if debug:
		print(f"Compressed resource data header: {header_info}")
	
	yield from decompress_stream_parsed(header_info, stream, debug=debug)


def decompress(data: bytes, *, debug: bool = False) -> bytes:
	"""Decompress the given compressed resource data."""
	
	return b"".join(decompress_stream(io.BytesIO(data), debug=debug))


class DecompressingStream(io.BufferedIOBase, typing.BinaryIO):
	_compressed_stream: typing.BinaryIO
	_close_stream: bool
	_header_info: CompressedHeaderInfo
	_decompress_iter: typing.Iterator[bytes]
	_decompressed_stream: typing.BinaryIO
	_seek_position: int
	
	def __init__(self, compressed_stream: typing.BinaryIO, header_info: typing.Optional[CompressedHeaderInfo], *, close_stream: bool = False) -> None:
		super().__init__()
		
		self._compressed_stream = compressed_stream
		self._close_stream = close_stream
		
		if header_info is not None:
			self._header_info = header_info
		else:
			self._header_info = CompressedHeaderInfo.parse_stream(self._compressed_stream)
		
		self._decompress_iter = decompress_stream_parsed(self._header_info, self._compressed_stream)
		self._decompressed_stream = io.BytesIO()
		self._seek_position = 0
	
	# This override does nothing,
	# but is needed to make mypy happy,
	# otherwise it complains (apparently incorrectly) about the __enter__ definitions from IOBase and BinaryIO being incompatible with each other.
	def __enter__(self: "DecompressingStream") -> "DecompressingStream":
		return super().__enter__()
	
	def close(self) -> None:
		super().close()
		if self._close_stream:
			self._compressed_stream.close()
		del self._decompress_iter
		self._decompressed_stream.close()
	
	def seekable(self) -> bool:
		return True
	
	def tell(self) -> int:
		return self._seek_position
	
	def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
		if whence == io.SEEK_SET:
			if offset < 0:
				raise ValueError(f"Negative seek offset not allowed with SEEK_SET: {offset}")
			
			self._seek_position = offset
		elif whence == io.SEEK_CUR:
			self._seek_position += offset
		elif whence == io.SEEK_END:
			self._seek_position = self._header_info.decompressed_length - offset
		else:
			raise ValueError(f"Invalid whence value: {whence}")
		
		self._seek_position = max(0, min(self._header_info.decompressed_length, self._seek_position))
		
		return self._seek_position
	
	def readable(self) -> bool:
		return True
	
	def read(self, size: typing.Optional[int] = -1) -> bytes:
		if size is None:
			size = -1
		
		self._decompressed_stream.seek(0, io.SEEK_END)
		
		if size < 0:
			for chunk in self._decompress_iter:
				self._decompressed_stream.write(chunk)
		else:
			if self._decompressed_stream.tell() - self._seek_position < size:
				for chunk in self._decompress_iter:
					self._decompressed_stream.write(chunk)
					
					if self._decompressed_stream.tell() - self._seek_position >= size:
						break
		
		self._decompressed_stream.seek(self._seek_position)
		ret = self._decompressed_stream.read(size)
		self._seek_position += len(ret)
		return ret
