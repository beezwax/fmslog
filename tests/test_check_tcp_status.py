from importlib.util import spec_from_loader, module_from_spec
from importlib.machinery import SourceFileLoader

targetSpec = spec_from_loader ('fmslogs', SourceFileLoader ('fmslogs', 'fmslogs'))
target = module_from_spec (targetSpec)
targetSpec.loader.exec_module (target)

check_tcp_status = target.check_tcp_status

#check_tcp_status ('FMP Client - Internal', 'localhost', 5003)

def test_check_tcp_status_success(monkeypatch):
    class _DummySocket:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
    def _fake_create_connection(address, timeout=None):
        return _DummySocket()
    monkeypatch.setattr(target.socket, "create_connection", _fake_create_connection)
    result = check_tcp_status('FMP Client - Internal', 'localhost', 5003)
    assert result is True

def test_check_tcp_status_failure(monkeypatch):
    def _fake_create_connection(address, timeout=None):
        raise OSError("connection failed")
    monkeypatch.setattr(target.socket, "create_connection", _fake_create_connection)
    result = check_tcp_status('FMP Client - Internal', 'localhost', 5003)
    assert result is False