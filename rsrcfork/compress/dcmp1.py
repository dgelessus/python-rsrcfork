from . import common

# Lookup table for codes in range(0xd5, 0xfe).
# This table was obtained by decompressing a manually created compressed resource with the following contents:
# b'\xa8\x9fer\x00\x12\x08\x01\x00\x00\x00R\x80\x03\x00\x01\x00\x00' + bytes(range(0xd5, 0xfe)) + b'\xff'
TABLE_DATA = (
	# First line corresponds to codes in range(0xd5, 0xd8).
	b"\x00\x00\x00\x01\x00\x02"
	# All following lines correspond to 8 codes each.
	b"\x00\x03.\x01>\x01\x01\x01\x1e\x01\xff\xff\x0e\x011\x00"
	b"\x11\x12\x01\x0732\x129\xed\x10\x01'#\"\x017"
	b"\x07\x06\x01\x17\x01#\x00\xff\x00/\x07\x0e\xfd<\x015"
	b"\x01\x15\x01\x02\x00\x07\x00>\x05\xd5\x02\x01\x06\x07\x07\x08"
	# Last line corresponds to codes in range(0xf8, 0xfe).
	b"0\x01\x013\x00\x10\x17\x167>67"
)
# Note: index 0 in this table corresponds to code 0xd5, index 1 to 0xd6, etc.
TABLE = [TABLE_DATA[i:i + 2] for i in range(0, len(TABLE_DATA), 2)]
assert len(TABLE) == len(range(0xd5, 0xfe))


def decompress(data: bytes, decompressed_length: int, *, debug: bool=False) -> bytes:
	"""Decompress compressed data in the format used by 'dcmp' (1)."""
	
	prev_literals = []
	decompressed = b""
	
	i = 0
	
	while i < len(data):
		byte = data[i]
		if debug:
			print(f"Tag byte 0x{byte:>02x}, at 0x{i:x}, decompressing to 0x{len(decompressed):x}")
		
		if byte in range(0x00, 0x20):
			# Literal byte sequence, 1-byte header.
			# The length of the literal data is stored in the low nibble of the tag byte.
			count = (byte >> 0 & 0xf) + 1
			begin = i + 1
			end = begin + count
			# Controls whether or not the literal is stored so that it can be referenced again later.
			do_store = byte >= 0x10
			literal = data[begin:end]
			if debug:
				print(f"Literal (1-byte header, storing: {do_store})")
				print(f"\t-> {literal}")
			decompressed += literal
			if do_store:
				if debug:
					print(f"\t-> stored as literal number 0x{len(prev_literals):x}")
				prev_literals.append(literal)
			i = end
		elif byte in range(0x20, 0xd0):
			# Backreference to a previous literal, 1-byte form.
			# This can reference literals with indices in range(0xb0).
			table_index = byte - 0x20
			i += 1
			if debug:
				print(f"Backreference (1-byte form) to 0x{table_index:>02x}")
			literal = prev_literals[table_index]
			if debug:
				print(f"\t-> {literal}")
			decompressed += literal
		elif byte in (0xd0, 0xd1):
			# Literal byte sequence, 2-byte header.
			# The length of the literal data is stored in the following byte.
			count = data[i+1]
			begin = i + 2
			end = begin + count
			# Controls whether or not the literal is stored so that it can be referenced again later.
			do_store = byte == 0xd1
			literal = data[begin:end]
			if debug:
				print(f"Literal (2-byte header, storing: {do_store})")
				print(f"\t-> {literal}")
			decompressed += literal
			if do_store:
				if debug:
					print(f"\t-> stored as literal number 0x{len(prev_literals):x}")
				prev_literals.append(literal)
			i = end
		elif byte == 0xd2:
			# Backreference to a previous literal, 2-byte form.
			# This can reference literals with indices in range(0xb0, 0x1b0).
			table_index = data[i+1] + 0xb0
			i += 2
			if debug:
				print(f"Backreference (2-byte form) to 0x{table_index:>02x}")
			literal = prev_literals[table_index]
			if debug:
				print(f"\t-> {literal}")
			decompressed += literal
		elif byte in range(0xd5, 0xfe):
			# Reference into a fixed table of two-byte literals.
			# All compressed resources use the same table.
			table_index = byte - 0xd5
			i += 1
			if debug:
				print(f"Fixed table reference to 0x{table_index:>02x}")
			entry = TABLE[table_index]
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
			
			if kind == 0x02:
				# Repeat 1 byte a certain number of times.
				
				byte_count = 1 # Unlike with 'dcmp' (0) compression, there doesn't appear to be a 2-byte repeat (or if there is, it's never used in practice).
				
				if debug:
					print(f"Repeat {byte_count}-byte value")
				
				# The byte(s) to repeat, stored as a variable-length integer. The value is treated as unsigned, i. e. the integer is never negative.
				to_repeat_int, length = common._read_variable_length_integer(data, i)
				i += length
				try:
					to_repeat = to_repeat_int.to_bytes(byte_count, "big", signed=False)
				except OverflowError:
					raise common.DecompressError(f"Value to repeat out of range for {byte_count}-byte repeat: {to_repeat_int:#x}")
				
				count_m1, length = common._read_variable_length_integer(data, i)
				i += length
				count = count_m1 + 1
				if count <= 0:
					raise common.DecompressError(f"Repeat count must be positive: {count}")
				
				repeated = to_repeat * count
				if debug:
					print(f"\t-> {to_repeat} * {count}: {repeated}")
				decompressed += repeated
			else:
				raise common.DecompressError(f"Unknown extended code: 0x{kind:>02x}")
		elif byte == 0xff:
			# End of data marker, always occurs exactly once as the last byte of the compressed data.
			if debug:
				print("End marker")
			if i != len(data) - 1:
				raise common.DecompressError(f"End marker reached at {i}, before the expected end of data at {len(data) - 1}")
			i += 1
		else:
			raise common.DecompressError(f"Unknown tag byte: 0x{data[i]:>02x}")
	
	return decompressed
