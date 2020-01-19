import collections
import pathlib
import unittest

import rsrcfork


DATA_DIR = pathlib.Path(__file__).parent / "data"
EMPTY_RSRC_FILE = DATA_DIR / "empty.rsrc"
TEXTCLIPPING_RSRC_FILE = DATA_DIR / "unicode.textClipping.rsrc"
TESTFILE_RSRC_FILE = DATA_DIR / "testfile.rsrc"


def make_pascal_string(s):
	return bytes([len(s)]) + s


UNICODE_TEXT = "Here is some text, including Üñïçø∂é!"
DRAG_DATA = (
	b"\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x03"
	b"utxt\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00"
	b"utf8\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00"
	b"TEXT\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00"
)
TEXTCLIPPING_RESOURCES = collections.OrderedDict([
	(b"utxt", collections.OrderedDict([
		(256, UNICODE_TEXT.encode("utf-16-be")),
	])),
	(b"utf8", collections.OrderedDict([
		(256, UNICODE_TEXT.encode("utf-8")),
	])),
	(b"TEXT", collections.OrderedDict([
		(256, UNICODE_TEXT.encode("macroman")),
	])),
	(b"drag", collections.OrderedDict([
		(128, DRAG_DATA),
	]))
])

TESTFILE_HEADER_SYSTEM_DATA = (
	b"\xa7F$\x08 <\x00\x00\xab\x03\xa7F <\x00\x00"
	b"\x01\x00\xb4\x88f\x06`\np\x00`\x06 <\x00\x00"
	b"\x08testfile\x00\x02\x00\x02\x00rs"
	b"rcRSED\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
	b"\x02\x00rsrcRSED\x00\x00\x00\x00\x00\x00"
	b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
	b"\x00\x00\xdaIp~\x00\x00\x00\x00\x00\x00\x02.\xfe\x84"
)
TESTFILE_HEADER_APPLICATION_DATA = b"This is the application-specific header data section. Apparently I can write whatever nonsense I want here. A few more bytes...."
TESTFILE_RESOURCES = collections.OrderedDict([
	(b"STR ", collections.OrderedDict([
		(128, (
			None, rsrcfork.ResourceAttrs(0),
			make_pascal_string(b"The String, without name or attributes"),
		)),
		(129, (
			b"The Name", rsrcfork.ResourceAttrs(0),
			make_pascal_string(b"The String, with name and no attributes"),
		)),
		(130, (
			None, rsrcfork.ResourceAttrs.resProtected | rsrcfork.ResourceAttrs.resPreload,
			make_pascal_string(b"The String, without name but with attributes"),
		)),
		(131, (
			b"The Name with Attributes", rsrcfork.ResourceAttrs.resSysHeap,
			make_pascal_string(b"The String, with both name and attributes"),
		)),
	])),
])


class ResourceFileReadTests(unittest.TestCase):
	def test_empty(self) -> None:
		with rsrcfork.open(EMPTY_RSRC_FILE, fork="data") as rf:
			self.assertEqual(rf.header_system_data, bytes(112))
			self.assertEqual(rf.header_application_data, bytes(128))
			self.assertEqual(rf.file_attributes, rsrcfork.ResourceFileAttrs(0))
			self.assertEqual(list(rf), [])
	
	def test_textclipping(self) -> None:
		with rsrcfork.open(TEXTCLIPPING_RSRC_FILE, fork="data") as rf:
			self.assertEqual(rf.header_system_data, bytes(112))
			self.assertEqual(rf.header_application_data, bytes(128))
			self.assertEqual(rf.file_attributes, rsrcfork.ResourceFileAttrs(0))
			self.assertEqual(list(rf), list(TEXTCLIPPING_RESOURCES))
			
			for (actual_type, actual_reses), (expected_type, expected_reses) in zip(rf.items(), TEXTCLIPPING_RESOURCES.items()):
				with self.subTest(type=expected_type):
					self.assertEqual(actual_type, expected_type)
					self.assertEqual(list(actual_reses), list(expected_reses))
					
					for (actual_id, actual_res), (expected_id, expected_data) in zip(actual_reses.items(), expected_reses.items()):
						with self.subTest(id=expected_id):
							self.assertEqual(actual_res.type, expected_type)
							self.assertEqual(actual_id, expected_id)
							self.assertEqual(actual_res.id, expected_id)
							self.assertEqual(actual_res.name, None)
							self.assertEqual(actual_res.attributes, rsrcfork.ResourceAttrs(0))
							self.assertEqual(actual_res.data, expected_data)
							self.assertEqual(actual_res.compressed_info, None)
	
	def test_testfile(self) -> None:
		with rsrcfork.open(TESTFILE_RSRC_FILE, fork="data") as rf:
			self.assertEqual(rf.header_system_data, TESTFILE_HEADER_SYSTEM_DATA)
			self.assertEqual(rf.header_application_data, TESTFILE_HEADER_APPLICATION_DATA)
			self.assertEqual(rf.file_attributes, rsrcfork.ResourceFileAttrs.mapPrinterDriverMultiFinderCompatible | rsrcfork.ResourceFileAttrs.mapReadOnly)
			self.assertEqual(list(rf), list(TESTFILE_RESOURCES))
			
			for (actual_type, actual_reses), (expected_type, expected_reses) in zip(rf.items(), TESTFILE_RESOURCES.items()):
				with self.subTest(type=expected_type):
					self.assertEqual(actual_type, expected_type)
					self.assertEqual(list(actual_reses), list(expected_reses))
					
					for (actual_id, actual_res), (expected_id, (expected_name, expected_attrs, expected_data)) in zip(actual_reses.items(), expected_reses.items()):
						with self.subTest(id=expected_id):
							self.assertEqual(actual_res.type, expected_type)
							self.assertEqual(actual_id, expected_id)
							self.assertEqual(actual_res.id, expected_id)
							self.assertEqual(actual_res.name, expected_name)
							self.assertEqual(actual_res.attributes, expected_attrs)
							self.assertEqual(actual_res.data, expected_data)
							self.assertEqual(actual_res.compressed_info, None)


if __name__ == "__main__":
	unittest.main()
