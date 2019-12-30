import argparse
import collections
import enum
import itertools
import pathlib
import sys
import textwrap
import typing

from . import __version__, api, compress

# The encoding to use when rendering bytes as text (in four-char codes, strings, hex dumps, etc.) or reading a quoted byte string (from the command line).
_TEXT_ENCODING = "MacRoman"

# Translation table to replace ASCII non-printable characters with periods.
_TRANSLATE_NONPRINTABLES = {k: "." for k in [*range(0x20), 0x7f]}

_REZ_ATTR_NAMES = {
	api.ResourceAttrs.resSysRef: None, # "Illegal or reserved attribute"
	api.ResourceAttrs.resSysHeap: "sysheap",
	api.ResourceAttrs.resPurgeable: "purgeable",
	api.ResourceAttrs.resLocked: "locked",
	api.ResourceAttrs.resProtected: "protected",
	api.ResourceAttrs.resPreload: "preload",
	api.ResourceAttrs.resChanged: None, # "Illegal or reserved attribute"
	api.ResourceAttrs.resCompressed: None, # "Extended Header resource attribute"
}

F = typing.TypeVar("F", bound=enum.Flag)
def decompose_flags(value: F) -> typing.Sequence[F]:
	"""Decompose an enum.Flags instance into separate enum constants."""
	
	return [bit for bit in type(value) if bit in value]

def is_printable(char: str) -> bool:
	"""Determine whether a character is printable for our purposes.
	
	We mainly use Python's definition of printable (i. e. everything that Unicode does not consider a separator or "other" character). However, we also treat U+F8FF as printable, which is the private use codepoint used for the Apple logo character.
	"""
	
	return char.isprintable() or char == "\uf8ff"

def bytes_unescape(string: str) -> bytes:
	"""Convert a string containing text (in _TEXT_ENCODING) and hex escapes to a bytestring.
	
	(We implement our own unescaping mechanism here to not depend on any of Python's string/bytes escape syntax.)
	"""
	
	out: typing.List[int] = []
	it = iter(string)
	for char in it:
		if char == "\\":
			try:
				esc = next(it)
				if esc in "\\\'\"":
					out.extend(esc.encode(_TEXT_ENCODING))
				elif esc == "x":
					x1, x2 = next(it), next(it)
					out.append(int(x1+x2, 16))
				else:
					raise ValueError(f"Unknown escape character: {esc}")
			except StopIteration:
				raise ValueError("End of string in escape sequence")
		else:
			out.extend(char.encode(_TEXT_ENCODING))
	
	return bytes(out)

def bytes_escape(bs: bytes, *, quote: typing.Optional[str]=None) -> str:
	"""Convert a bytestring to a string (using _TEXT_ENCODING), with non-printable characters hex-escaped.
	
	(We implement our own escaping mechanism here to not depend on Python's str or bytes repr.)
	"""
	
	out = []
	for byte, char in zip(bs, bs.decode(_TEXT_ENCODING)):
		if char in {quote, "\\"}:
			out.append(f"\\{char}")
		elif is_printable(char):
			out.append(char)
		else:
			out.append(f"\\x{byte:02x}")
	
	return "".join(out)

MIN_RESOURCE_ID = -0x8000
MAX_RESOURCE_ID = 0x7fff

