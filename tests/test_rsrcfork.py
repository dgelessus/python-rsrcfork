import collections
import pathlib
import unittest

import rsrcfork


DATA_DIR = pathlib.Path(__file__).parent / "data"
EMPTY_RSRC_FILE = DATA_DIR / "empty.rsrc"
TEXTCLIPPING_RSRC_FILE = DATA_DIR / "unicode.textClipping.rsrc"
TESTFILE_RSRC_FILE = DATA_DIR / "testfile.rsrc"

COMPRESS_DATA_DIR = DATA_DIR / "compress"
COMPRESSED_DIR = COMPRESS_DATA_DIR / "compressed"
UNCOMPRESSED_DIR = COMPRESS_DATA_DIR / "uncompressed"
COMPRESS_RSRC_FILE_NAMES = [
	"Finder.rsrc",
	"Finder Help.rsrc",
	# "Install.rsrc", # Commented out for performance - this file contains a lot of small resources.
	"System.rsrc",
]


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
	
	def test_compress_compare(self) -> None:
		# This test goes through pairs of resource files: one original file with both compressed and uncompressed resources, and one modified file where all compressed resources have been decompressed (using ResEdit on System 7.5.5).
		# It checks that the rsrcfork library performs automatic decompression on the compressed resources, so that the compressed resource file appears to the user like the uncompressed resource file (ignoring resource order, which was lost during decompression using ResEdit).
		
		for name in COMPRESS_RSRC_FILE_NAMES:
			with self.subTest(name=name):
				with rsrcfork.open(COMPRESSED_DIR / name, fork="data") as compressed_rf, rsrcfork.open(UNCOMPRESSED_DIR / name, fork="data") as uncompressed_rf:
					self.assertEqual(sorted(compressed_rf), sorted(uncompressed_rf))
					
					for (compressed_type, compressed_reses), (uncompressed_type, uncompressed_reses) in zip(sorted(compressed_rf.items()), sorted(uncompressed_rf.items())):
						with self.subTest(type=compressed_type):
							self.assertEqual(compressed_type, uncompressed_type)
							self.assertEqual(sorted(compressed_reses), sorted(uncompressed_reses))
							
							for (compressed_id, compressed_res), (uncompressed_id, uncompressed_res) in zip(sorted(compressed_reses.items()), sorted(uncompressed_reses.items())):
								with self.subTest(id=compressed_id):
									# The metadata of the compressed and uncompressed resources must match.
									self.assertEqual(compressed_res.type, uncompressed_res.type)
									self.assertEqual(compressed_id, uncompressed_id)
									self.assertEqual(compressed_res.id, compressed_id)
									self.assertEqual(compressed_res.id, uncompressed_res.id)
									self.assertEqual(compressed_res.name, uncompressed_res.name)
									self.assertEqual(compressed_res.attributes & ~rsrcfork.ResourceAttrs.resCompressed, uncompressed_res.attributes)
									
									# The uncompressed resource really has to be not compressed.
									self.assertNotIn(rsrcfork.ResourceAttrs.resCompressed, uncompressed_res.attributes)
									self.assertEqual(uncompressed_res.compressed_info, None)
									self.assertEqual(uncompressed_res.data, uncompressed_res.data_raw)
									self.assertEqual(uncompressed_res.length, uncompressed_res.length_raw)
									
									# The compressed resource's (automatically decompressed) data must match the uncompressed data.
									self.assertEqual(compressed_res.data, uncompressed_res.data)
									self.assertEqual(compressed_res.length, uncompressed_res.length)
									
									if rsrcfork.ResourceAttrs.resCompressed in compressed_res.attributes:
										# Resources with the compressed attribute must expose correct compression metadata.
										self.assertNotEqual(compressed_res.compressed_info, None)
										self.assertEqual(compressed_res.compressed_info.decompressed_length, compressed_res.length)
									else:
										# Some resources in the "compressed" files are not actually compressed, in which case there is no compression metadata.
										self.assertEqual(compressed_res.compressed_info, None)
										self.assertEqual(compressed_res.data, compressed_res.data_raw)
										self.assertEqual(compressed_res.length, compressed_res.length_raw)


if __name__ == "__main__":
	unittest.main()
