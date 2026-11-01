import ast
from contextlib import contextmanager, nullcontext, redirect_stdout
import datetime
import io
import linecache
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import Mock, patch
from typing import Optional, Tuple


SOURCE = Path(__file__).resolve().parents[1] / 'fmslog'
FUNCTIONS = [
	node for node in ast.parse(SOURCE.read_text(encoding='utf-8')).body
	if isinstance(node, ast.FunctionDef)
	and node.name in (
		'parse_log_timestamp', 'scan_first_timestamp',
		'find_first_timestamp', 'read_tail_time', 'print_data_dirs_info',
		'print_documents_info', 'print_documents_web_info',
	)
]
NAMESPACE = {
	'datetime': datetime, 'linecache': linecache, 'os': os, 're': re,
	'Optional': Optional, 'Tuple': Tuple,
}
exec(compile(ast.Module(body=FUNCTIONS, type_ignores=[]), str(SOURCE), 'exec'), NAMESPACE)


class TimestampScanningTests(unittest.TestCase):
	def scan(self, lines, threshold):
		with tempfile.TemporaryDirectory() as directory:
			path = Path(directory) / 'sample.log'
			path.write_text(lines, encoding='utf-8')
			try:
				return NAMESPACE['find_first_timestamp'](str(path), threshold)
			finally:
				linecache.clearcache()

	def test_slash_timestamp_preserves_fractional_precision(self):
		lines = (
			'header\n'
			'2025/10/25 17:49:09.0162: [ 2525]: TRACE: first\n'
			'2025/10/25 17:49:09.0163: [ 2525]: TRACE: second\n'
		)
		for microsecond, expected in ((16200, 2), (16201, 3), (16301, 3)):
			with self.subTest(microsecond=microsecond):
				self.assertEqual(self.scan(lines,
					datetime.datetime(2025, 10, 25, 17, 49, 9, microsecond)), expected)

	def test_odata_offsets_are_compared_in_local_time(self):
		for offset in ('-08:00', '+05:30', '+00:00'):
			with self.subTest(offset=offset):
				value = '2025-10-14T13:01:31.232452' + offset
				local = datetime.datetime.fromisoformat(value).astimezone().replace(tzinfo=None)
				lines = 'header\n' + value + '\t0\tINFO\t192.0.2.1\tGET\t/fmi/odata/v4\t75\n'
				self.assertEqual(self.scan(lines, local), 2)
				self.assertEqual(self.scan(lines, local - datetime.timedelta(microseconds=1)), 2)
				self.assertEqual(self.scan(lines, local + datetime.timedelta(microseconds=1)), 2)

	def test_existing_formats(self):
		for line, threshold in (
			('2025-10-27 04:13:24.101 -0700\tInformation\t228\thost\tmessage\n',
				datetime.datetime(2025, 10, 27, 4, 13, 24, 101000)),
			('Sep 11, 2025 12:40:52 PM org.atmosphere.cpr message\n',
				datetime.datetime(2025, 9, 11, 12, 40, 52)),
			('Thrift: Sat Jun  7 10:47:03 2025 TNonblockingServer: message\n',
				datetime.datetime(2025, 6, 7, 10, 47, 3)),
		):
			with self.subTest(line=line):
				self.assertEqual(self.scan('\nheader\n' + line, threshold), 3)

	def test_date_only_timestamps(self):
		lines = (
			'2025-10-26 Previous day message\n'
			'2025-10-27 Start date message\n'
			'2025-10-28 Following day message\n'
		)
		self.assertEqual(self.scan(lines, datetime.datetime(2025, 10, 27)), 2)

	def test_falls_back_to_last_supported_timestamp_before_threshold(self):
		lines = (
			'log preamble\n'
			'2025-10-26 first message\n'
			'message without a timestamp\n'
			'2025-10-26 last message\n'
		)
		self.assertEqual(self.scan(lines, datetime.datetime(2025, 10, 27)), 4)

	def test_tail_starts_at_last_supported_timestamp_before_begin_time(self):
		with tempfile.TemporaryDirectory() as directory:
			path = Path(directory) / 'sample.log'
			path.write_text(
				'log preamble\n'
				'2025-10-26 first message\n'
				'2025-10-26 last message\n'
				'trailing message\n',
				encoding='utf-8',
			)
			with patch.dict(NAMESPACE, {
				'TIMESTAMP_START': datetime.datetime(2025, 10, 27),
				'check_file_validity': lambda file_path: None,
			}):
				self.assertEqual(NAMESPACE['read_tail_time'](str(path), 10), [3, 4])