class ResourceFilter(object):
	type: bytes
	min_id: int
	max_id: int
	name: typing.Optional[bytes]
	
	@classmethod
	def from_string(cls, filter: str) -> "ResourceFilter":
		if len(filter) == 4:
			restype = filter.encode("ascii")
			return cls(restype, MIN_RESOURCE_ID, MAX_RESOURCE_ID, None)
		elif filter[0] == filter[-1] == "'":
			restype = bytes_unescape(filter[1:-1])
			return cls(restype, MIN_RESOURCE_ID, MAX_RESOURCE_ID, None)
		else:
			pos = filter.find("'", 1)
			if pos == -1:
				raise ValueError(f"Invalid filter {filter!r}: Resource type must be single-quoted")
			elif filter[pos + 1] != " ":
				raise ValueError(f"Invalid filter {filter!r}: Resource type and ID must be separated by a space")
			
			restype_str, resid_str = filter[:pos + 1], filter[pos + 2:]
			
			if not restype_str[0] == restype_str[-1] == "'":
				raise ValueError(
					f"Invalid filter {filter!r}: Resource type is not a single-quoted type identifier: {restype_str!r}")
			restype = bytes_unescape(restype_str[1:-1])
			
			if resid_str[0] != "(" or resid_str[-1] != ")":
				raise ValueError(f"Invalid filter {filter!r}: Resource ID must be parenthesized")
			resid_str = resid_str[1:-1]
			
			if resid_str[0] == resid_str[-1] == '"':
				name = bytes_unescape(resid_str[1:-1])
				return cls(restype, MIN_RESOURCE_ID, MAX_RESOURCE_ID, name)
			elif ":" in resid_str:
				if resid_str.count(":") > 1:
					raise ValueError(f"Invalid filter {filter!r}: Too many colons in ID range expression: {resid_str!r}")
				start_str, end_str = resid_str.split(":")
				start, end = int(start_str), int(end_str)
				return cls(restype, start, end, None)
			else:
				resid = int(resid_str)
				return cls(restype, resid, resid, None)
	
	def __init__(self, restype: bytes, min_id: int, max_id: int, name: typing.Optional[bytes]) -> None:
		super().__init__()
		
		if len(restype) != 4:
			raise ValueError(f"Invalid filter: Type code must be exactly 4 bytes long, not {len(restype)} bytes: {restype!r}")
		elif min_id < MIN_RESOURCE_ID:
			raise ValueError(f"Invalid filter: Resource ID lower bound ({min_id}) cannot be lower than {MIN_RESOURCE_ID}")
		elif max_id > MAX_RESOURCE_ID:
			raise ValueError(f"Invalid filter: Resource ID upper bound ({max_id}) cannot be greater than {MAX_RESOURCE_ID}")
		elif min_id > max_id:
			raise ValueError(f"Invalid filter: Resource ID lower bound ({min_id}) cannot be greater than upper bound ({max_id})")
		
		self.type = restype
		self.min_id = min_id
		self.max_id = max_id
		self.name = name
	
	def __repr__(self) -> str:
		return f"{type(self).__name__}({self.type!r}, {self.min_id!r}, {self.max_id!r}, {self.name!r})"
	
	def matches(self, res: api.Resource) -> bool:
		return res.type == self.type and self.min_id <= res.id <= self.max_id and (self.name is None or res.name == self.name)

def filter_resources(rf: api.ResourceFile, filters: typing.Sequence[str]) -> typing.Iterable[api.Resource]:
	if not filters:
		# Special case: an empty list of filters matches all resources rather than none
		for reses in rf.values():
			yield from reses.values()
	else:
		filter_objs = [ResourceFilter.from_string(filter) for filter in filters]
		
		for reses in rf.values():
			for res in reses.values():
				if any(filter_obj.matches(res) for filter_obj in filter_objs):
					yield res

def hexdump(data: bytes) -> None:
	last_line = None
	asterisk_shown = False
	for i in range(0, len(data), 16):
		line = data[i:i + 16]
		# If the same 16-byte lines appear multiple times, print only the first one, and replace all further lines with a single line with an asterisk.
		# This is unambiguous - to find out how many lines were collapsed this way, the user can compare the addresses of the lines before and after the asterisk.
		if line == last_line:
			if not asterisk_shown:
				print("*")
				asterisk_shown = True
		else:
			line_hex_left = " ".join(f"{byte:02x}" for byte in line[:8])
			line_hex_right = " ".join(f"{byte:02x}" for byte in line[8:])
			line_char = line.decode(_TEXT_ENCODING).translate(_TRANSLATE_NONPRINTABLES)
			print(f"{i:08x}  {line_hex_left:<{8*2+7}}  {line_hex_right:<{8*2+7}}  |{line_char}|")
			asterisk_shown = False
		last_line = line
	
	if data:
		print(f"{len(data):08x}")

def raw_hexdump(data: bytes) -> None:
	for i in range(0, len(data), 16):
		print(" ".join(f"{byte:02x}" for byte in data[i:i + 16]))

def translate_text(data: bytes) -> str:
	return data.decode(_TEXT_ENCODING).replace("\r", "\n")

