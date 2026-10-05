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


def test_verified_admin_token_does_not_depend_on_optional_userinfo(client,monkeypatch):
    oidc_client(monkeypatch,{'sub':'operator','groups':['admin']}, {'sub':'operator'})
    async def unavailable(**kwargs):
        raise RuntimeError('Optional upstream is unavailable')
    monkeypatch.setattr(main.oauth.admin,'userinfo',unavailable)
    assert client.get('/auth/admin/callback',follow_redirects=False).status_code==303


@pytest.mark.parametrize('code',['mismatching_state','invalid_client','invalid_scope'])
def test_protocol_failure_diagnoses_only_safe_codes(client,monkeypatch,caplog,code):
    from authlib.integrations.base_client.errors import OAuthError
    oidc_client(monkeypatch,{'sub':'operator'})
    async def fail(request):
        raise OAuthError(error=code,description='private-token-and-provider-body')
    monkeypatch.setattr(main.oauth.admin,'authorize_access_token',fail)
    result=client.get('/auth/admin/callback')
    assert result.status_code==400
    assert code in caplog.text and 'token_exchange_and_validation' in caplog.text
    assert 'private-token-and-provider-body' not in caplog.text+result.text
    assert client.get('/api/admin').status_code==401


def test_userinfo_failure_reports_stage_and_http_status_without_response_body(client,monkeypatch,caplog):
    import httpx
    oidc_client(monkeypatch,{'sub':'operator'}, {'sub':'operator'})
    async def fail(**kwargs):
        response=httpx.Response(403,text='private-profile',request=httpx.Request('GET','https://idp.example/userinfo?secret=private-token'))
        response.raise_for_status()
    monkeypatch.setattr(main.oauth.admin,'userinfo',fail)
    result=client.get('/auth/admin/callback')
    assert result.status_code==400 and 'userinfo' in result.text and 'HTTP 403' in result.text
    assert 'HTTPStatusError' in caplog.text
    for private in ('private-profile','private-token','idp.example/userinfo'):
        assert private not in caplog.text+result.text


@pytest.mark.parametrize('bad_nonce',[False,True])
def test_real_authlib_oidc_flow_validates_nonce_and_uses_own_cookie(client,monkeypatch,bad_nonce):
    import base64,hashlib,json,time
    from urllib.parse import parse_qs,urlsplit
    import httpx,jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from authlib.integrations.starlette_client import OAuth
    issuer='https://idp.example'; client_id='teslatalk-client'; pending={}
    private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    jwk=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key())); jwk['kid']='test-key'
    def provider(request):
        if request.url.path=='/.well-known/openid-configuration':
            return httpx.Response(200,json={'issuer':issuer,'authorization_endpoint':issuer+'/authorize','token_endpoint':issuer+'/token','jwks_uri':issuer+'/jwks','userinfo_endpoint':issuer+'/userinfo','id_token_signing_alg_values_supported':['RS256']})
        if request.url.path=='/token':
            data=parse_qs(request.content.decode())
            challenge=base64.urlsafe_b64encode(hashlib.sha256(data['code_verifier'][0].encode()).digest()).decode().rstrip('=')
            assert challenge==pending['code_challenge'][0]
            assert data['redirect_uri']==['http://testserver/auth/admin/callback']
            now=int(time.time())
            token=jwt.encode({'iss':issuer,'aud':client_id,'sub':'operator','iat':now,'exp':now+300,'nonce':'wrong' if bad_nonce else pending['nonce'][0],'groups':['admin']},private,algorithm='RS256',headers={'kid':'test-key'})
            return httpx.Response(200,json={'access_token':'isolated-test-token','token_type':'Bearer','id_token':token})
        if request.url.path=='/jwks':
            return httpx.Response(200,json={'keys':[jwk]})
        raise AssertionError('No redundant UserInfo call expected')
    oauth=OAuth()
    oauth.register('admin',client_id=client_id,client_secret='isolated-client-secret',server_metadata_url=issuer+'/.well-known/openid-configuration',client_kwargs={'scope':'openid email profile groups','code_challenge_method':'S256','transport':httpx.MockTransport(provider)})
    monkeypatch.setattr(main,'oauth',oauth)
    monkeypatch.setattr(settings,'oidc_issuer',issuer); monkeypatch.setattr(settings,'oidc_client_id',client_id)
    monkeypatch.setattr(settings,'admin_group','admin'); monkeypatch.setattr(settings,'admin_emails',set())
    client.cookies.set('session','unrelated-application-cookie')
    login=client.get('/auth/admin',follow_redirects=False)
    assert login.status_code==302 and client.cookies.get('tt_oidc')
    pending.update(parse_qs(urlsplit(login.headers['location']).query))
    result=client.get('/auth/admin/callback',params={'code':'test-code','state':pending['state'][0]},follow_redirects=False)
    assert result.status_code==(400 if bad_nonce else 303),result.text
    assert client.get('/api/admin').status_code==(401 if bad_nonce else 200)
