import collections
import pathlib
import unittest

import rsrcfork


DATA_DIR = pathlib.Path(__file__).parent / "data"
EMPTY_RSRC_FILE = DATA_DIR / "empty.rsrc"
TEXTCLIPPING_RSRC_FILE = DATA_DIR / "unicode.textClipping.rsrc"

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


class ResourceFileReadTests(unittest.TestCase):
	def test_empty(self) -> None:
		with rsrcfork.open(EMPTY_RSRC_FILE, fork="data") as rf:
			self.assertEqual(rf.header_system_data, bytes(112))
			self.assertEqual(rf.header_application_data, bytes(128))
			for attr in rsrcfork.ResourceFileAttrs:
				self.assertNotIn(attr, rf.file_attributes)
			self.assertEqual(list(rf), [])
	
	def test_textclipping(self) -> None:
		with rsrcfork.open(TEXTCLIPPING_RSRC_FILE, fork="data") as rf:
			self.assertEqual(rf.header_system_data, bytes(112))
			self.assertEqual(rf.header_application_data, bytes(128))
			for attr in rsrcfork.ResourceFileAttrs:
				self.assertNotIn(attr, rf.file_attributes)
			self.assertEqual(list(rf), list(TEXTCLIPPING_RESOURCES))
			
			for (actual_type, actual_reses), (expected_type, expected_reses) in zip(rf.items(), TEXTCLIPPING_RESOURCES.items()):
				with self.subTest(type=expected_type):
					self.assertEqual(actual_type, expected_type)
					for (actual_id, actual_res), (expected_id, expected_data) in zip(actual_reses.items(), expected_reses.items()):
						with self.subTest(id=expected_id):
							self.assertEqual(actual_res.type, expected_type)
							self.assertEqual(actual_res.id, expected_id)
							self.assertEqual(actual_res.name, None)
							for attr in rsrcfork.ResourceAttrs:
								self.assertNotIn(attr, actual_res.attributes)
							self.assertEqual(actual_res.data, expected_data)
							self.assertEqual(actual_res.compressed_info, None)

if __name__ == "__main__":
	unittest.main()