def describe_resource(res: api.Resource, *, include_type: bool, decompress: bool) -> str:
	id_desc_parts = [f"{res.id}"]
	
	if res.name is not None:
		name = bytes_escape(res.name, quote='"')
		id_desc_parts.append(f'"{name}"')
	
	id_desc = ", ".join(id_desc_parts)
	
	content_desc_parts = []
	
	if decompress and api.ResourceAttrs.resCompressed in res.attributes:
		try:
			res.compressed_info
		except compress.DecompressError:
			length_desc = f"unparseable compressed data header ({res.length_raw} bytes compressed)"
		else:
			assert res.compressed_info is not None
			length_desc = f"{res.length} bytes ({res.length_raw} bytes compressed)"
	else:
		length_desc = f"{res.length_raw} bytes"
	content_desc_parts.append(length_desc)
	
	attrs = decompose_flags(res.attributes)
	if attrs:
		content_desc_parts.append(" | ".join(attr.name for attr in attrs))
	
	content_desc = ", ".join(content_desc_parts)
	
	desc = f"({id_desc}): {content_desc}"
	if include_type:
		restype = bytes_escape(res.type, quote="'")
		desc = f"'{restype}' {desc}"
	return desc

def show_filtered_resources(resources: typing.Sequence[api.Resource], format: str, decompress: bool) -> None:
	if not resources:
		if format in ("dump", "dump-text"):
			print("No resources matched the filter")
		elif format in ("hex", "raw"):
			print("No resources matched the filter", file=sys.stderr)
			sys.exit(1)
		elif format == "derez":
			print("/* No resources matched the filter */")
		else:
			raise AssertionError(f"Unhandled output format: {format}")
	elif format in ("hex", "raw") and len(resources) != 1:
		print(f"Format {format} can only output a single resource, but the filter matched {len(resources)} resources", file=sys.stderr)
		sys.exit(1)
	
	for res in resources:
		if decompress:
			data = res.data
		else:
			data = res.data_raw
		
		if format in ("dump", "dump-text"):
			# Human-readable info and hex or text dump
			desc = describe_resource(res, include_type=True, decompress=decompress)
			print(f"Resource {desc}:")
			if format == "dump":
				hexdump(data)
			elif format == "dump-text":
				print(translate_text(data))
			else:
				raise AssertionError(f"Unhandled format: {format!r}")
			print()
		elif format == "hex":
			# Data only as hex
			
			raw_hexdump(data)
		elif format == "raw":
			# Data only as raw bytes
			
			sys.stdout.buffer.write(data)
		elif format == "derez":
			# Like DeRez with no resource definitions
			
			attrs = list(decompose_flags(res.attributes))
			
			if decompress and api.ResourceAttrs.resCompressed in attrs:
				attrs.remove(api.ResourceAttrs.resCompressed)
				attrs_comment = " /* was compressed */"
			else:
				attrs_comment = ""
			
			attr_descs_with_none = [_REZ_ATTR_NAMES[attr] for attr in attrs]
			if None in attr_descs_with_none:
				attr_descs = [f"${res.attributes.value:02X}"]
			else:
				attr_descs = typing.cast(typing.List[str], attr_descs_with_none)
			
			parts = [str(res.id)]
			
			if res.name is not None:
				name = bytes_escape(res.name, quote='"')
				parts.append(f'"{name}"')
			
			parts += attr_descs
			
			restype = bytes_escape(res.type, quote="'")
			print(f"data '{restype}' ({', '.join(parts)}{attrs_comment}) {{")
			
			for i in range(0, len(data), 16):
				# Two-byte grouping is really annoying to implement.
				groups = []
				for j in range(0, 16, 2):
					if i+j >= len(data):
						break
					elif i+j+1 >= len(data):
						groups.append(f"{data[i+j]:02X}")
					else:
						groups.append(f"{data[i+j]:02X}{data[i+j+1]:02X}")
				
				s = f'$"{" ".join(groups)}"'
				comment = "/* " + data[i:i + 16].decode(_TEXT_ENCODING).translate(_TRANSLATE_NONPRINTABLES) + " */"
				print(f"\t{s:<54s}{comment}")
			
			print("};")
			print()
		else:
			raise ValueError(f"Unhandled output format: {format}")

