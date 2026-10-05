from types import SimpleNamespace
import pytest
from app.config import Settings, settings
from app import main


def oidc_client(monkeypatch, identity, profile=None, *, has_id_token=True):
    class Client:
        async def authorize_access_token(self, request):
            # Stand-in for Authlib's already validated ID token and parsed identity.
            token = {'userinfo': identity, 'access_token': 'private-access-token'}
            if has_id_token:
                token['id_token'] = 'verified-id-token'
            return token

        async def load_server_metadata(self):
            return {'userinfo_endpoint': 'https://idp.example.com/userinfo'} if profile is not None else {}

        async def userinfo(self, *, token):
            assert token['access_token'] == 'private-access-token'
            return profile

    monkeypatch.setattr(main, 'oauth', SimpleNamespace(admin=Client()))
    monkeypatch.setattr(settings, 'admin_group', 'admin')
    monkeypatch.setattr(settings, 'admin_emails', set())
    monkeypatch.setattr(settings, 'oidc_groups_claim', 'groups')


@pytest.mark.parametrize('groups', [['admin'], 'admin'])
def test_admin_matching_group_creates_admin_session(client, monkeypatch, groups):
    oidc_client(monkeypatch, {'sub': 'operator', 'groups': groups})
    response = client.get('/auth/admin/callback', follow_redirects=False)
    assert response.status_code == 303
    assert response.headers['location'] == '/admin'
    assert client.get('/api/admin').status_code == 200
    assert client.get('/api/me').status_code == 401


def test_admin_groups_available_only_from_userinfo(client, monkeypatch):
    oidc_client(monkeypatch, {'sub': 'operator'}, {'sub': 'operator', 'groups': ['admin']})
    assert client.get('/auth/admin/callback', follow_redirects=False).status_code == 303


def test_userinfo_cannot_authorize_another_subject(client, monkeypatch):
    oidc_client(monkeypatch, {'sub': 'operator'}, {'sub': 'another-user', 'groups': ['admin']})
    assert client.get('/auth/admin/callback').status_code == 400
    assert client.get('/api/admin').status_code == 401


@pytest.mark.parametrize('identity', [None, {}, {'sub': ''}, {'sub': 123}])
def test_missing_verified_identity_is_denied(client, monkeypatch, identity):
    oidc_client(monkeypatch, identity, {'sub': 'operator', 'groups': ['admin']})
    assert client.get('/auth/admin/callback').status_code == 400
    assert client.get('/api/admin').status_code == 401


def test_token_response_cannot_supply_identity_without_id_token(client, monkeypatch):
    oidc_client(monkeypatch, {'sub': 'operator', 'groups': ['admin']}, has_id_token=False)
    assert client.get('/auth/admin/callback').status_code == 400
    assert client.get('/api/admin').status_code == 401


def test_nested_role_claim_is_explicitly_configured(client, monkeypatch):
    oidc_client(monkeypatch, {'sub': 'operator', 'realm_access': {'roles': ['admin']}})
    assert client.get('/auth/admin/callback').status_code == 403
    monkeypatch.setattr(settings, 'oidc_groups_claim', 'realm_access.roles')
    assert client.get('/auth/admin/callback', follow_redirects=False).status_code == 303


@pytest.mark.parametrize('groups', [None, [], ['user'], {'admin': True}, ['Admin'], [True, 1]])
def test_missing_or_wrong_groups_remain_denied(client, monkeypatch, groups):
    oidc_client(monkeypatch, {'sub': 'operator', 'groups': groups})
    assert client.get('/auth/admin/callback').status_code == 403
    assert client.get('/api/admin').status_code == 401


@pytest.mark.parametrize('verified, allowed', [(True, True), (False, False), ('true', False)])
def test_email_allowlist_requires_verified_email(client, monkeypatch, verified, allowed):
    oidc_client(monkeypatch, {'sub': 'operator', 'email': 'OWNER@example.com', 'email_verified': verified})
    monkeypatch.setattr(settings, 'admin_emails', {'owner@example.com'})
    response = client.get('/auth/admin/callback', follow_redirects=False)
    assert response.status_code == (303 if allowed else 403)


def test_denial_diagnostics_exclude_profile_values_and_tokens(client, monkeypatch, caplog):
    oidc_client(monkeypatch, {'sub': 'private-subject', 'groups': ['private-group'], 'email': 'private@example.com'})
    assert client.get('/auth/admin/callback').status_code == 403
    assert '"expected_group": "admin"' in caplog.text
    assert '"group_count": 1' in caplog.text
    for value in ('private-subject', 'private-group', 'private@example.com', 'private-access-token'):
        assert value not in caplog.text


def test_oidc_settings_allow_group_scope_and_trim_admin_group(monkeypatch):
    monkeypatch.setenv('OIDC_SCOPES', 'email profile groups')
    monkeypatch.setenv('ADMIN_GROUP', ' admin ')
    configured = Settings()
    assert configured.oidc_scopes == 'openid email profile groups'
    assert configured.admin_group == 'admin'


@pytest.mark.parametrize('groups,expected',[(None,'Gruppen-Claim'),([], 'keine verwertbaren Gruppen'),(['member'],'tatsächliche Gruppenname')])
def test_admin_denial_explains_configuration_without_revealing_groups(client,monkeypatch,groups,expected):
    oidc_client(monkeypatch,{'sub':'private-user','groups':groups})
    result=client.get('/auth/admin/callback')
    assert result.status_code==403
    assert expected in result.json()['detail']
    assert 'private-user' not in result.text
    assert 'member' not in result.text
