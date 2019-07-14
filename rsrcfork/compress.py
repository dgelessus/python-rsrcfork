import enum
import struct
import typing

__all__ = [
	"DecompressError",
	"decompress",
]

# The signature of all compressed resource data, 0xa89f6572 in hex, or "®üer" in MacRoman.
COMPRESSED_SIGNATURE = b"\xa8\x9fer"
# The compression type commonly used for System file resources.
COMPRESSED_TYPE_SYSTEM = 0x0901

# Header for a compressed resource.
# 4 bytes: Signature (see above).
# 2 bytes: Length of the header. (This meaning is just a guess - the field's value is always 0x0012, so there's no way to know for certain what it means.)
# 2 bytes: Compression type. Known so far: 0x0901 is used in the System file's resources. 0x0801 is used in other files' resources. Currently only the first type is supported.
# 4 bytes: Length of the data after decompression.
# 2 bytes: The ID of the 'dcmp' resource that can decompress this resource. Currently only ID 2 is supported.
# 2 bytes: Unknown meaning, doesn't appear to have any effect on the decompression algorithm. Usually zero, sometimes set to a small integer (< 10). On 'lpch' resources, the value is always nonzero, and sometimes larger than usual.
# 1 byte: Number of entries in the custom lookup table minus one. Set to zero if the default lookup table is used.
# 1 byte: Flags. See the CompressedFlags enum below for details.
STRUCT_COMPRESSED_HEADER = struct.Struct(">4sHHIhHBB")

# Default lookup table for compressed resources.
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


class CompressedFlags(enum.Flag):
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


def _decompress_untagged(data: bytes, decompressed_length: int, table: typing.Sequence[bytes], *, debug: bool=False) -> bytes:
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

def _decompress_tagged(data: bytes, decompressed_length: int, table: typing.Sequence[bytes], *, debug: bool=False) -> bytes:
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


def decompress(data: bytes, *, debug: bool=False) -> bytes:
	"""Decompress the given compressed resource data."""
	
	try:
		signature, header_length, compression_type, decompressed_length, dcmp_id, unknown, table_count_m1, flags_raw = STRUCT_COMPRESSED_HEADER.unpack_from(data, offset=0)
	except struct.error:
		raise DecompressError(f"Invalid header")
	if signature != COMPRESSED_SIGNATURE:
		raise DecompressError(f"Invalid signature: {signature!r}, expected {COMPRESSED_SIGNATURE}")
	if header_length != STRUCT_COMPRESSED_HEADER.size:
		raise DecompressError(f"Unsupported header length: 0x{header_length:>04x}, expected 0x{STRUCT_COMPRESSED_HEADER.size:>04x}")
	if compression_type != COMPRESSED_TYPE_SYSTEM:
		raise DecompressError(f"Unsupported compression type: 0x{compression_type:>04x}, expected 0x{COMPRESSED_TYPE_SYSTEM:>04x}")
	if dcmp_id != 2:
		raise DecompressError(f"Unsupported 'dcmp' ID: {dcmp_id}, expected 2")
	if debug:
		print(f"Value of unknown field at bytes 0xc-0xe: 0x{unknown:>04x}")
	
	table_count = table_count_m1 + 1
	if debug:
		print(f"Table has {table_count} entries")
	
	try:
		flags = CompressedFlags(flags_raw)
	except ValueError:
		raise DecompressError(f"Unsupported flags set: 0b{flags_raw:>08b}, currently only bits 0 and 1 are supported")
	
	if debug:
		print(f"Flags: {flags}")
	
	if CompressedFlags.CUSTOM_TABLE in flags:
		table_start = STRUCT_COMPRESSED_HEADER.size
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
		data_start = STRUCT_COMPRESSED_HEADER.size
		if debug:
			print("Using default table")
	
	if CompressedFlags.TAGGED in flags:
		decompress_func = _decompress_tagged
	else:
		decompress_func = _decompress_untagged
	
	decompressed = decompress_func(data[data_start:], decompressed_length, table, debug=debug)
	if len(decompressed) != decompressed_length:
		raise DecompressError(f"Actual length of decompressed data ({len(decompressed)}) does not match length stored in resource ({decompressed_length})")
	return decompressed
