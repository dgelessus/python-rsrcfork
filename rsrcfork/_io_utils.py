"""A collection of utility functions and classes related to IO streams. For internal use only."""

import typing


def read_exact(stream: typing.BinaryIO, byte_count: int) -> bytes:
	"""Read byte_count bytes from the stream and raise an exception if too few bytes are read (i. e. if EOF was hit prematurely).
	
	:param stream: The stream to read from.
	:param byte_count: The number of bytes to read.
	:return: The read data, which is exactly ``byte_count`` bytes long.
	:raise EOFError: If not enough data could be read from the stream.
	"""
	
	data = stream.read(byte_count)
	if len(data) != byte_count:
		raise EOFError(f"Attempted to read {byte_count} bytes of data, but only got {len(data)} bytes")
	return data
