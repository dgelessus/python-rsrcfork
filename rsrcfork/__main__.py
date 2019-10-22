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

def filter_resources(rf: api.ResourceFile, filters: typing.Sequence[str]) -> typing.List[api.Resource]:
	matching: typing.MutableMapping[typing.Tuple[bytes, int], api.Resource] = collections.OrderedDict()
	
	for filter in filters:
		if len(filter) == 4:
			try:
				resources = rf[filter.encode("ascii")]
			except KeyError:
				continue
			
			for res in resources.values():
				matching[res.type, res.id] = res
		elif filter[0] == filter[-1] == "'":
			try:
				resources = rf[bytes_unescape(filter[1:-1])]
			except KeyError:
				continue
			
			for res in resources.values():
				matching[res.type, res.id] = res
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
			
			if len(restype) != 4:
				raise ValueError(
					f"Invalid filter {filter!r}: Type identifier must be 4 bytes after replacing escapes, got {len(restype)} bytes: {restype!r}")
			
			if resid_str[0] != "(" or resid_str[-1] != ")":
				raise ValueError(f"Invalid filter {filter!r}: Resource ID must be parenthesized")
			resid_str = resid_str[1:-1]
			
			try:
				resources = rf[restype]
			except KeyError:
				continue
			
			if resid_str[0] == resid_str[-1] == '"':
				name = bytes_unescape(resid_str[1:-1])
				
				for res in resources.values():
					if res.name == name:
						matching[res.type, res.id] = res
						break
			elif ":" in resid_str:
				if resid_str.count(":") > 1:
					raise ValueError(f"Invalid filter {filter!r}: Too many colons in ID range expression: {resid_str!r}")
				start_str, end_str = resid_str.split(":")
				start, end = int(start_str), int(end_str)
				
				for res in resources.values():
					if start <= res.id <= end:
						matching[res.type, res.id] = res
			else:
				resid = int(resid_str)
				try:
					res = resources[resid]
				except KeyError:
					continue
				matching[res.type, res.id] = res
	
	return list(matching.values())

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
			length_desc = f"{res.length} bytes ({res.length_raw} bytes compressed, 'dcmp' ({res.compressed_info.dcmp_id}) format)"
	else:
		assert res.compressed_info is None
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

def parse_args_old(args: typing.List[str]) -> argparse.Namespace:
	ap = argparse.ArgumentParser(
		add_help=False,
		fromfile_prefix_chars="@",
		formatter_class=argparse.RawDescriptionHelpFormatter,
		description=textwrap.dedent("""
		Read and display resources from a file's resource or data fork.
		
		When specifying resource filters, each one may be of one of the
		following forms:
		
		An unquoted type name (without escapes): TYPE
		A quoted type name: 'TYPE'
		A quoted type name and an ID: 'TYPE' (42)
		A quoted type name and an ID range: 'TYPE' (24:42)
		A quoted type name and a resource name: 'TYPE' ("foobar")
		
		When multiple filters are specified, all resources matching any of them
		are displayed.
		"""),
	)
	
	ap.add_argument("--help", action="help", help="Display this help message and exit")
	ap.add_argument("--version", action="version", version=__version__, help="Display version information and exit")
	ap.add_argument("-a", "--all", action="store_true", help="When no filters are given, show all resources in full, instead of an overview")
	ap.add_argument("-f", "--fork", choices=["auto", "data", "rsrc"], default="auto", help="The fork from which to read the resource data, or auto to guess (default: %(default)s)")
	ap.add_argument("--no-decompress", action="store_false", dest="decompress", help="Do not decompress compressed resources, output compressed resource data as-is")
	ap.add_argument("--format", choices=["dump", "dump-text", "hex", "raw", "derez"], default="dump", help="How to output the resources - human-readable info with hex dump (dump) (default), human-readable info with newline-translated data (dump-text), data only as hex (hex), data only as raw bytes (raw), or like DeRez with no resource definitions (derez)")
	ap.add_argument("--group", action="store", choices=["none", "type", "id"], default="type", help="Group resources in list view by type or ID, or disable grouping (default: type)")
	ap.add_argument("--no-sort", action="store_false", dest="sort", help="Output resources in the order in which they are stored in the file, instead of sorting them by type and ID")
	ap.add_argument("--header-system", action="store_true", help="Output system-reserved header data and nothing else")
	ap.add_argument("--header-application", action="store_true", help="Output application-specific header data and nothing else")
	
	ap.add_argument("file", help="The file to read, or - for stdin")
	ap.add_argument("filter", nargs="*", help="One or more filters to select which resources to display, or omit to show an overview of all resources")
	
	ns = ap.parse_args(args)
	return ns

def show_header_data(data: bytes, *, format: str) -> None:
	if format == "dump":
		hexdump(data)
	elif format == "dump-text":
		print(translate_text(data))
	elif format == "hex":
		raw_hexdump(data)
	elif format == "raw":
		sys.stdout.buffer.write(data)
	elif format == "derez":
		print("Cannot output file header data in derez format", file=sys.stderr)
		sys.exit(1)
	else:
		raise ValueError(f"Unhandled output format: {format}")

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