def list_resources(resources: typing.List[api.Resource], *, sort: bool, group: str, decompress: bool) -> None:
	if len(resources) == 0:
		print("No resources matched the filter")
		return
	
	if group == "none":
		if sort:
			resources.sort(key=lambda res: (res.type, res.id))
		print(f"{len(resources)} resources:")
		for res in resources:
			print(describe_resource(res, include_type=True, decompress=decompress))
	elif group == "type":
		if sort:
			resources.sort(key=lambda res: res.type)
		resources_by_type = {restype: list(reses) for restype, reses in itertools.groupby(resources, key=lambda res: res.type)}
		print(f"{len(resources_by_type)} resource types:")
		for restype, restype_resources in resources_by_type.items():
			escaped_restype = bytes_escape(restype, quote="'")
			print(f"'{escaped_restype}': {len(restype_resources)} resources:")
			if sort:
				restype_resources.sort(key=lambda res: res.id)
			for res in restype_resources:
				print(describe_resource(res, include_type=False, decompress=decompress))
			print()
	elif group == "id":
		resources.sort(key=lambda res: res.id)
		resources_by_id = {resid: list(reses) for resid, reses in itertools.groupby(resources, key=lambda res: res.id)}
		print(f"{len(resources_by_id)} resource IDs:")
		for resid, resid_resources in resources_by_id.items():
			print(f"({resid}): {len(resid_resources)} resources:")
			if sort:
				resid_resources.sort(key=lambda res: res.type)
			for res in resid_resources:
				print(describe_resource(res, include_type=True, decompress=decompress))
			print()
	else:
		raise AssertionError(f"Unhandled group mode: {group!r}")

def format_compressed_header_info(header_info: compress.CompressedHeaderInfo) -> typing.Iterable[str]:
	yield f"Header length: {header_info.header_length} bytes"
	yield f"Compression type: 0x{header_info.compression_type:>04x}"
	yield f"Decompressed data length: {header_info.decompressed_length} bytes"
	yield f"'dcmp' resource ID: {header_info.dcmp_id}"
	
	if isinstance(header_info, compress.CompressedType8HeaderInfo):
		yield f"Working buffer fractional size: {header_info.working_buffer_fractional_size} 256ths of compressed data length"
		yield f"Expansion buffer size: {header_info.expansion_buffer_size} bytes"
	elif isinstance(header_info, compress.CompressedType9HeaderInfo):
		yield f"Decompressor-specific parameters: {header_info.parameters}"
	else:
		raise AssertionError(f"Unhandled compressed header info type: {type(header_info)}")


def make_argument_parser(*, description: str, **kwargs: typing.Any) -> argparse.ArgumentParser:
	"""Create an argparse.ArgumentParser with some slightly modified defaults.
	
	This function is used to ensure that all subcommands use the same base configuration for their ArgumentParser.
	"""
	
	ap = argparse.ArgumentParser(
		formatter_class=argparse.RawDescriptionHelpFormatter,
		description=description,
		allow_abbrev=False,
		add_help=False,
		**kwargs,
	)
	
	ap.add_argument("--help", action="help", help="Display this help message and exit")
	
	return ap

def add_resource_file_args(ap: argparse.ArgumentParser) -> None:
	"""Define common options/arguments for specifying an input resource file.
	
	This includes a positional argument for the resource file's path, and the ``--fork`` option to select which fork of the file to use.
	"""
	
	ap.add_argument("--fork", choices=["auto", "data", "rsrc"], default="auto", help="The fork from which to read the resource file data, or auto to guess. Default: %(default)s")
	ap.add_argument("file", help="The file from which to read resources, or - for stdin.")

RESOURCE_FILTER_HELP = """
The resource filters use syntax similar to Rez (resource definition) files.
Each filter can have one of the following forms:

An unquoted type name (without escapes): TYPE
A quoted type name: 'TYPE'
A quoted type name and an ID: 'TYPE' (42)
A quoted type name and an ID range: 'TYPE' (24:42)
A quoted type name and a resource name: 'TYPE' ("foobar")

Note that the resource filter syntax uses quotes, parentheses and spaces,
which have special meanings in most shells. It is recommended to quote each
resource filter (using double quotes) to ensure that it is not interpreted
or rewritten by the shell.
"""