class DirectoryReportingTests(unittest.TestCase):
	def test_database_columns_align_for_terminal_and_redirected_output(self):
		paths = ('/default', '/secure', '/additional1', '/additional2', '/container1', '/container2')
		for terminal in (False, True):
			for missing in (False, True):
				with self.subTest(terminal=terminal, missing=missing):
					@contextmanager
					def spinner(message):
						print(message, end='')
						yield
						print(' ' if terminal else '\r', end='')

					other_reports = {
						name: Mock() for name in (
							'print_fms_cache_info', 'print_documents_info',
							'print_documents_web_info', 'print_fmtmp_info',
							'print_remotebackup_info', 'print_standby_info',
						)
					}
					output = io.StringIO()
					with patch.dict(NAMESPACE, {
						'get_db_directories': lambda: paths,
						'get_folder_stats': Mock(return_value=(-1, 0, 0) if missing else (1234, 7, 567)),
						'Spinner': spinner,
						**other_reports,
					}), redirect_stdout(output):
						NAMESPACE['print_data_dirs_info']()

					lines = [line.rsplit('\r', 1)[-1] for line in output.getvalue().split('\n')]
					header = next(line for line in lines if 'H/L SIZE' in line)
					rows = [line for line in lines if ':' in line]
					self.assertEqual(len(rows), 14)
					self.assertEqual(header.index('PATH'), 75)
					for row in rows:
						with self.subTest(row=row):
							expected = ('7', '1,234', '567')
							if missing:
								expected = ('-', '-', '-') if row.startswith('  ') else ('0', '-1', '0')
							actual = tuple(row[start:end].strip() for start, end in ((26, 37), (39, 55), (57, 73)))
							self.assertEqual(actual, expected)
							self.assertTrue(row[75:].startswith('/') or row[75:] == '-')

	def test_document_columns_align_for_terminal_and_redirected_output(self):
		for terminal in (False, True):
			with self.subTest(terminal=terminal):
				@contextmanager
				def spinner(message):
					print(message, end='')
					yield
					print(' ' if terminal else '\r', end='')

				output = io.StringIO()
				with patch.dict(NAMESPACE, {
					'BASE_PATH': '/server',
					'get_folder_stats': Mock(return_value=(1234, 7, 0)),
					'Spinner': spinner,
				}), redirect_stdout(output):
					NAMESPACE['print_documents_info']()
					NAMESPACE['print_documents_web_info']()
				lines = [line.rsplit('\r', 1)[-1] for line in output.getvalue().split('\n') if line]
				self.assertEqual(len(lines), 2)
				for line, label in zip(lines, ('Documents', 'Web Documents')):
					self.assertEqual(line[:26], f'{label:26}')
					self.assertEqual(line[26:37].strip(), '7')
					self.assertEqual(line[39:55].strip(), '1,234')
					self.assertTrue(line[75:].startswith('/server/'))

	def test_missing_paths_are_reported_and_other_sections_continue(self):
		for default in (None, '/default'):
			for secure in (None, '/secure'):
				with self.subTest(default=default, secure=secure):
					stats = Mock(return_value=(1024, 2, 0))
					warning = Mock()
					other_reports = {
						name: Mock() for name in (
							'print_fms_cache_info', 'print_documents_info',
							'print_documents_web_info', 'print_fmtmp_info',
							'print_remotebackup_info', 'print_standby_info',
						)
					}
					output = io.StringIO()
					with patch.dict(NAMESPACE, {
						'get_db_directories': lambda: (default, secure, '/additional', None, None, None),
						'get_folder_stats': stats,
						'Spinner': lambda message: nullcontext(),
						'print_warning': warning,
						**other_reports,
					}), redirect_stdout(output):
						NAMESPACE['print_data_dirs_info']()
					for label, path in (('Default', default), ('Secure', secure)):
						if path:
							stats.assert_any_call(path, exclude_dirs=['RC_Data_FMS', 'Removed_by_FMS'])
							for subdir in ('RC_Data_FMS', 'Removed_by_FMS'):
								stats.assert_any_call(os.path.join(path, subdir))
							self.assertIn(path, output.getvalue())
						else:
							warning.assert_any_call(
								f'{label}: path unavailable in Event.log or Event-old.log')
					self.assertEqual(warning.call_count, int(default is None) + int(secure is None))
					stats.assert_any_call('/additional', exclude_dirs=['RC_Data_FMS', 'Removed_by_FMS'])
					for report in other_reports.values():
						report.assert_called_once_with()


if __name__ == '__main__':
	unittest.main()
