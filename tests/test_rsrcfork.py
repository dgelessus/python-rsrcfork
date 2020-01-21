import collections
import io
import pathlib
import shutil
import sys
import tempfile
import typing
import unittest

import rsrcfork

RESOURCE_FORKS_SUPPORTED = sys.platform.startswith("darwin")
RESOURCE_FORKS_NOT_SUPPORTED_MESSAGE = "Resource forks are only supported on Mac"

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


class UnseekableStreamWrapper(io.BufferedIOBase):
	_wrapped: typing.BinaryIO
	
	def __init__(self, wrapped: typing.BinaryIO) -> None:
		super().__init__()
		
		self._wrapped = wrapped
	
	def read(self, size: typing.Optional[int] = -1) -> bytes:
		return self._wrapped.read(size)


def open_resource_fork(path: pathlib.Path, mode: str) -> typing.BinaryIO:
	return (path / "..namedfork" / "rsrc").open(mode)


class ResourceFileReadTests(unittest.TestCase):
	def test_empty(self) -> None:
		with rsrcfork.open(EMPTY_RSRC_FILE, fork="data") as rf:
			self.assertEqual(rf.header_system_data, bytes(112))
			self.assertEqual(rf.header_application_data, bytes(128))
			self.assertEqual(rf.file_attributes, rsrcfork.ResourceFileAttrs(0))
			self.assertEqual(list(rf), [])
	
	def internal_test_textclipping(self, rf: rsrcfork.ResourceFile) -> None:
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
	
	def test_textclipping_seekable_stream(self) -> None:
		with TEXTCLIPPING_RSRC_FILE.open("rb") as f:
			with rsrcfork.ResourceFile(f) as rf:
				self.internal_test_textclipping(rf)
	
	def test_textclipping_unseekable_stream(self) -> None:
		with TEXTCLIPPING_RSRC_FILE.open("rb") as f:
			with UnseekableStreamWrapper(f) as usf:
				with rsrcfork.ResourceFile(usf) as rf:
					self.internal_test_textclipping(rf)
	
	def test_textclipping_path_data_fork(self) -> None:
		with rsrcfork.open(TEXTCLIPPING_RSRC_FILE, fork="data") as rf:
			self.internal_test_textclipping(rf)
	
	@unittest.skipUnless(RESOURCE_FORKS_SUPPORTED, RESOURCE_FORKS_NOT_SUPPORTED_MESSAGE)
	def test_textclipping_path_resource_fork(self) -> None:
		with tempfile.NamedTemporaryFile() as tempf:
			# 
			with TEXTCLIPPING_RSRC_FILE.open("rb") as dataf:
				with open_resource_fork(pathlib.Path(tempf.name), "wb") as rsrcf:
					shutil.copyfileobj(dataf, rsrcf)
			
			with rsrcfork.open(tempf.name, fork="rsrc") as rf:
				self.internal_test_textclipping(rf)
	
	@unittest.skipUnless(RESOURCE_FORKS_SUPPORTED, RESOURCE_FORKS_NOT_SUPPORTED_MESSAGE)
	def test_textclipping_path_auto_resource_fork(self) -> None:
		with tempfile.NamedTemporaryFile() as temp_data_fork:
			with TEXTCLIPPING_RSRC_FILE.open("rb") as source_file:
				with open_resource_fork(pathlib.Path(temp_data_fork.name), "wb") as temp_rsrc_fork:
					shutil.copyfileobj(source_file, temp_rsrc_fork)
			
			with self.subTest(data_fork="empty"):
				# Resource fork is selected when data fork is empty.
				
				with rsrcfork.open(temp_data_fork.name) as rf:
					self.internal_test_textclipping(rf)
			
			with self.subTest(data_fork="non-resource data"):
				# Resource fork is selected when data fork contains non-resource data.
				
				temp_data_fork.write(b"This is the file's data fork. It should not be read, as the file has a resource fork.")
				
				with rsrcfork.open(temp_data_fork.name) as rf:
					self.internal_test_textclipping(rf)
			
			with self.subTest(data_fork="valid resource data"):
				# Resource fork is selected even when data fork contains valid resource data.
				
				with EMPTY_RSRC_FILE.open("rb") as source_file:
					shutil.copyfileobj(source_file, temp_data_fork)
				
				with rsrcfork.open(temp_data_fork.name) as rf:
					self.internal_test_textclipping(rf)
	
	@unittest.skipUnless(RESOURCE_FORKS_SUPPORTED, RESOURCE_FORKS_NOT_SUPPORTED_MESSAGE)
	def test_textclipping_path_auto_data_fork(self) -> None:
		with tempfile.NamedTemporaryFile() as temp_data_fork:
			with TEXTCLIPPING_RSRC_FILE.open("rb") as source_file:
				shutil.copyfileobj(source_file, temp_data_fork)
				# Have to flush the temporary file manually so that the data is visible to the other reads below.
				# Normally this happens automatically as part of the close method, but that would also delete the temporary file, which we don't want.
				temp_data_fork.flush()
			
			with self.subTest(rsrc_fork="nonexistant"):
				# Data fork is selected when resource fork does not exist.
				
				with rsrcfork.open(temp_data_fork.name) as rf:
					self.internal_test_textclipping(rf)
			
			with self.subTest(rsrc_fork="empty"):
				# Data fork is selected when resource fork exists, but is empty.
				
				with open_resource_fork(pathlib.Path(temp_data_fork.name), "wb") as temp_rsrc_fork:
					temp_rsrc_fork.write(b"")
				
				with rsrcfork.open(temp_data_fork.name) as rf:
					self.internal_test_textclipping(rf)
			
			with self.subTest(rsrc_fork="non-resource data"):
				# Data fork is selected when resource fork contains non-resource data.
				
				with open_resource_fork(pathlib.Path(temp_data_fork.name), "wb") as temp_rsrc_fork:
					temp_rsrc_fork.write(b"This is the file's resource fork. It contains junk, so it should be ignored in favor of the data fork.")
				
				with rsrcfork.open(temp_data_fork.name) as rf:
					self.internal_test_textclipping(rf)
	
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