def add_resource_filter_args(ap: argparse.ArgumentParser) -> None:
	"""Define common options/arguments for specifying resource filters."""
	
	ap.add_argument("filter", nargs="*", help="One or more filters to select resources. If no filters are specified, all resources are selected.")

def open_resource_file(file: str, *, fork: str) -> api.ResourceFile:
	"""Open a resource file at the given path, using the specified fork."""
	
	if file == "-":
		if fork != "auto":
			print("Cannot specify an explicit fork when reading from stdin", file=sys.stderr)
			sys.exit(1)
		
		return api.ResourceFile(sys.stdin.buffer)
	else:
		return api.ResourceFile.open(file, fork=fork)


def do_read_header(prog: str, args: typing.List[str]) -> typing.NoReturn:
	"""Read the header data from a resource file."""
	
	ap = make_argument_parser(
		prog=prog,
		description="""
Read and output a resource file's header data.

The header data consists of two parts:

The system-reserved data is 112 bytes long and used by the Classic Mac OS
Finder as temporary storage space. It usually contains parts of the
file metadata (name, type/creator code, etc.).

The application-specific data is 128 bytes long and is available for use by
applications. In practice it usually contains junk data that happened to be in
memory when the resource file was written.

Mac OS X does not use the header data fields anymore. Resource files written
on Mac OS X normally have both parts of the header data set to all zero bytes.
""",
	)
	
	ap.add_argument("--format", choices=["dump", "dump-text", "hex", "raw"], default="dump", help="How to output the header data: human-readable info with hex dump (dump) (default), human-readable info with newline-translated data (dump-text), data only as hex (hex), or data only as raw bytes (raw). Default: %(default)s")
	ap.add_argument("--part", choices=["system", "application", "all"], default="all", help="Which part of the header to read. Default: %(default)s")
	add_resource_file_args(ap)
	
	ns = ap.parse_args(args)
	
	with open_resource_file(ns.file, fork=ns.fork) as rf:
		if ns.format in {"dump", "dump-text"}:
			if ns.format == "dump":
				dump_func = hexdump
			elif ns.format == "dump-text":
				def dump_func(data: bytes) -> None:
					print(translate_text(data))
			else:
				raise AssertionError(f"Unhandled --format: {ns.format!r}")
			
			if ns.part in {"system", "all"}:
				print("System-reserved header data:")
				dump_func(rf.header_system_data)
			
			if ns.part in {"application", "all"}:
				print("Application-specific header data:")
				dump_func(rf.header_application_data)
		elif ns.format in {"hex", "raw"}:
			if ns.part == "system":
				data = rf.header_system_data
			elif ns.part == "application":
				data = rf.header_application_data
			elif ns.part == "all":
				data = rf.header_system_data + rf.header_application_data
			else:
				raise AssertionError(f"Unhandled --part: {ns.part!r}")
			
			if ns.format == "hex":
				raw_hexdump(data)
			elif ns.format == "raw":
				sys.stdout.buffer.write(data)
			else:
				raise AssertionError(f"Unhandled --format: {ns.format!r}")
		else:
			raise AssertionError(f"Unhandled --format: {ns.format!r}")
	
	sys.exit(0)

def do_info(prog: str, args: typing.List[str]) -> typing.NoReturn:
	"""Display technical information about the resource file."""
	
	ap = make_argument_parser(
		prog=prog,
		description="""
Display technical information and stats about the resource file.
""",
	)
	add_resource_file_args(ap)
	
	ns = ap.parse_args(args)
	
	with open_resource_file(ns.file, fork=ns.fork) as rf:
		print("System-reserved header data:")
		hexdump(rf.header_system_data)
		print()
		print("Application-specific header data:")
		hexdump(rf.header_application_data)
		print()
		
		print(f"Resource data starts at {rf.data_offset:#x} and is {rf.data_length:#x} bytes long")
		print(f"Resource map starts at {rf.map_offset:#x} and is {rf.map_length:#x} bytes long")
		attrs = decompose_flags(rf.file_attributes)
		if attrs:
			attrs_desc = " | ".join(attr.name for attr in attrs)
		else:
			attrs_desc = "(none)"
		print(f"Resource map attributes: {attrs_desc}")
		print(f"Resource map type list starts at {rf.map_type_list_offset:#x} (relative to map start) and contains {len(rf)} types")
		print(f"Resource map name list starts at {rf.map_name_list_offset:#x} (relative to map start)")
	
	sys.exit(0)

