import ast
import builtins
from contextlib import redirect_stdout
import io
from pathlib import Path
import runpy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


SOURCE = Path(__file__).resolve().parents[1] / 'fmslog'
TREE = ast.parse(SOURCE.read_text(encoding='utf-8'))
FUNCTIONS = [
	node for node in TREE.body
	if isinstance(node, ast.FunctionDef)
	and node.name in ('strip_line', 'print_crash_reports')
]
NAMESPACE = {}
exec(compile(ast.Module(body=FUNCTIONS, type_ignores=[]), str(SOURCE), 'exec'), NAMESPACE)
strip_line = NAMESPACE['strip_line']


class SuccinctOutputTests(unittest.TestCase):
	def test_preserves_clientstats_and_topcall_fields(self):
		timestamp = '2025-10-16 15:46:18.054'
		for log_name, fields in (
			('clientstats', '37781\t8559\t209\t0\t46442\t0\t28\tClient [192.0.2.1]\n'),
			('topcall', '166630.877193\t166635.541004\t4663811\tQuery (Find)\tTool::table\t509\tClient\n'),
		):
			for zone in ('-0700', '+0530'):
				with self.subTest(log_name=log_name, zone=zone):
					line = timestamp + ' ' + zone + '\t' + fields
					self.assertEqual(strip_line(log_name, line), timestamp + '\t' + fields)

	def test_dapi_removes_only_timezone_and_host(self):
		timestamp = '2025-08-27 11:08:10.055'
		for host in ('192.0.2.1', '250.130.228.236', '2001:db8::1'):
			for ending in ('\n', ''):
				with self.subTest(host=host, ending=ending):
					fields = [
						timestamp + ' -0700', '4101', 'ERROR', host,
						'some-user-name', 'POST', 'Script Error -- Script Name: test', '0' + ending,
					]
					expected = [timestamp] + fields[1:3] + fields[4:]
					self.assertEqual(strip_line('dapi', '\t'.join(fields)), '\t'.join(expected))

	def test_other_logs_are_unchanged(self):
		line = '2025-10-16 15:46:18.054 -0700\tmessage\n'
		self.assertEqual(strip_line('fmsdebug', line), line)


class PlatformImportTests(unittest.TestCase):
	def test_windows_help_does_not_import_pwd_or_run_discovery(self):
		real_import = builtins.__import__

		def import_without_pwd(name, *args, **kwargs):
			if name == 'pwd':
				raise ModuleNotFoundError("No module named 'pwd'")
			return real_import(name, *args, **kwargs)

		output = io.StringIO()
		with (
			patch('builtins.__import__', side_effect=import_without_pwd),
			patch('platform.system', return_value='Windows'),
			patch('subprocess.run', side_effect=AssertionError('Unexpected subprocess')),
			patch('sys.argv', [str(SOURCE), '--help']),
			redirect_stdout(output),
			self.assertRaises(SystemExit) as result,
		):
			runpy.run_path(str(SOURCE), run_name='__main__')
		self.assertEqual(result.exception.code, 0)
		self.assertIn('View FileMaker Server logs', output.getvalue())

	def test_unix_crash_reports_still_look_up_fmserver(self):
		for system in ('Darwin', 'Linux'):
			with self.subTest(system=system):
				pwd = SimpleNamespace(getpwnam=Mock(side_effect=KeyError('fmserver')))
				with (
					patch.dict('sys.modules', pwd=pwd),
					patch.dict(NAMESPACE, platform=SimpleNamespace(system=lambda: system),
						CRASH_PATHS={system: '/unused'}),
					redirect_stdout(io.StringIO()) as output,
				):
					NAMESPACE['print_crash_reports']()
				pwd.getpwnam.assert_called_once_with('fmserver')
				self.assertIn('fmserver user not found', output.getvalue())


if __name__ == '__main__':
	unittest.main()