def list_resource_file(rf: api.ResourceFile, *, sort: bool, group: str, decompress: bool) -> None:
	if len(rf) == 0:
		print("No resources (empty resource file)")
		return
	
	if group == "none":
		all_resources: typing.List[api.Resource] = []
		for reses in rf.values():
			all_resources.extend(reses.values())
		if sort:
			all_resources.sort(key=lambda res: (res.type, res.id))
		print(f"{len(all_resources)} resources:")
		for res in all_resources:
			print(describe_resource(res, include_type=True, decompress=decompress))
	elif group == "type":
		print(f"{len(rf)} resource types:")
		restype_items: typing.Collection[typing.Tuple[bytes, typing.Mapping[int, api.Resource]]] = rf.items()
		if sort:
			restype_items = sorted(restype_items, key=lambda item: item[0])
		for typecode, resources_map in restype_items:
			restype = bytes_escape(typecode, quote="'")
			print(f"'{restype}': {len(resources_map)} resources:")
			resources_items: typing.Collection[typing.Tuple[int, api.Resource]] = resources_map.items()
			if sort:
				resources_items = sorted(resources_items, key=lambda item: item[0])
			for resid, res in resources_items:
				print(describe_resource(res, include_type=False, decompress=decompress))
			print()
	elif group == "id":
		all_resources = []
		for reses in rf.values():
			all_resources.extend(reses.values())
		all_resources.sort(key=lambda res: res.id)
		resources_by_id = {resid: list(reses) for resid, reses in itertools.groupby(all_resources, key=lambda res: res.id)}
		print(f"{len(resources_by_id)} resource IDs:")
		for resid, resources in resources_by_id.items():
			print(f"({resid}): {len(resources)} resources:")
			if sort:
				resources.sort(key=lambda res: res.type)
			for res in resources:
				print(describe_resource(res, include_type=True, decompress=decompress))
			print()
	else:
		raise AssertionError(f"Unhandled group mode: {group!r}")

def main_old(args: typing.List[str]) -> typing.NoReturn:
	ns = parse_args_old(args)
	
	if ns.file == "-":
		if ns.fork != "auto":
			print("Cannot specify an explicit fork when reading from stdin", file=sys.stderr)
			sys.exit(1)
		
		rf = api.ResourceFile(sys.stdin.buffer)
	else:
		rf = api.ResourceFile.open(ns.file, fork=ns.fork)
	
	with rf:
		print("Warning: The syntax of the rsrcfork command has changed.", file=sys.stderr)
		
		if ns.header_system or ns.header_application:
			if ns.header_system:
				print('Please use "rsrcfork read-header --part=system <file>" instead of "rsrcfork --header-system <file>".', file=sys.stderr)
				print(file=sys.stderr)
				
				data = rf.header_system_data
			else:
				print('Please use "rsrcfork read-header --part=application <file>" instead of "rsrcfork --header-application <file>".', file=sys.stderr)
				print(file=sys.stderr)
				
				data = rf.header_application_data
			
			show_header_data(data, format=ns.format)
		elif ns.filter or ns.all:
			if ns.filter:
				print('Please use "rsrcfork read <file> <filters...>" instead of "rsrcfork <file> <filters...>".', file=sys.stderr)
				print(file=sys.stderr)
				
				resources = filter_resources(rf, ns.filter)
			else:
				print('Please use "rsrcfork read <file>" instead of "rsrcfork <file> --all".', file=sys.stderr)
				print(file=sys.stderr)
				
				resources = []
				for reses in rf.values():
					resources.extend(reses.values())
			
			if ns.sort:
				resources.sort(key=lambda res: (res.type, res.id))
			
			show_filtered_resources(resources, format=ns.format, decompress=ns.decompress)
		else:
			print('Please use "rsrcfork list <file>" instead of "rsrcfork <file>".', file=sys.stderr)
			print(file=sys.stderr)
			
			if rf.header_system_data != bytes(len(rf.header_system_data)):
				print("Header system data:")
				hexdump(rf.header_system_data)
			
			if rf.header_application_data != bytes(len(rf.header_application_data)):
				print("Header application data:")
				hexdump(rf.header_application_data)
			
			attrs = decompose_flags(rf.file_attributes)
			if attrs:
				print("File attributes: " + " | ".join(attr.name for attr in attrs))
			
			list_resource_file(rf, sort=ns.sort, group=ns.group, decompress=ns.decompress)
	
	sys.exit(0)