def do_list(prog: str, args: typing.List[str]) -> typing.NoReturn:
	"""List the resources in a file."""
	
	ap = make_argument_parser(
		prog=prog,
		description=f"""
List the resources stored in a resource file.

Each resource's type, ID, name (if any), attributes (if any), and data length
are displayed. For compressed resources, the compressed and decompressed data
length are displayed, as well as the ID of the 'dcmp' resource used to
decompress the resource data.

{RESOURCE_FILTER_HELP}
""",
	)
	
	ap.add_argument("--no-decompress", action="store_false", dest="decompress", help="Do not parse the data header of compressed resources and only output their compressed length.")
	ap.add_argument("--group", action="store", choices=["none", "type", "id"], default="type", help="Group resources by type or ID, or disable grouping. Default: %(default)s")
	ap.add_argument("--no-sort", action="store_false", dest="sort", help="Output resources in the order in which they are stored in the file, instead of sorting them by type and ID.")
	add_resource_file_args(ap)
	add_resource_filter_args(ap)
	
	ns = ap.parse_args(args)
	
	with open_resource_file(ns.file, fork=ns.fork) as rf:
		if not rf:
			print("No resources (empty resource file)")
		else:
			resources = list(filter_resources(rf, ns.filter))
			list_resources(resources, sort=ns.sort, group=ns.group, decompress=ns.decompress)
	
	sys.exit(0)

def do_resource_info(prog: str, args: typing.List[str]) -> typing.NoReturn:
	"""Display technical information about resources."""
	
	ap = make_argument_parser(
		prog=prog,
		description=f"""
Display technical information about one or more resources.

{RESOURCE_FILTER_HELP}
""",
	)
	
	ap.add_argument("--no-decompress", action="store_false", dest="decompress", help="Do not parse the contents of compressed resources, only output regular resource information.")
	ap.add_argument("--no-sort", action="store_false", dest="sort", help="Output resources in the order in which they are stored in the file, instead of sorting them by type and ID.")
	add_resource_file_args(ap)
	add_resource_filter_args(ap)
	
	ns = ap.parse_args(args)
	
	with open_resource_file(ns.file, fork=ns.fork) as rf:
		resources = list(filter_resources(rf, ns.filter))
		
		if ns.sort:
			resources.sort(key=lambda res: (res.type, res.id))
		
		if not resources:
			print("No resources matched the filter")
			sys.exit(0)
		
		for res in resources:
			restype = bytes_escape(res.type, quote="'")
			print(f"Resource '{restype}' ({res.id}):")
			
			if res.name is None:
				print("\tName: none (unnamed)")
			else:
				assert res.name_offset is not None
				name = bytes_escape(res.name, quote='"')
				print(f'\tName: "{name}" (at offset {res.name_offset} in name list)')
			
			attrs = decompose_flags(res.attributes)
			if attrs:
				attrs_desc = " | ".join(attr.name for attr in attrs)
			else:
				attrs_desc = "(none)"
			print(f"\tAttributes: {attrs_desc}")
			
			print(f"\tData: {res.length_raw} bytes stored at offset {res.data_raw_offset} in resource file data")
			
			if api.ResourceAttrs.resCompressed in res.attributes and ns.decompress:
				print()
				print("\tCompressed resource header info:")
				try:
					res.compressed_info
				except compress.DecompressError:
					print("\t\t(failed to parse compressed resource header)")
				else:
					assert res.compressed_info is not None
					for line in format_compressed_header_info(res.compressed_info):
						print(f"\t\t{line}")
			
			print()
	
	sys.exit(0)

