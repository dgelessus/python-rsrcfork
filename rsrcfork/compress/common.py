import typing


class DecompressError(Exception):
	"""Raised when resource data decompression fails, because the data is invalid or the compression type is not supported."""


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
