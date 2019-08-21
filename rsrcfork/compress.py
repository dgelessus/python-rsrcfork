import enum
import struct
import typing

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

# Lookup table for codes in range(0x4b, 0xfe) in "application" compressed resources.
# This table was obtained by decompressing a manually created compressed resource that refers to every possible table entry. Detailed steps:
# 1. Create a file with a resource fork
# 2. Add a resource with the following contents: b'\xa8\x9fer\x00\x12\x08\x01\x00\x00\x01f\x80\x03\x00\x00\x00\x00' + bytes(range(0x4b, 0xfe)) + b'\xff'
# 3. Set the "compressed" flag (0x01) on the resource
# 4. Open the file in ResEdit
# 5. Duplicate the resource - this will decompress the original resource and write its contents uncompressed into the duplicate
# 6. Read the data from the duplicated resource
COMPRESSED_APPLICATION_TABLE_DATA = (
	# First line corresponds to codes in range(0x4b, 0x50).
	b"\x00\x00N\xba\x00\x08Nu\x00\x0c"
	# All following lines correspond to 8 codes each.
	b"N\xad S/\x0ba\x00\x00\x10p\x00/\x00Hn"
	b" P n/.\xff\xfcH\xe7?<\x00\x04\xff\xf8"
	b"/\x0c \x06N\xedNV hN^\x00\x01X\x8f"
	b"O\xef\x00\x02\x00\x18`\x00\xff\xffP\x8fN\x90\x00\x06"
	b"&n\x00\x14\xff\xf4L\xee\x00\n\x00\x0eA\xeeL\xdf"
	b"H\xc0\xff\xf0-@\x00\x120.p\x01/( T"
	b"g\x00\x00 \x00\x1c _\x18\x00&oHx\x00\x16"
	b"A\xfa0<(@r\x00(n \x0cf\x00 k"
	b"/\x07U\x8f\x00(\xff\xfe\xff\xec\"\xd8 \x0b\x00\x0f"
	b"Y\x8f/<\xff\x00\x01\x18\x81\xe1J\x00N\xb0\xff\xe8"
	b"H\xc7\x00\x03\x00\"\x00\x07\x00\x1ag\x06g\x08N\xf9"
	b"\x00$ x\x08\x00f\x04\x00*N\xd00(&_"
	b"g\x04\x000C\xee?\x00 \x1f\x00\x1e\xff\xf6 ."
	b"B\xa7 \x07\xff\xfa`\x02=@\x0c@f\x06\x00&"
	b"-H/\x01p\xff`\x04\x18\x80J@\x00@\x00,"
	b"/\x08\x00\x11\xff\xe4!@&@\xff\xf2BnN\xb9"
	b"=|\x008\x00\r`\x06B. <g\x0c-h"
	b"f\x08J.J\xae\x00.H@\"_\"\x00g\n"
	b"0\x07Bg\x002 (\x00\tHz\x02\x00/+"
	b"\x00\x05\"nf\x02\xe5\x80g\x0ef\n\x00P>\x00"
	b"f\x0c.\x00\xff\xee m @\xff\xe0S@`\x08"
	# Last line corresponds to codes in range(0xf8, 0xfe).
	b"\x04\x80\x00h\x0b|D\x00A\xe8HA"
)
# Note: index 0 in this table corresponds to code 0x4b, index 1 to 0x4c, etc.
COMPRESSED_APPLICATION_TABLE = [COMPRESSED_APPLICATION_TABLE_DATA[i:i + 2] for i in range(0, len(COMPRESSED_APPLICATION_TABLE_DATA), 2)]
assert len(COMPRESSED_APPLICATION_TABLE) == len(range(0x4b, 0xfe))

# Header continuation part for a "system" compressed resource.
# 2 bytes: The ID of the 'dcmp' resource that can decompress this resource. Currently only ID 2 is supported.
# 2 bytes: Unknown meaning, doesn't appear to have any effect on the decompression algorithm. Usually zero, sometimes set to a small integer (< 10). On 'lpch' resources, the value is always nonzero, and sometimes larger than usual.
# 1 byte: Number of entries in the custom lookup table minus one. Set to zero if the default lookup table is used.
# 1 byte: Flags. See the CompressedSystemFlags enum below for details.
STRUCT_COMPRESSED_SYSTEM_HEADER = struct.Struct(">hHBB")

