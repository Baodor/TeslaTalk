import importlib.util
from pathlib import Path
import pytest
import yaml

path = Path(__file__).resolve().parents[2] / 'scripts/configure_voice.py'
spec = importlib.util.spec_from_file_location('configure_voice', path)
voice = importlib.util.module_from_spec(spec)
spec.loader.exec_module(voice)


def test_manual_vps_ip_preserves_credentials_ports_and_turn_settings():
    previous = '''port: 7880
rtc:
  tcp_port: 7881
  udp_port: 7882
  use_external_ip: true
  stun_servers: [stun.example.com:3478]
keys:
  private-key: private-secret
turn:
  enabled: true
  domain: turn.example.com
'''
    updated = voice.configure(previous, '1.1.1.1')
    data = yaml.safe_load(updated)
    assert data['rtc']['node_ip'] == '1.1.1.1'
    assert data['rtc']['use_external_ip'] is False
    assert data['rtc']['advertise_internal_ip'] is False
    assert data['rtc']['tcp_port'] == 7881 and data['rtc']['udp_port'] == 7882
    assert data['keys'] == yaml.safe_load(previous)['keys']
    assert data['turn'] == yaml.safe_load(previous)['turn']
    assert data['rtc']['stun_servers'] == ['stun.example.com:3478']
    assert voice.configure(updated, '1.1.1.1') == updated
    restored = yaml.safe_load(voice.configure(updated, ''))
    assert 'node_ip' not in restored['rtc'] and restored['rtc']['use_external_ip'] is True


@pytest.mark.parametrize('value', ['127.0.0.1', '10.0.0.2', '100.64.0.1', '203.0.113.1', '::1', '2001:4860:4860::8888', '224.0.0.1', 'example.com', '1.1.1.1\nkeys: invalid'])
def test_only_numeric_public_vps_ipv4_is_accepted(value):
    with pytest.raises(ValueError):
        voice.public_ip(value)


def test_check_never_changes_livekit_or_prints_secrets(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(voice, 'ROOT', tmp_path)
    (tmp_path / 'deploy').mkdir()
    (tmp_path / '.env').write_text('APP_SECRET=private-app-secret\nLIVEKIT_PUBLIC_IP="1.1.1.1" # VPS\n')
    config = tmp_path / 'deploy/livekit.yaml'
    previous = 'rtc:\n  use_external_ip: true\nkeys:\n  private-key: private-secret\n'
    config.write_text(previous)
    monkeypatch.setattr('sys.argv', ['configure_voice.py', '--check'])
    with pytest.raises(SystemExit) as stopped:
        voice.main()
    assert stopped.value.code == 1
    assert config.read_text() == previous
    output = capsys.readouterr().out
    assert 'private' not in output


@pytest.mark.parametrize('config', ['rtc: {use_external_ip: true}\n', 'rtc:\n    node_ip: 1.1.1.1\n', 'rtc:\n  node_ip: 1.1.1.1\n  node_ip: 2.2.2.2\n'])
def test_unsupported_custom_yaml_is_not_rewritten(config):
    with pytest.raises(ValueError):
        voice.configure(config, '1.1.1.1')
