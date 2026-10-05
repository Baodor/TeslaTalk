import importlib.util
import json
from pathlib import Path
import subprocess
import pytest

path = Path(__file__).resolve().parents[2] / 'scripts/setup_voice_vps.py'
spec = importlib.util.spec_from_file_location('setup_voice_vps', path)
vps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vps)


def test_only_media_rules_are_added_idempotently_and_undo_preserves_other_rules(tmp_path):
    state = tmp_path / 'rules.json'
    unrelated = [['filter', 'FORWARD', ['-j', 'DROP']]]
    state.write_text(json.dumps(unrelated))
    iptables = tmp_path / 'iptables'
    iptables.write_text('''#!/usr/bin/env python3
import json, sys
from pathlib import Path
state = Path(__file__).with_name('rules.json')
rows = json.loads(state.read_text())
args = sys.argv[1:]
assert args[:3] == ['-w', '10', '-t']
table, action, chain = args[3:6]
tail = args[7:] if action == '-I' else args[6:]
rule = [table, chain, tail]
if action == '-C':
    sys.exit(0 if rule in rows else 1)
elif action == '-I':
    assert args[6] == '1'
    rows.insert(0, rule)
elif action == '-D':
    rows.remove(rule)
else:
    raise AssertionError(action)
state.write_text(json.dumps(rows))
''')
    iptables.chmod(0o700)
    script = tmp_path / 'forward.sh'
    script.write_text(vps.render(vps.rules('1.1.1.1', '10.66.0.2', '10.66.0.1', 'ens6', 'wg0'), str(iptables)))
    subprocess.run(['bash', '-n', str(script)], check=True)
    for _ in range(2):
        subprocess.run(['bash', str(script), 'apply'], check=True)
        assert len(json.loads(state.read_text())) == 9
    for _ in range(2):
        subprocess.run(['bash', str(script), 'remove'], check=True)
        assert json.loads(state.read_text()) == unrelated


@pytest.mark.parametrize('value', ['ens6;shutdown', 'wg0\ncommand', 'interface-name-too-long'])
def test_interface_names_cannot_inject_commands(value):
    with pytest.raises(ValueError):
        vps.interface(value)