# Default lookup table for "system" compressed resources.
# If the custom table flag is set, a custom table (usually with fewer than 256 entries) is used instead of this one.
# This table was obtained by decompressing a manually created compressed resource that refers to every possible table entry. Detailed steps:
# 1. Create a file with a resource fork
# 2. Add a resource with the following contents: b'\xa8\x9fer\x00\x12\t\x01\x00\x00\x02\x00\x00\x02\x00\x00\x00\x00' + bytes(range(256))
# 3. Set the "compressed" flag (0x01) on the resource
# 4. Open the file in ResEdit
# 5. Duplicate the resource - this will decompress the original resource and write its contents uncompressed into the duplicate
# 6. Read the data from the duplicated resource
COMPRESSED_DEFAULT_TABLE_DATA = (
	b"\x00\x00\x00\x08N\xba nNu\x00\x0c\x00\x04p\x00"
	b"\x00\x10\x00\x02Hn\xff\xfc`\x00\x00\x01H\xe7/."
	b"NV\x00\x06N^/\x00a\x00\xff\xf8/\x0b\xff\xff"
	b"\x00\x14\x00\n\x00\x18 _\x00\x0e P?<\xff\xf4"
	b"L\xee0.g\x00L\xdf&n\x00\x12\x00\x1cBg"
	b"\xff\xf00</\x0c\x00\x03N\xd0\x00 p\x01\x00\x16"
	b"-@H\xc0 xr\x00X\x8ff\x00O\xefB\xa7"
	b"g\x06\xff\xfaU\x8f(n?\x00\xff\xfe/<g\x04"
	b"Y\x8f k\x00$ \x1fA\xfa\x81\xe1f\x04g\x08"
	b"\x00\x1aN\xb9P\x8f .\x00\x07N\xb0\xff\xf2=@"
	b"\x00\x1e hf\x06\xff\xf6N\xf9\x08\x00\x0c@=|"
	b"\xff\xec\x00\x05 <\xff\xe8\xde\xfcJ.\x000\x00("
	b"/\x08 \x0b`\x02Bn-H S @\x18\x00"
	b"`\x04A\xee/(/\x01g\nH@ \x07f\x08"
	b"\x01\x18/\x070(?.0+\"n/+\x00,"
	b"g\x0c\"_`\x06\x00\xff0\x07\xff\xeeS@\x00@"
	b"\xff\xe4J@f\n\x00\x0fN\xadp\xff\"\xd8Hk"
	b"\x00\" Kg\x0eJ\xaeN\x90\xff\xe0\xff\xc0\x00*"
	b"'@g\x02Q\xc8\x02\xb6Hz\"x\xb0n\xff\xe6"
	b"\x00\t2.>\x00HA\xff\xeaC\xeeNqt\x00"
	b"/, l\x00<\x00&\x00P\x18\x800\x1f\"\x00"
	b"f\x0c\xff\xda\x008f\x020, \x0c-nB@"
	b"\xff\xe2\xa9\xf0\xff\x007|\xe5\x80\xff\xdcHhYO"
	b"\x004>\x1f`\x08/\x06\xff\xde`\np\x02\x002"
	b"\xff\xcc\x00\x80\"Q\x10\x1f1|\xa0)\xff\xd8R@"
	b"\x01\x00g\x10\xa0#\xff\xce\xff\xd4 \x06Hx\x00."
	b"POC\xfag\x12v\x00A\xe8Jn \xd9\x00Z"
	b"\x7f\xffQ\xca\x00\\.\x00\x02@H\xc7g\x14\x0c\x80"
	b".\x9f\xff\xd6\x80\x00\x10\x00HBJk\xff\xd2\x00H"
	b"JGN\xd1 o\x00A`\x0c*xB.2\x00"
	b"etg\x16\x00DHm \x08Hl\x0b|&@"
	b"\x04\x00\x00h m\x00\r*@\x00\x0b\x00>\x02 "
)
COMPRESSED_DEFAULT_TABLE = [COMPRESSED_DEFAULT_TABLE_DATA[i:i + 2] for i in range(0, len(COMPRESSED_DEFAULT_TABLE_DATA), 2)]