def make_argument_parser(*, description: str, **kwargs: typing.Any) -> argparse.ArgumentParser:
	"""Create an argparse.ArgumentParser with some slightly modified defaults.
	
	This function is used to ensure that all subcommands use the same base configuration for their ArgumentParser.
	"""
	
	ap = argparse.ArgumentParser(
		formatter_class=argparse.RawDescriptionHelpFormatter,
		description=textwrap.dedent(description),
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

def open_resource_file(file: str, *, fork: str = None) -> api.ResourceFile:
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
				def dump_func(d):
					print(translate_text(d))
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

def do_list(prog: str, args: typing.List[str]) -> typing.NoReturn:
	"""List the resources in a file."""
	
	ap = make_argument_parser(
		prog=prog,
		description="""
		List the resources stored in a resource file.
		
		Each resource's type, ID, name (if any), attributes (if any), and data length
		are displayed. For compressed resources, the compressed and decompressed data
		length are displayed, as well as the ID of the 'dcmp' resource used to
		decompress the resource data.
		
		If the resource file has any global (resource map) attributes or non-zero
		header data, they are displayed before the list of resources.
		""",
	)
	
	ap.add_argument("--no-decompress", action="store_false", dest="decompress", help="Do not parse the data header of compressed resources and only output their compressed length.")
	ap.add_argument("--group", action="store", choices=["none", "type", "id"], default="type", help="Group resources by type or ID, or disable grouping. Default: %(default)s")
	ap.add_argument("--no-sort", action="store_false", dest="sort", help="Output resources in the order in which they are stored in the file, instead of sorting them by type and ID.")
	add_resource_file_args(ap)
	
	ns = ap.parse_args(args)
	
	with open_resource_file(ns.file, fork=ns.fork) as rf:
		list_resource_file(rf, sort=ns.sort, group=ns.group, decompress=ns.decompress)
	
def do_read(prog: str, args: typing.List[str]) -> typing.NoReturn:
	"""Read data from resources."""
	
	ap = make_argument_parser(
		prog=prog,
		description="""
		Read the data of one or more resources.
		
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
		""",
	)
	
	ap.add_argument("--no-decompress", action="store_false", dest="decompress", help="Do not decompress compressed resources, output the raw compressed resource data.")
	ap.add_argument("--format", choices=["dump", "dump-text", "hex", "raw", "derez"], default="dump", help="How to output the resources: human-readable info with hex dump (dump), human-readable info with newline-translated data (dump-text), data only as hex (hex), data only as raw bytes (raw), or like DeRez with no resource definitions (derez). Default: %(default)s")
	ap.add_argument("--no-sort", action="store_false", dest="sort", help="Output resources in the order in which they are stored in the file, instead of sorting them by type and ID.")
	add_resource_file_args(ap)
	ap.add_argument("filter", nargs="*", help="One or more filters to select which resources to read. If no filters ae specified, all resources are read.")
	
	ns = ap.parse_args(args)
	
	with open_resource_file(ns.file, fork=ns.fork) as rf:
		if ns.filter:
			resources = filter_resources(rf, ns.filter)
		else:
			resources = []
			for reses in rf.values():
				resources.extend(reses.values())
		
		if ns.sort:
			resources.sort(key=lambda res: (res.type, res.id))
		
		show_filtered_resources(resources, format=ns.format, decompress=ns.decompress)


SUBCOMMANDS = {
	"read-header": do_read_header,
	"info": do_info,
	"list": do_list,
	"read": do_read,
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
	# In addition, it detects use of the old, non-subcommand-based CLI syntax, and delegates to the old main function in that case.
	# This backwards compatibility handling is one of the reasons why we cannot use the subcommand support of argparse or other CLI parsing libraries, so we have to implement most of the subcommand handling ourselves.
	
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
	# If the old, non-subcommand syntax is used, the subcommand argument can actually be a file name.
	ap.add_argument("subcommand", help=argparse.SUPPRESS)
	ap.add_argument("args", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)
	
	if not args:
		print(f"{prog}: Missing subcommand.", file=sys.stderr)
		ap.print_help()
		sys.exit(2)
	
	# First, parse only known arguments from the CLI.
	# This is so that we can extract the subcommand/file to check if the old CLI syntax was used, without causing CLI syntax errors because of unknown options before the subcommand/file.
	ns, _ = ap.parse_known_args(args)
	
	try:
		# Check if the subcommand is valid.
		subcommand_func = SUBCOMMANDS[ns.subcommand]
	except KeyError:
		if ns.subcommand == "-" or pathlib.Path(ns.subcommand).exists():
			# Subcommand is actually a file path.
			# Call the old main function with the entire unparsed argument list, so that it can be reparsed and handled like in previous versions.
			main_old(args)
		else:
			# Subcommand is invalid and also not a path to an existing file. Display an error.
			print(f"{prog}: Unknown subcommand: {ns.subcommand}", file=sys.stderr)
			print(f"Run {prog} --help for a list of available subcommands.", file=sys.stderr)
			sys.exit(2)
	else:
		# Subcommand is valid. Parse the arguments again, this time without allowing unknown arguments before the subcommand.
		ns = ap.parse_args(args)
		# Call the looked up subcommand and pass on further arguments.
		subcommand_func(f"{prog} {ns.subcommand}", ns.args)

if __name__ == "__main__":
	sys.exit(main())
