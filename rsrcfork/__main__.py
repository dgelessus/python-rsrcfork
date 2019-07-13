import argparse
import collections
import enum
import sys
import textwrap
import typing

from . import __version__, api

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

def _bytes_unescape(string: str) -> bytes:
	"""Convert a string containing ASCII characters and hex escapes to a bytestring.
	
	(We implement our own unescaping mechanism here to not depend on any of Python's string/bytes escape syntax.)
	"""
	
	out = []
	it = iter(string)
	n = 0
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
			out.append(ord(char))
		n += 1
	
	return bytes(out)

def _bytes_escape(bs: bytes, *, quote: str=None) -> str:
	"""Convert a bytestring to a string, with non-ASCII bytes hex-escaped.
	
	(We implement our own escaping mechanism here to not depend on Python's str or bytes repr.)
	"""
	
	out = []
	for byte in bs:
		c = chr(byte)
		if c in {quote, "\\"}:
			out.append(f"\\{c}")
		elif 0x20 <= byte < 0x7f:
			out.append(c)
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
				matching[res.resource_type, res.resource_id] = res
		elif filter[0] == filter[-1] == "'":
			try:
				resources = rf[_bytes_unescape(filter[1:-1])]
			except KeyError:
				continue
			
			for res in resources.values():
				matching[res.resource_type, res.resource_id] = res
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
						matching[res.resource_type, res.resource_id] = res
						break
			elif ":" in resid:
				if resid.count(":") > 1:
					raise ValueError(f"Invalid filter {filter!r}: Too many colons in ID range expression: {resid!r}")
				start, end = resid.split(":")
				start, end = int(start), int(end)
				
				for res in resources.values():
					if start <= res.resource_id <= end:
						matching[res.resource_type, res.resource_id] = res
			else:
				resid = int(resid)
				try:
					res = resources[resid]
				except KeyError:
					continue
				matching[res.resource_type, res.resource_id] = res
	
	return list(matching.values())

def _hexdump(data: bytes):
	for i in range(0, len(data), 16):
		line = data[i:i + 16]
		line_hex = " ".join(f"{byte:02x}" for byte in line)
		line_char = line.decode("MacRoman").translate(_TRANSLATE_NONPRINTABLES)
		print(f"{i:08x} {line_hex:<{16*2+15}} |{line_char}|")
	
	if data:
		print(f"{len(data):08x}")

def _raw_hexdump(data: bytes):
	for i in range(0, len(data), 16):
		print(" ".join(f"{byte:02x}" for byte in data[i:i + 16]))