class CompressedSystemFlags(enum.Flag):
	TAGGED = 1 << 1 # The compressed data is tagged, meaning that it consists of "blocks" of a tag byte followed by 8 table references and/or literals. See comments in the decompress function for details.
	CUSTOM_TABLE = 1 << 0 # A custom lookup table is included before the compressed data, which is used instead of the default table.


class DecompressError(Exception):
	"""Raised when resource data decompression fails, because the data is invalid or the compression type is not supported."""


def _split_bits(i: int) -> typing.Tuple[bool, bool, bool, bool, bool, bool, bool, bool]:
	"""Split a byte (an int) into its 8 bits (a tuple of 8 bools)."""
	
	assert i in range(256)
	return (
		bool(i & (1 << 7)),
		bool(i & (1 << 6)),
		bool(i & (1 << 5)),
		bool(i & (1 << 4)),
		bool(i & (1 << 3)),
		bool(i & (1 << 2)),
		bool(i & (1 << 1)),
		bool(i & (1 << 0)),
	)

def _read_variable_length_integer(data: bytes, position: int) -> typing.Tuple[int, int]:
	"""Read a variable-length integer starting at the given position in the data, and return the integer as well as the number of bytes consumed.
	
	This variable-length integer format is used by the 0xfe codes in "application" compressed resources.
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


def _decompress_application_0(data: bytes, decompressed_length: int, *, debug: bool=False) -> bytes:
	prev_literals = []
	decompressed = b""
	
	i = 0
	
	while i < len(data):
		byte = data[i]
		if debug:
			print(f"Tag byte 0x{byte:>02x}, at 0x{i:x}, decompressing to 0x{len(decompressed):x}")
		
		if byte in range(0x00, 0x20):
			# Literal byte sequence.
			if byte in (0x00, 0x10):
				# The length of the literal data is stored in the next byte.
				count_div2 = data[i+1]
				begin = i + 2
			else:
				# The length of the literal data is stored in the low nibble of the tag byte.
				count_div2 = byte >> 0 & 0xf
				begin = i + 1
			end = begin + 2*count_div2
			# Controls whether or not the literal is stored so that it can be referenced again later.
			do_store = byte >= 0x10
			literal = data[begin:end]
			if debug:
				print(f"Literal (storing: {do_store})")
				print(f"\t-> {literal}")
			decompressed += literal
			if do_store:
				if debug:
					print(f"\t-> stored as literal number 0x{len(prev_literals):x}")
				prev_literals.append(literal)
			i = end
		elif byte in (0x20, 0x21):
			# Backreference to a previous literal, 2-byte form.
			# This can reference literals with index in range(0x28, 0x228).
			table_index = 0x28 + ((byte - 0x20) << 8 | data[i+1])
			i += 2
			if debug:
				print(f"Backreference (2-byte form) to 0x{table_index:>02x}")
			literal = prev_literals[table_index]
			if debug:
				print(f"\t-> {literal}")
			decompressed += literal
		elif byte == 0x22:
			# Backreference to a previous literal, 3-byte form.
			# This can reference any literal with index 0x28 and higher, but is only necessary for literals with index 0x228 and higher.
			table_index = 0x28 + int.from_bytes(data[i+1:i+3], "big", signed=False)
			i += 3
			if debug:
				print(f"Backreference (3-byte form) to 0x{table_index:>02x}")
			literal = prev_literals[table_index]
			if debug:
				print(f"\t-> {literal}")
			decompressed += literal
		elif byte in range(0x23, 0x4b):
			# Backreference to a previous literal, 1-byte form.
			# This can reference literals with indices in range(0x28).
			table_index = byte - 0x23
			i += 1
			if debug:
				print(f"Backreference (1-byte form) to 0x{table_index:>02x}")
			literal = prev_literals[table_index]
			if debug:
				print(f"\t-> {literal}")
			decompressed += literal
		elif byte in range(0x4b, 0xfe):
			# Reference into a fixed table of two-byte literals.
			# All compressed resource use the same table.
			table_index = byte - 0x4b
			i += 1
			if debug:
				print(f"Fixed table reference to 0x{table_index:>02x}")
			entry = COMPRESSED_APPLICATION_TABLE[table_index]
			if debug:
				print(f"\t-> {entry}")
			decompressed += entry
		elif byte == 0xfe:
			# Extended code, whose meaning is controlled by the following byte.
			
			i += 1
			kind = data[i]
			if debug:
				print(f"Extended code: 0x{kind:>02x}")
			i += 1
			
			if kind == 0x00:
				# Compact representation of (part of) a segment loader jump table, as used in 'CODE' (0) resources.
				
				if debug:
					print(f"Segment loader jump table entries")
				
				# All generated jump table entries have the same segment number.
				segment_number_int, length = _read_variable_length_integer(data, i)
				i += length
				if debug:
					print(f"\t-> segment number: {segment_number_int:#x}")
				
				# The tail part of all jump table entries (i. e. everything except for the address).
				entry_tail = b"?<" + segment_number_int.to_bytes(2, "big", signed=True) + b"\xa9\xf0"
				if debug:
					print(f"\t-> tail of first entry: {entry_tail}")
				# The tail is output once *without* an address in front, i. e. the first entry's address must be generated manually by a previous code.
				decompressed += entry_tail
				
				count, length = _read_variable_length_integer(data, i)
				i += length
				if count <= 0:
					raise DecompressError(f"Jump table entry count must be greater than 0, not {count}")
				
				# The second entry's address is stored explicitly.
				current_int, length = _read_variable_length_integer(data, i)
				i += length
				if debug:
					print(f"-> address of second entry: {current_int:#x}")
				entry = current_int.to_bytes(2, "big", signed=False) + entry_tail
				if debug:
					print(f"-> second entry: {entry}")
				decompressed += entry
				
				for _ in range(1, count):
					# All further entries' addresses are stored as differences relative to the previous entry's address.
					diff, length = _read_variable_length_integer(data, i)
					i += length
					# For some reason, each difference is 6 higher than it should be.
					diff -= 6
					
					# Simulate 16-bit integer wraparound.
					current_int = (current_int + diff) & 0xffff
					if debug:
						print(f"\t-> difference {diff:#x}: {current_int:#x}")
					entry = current_int.to_bytes(2, "big", signed=False) + entry_tail
					if debug:
						print(f"\t-> {entry}")
					decompressed += entry
			elif kind in (0x02, 0x03):
				# Repeat 1 or 2 bytes a certain number of times.
				
				if kind == 0x02:
					byte_count = 1
				elif kind == 0x03:
					byte_count = 2
				else:
					raise AssertionError()
				
				if debug:
					print(f"Repeat {byte_count}-byte value")
				
				# The byte(s) to repeat, stored as a variable-length integer. The value is treated as unsigned, i. e. the integer is never negative.
				to_repeat_int, length = _read_variable_length_integer(data, i)
				i += length
				try:
					to_repeat = to_repeat_int.to_bytes(byte_count, "big", signed=False)
				except OverflowError:
					raise DecompressError(f"Value to repeat out of range for {byte_count}-byte repeat: {to_repeat_int:#x}")
				
				count_m1, length = _read_variable_length_integer(data, i)
				i += length
				count = count_m1 + 1
				if count <= 0:
					raise DecompressError(f"Repeat count must be positive: {count}")
				
				repeated = to_repeat * count
				if debug:
					print(f"\t-> {to_repeat} * {count}: {repeated}")
				decompressed += repeated
			elif kind == 0x04:
				# A sequence of 16-bit signed integers, with each integer encoded as a difference relative to the previous integer. The first integer is stored explicitly.
				
				if debug:
					print(f"Difference-encoded 16-bit integers")
				
				# The first integer is stored explicitly, as a signed value.
				initial_int, length = _read_variable_length_integer(data, i)
				i += length
				try:
					initial = initial_int.to_bytes(2, "big", signed=True)
				except OverflowError:
					raise DecompressError(f"Initial value out of range for 16-bit integer difference encoding: {initial_int:#x}")
				if debug:
					print(f"\t-> initial: {initial}")
				decompressed += initial
				
				count, length = _read_variable_length_integer(data, i)
				i += length
				if count < 0:
					raise DecompressError(f"Count cannot be negative: {count}")
				
				# To make the following calculations simpler, the signed initial_int value is converted to unsigned.
				current_int = initial_int & 0xffff
				for _ in range(count):
					# The difference to the previous integer is stored as an 8-bit signed integer.
					# The usual variable-length integer format is *not* used here.
					diff = int.from_bytes(data[i:i+1], "big", signed=True)
					i += 1
					
					# Simulate 16-bit integer wraparound.
					current_int = (current_int + diff) & 0xffff
					current = current_int.to_bytes(2, "big", signed=False)
					if debug:
						print(f"\t-> difference {diff:#x}: {current}")
					decompressed += current
			elif kind == 0x06:
				# A sequence of 32-bit signed integers, with each integer encoded as a difference relative to the previous integer. The first integer is stored explicitly.
				
				if debug:
					print(f"Difference-encoded 16-bit integers")
				
				# The first integer is stored explicitly, as a signed value.
				initial_int, length = _read_variable_length_integer(data, i)
				i += length
				try:
					initial = initial_int.to_bytes(4, "big", signed=True)
				except OverflowError:
					raise DecompressError(f"Initial value out of range for 32-bit integer difference encoding: {initial_int:#x}")
				if debug:
					print(f"\t-> initial: {initial}")
				decompressed += initial
				
				count, length = _read_variable_length_integer(data, i)
				i += length
				assert count >= 0
				
				# To make the following calculations simpler, the signed initial_int value is converted to unsigned.
				current_int = initial_int & 0xffffffff
				for _ in range(count):
					# The difference to the previous integer is stored as a variable-length integer, whose value may be negative.
					diff, length = _read_variable_length_integer(data, i)
					i += length
					
					# Simulate 32-bit integer wraparound.
					current_int = (current_int + diff) & 0xffffffff
					current = current_int.to_bytes(4, "big", signed=False)
					if debug:
						print(f"\t-> difference {diff:#x}: {current}")
					decompressed += current
			else:
				raise DecompressError(f"Unknown extended code: 0x{kind:>02x}")
		elif byte == 0xff:
			# End of data marker, always occurs exactly once as the last byte of the compressed data.
			if debug:
				print("End marker")
			if i != len(data) - 1:
				raise DecompressError(f"End marker reached at {i}, before the expected end of data at {len(data) - 1}")
			i += 1
		else:
			raise DecompressError(f"Unknown tag byte: 0x{data[i]:>02x}")
	
	if decompressed_length % 2 != 0 and len(decompressed) == decompressed_length + 1:
		# Special case: if the decompressed data length stored in the header is odd and one less than the length of the actual decompressed data, drop the last byte.
		# This is necessary because nearly all codes generate data in groups of 2 or 4 bytes, so it is basically impossible to represent data with an odd length using this compression format.
		decompressed = decompressed[:-1]
	
	return decompressed


def _decompress_application_1(data: bytes, decompressed_length: int, *, debug: bool=False) -> bytes:
	raise NotImplementedError("'dcmp' (1) decompression not supported yet")


def _decompress_application(data: bytes, decompressed_length: int, *, debug: bool=False) -> bytes:
	working_buffer_fractional_size, expansion_buffer_size, dcmp_id, reserved = STRUCT_COMPRESSED_APPLICATION_HEADER.unpack_from(data)
	
	if debug:
		print(f"Working buffer fractional size: {working_buffer_fractional_size} (=> {len(data) * 256 / working_buffer_fractional_size})")
		print(f"Expansion buffer size: {expansion_buffer_size}")
	
	if dcmp_id == 0:
		decompress_func = _decompress_application_0
	elif dcmp_id == 1:
		decompress_func = _decompress_application_1
	else:
		raise DecompressError(f"Unsupported 'dcmp' ID: {dcmp_id}, expected 0 or 1")
	
	if reserved != 0:
		raise DecompressError(f"Reserved field should be 0, not 0x{reserved:>04x}")
	
	return decompress_func(data[STRUCT_COMPRESSED_APPLICATION_HEADER.size:], decompressed_length, debug=debug)


def _decompress_system_untagged(data: bytes, decompressed_length: int, table: typing.Sequence[bytes], *, debug: bool=False) -> bytes:
	parts = []
	i = 0
	while i < len(data):
		if i == len(data) - 1 and decompressed_length % 2 != 0:
			# Special case: if we are at the last byte of the compressed data, and the decompressed data has an odd length, the last byte is a single literal byte, and not a table reference.
			if debug:
				print(f"Last byte: {data[-1:]}")
			parts.append(data[-1:])
			break
		
		# Compressed data is untagged, every byte is a table reference.
		if debug:
			print(f"Reference: {data[i]} -> {table[data[i]]}")
		parts.append(table[data[i]])
		i += 1
	
	return b"".join(parts)

def _decompress_system_tagged(data: bytes, decompressed_length: int, table: typing.Sequence[bytes], *, debug: bool=False) -> bytes:
	parts = []
	i = 0
	while i < len(data):
		if i == len(data) - 1 and decompressed_length % 2 != 0:
			# Special case: if we are at the last byte of the compressed data, and the decompressed data has an odd length, the last byte is a single literal byte, and not a tag or a table reference.
			if debug:
				print(f"Last byte: {data[-1:]}")
			parts.append(data[-1:])
			break
		
		# Compressed data is tagged, each tag byte is followed by 8 table references and/or literals.
		tag = data[i]
		if debug:
			print(f"Tag: 0b{tag:>08b}")
		i += 1
		for is_ref in _split_bits(tag):
			if is_ref:
				# This is a table reference (a single byte that is an index into the table).
				if debug:
					print(f"Reference: {data[i]} -> {table[data[i]]}")
				parts.append(table[data[i]])
				i += 1
			else:
				# This is a literal (two uncompressed bytes that are literally copied into the output).
				# Note: if i == len(data)-1, the literal is actually only a single byte long.
				# This case is handled automatically - the slice extends one byte past the end of the data, and only one byte is returned.
				if debug:
					print(f"Literal: {data[i:i+2]}")
				parts.append(data[i:i + 2])
				i += 2
			
			# If the end of the compressed data is reached in the middle of a chunk, all further tag bits are ignored (they should be zero) and decompression ends.
			if i >= len(data):
				break
	
	return b"".join(parts)

def _decompress_system(data: bytes, decompressed_length: int, *, debug: bool=False) -> bytes:
	dcmp_id, unknown, table_count_m1, flags_raw = STRUCT_COMPRESSED_SYSTEM_HEADER.unpack_from(data)
	if dcmp_id != 2:
		raise DecompressError(f"Unsupported 'dcmp' ID: {dcmp_id}, expected 2")
	if debug:
		print(f"Value of unknown field at bytes 0xc-0xe: 0x{unknown:>04x}")
	
	table_count = table_count_m1 + 1
	if debug:
		print(f"Table has {table_count} entries")
	
	try:
		flags = CompressedSystemFlags(flags_raw)
	except ValueError:
		raise DecompressError(f"Unsupported flags set: 0b{flags_raw:>08b}, currently only bits 0 and 1 are supported")
	
	if debug:
		print(f"Flags: {flags}")
	
	if CompressedSystemFlags.CUSTOM_TABLE in flags:
		table_start = STRUCT_COMPRESSED_SYSTEM_HEADER.size
		data_start = table_start + table_count * 2
		table = []
		for i in range(table_start, data_start, 2):
			table.append(data[i:i + 2])
		if debug:
			print(f"Using custom table: {table}")
	else:
		if table_count_m1 != 0:
			raise DecompressError(f"table_count_m1 field is {table_count_m1}, but must be zero when the default table is used")
		table = COMPRESSED_DEFAULT_TABLE
		data_start = STRUCT_COMPRESSED_SYSTEM_HEADER.size
		if debug:
			print("Using default table")
	
	if CompressedSystemFlags.TAGGED in flags:
		decompress_func = _decompress_system_tagged
	else:
		decompress_func = _decompress_system_untagged
	
	return decompress_func(data[data_start:], decompressed_length, table, debug=debug)


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
