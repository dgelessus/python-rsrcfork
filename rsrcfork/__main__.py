import argparse
import collections
import enum
import itertools
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

F = typing.TypeVar("F", bound=enum.Flag, covariant=True)
def _decompose_flags(value: F) -> typing.Sequence[F]:
	"""Decompose an enum.Flags instance into separate enum constants."""
	
	return [bit for bit in type(value) if bit in value]

def _is_printable(char: str) -> bool:
	"""Determine whether a character is printable for our purposes.
	
	We mainly use Python's definition of printable (i. e. everything that Unicode does not consider a separator or "other" character). However, we also treat U+F8FF as printable, which is the private use codepoint used for the Apple logo character.
	"""
	
	return char.isprintable() or char == "\uf8ff"

def _bytes_unescape(string: str) -> bytes:
	"""Convert a string containing text (in _TEXT_ENCODING) and hex escapes to a bytestring.
	
	(We implement our own unescaping mechanism here to not depend on any of Python's string/bytes escape syntax.)
	"""
	
	out = []
	it = iter(string)
	for char in it:
		if char == "\\":
			try:
				esc = next(it)
				if esc in "\\\'\"":
					out.append(esc)
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

def _bytes_escape(bs: bytes, *, quote: str=None) -> str:
	"""Convert a bytestring to a string (using _TEXT_ENCODING), with non-printable characters hex-escaped.
	
	(We implement our own escaping mechanism here to not depend on Python's str or bytes repr.)
	"""
	
	out = []
	for byte, char in zip(bs, bs.decode(_TEXT_ENCODING)):
		if char in {quote, "\\"}:
			out.append(f"\\{char}")
		elif _is_printable(char):
			out.append(char)
		else:
			out.append(f"\\x{byte:02x}")
	
	return "".join(out)

def _filter_resources(rf: api.ResourceFile, filters: typing.Sequence[str]) -> typing.Sequence[api.Resource]:
	matching = collections.OrderedDict()
	
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
				resources = rf[_bytes_unescape(filter[1:-1])]
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
			
			restype, resid = filter[:pos + 1], filter[pos + 2:]
			
			if not restype[0] == restype[-1] == "'":
				raise ValueError(
					f"Invalid filter {filter!r}: Resource type is not a single-quoted type identifier: {restype!r}")
			restype = _bytes_unescape(restype[1:-1])
			
			if len(restype) != 4:
				raise ValueError(
					f"Invalid filter {filter!r}: Type identifier must be 4 bytes after replacing escapes, got {len(restype)} bytes: {restype!r}")
			
			if resid[0] != "(" or resid[-1] != ")":
				raise ValueError(f"Invalid filter {filter!r}: Resource ID must be parenthesized")
			resid = resid[1:-1]
			
			try:
				resources = rf[restype]
			except KeyError:
				continue
			
			if resid[0] == resid[-1] == '"':
				name = _bytes_unescape(resid[1:-1])
				
				for res in resources.values():
					if res.name == name:
						matching[res.type, res.id] = res
						break
			elif ":" in resid:
				if resid.count(":") > 1:
					raise ValueError(f"Invalid filter {filter!r}: Too many colons in ID range expression: {resid!r}")
				start, end = resid.split(":")
				start, end = int(start), int(end)
				
				for res in resources.values():
					if start <= res.id <= end:
						matching[res.type, res.id] = res
			else:
				resid = int(resid)
				try:
					res = resources[resid]
				except KeyError:
					continue
				matching[res.type, res.id] = res
	
	return list(matching.values())

def _hexdump(data: bytes):
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

def _raw_hexdump(data: bytes):
	for i in range(0, len(data), 16):
		print(" ".join(f"{byte:02x}" for byte in data[i:i + 16]))

def _translate_text(data: bytes) -> str:
	return data.decode(_TEXT_ENCODING).replace("\r", "\n")

def _describe_resource(res: api.Resource, *, include_type: bool, decompress: bool) -> str:
	id_desc_parts = [f"{res.id}"]
	
	if res.name is not None:
		name = _bytes_escape(res.name, quote='"')
		id_desc_parts.append(f'"{name}"')
	
	id_desc = ", ".join(id_desc_parts)
	
	content_desc_parts = []
	
	if decompress and api.ResourceAttrs.resCompressed in res.attributes:
		try:
			res.data
		except compress.DecompressError:
			length_desc = f"decompression failed ({len(res.data_raw)} bytes compressed)"
		else:
			length_desc = f"{len(res.data)} bytes ({len(res.data_raw)} bytes compressed)"
	else:
		length_desc = f"{len(res.data_raw)} bytes"
	content_desc_parts.append(length_desc)
	
	attrs = _decompose_flags(res.attributes)
	if attrs:
		content_desc_parts.append(" | ".join(attr.name for attr in attrs))
	
	content_desc = ", ".join(content_desc_parts)
	
	desc = f"({id_desc}): {content_desc}"
	if include_type:
		restype = _bytes_escape(res.type, quote="'")
		desc = f"'{restype}' {desc}"
	return desc

