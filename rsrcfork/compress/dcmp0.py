from . import common

# Lookup table for codes in range(0x4b, 0xfe).
# This table was obtained by decompressing a manually created compressed resource with the following contents:
# b'\xa8\x9fer\x00\x12\x08\x01\x00\x00\x01f\x80\x03\x00\x00\x00\x00' + bytes(range(0x4b, 0xfe)) + b'\xff'
TABLE_DATA = (
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
TABLE = [TABLE_DATA[i:i + 2] for i in range(0, len(TABLE_DATA), 2)]
assert len(TABLE) == len(range(0x4b, 0xfe))


def decompress(data: bytes, decompressed_length: int, *, debug: bool=False) -> bytes:
	"""Decompress compressed data in the format used by 'dcmp' (0)."""
	
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
			# All compressed resources use the same table.
			table_index = byte - 0x4b
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
			
			if kind == 0x00:
				# Compact representation of (part of) a segment loader jump table, as used in 'CODE' (0) resources.
				
				if debug:
					print(f"Segment loader jump table entries")
				
				# All generated jump table entries have the same segment number.
				segment_number_int, length = common._read_variable_length_integer(data, i)
				i += length
				if debug:
					print(f"\t-> segment number: {segment_number_int:#x}")
				
				# The tail part of all jump table entries (i. e. everything except for the address).
				entry_tail = b"?<" + segment_number_int.to_bytes(2, "big", signed=True) + b"\xa9\xf0"
				if debug:
					print(f"\t-> tail of first entry: {entry_tail}")
				# The tail is output once *without* an address in front, i. e. the first entry's address must be generated manually by a previous code.
				decompressed += entry_tail
				
				count, length = common._read_variable_length_integer(data, i)
				i += length
				if count <= 0:
					raise common.DecompressError(f"Jump table entry count must be greater than 0, not {count}")
				
				# The second entry's address is stored explicitly.
				current_int, length = common._read_variable_length_integer(data, i)
				i += length
				if debug:
					print(f"-> address of second entry: {current_int:#x}")
				entry = current_int.to_bytes(2, "big", signed=False) + entry_tail
				if debug:
					print(f"-> second entry: {entry}")
				decompressed += entry
				
				for _ in range(1, count):
					# All further entries' addresses are stored as differences relative to the previous entry's address.
					diff, length = common._read_variable_length_integer(data, i)
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
			elif kind == 0x04:
				# A sequence of 16-bit signed integers, with each integer encoded as a difference relative to the previous integer. The first integer is stored explicitly.
				
				if debug:
					print(f"Difference-encoded 16-bit integers")
				
				# The first integer is stored explicitly, as a signed value.
				initial_int, length = common._read_variable_length_integer(data, i)
				i += length
				try:
					initial = initial_int.to_bytes(2, "big", signed=True)
				except OverflowError:
					raise common.DecompressError(f"Initial value out of range for 16-bit integer difference encoding: {initial_int:#x}")
				if debug:
					print(f"\t-> initial: {initial}")
				decompressed += initial
				
				count, length = common._read_variable_length_integer(data, i)
				i += length
				if count < 0:
					raise common.DecompressError(f"Count cannot be negative: {count}")
				
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
				initial_int, length = common._read_variable_length_integer(data, i)
				i += length
				try:
					initial = initial_int.to_bytes(4, "big", signed=True)
				except OverflowError:
					raise common.DecompressError(f"Initial value out of range for 32-bit integer difference encoding: {initial_int:#x}")
				if debug:
					print(f"\t-> initial: {initial}")
				decompressed += initial
				
				count, length = common._read_variable_length_integer(data, i)
				i += length
				assert count >= 0
				
				# To make the following calculations simpler, the signed initial_int value is converted to unsigned.
				current_int = initial_int & 0xffffffff
				for _ in range(count):
					# The difference to the previous integer is stored as a variable-length integer, whose value may be negative.
					diff, length = common._read_variable_length_integer(data, i)
					i += length
					
					# Simulate 32-bit integer wraparound.
					current_int = (current_int + diff) & 0xffffffff
					current = current_int.to_bytes(4, "big", signed=False)
					if debug:
						print(f"\t-> difference {diff:#x}: {current}")
					decompressed += current
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
	
	if decompressed_length % 2 != 0 and len(decompressed) == decompressed_length + 1:
		# Special case: if the decompressed data length stored in the header is odd and one less than the length of the actual decompressed data, drop the last byte.
		# This is necessary because nearly all codes generate data in groups of 2 or 4 bytes, so it is basically impossible to represent data with an odd length using this compression format.
		decompressed = decompressed[:-1]
	
	return decompressed
