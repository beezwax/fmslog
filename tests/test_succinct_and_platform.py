import ast
import builtins
from contextlib import redirect_stdout
import datetime
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
	and node.name in ('strip_line', 'print_crash_reports', 'print_system_log')
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


class SystemLogTests(unittest.TestCase):
	def test_macos_uses_formatted_start_when_set(self):
		start = datetime.datetime(2025, 11, 4, 14, 5, 6, 123456)
		run = Mock(return_value=SimpleNamespace(stdout='message\n', stderr='', returncode=0))
		with (
			patch.dict(NAMESPACE, TIMESTAMP_START=start,
				platform=SimpleNamespace(system=lambda: 'Darwin'),
				subprocess=SimpleNamespace(run=run)),
			redirect_stdout(io.StringIO()),
		):
			self.assertEqual(NAMESPACE['print_system_log'](), 1)
		command = run.call_args.args[0]
		self.assertEqual(command[command.index('--start') + 1], '2025-11-04 14:05:06')

	def test_macos_omits_start_when_unset(self):
		run = Mock(return_value=SimpleNamespace(stdout='message\n', stderr='', returncode=0))
		with (
			patch.dict(NAMESPACE, TIMESTAMP_START=None,
				platform=SimpleNamespace(system=lambda: 'Darwin'),
				subprocess=SimpleNamespace(run=run)),
			redirect_stdout(io.StringIO()),
		):
			NAMESPACE['print_system_log']()
		self.assertNotIn('--start', run.call_args.args[0])
		command = run.call_args.args[0]
		self.assertEqual(command[command.index('--last') + 1], '1h')

	def test_cli_routes_syslog_with_and_without_begin_to_log_command(self):
		for system, options in (
			('Darwin', []), ('Darwin', ['-b', '10h']),
			('Linux', []), ('Linux', ['-b', '10h']),
		):
			with self.subTest(system=system, options=options):
				executable = '/usr/bin/log' if system == 'Darwin' else '/usr/bin/journalctl'

				def run(command, **kwargs):
					if command[0] == executable:
						return SimpleNamespace(stdout='FileMaker test message\n', stderr='', returncode=0)
					return SimpleNamespace(stdout='package-id: test\nversion: 21.0\n', stderr='', returncode=0)

				before = datetime.datetime.now() - datetime.timedelta(hours=10)
				with (
					patch('platform.system', return_value=system),
					patch('subprocess.run', side_effect=run) as subprocess_run,
					patch('sys.argv', [str(SOURCE), *options, 'syslog']),
					redirect_stdout(io.StringIO()) as output,
				):
					runpy.run_path(str(SOURCE), run_name='__main__')
				after = datetime.datetime.now() - datetime.timedelta(hours=10)
				log_commands = [
					call.args[0] for call in subprocess_run.call_args_list
					if call.args[0][0] == executable
				]
				self.assertEqual(len(log_commands), 1)
				command = log_commands[0]
				self.assertIn('FileMaker test message', output.getvalue())
				if system == 'Linux':
					self.assertIn('--no-pager', command)
					self.assertEqual(command[command.index('--unit') + 1], 'fmshelper.service')
				if options:
					start_option = '--start' if system == 'Darwin' else '--since'
					start = datetime.datetime.strptime(command[command.index(start_option) + 1], '%Y-%m-%d %H:%M:%S')
					self.assertGreaterEqual(start, before.replace(microsecond=0))
					self.assertLessEqual(start, after)
					self.assertNotIn('--last', command)
				elif system == 'Linux':
					self.assertEqual(command[command.index('--since') + 1], '1 hour ago')

	def test_macos_log_failure_reports_stderr_and_returns_error(self):
		run = Mock(return_value=SimpleNamespace(stdout='', stderr='permission denied\n', returncode=1))
		print_error = Mock()
		with patch.dict(NAMESPACE, TIMESTAMP_START=None,
			platform=SimpleNamespace(system=lambda: 'Darwin'),
			subprocess=SimpleNamespace(run=run), print_error=print_error):
			self.assertLess(NAMESPACE['print_system_log'](), 0)
		print_error.assert_called_once()
		self.assertIn('permission denied', print_error.call_args.args[0])

	def test_ubuntu_reports_journal_access_warning(self):
		run = Mock(return_value=SimpleNamespace(
			stdout='message\n', stderr='Not seeing messages from other users and the system.\n', returncode=0))
		print_warning = Mock()
		with (
			patch.dict(NAMESPACE, TIMESTAMP_START=None,
				platform=SimpleNamespace(system=lambda: 'Linux'),
				subprocess=SimpleNamespace(run=run), print_warning=print_warning),
			redirect_stdout(io.StringIO()),
		):
			self.assertEqual(NAMESPACE['print_system_log'](), 1)
		print_warning.assert_called_once_with('Not seeing messages from other users and the system.')


if __name__ == '__main__':
	unittest.main()
