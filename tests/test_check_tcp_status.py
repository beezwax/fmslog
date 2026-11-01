import pytest
from importlib.util import spec_from_loader, module_from_spec
from importlib.machinery import SourceFileLoader

targetSpec = spec_from_loader ('fmslogs', SourceFileLoader ('fmslogs', 'fmslogs'))
target = module_from_spec (targetSpec)
targetSpec.loader.exec_module (target)

check_tcp_status = target.check_tcp_status

check_tcp_status ('FMP Client - Internal', 'localost', 5003)
