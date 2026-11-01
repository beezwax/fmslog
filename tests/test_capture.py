import ast
import datetime
from pathlib import Path
import tempfile
import unittest
import zipfile
from typing import Optional, Tuple


SOURCE = Path(__file__).resolve().parents[1] / 'fmslog'
FUNCTIONS = [
	node for node in ast.parse(SOURCE.read_text(encoding='utf-8')).body
	if isinstance(node, ast.FunctionDef)
	and node.name in (
		'parse_log_timestamp', 'scan_first_timestamp',
		'find_first_timestamp', 'write_log_to_zip',
	)
]
NAMESPACE = {
	'datetime': datetime, 'zipfile': zipfile,
	'Optional': Optional, 'Tuple': Tuple,
}
exec(compile(ast.Module(body=FUNCTIONS, type_ignores=[]), str(SOURCE), 'exec'), NAMESPACE)
write_log_to_zip = NAMESPACE['write_log_to_zip']


class CaptureTests(unittest.TestCase):
	def capture(self, content, timestamp):
		with tempfile.TemporaryDirectory() as directory:
			log_path = Path(directory) / 'sample.log'
			archive_path = Path(directory) / 'capture.zip'
			log_path.write_bytes(content)
			with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as archive:
				write_log_to_zip(archive, str(log_path), 'sample.log', timestamp)
			with zipfile.ZipFile(archive_path) as archive:
				return archive.read('sample.log')

	def test_begin_captures_from_first_matching_timestamp_and_skips_preamble(self):
		content = (
			b'log preamble\r\n'
			b'2025-10-27 04:13:24.101 -0700\told message\r\n'
			b'2025-10-27 04:14:24.101 -0700\tmatching message\r\n'
			b'2025-10-27 04:15:24.101 -0700\tlater message\r\n'
		)
		self.assertEqual(
			self.capture(content, datetime.datetime(2025, 10, 27, 4, 14)),
			content[content.index(b'2025-10-27 04:14'):],
		)

	def test_begin_replaces_invalid_utf8_in_timestamped_log(self):
		content = b'2025-10-27 04:14:24.101 -0700\tinvalid: \xff\n'
		self.assertEqual(
			self.capture(content, datetime.datetime(2025, 10, 27, 4, 14)),
			'2025-10-27 04:14:24.101 -0700\tinvalid: \ufffd\n'.encode('utf-8'),
		)

	def test_begin_captures_full_log_when_timestamps_are_unsupported(self):
		content = b'log preamble\nmessage without a supported timestamp\n'
		self.assertEqual(
			self.capture(content, datetime.datetime(2025, 10, 27)),
			content,
		)

	def test_begin_captures_from_last_timestamp_before_threshold(self):
		content = (
			b'log preamble\n'
			b'2025-10-27 04:12:24.101 -0700\tfirst old message\n'
			b'2025-10-27 04:13:24.101 -0700\tlast old message\n'
		)
		self.assertEqual(
			self.capture(content, datetime.datetime(2025, 10, 27, 5)),
			content[content.index(b'2025-10-27 04:13'):],
		)

	def test_capture_without_begin_preserves_entire_file(self):
		content = b'log preamble\r\nmessage\r\n'
		self.assertEqual(self.capture(content, None), content)


if __name__ == '__main__':
	unittest.main()
