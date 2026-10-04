import importlib.util
import io
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs
import pytest


spec = importlib.util.spec_from_file_location('register_tesla', Path(__file__).resolve().parents[2]/'scripts/register_tesla.py')
registration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(registration)


def test_dotenv_quotes_comments_and_shell_characters_are_literal(tmp_path):
    path = tmp_path/'.env'
    path.write_text("# comment\nexport APP_URL = 'https://talk.example.com'\nTESLA_CLIENT_SECRET=\"literal-$(command)-`command`#value\" # comment\nTESLA_CLIENT_ID=client # comment\n")
    assert registration.read_env(path) == {
        'APP_URL': 'https://talk.example.com',
        'TESLA_CLIENT_SECRET': 'literal-$(command)-`command`#value',
        'TESLA_CLIENT_ID': 'client',
    }


@pytest.fixture
def configured(monkeypatch, tmp_path):
    (tmp_path/'.env').write_text("APP_URL=https://talk.example.com\nTESLA_CLIENT_ID='client'\nTESLA_CLIENT_SECRET='private-secret'\n")
    monkeypatch.setattr(registration, 'ROOT', tmp_path)
    monkeypatch.setattr(registration, 'check_public_key', lambda origin: None)
    return tmp_path


def test_preflight_never_requests_a_token_or_registration(configured, monkeypatch, capsys):
    def unexpected(*args, **kwargs):
        pytest.fail('Preflight must not request partner credentials or register the domain')
    monkeypatch.setattr(registration, 'urlopen', unexpected)
    registration.main(['--check'])
    output = capsys.readouterr().out
    assert 'No registration request was sent' in output
    assert 'private-secret' not in output


def test_registration_uses_configured_region_and_keeps_secrets_private(configured, monkeypatch, capsys):
    calls = []
    def response(request, timeout):
        calls.append(request)
        result = io.BytesIO(json.dumps({'access_token': 'private-token'}).encode())
        result.status = 200
        return result
    monkeypatch.setattr(registration, 'urlopen', response)
    registration.main([])
    assert len(calls) == 2
    assert calls[0].full_url == 'https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token'
    assert parse_qs(calls[0].data.decode())['client_secret'] == ['private-secret']
    assert calls[1].full_url == registration.REGIONS[0]+'/api/1/partner_accounts'
    assert json.loads(calls[1].data) == {'domain': 'talk.example.com'}
    assert calls[1].get_header('Authorization') == 'Bearer private-token'
    output = capsys.readouterr().out
    assert 'registration completed' in output
    assert 'private-secret' not in output and 'private-token' not in output


def test_http_failure_names_phase_without_printing_response_body(configured, monkeypatch):
    def failure(request, timeout):
        raise HTTPError(request.full_url, 401, 'private-secret', {}, io.BytesIO(b'private-token'))
    monkeypatch.setattr(registration, 'urlopen', failure)
    with pytest.raises(SystemExit) as error:
        registration.main([])
    assert str(error.value) == 'partner-token request failed (HTTP 401). Check Tesla client ID and secret.'


@pytest.mark.parametrize('url', ['http://talk.example.com', 'https://talk.example.com/path', 'https://user:secret@talk.example.com', 'https://talk.example.com?query=1'])
def test_invalid_origin_never_sends_credentials(configured, monkeypatch, url):
    with (configured/'.env').open('a') as file:
        file.write('APP_URL='+url+'\n')
    monkeypatch.setattr(registration, 'urlopen', lambda *a, **kw: pytest.fail('Invalid origin must fail before network access'))
    with pytest.raises(SystemExit, match='HTTPS APP_URL'):
        registration.main([])


def test_hosted_key_must_match_local_key(monkeypatch, tmp_path):
    keys = tmp_path/'deploy/keys'
    keys.mkdir(parents=True)
    (keys/'tesla-public-key.pem').write_bytes(b'local')
    monkeypatch.setattr(registration, 'ROOT', tmp_path)
    monkeypatch.setattr(registration, 'urlopen', lambda *a, **kw: io.BytesIO(b'-----BEGIN PUBLIC KEY-----\nhosted'))
    monkeypatch.setattr(registration, 'public_der', lambda pem: pem)
    with pytest.raises(ValueError, match='differs'):
        registration.check_public_key('https://talk.example.com')