def do_read(prog: str, args: typing.List[str]) -> typing.NoReturn:
	"""Read data from resources."""
	
	ap = make_argument_parser(
		prog=prog,
		description=f"""
Read the data of one or more resources.

{RESOURCE_FILTER_HELP}
""",
	)
	
	ap.add_argument("--no-decompress", action="store_false", dest="decompress", help="Do not decompress compressed resources, output the raw compressed resource data.")
	ap.add_argument("--format", choices=["dump", "dump-text", "hex", "raw", "derez"], default="dump", help="How to output the resources: human-readable info with hex dump (dump), human-readable info with newline-translated data (dump-text), data only as hex (hex), data only as raw bytes (raw), or like DeRez with no resource definitions (derez). Default: %(default)s")
	ap.add_argument("--no-sort", action="store_false", dest="sort", help="Output resources in the order in which they are stored in the file, instead of sorting them by type and ID.")
	add_resource_file_args(ap)
	add_resource_filter_args(ap)
	
	ns = ap.parse_args(args)
	
	with open_resource_file(ns.file, fork=ns.fork) as rf:
		resources = list(filter_resources(rf, ns.filter))
		
		if ns.sort:
			resources.sort(key=lambda res: (res.type, res.id))
		
		show_filtered_resources(resources, format=ns.format, decompress=ns.decompress)
	
	sys.exit(0)

def do_raw_compress_info(prog: str, args: typing.List[str]) -> typing.NoReturn:
	"""Display technical information about raw compressed resource data."""
	
	ap = make_argument_parser(
		prog=prog,
		description="""
Display technical information about raw compressed resource data that is stored
in a standalone file and not as a resource in a resource file.
""",
	)
	
	ap.add_argument("input_file", help="The file from which to read the compressed resource data, or - for stdin.")
	
	ns = ap.parse_args(args)
	
	if ns.input_file == "-":
		in_stream = sys.stdin.buffer
		close_in_stream = False
	else:
		in_stream = open(ns.input_file, "rb")
		close_in_stream = True
	
	try:
		for line in format_compressed_header_info(compress.CompressedHeaderInfo.parse_stream(in_stream)):
			print(line)
	finally:
		if close_in_stream:
			in_stream.close()
	
	sys.exit(0)

def do_raw_decompress(prog: str, args: typing.List[str]) -> typing.NoReturn:
	"""Decompress raw compressed resource data."""
	
	ap = make_argument_parser(
		prog=prog,
		description="""
Decompress raw compressed resource data that is stored in a standalone file
and not as a resource in a resource file.

This subcommand can be used in a shell pipeline by passing - as the input and
output file name, i. e. "%(prog)s - -".

Note: All other rsrcfork subcommands natively support compressed resources and
will automatically decompress them as needed. This subcommand is only needed
to decompress resource data that has been read from a resource file in
compressed form (e. g. using --no-decompress or another tool that does not
handle resource compression).
""",
	)
	
	ap.add_argument("--debug", action="store_true", help="Display debugging output from the decompressor on stdout. Cannot be used if the output file is - (stdout).")
	
	ap.add_argument("input_file", help="The file from which to read the compressed resource data, or - for stdin.")
	ap.add_argument("output_file", help="The file to which to write the decompressed resource data, or - for stdout.")
	
	ns = ap.parse_args(args)
	
	if ns.input_file == "-":
		in_stream = sys.stdin.buffer
		close_in_stream = False
	else:
		in_stream = open(ns.input_file, "rb")
		close_in_stream = True
	
	try:
		header_info = compress.CompressedHeaderInfo.parse_stream(in_stream)
		
		# Open the output file only after parsing the header, so that the file is only created (or its existing contents deleted) if the input file is valid.
		if ns.output_file == "-":
			if ns.debug:
				print("Cannot use --debug if the decompression output file is - (stdout).", file=sys.stderr)
				print("The debug output goes to stdout and would conflict with the decompressed data.", file=sys.stderr)
				sys.exit(2)
			
			out_stream = sys.stdout.buffer
			close_out_stream = False
		else:
			out_stream = open(ns.output_file, "wb")
			close_out_stream = True
		
		try:
			for chunk in compress.decompress_stream_parsed(header_info, in_stream, debug=ns.debug):
				out_stream.write(chunk)
		finally:
			if close_out_stream:
				out_stream.close()
	finally:
		if close_in_stream:
			in_stream.close()
	
	sys.exit(0)