def _parse_args() -> argparse.Namespace:
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
	
	ns = ap.parse_args()
	return ns

def _show_header_data(data: bytes, *, format: str) -> None:
	if format == "dump":
		_hexdump(data)
	elif format == "dump-text":
		print(_translate_text(data))
	elif format == "hex":
		_raw_hexdump(data)
	elif format == "raw":
		sys.stdout.buffer.write(data)
	elif format == "derez":
		print("Cannot output file header data in derez format", file=sys.stderr)
		sys.exit(1)
	else:
		raise ValueError(f"Unhandled output format: {format}")

def _show_filtered_resources(resources: typing.Sequence[api.Resource], format: str, decompress: bool) -> None:
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
			desc = _describe_resource(res, include_type=True, decompress=decompress)
			print(f"Resource {desc}:")
			if format == "dump":
				_hexdump(data)
			elif format == "dump-text":
				print(_translate_text(data))
			else:
				raise AssertionError(f"Unhandled format: {format!r}")
			print()
		elif format == "hex":
			# Data only as hex
			
			_raw_hexdump(data)
		elif format == "raw":
			# Data only as raw bytes
			
			sys.stdout.buffer.write(data)
		elif format == "derez":
			# Like DeRez with no resource definitions
			
			attrs = list(_decompose_flags(res.attributes))
			
			if decompress and api.ResourceAttrs.resCompressed in attrs:
				attrs.remove(api.ResourceAttrs.resCompressed)
				attrs_comment = " /* was compressed */"
			else:
				attrs_comment = ""
			
			attr_descs = [_REZ_ATTR_NAMES[attr] for attr in attrs]
			if None in attr_descs:
				attr_descs[:] = [f"${res.attributes.value:02X}"]
			
			parts = [str(res.id)]
			
			if res.name is not None:
				name = _bytes_escape(res.name, quote='"')
				parts.append(f'"{name}"')
			
			parts += attr_descs
			
			restype = _bytes_escape(res.type, quote="'")
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

def _list_resource_file(rf: api.ResourceFile, *, sort: bool, group: str, decompress: bool) -> None:
	if rf.header_system_data != bytes(len(rf.header_system_data)):
		print("Header system data:")
		_hexdump(rf.header_system_data)
	
	if rf.header_application_data != bytes(len(rf.header_application_data)):
		print("Header application data:")
		_hexdump(rf.header_application_data)
	
	attrs = _decompose_flags(rf.file_attributes)
	if attrs:
		print("File attributes: " + " | ".join(attr.name for attr in attrs))
	
	if len(rf) == 0:
		print("No resources (empty resource file)")
		return
	
	if group == "none":
		all_resources = []
		for reses in rf.values():
			all_resources.extend(reses.values())
		if sort:
			all_resources.sort(key=lambda res: (res.type, res.id))
		print(f"{len(all_resources)} resources:")
		for res in all_resources:
			print(_describe_resource(res, include_type=True, decompress=decompress))
	elif group == "type":
		print(f"{len(rf)} resource types:")
		restype_items = rf.items()
		if sort:
			restype_items = sorted(restype_items, key=lambda item: item[0])
		for typecode, resources in restype_items:
			restype = _bytes_escape(typecode, quote="'")
			print(f"'{restype}': {len(resources)} resources:")
			resources_items = resources.items()
			if sort:
				resources_items = sorted(resources_items, key=lambda item: item[0])
			for resid, res in resources_items:
				print(_describe_resource(res, include_type=False, decompress=decompress))
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
				print(_describe_resource(res, include_type=True, decompress=decompress))
			print()
	else:
		raise AssertionError(f"Unhandled group mode: {group!r}")

def main():
	ns = _parse_args()
	
	if ns.file == "-":
		if ns.fork is not None:
			print("Cannot specify an explicit fork when reading from stdin", file=sys.stderr)
			sys.exit(1)
		
		rf = api.ResourceFile(sys.stdin.buffer)
	else:
		rf = api.ResourceFile.open(ns.file, fork=ns.fork)
	
	with rf:
		if ns.header_system or ns.header_application:
			if ns.header_system:
				data = rf.header_system_data
			else:
				data = rf.header_application_data
			
			_show_header_data(data, format=ns.format)
		elif ns.filter or ns.all:
			if ns.filter:
				resources = _filter_resources(rf, ns.filter)
			else:
				resources = []
				for reses in rf.values():
					resources.extend(reses.values())
			
			if ns.sort:
				resources.sort(key=lambda res: (res.type, res.id))
			
			_show_filtered_resources(resources, format=ns.format, decompress=ns.decompress)
		else:
			_list_resource_file(rf, sort=ns.sort, group=ns.group, decompress=ns.decompress)
	
	sys.exit(0)

if __name__ == "__main__":
	sys.exit(main())
