import ast
import datetime
import io
from pathlib import Path
import re
import sys
from contextlib import redirect_stdout
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / 'fmslog'
# Isolate the parser from module-level FileMaker Server discovery.
FUNCTION = next(
	node for node in ast.parse(SOURCE.read_text(encoding='utf-8')).body
	if isinstance(node, ast.FunctionDef) and node.name == 'parse_begin_time'
)
NAMESPACE = {'datetime': datetime, 're': re, 'sys': sys}
exec(compile(ast.Module(body=[FUNCTION], type_ignores=[]), str(SOURCE), 'exec'), NAMESPACE)
parse_begin_time = NAMESPACE['parse_begin_time']


class ParseBeginTimeTests(unittest.TestCase):
	def test_absolute_timestamps(self):
		cases = (
			('2025-11-04 14:00', datetime.datetime(2025, 11, 4, 14)),
			('2025-11-04 14:00:10', datetime.datetime(2025, 11, 4, 14, 0, 10)),
			('2025-11-04T14:00', datetime.datetime(2025, 11, 4, 14)),
			('2025-11-04T14:00:10', datetime.datetime(2025, 11, 4, 14, 0, 10)),
			('2025-11-04', datetime.datetime(2025, 11, 4)),
			('2024-02-29', datetime.datetime(2024, 2, 29)),
			('2024-02-29T23:59:59', datetime.datetime(2024, 2, 29, 23, 59, 59)),
		)
		for value, expected in cases:
			with self.subTest(value=value):
				actual = parse_begin_time(value)
				self.assertEqual(actual, expected)
				self.assertIsNone(actual.tzinfo)

	def test_time_only_and_relative_values(self):
		now = datetime.datetime(2026, 10, 23, 18, 35, 27, 123456)
		midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
		cases = [
			('14:00', now.replace(hour=14, minute=0, second=0, microsecond=0)),
			('14:00:10', now.replace(hour=14, minute=0, second=10, microsecond=0)),
			('30s', now - datetime.timedelta(seconds=30)),
			('15m', now - datetime.timedelta(minutes=15)),
			('2h', now - datetime.timedelta(hours=2)),
			('7d', midnight - datetime.timedelta(days=6)),
			('2d', midnight - datetime.timedelta(days=1)),
			('0s', now - datetime.timedelta(seconds=1)),
		]
		for unit in ('s', 'm', 'h', 'd'):
			delta = {'s': datetime.timedelta(seconds=1),
				'm': datetime.timedelta(minutes=1), 'h': datetime.timedelta(hours=1)}
			cases.append((unit, midnight if unit == 'd' else now - delta[unit]))
		with patch.dict(NAMESPACE, datetime=SimpleNamespace(
			datetime=unittest.mock.Mock(wraps=datetime.datetime),
			timedelta=datetime.timedelta,
		)):
			NAMESPACE['datetime'].datetime.now.return_value = now
			for value, expected in cases:
				with self.subTest(value=value):
					self.assertEqual(parse_begin_time(value), expected)

	def test_invalid_values(self):
		for value in (
			'', 'garbage', '2025-02-29', '2024-02-30', '2025-13-04',
			'2025-11-04T24:00', '2025-11-04 14:60', '25:00',
			'2025-11-04T14:00Z', '2025-11-04T14:00+01:00', '30seconds',
		):
			with self.subTest(value=value):
				output = io.StringIO()
				with redirect_stdout(output), self.assertRaises(SystemExit) as error:
					parse_begin_time(value)
				self.assertEqual(error.exception.code, 9)
				self.assertIn('Error: invalid begin time value', output.getvalue())
				self.assertIn('YYYY-MM-DD', output.getvalue())
				self.assertIn('HH:MM[:SS]', output.getvalue())
				self.assertIn('space or T separator', output.getvalue())


if __name__ == '__main__':
	unittest.main()