SUBCOMMANDS = {
	"read-header": do_read_header,
	"info": do_info,
	"list": do_list,
	"resource-info": do_resource_info,
	"read": do_read,
	"raw-compress-info": do_raw_compress_info,
	"raw-decompress": do_raw_decompress,
}


def format_subcommands_help() -> str:
	"""Return a formatted help text describing the availble subcommands.
	
	Because we do not use argparse's native support for subcommands (see comments in main function), the main ArgumentParser's help does not include any information about the subcommands by default, so we have to format and add it ourselves.
	"""
	
	# The list of subcommands is formatted using a "fake" ArgumentParser, which is never actually used to parse any arguments.
	# The options are chosen so that the help text will only include the subcommands list and epilog, but no usage or any other arguments.
	fake_ap = argparse.ArgumentParser(
		usage=argparse.SUPPRESS,
		epilog=textwrap.dedent("""
		Most of the above subcommands take additional arguments. Run a subcommand with
		the option --help for help about the options understood by that subcommand.
		"""),
		add_help=False,
		formatter_class=argparse.RawDescriptionHelpFormatter,
	)
	
	# The subcommands are added as positional arguments to a custom group with the title "subcommands".
	# Semantically this makes no sense, but it looks right in the formatted help text:
	# the result is a section "subcommands" with an aligned list of command names and short descriptions.
	fake_group = fake_ap.add_argument_group(title="subcommands")
	
	for name, func in SUBCOMMANDS.items():
		# Each command's short description is taken from the implementation function's docstring.
		fake_group.add_argument(name, help=func.__doc__)
	
	return fake_ap.format_help()


def main() -> typing.NoReturn:
	"""Main function of the CLI.
	
	This function is a valid setuptools entry point. Arguments are passed in sys.argv, and every execution path ends with a sys.exit call. (setuptools entry points are also permitted to return an integer, which will be treated as an exit code. We do not use this feature and instead always call sys.exit ourselves.)
	"""
	
	prog = pathlib.PurePath(sys.argv[0]).name
	args = sys.argv[1:]
	
	# The rsrcfork CLI is structured into subcommands, each implemented in a separate function.
	# The main function parses the command-line arguments enough to determine which subcommand to call, but leaves parsing of the rest of the arguments to the subcommand itself.
	# This should eventually be migrated to a standard CLI parsing library such as click or argh.
	# (Previously this was not possible because of backwards compatibility with the old CLI syntax, but this has now been removed.)
	
	ap = make_argument_parser(
		prog=prog,
		# Custom usage string to make "subcommand ..." show up in the usage, but not as "positional arguments" in the main help text.
		usage=f"{prog} (--help | --version | subcommand ...)",
		description="""
%(prog)s is a tool for working with Classic Mac OS resource files.
Currently this tool can only read resource files; modifying/writing resource
files is not supported yet.

Note: This tool is intended for human users. The output format is not
machine-readable and may change at any time. The command-line syntax usually
does not change much across versions, but this should not be relied on.
Automated scripts and programs should use the Python API provided by the
rsrcfork library, which this tool is a part of.
""",
		# The list of subcommands is shown in the epilog so that it appears under the list of optional arguments.
		epilog=format_subcommands_help(),
	)
	
	ap.add_argument("--version", action="version", version=__version__, help="Display version information and exit.")
	
	# The help of these arguments is set to argparse.SUPPRESS so that they do not cause a mostly useless "positional arguments" list to appear.
	ap.add_argument("subcommand", help=argparse.SUPPRESS)
	ap.add_argument("args", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)
	
	if not args:
		print(f"{prog}: Missing subcommand.", file=sys.stderr)
		ap.print_help()
		sys.exit(2)
	
	ns = ap.parse_args(args)
	
	try:
		# Check if the subcommand is valid.
		subcommand_func = SUBCOMMANDS[ns.subcommand]
	except KeyError:
		# Subcommand is invalid, display an error.
		print(f"{prog}: Unknown subcommand: {ns.subcommand}", file=sys.stderr)
		print(f"Run {prog} --help for a list of available subcommands.", file=sys.stderr)
		sys.exit(2)
	else:
		# Subcommand is valid, call the looked up subcommand and pass on further arguments.
		subcommand_func(f"{prog} {ns.subcommand}", ns.args)

if __name__ == "__main__":
	sys.exit(main())