def main():
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
	ap.add_argument("--format", choices=["dump", "hex", "raw", "derez"], default="dump", help="How to output the resources - human-readable info with hex dump (dump), data only as hex (hex), data only as raw bytes (raw), or like DeRez with no resource definitions (derez)")
	ap.add_argument("--header-system", action="store_true", help="Output system-reserved header data and nothing else")
	ap.add_argument("--header-application", action="store_true", help="Output application-specific header data and nothing else")
	ap.add_argument("--read-mode", choices=["auto", "stream", "seek"], default="auto", help="Whether to read the data sequentially (stream) or on-demand (seek), or auto to use seeking when possible (default: %(default)s)")
	
	ap.add_argument("file", help="The file to read, or - for stdin")
	ap.add_argument("filter", nargs="*", help="One or more filters to select which resources to display, or omit to show an overview of all resources")
	
	ns = ap.parse_args()
	
	ns.fork = {"auto": None, "data": False, "rsrc": True}[ns.fork]
	ns.read_mode = {"auto": None, "stream": False, "seek": True}[ns.read_mode]
	
	if ns.file == "-":
		if ns.fork is not None:
			print("Cannot specify an explicit fork when reading from stdin", file=sys.stderr)
			sys.exit(1)
		
		rf = api.ResourceFile(sys.stdin.buffer, allow_seek=ns.read_mode)
	else:
		rf = api.ResourceFile.open(ns.file, rsrcfork=ns.fork, allow_seek=ns.read_mode)
	
	with rf:
		if ns.header_system or ns.header_application:
			if ns.header_system:
				data = rf.header_system_data
			else:
				data = rf.header_application_data
			
			if ns.format == "dump":
				_hexdump(data)
			elif ns.format == "hex":
				_raw_hexdump(data)
			elif ns.format == "raw":
				sys.stdout.buffer.write(data)
			elif ns.format == "derez":
				print("Cannot output file header data in derez format", file=sys.stderr)
				sys.exit(1)
			else:
				raise ValueError(f"Unhandled output format: {ns.format}")
		elif ns.filter or ns.all:
			if ns.filter:
				resources = _filter_resources(rf, ns.filter)
			else:
				resources = []
				for reses in rf.values():
					resources.extend(reses.values())
			
			if ns.format in ("hex", "raw") and len(resources) != 1:
				print(f"Format {ns.format} only supports exactly one resource, but found {len(resources)}", file=sys.stderr)
				sys.exit(1)
			
			for res in resources:
				if ns.format == "dump":
					# Human-readable info and hex dump
					
					if res.name is None:
						name = "unnamed"
					else:
						name = _bytes_escape(res.name, quote='"')
						name = f'name "{name}"'
					
					attrs = _decompose_flags(res.attributes)
					if attrs:
						attrdesc = "attributes: " + " | ".join(attr.name for attr in attrs)
					else:
						attrdesc = "no attributes"
					
					restype = _bytes_escape(res.resource_type, quote="'")
					print(f"Resource '{restype}' ({res.resource_id}), {name}, {attrdesc}, {len(res.data)} bytes:")
					_hexdump(res.data)
					print()
				elif ns.format == "hex":
					# Data only as hex
					
					_raw_hexdump(res.data)
				elif ns.format == "raw":
					# Data only as raw bytes
					
					sys.stdout.buffer.write(res.data)
				elif ns.format == "derez":
					# Like DeRez with no resource definitions
					
					attrs = [_REZ_ATTR_NAMES[attr] for attr in _decompose_flags(res.attributes)]
					if None in attrs:
						attrs[:] = [f"${res.attributes.value:02X}"]
					
					parts = [str(res.resource_id)]
					
					if res.name is not None:
						name = _bytes_escape(res.name, quote='"')
						parts.append(f'"{name}"')
					
					parts += attrs
					
					restype = _bytes_escape(res.resource_type, quote="'")
					print(f"data '{restype}' ({', '.join(parts)}) {{")
					
					for i in range(0, len(res.data), 16):
						# Two-byte grouping is really annoying to implement.
						groups = []
						for j in range(0, 16, 2):
							if i+j >= len(res.data):
								break
							elif i+j+1 >= len(res.data):
								groups.append(f"{res.data[i+j]:02X}")
							else:
								groups.append(f"{res.data[i+j]:02X}{res.data[i+j+1]:02X}")
						
						s = f'$"{" ".join(groups)}"'
						comment = "/* " + res.data[i:i + 16].decode("MacRoman").translate(_TRANSLATE_NONPRINTABLES) + " */"
						print(f"\t{s:<54s}{comment}")
					
					print("};")
					print()
				else:
					raise ValueError(f"Unhandled output format: {ns.format}")
		else:
			if rf.header_system_data != bytes(len(rf.header_system_data)):
				print("Header system data:")
				_hexdump(rf.header_system_data)
			else:
				print("No header system data")
			
			if rf.header_application_data != bytes(len(rf.header_application_data)):
				print("Header application data:")
				_hexdump(rf.header_application_data)
			else:
				print("No header application data")
			
			attrs = _decompose_flags(rf.file_attributes)
			if attrs:
				print("File attributes: " + " | ".join(attr.name for attr in attrs))
			else:
				print("No file attributes")
			
			if len(rf) > 0:
				print(f"{len(rf)} resource types:")
				for typecode, resources in rf.items():
					restype = _bytes_escape(typecode, quote="'")
					print(f"'{restype}': {len(resources)} resources:")
					for resid, res in rf[typecode].items():
						if res.name is None:
							name = "unnamed"
						else:
							name = _bytes_escape(res.name, quote='"')
							name = f'name "{name}"'
						
						attrs = _decompose_flags(res.attributes)
						if attrs:
							attrdesc = " | ".join(attr.name for attr in attrs)
						else:
							attrdesc = "no attributes"
						
						print(f"({resid}), {name}, {attrdesc}, {len(res.data)} bytes")
					print()
			else:
				print("No resource types (empty resource file)")
	
	sys.exit(0)

if __name__ == "__main__":
	sys.exit(main())
