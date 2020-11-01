"""A collection of utility functions and classes related to IO streams. For internal use only."""

import io
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


if typing.TYPE_CHECKING:
	class PeekableIO(typing.Protocol):
		"""Minimal protocol for binary IO streams that support the peek method.
		
		The peek method is supported by various standard Python binary IO streams, such as io.BufferedReader. If a stream does not natively support the peek method, it may be wrapped using the custom helper function make_peekable.
		"""
		
		def readable(self) -> bool:
			...
		
		def read(self, size: typing.Optional[int] = ...) -> bytes:
			...
		
		def peek(self, size: int = ...) -> bytes:
			...


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
	elif not typing.TYPE_CHECKING and isinstance(stream, io.RawIOBase):
		# This branch is skipped when type checking - mypy incorrectly warns about this code being unreachable, because it thinks that a typing.BinaryIO cannot be an instance of io.RawIOBase.
		# Raw IO streams can be wrapped efficiently using BufferedReader.
		return io.BufferedReader(stream)
	else:
		# Other streams need to be wrapped using our custom wrapper class.
		return _PeekableIOWrapper(stream)
