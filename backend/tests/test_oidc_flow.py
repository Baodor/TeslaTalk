"""Exercise the real Authlib code flow and signed tokens, not only callback mocks."""
import time
from urllib.parse import parse_qs, urlsplit
import httpx
import jwt
from authlib.integrations.starlette_client import OAuth
from cryptography.hazmat.primitives.asymmetric import rsa
from app import main
from app.config import settings


def test_pocket_id_post_client_auth_pkce_and_verified_userinfo(client, monkeypatch):
    issuer = 'https://idp.example.com'
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key = jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key(), as_dict=True)
    key.update(kid='test-signing-key', use='sig', alg='RS256')
    state = {}
    requests = []

    def provider(request):
        requests.append(request.url.path)
        if request.url.path == '/.well-known/openid-configuration':
            return httpx.Response(200, json={'issuer': issuer, 'authorization_endpoint': issuer + '/authorize',
                'token_endpoint': issuer + '/token', 'userinfo_endpoint': issuer + '/userinfo',
                'jwks_uri': issuer + '/jwks', 'id_token_signing_alg_values_supported': ['RS256'],
                'token_endpoint_auth_methods_supported': ['client_secret_post']})
        if request.url.path == '/token':
            body = parse_qs(request.content.decode())
            assert body['client_id'] == ['test-client'] and body['client_secret'] == ['test-client-secret']
            assert 'authorization' not in request.headers
            import hashlib, base64
            challenge = base64.urlsafe_b64encode(hashlib.sha256(body['code_verifier'][0].encode()).digest()).decode().rstrip('=')
            assert challenge == state['code_challenge'][0]
            token = jwt.encode({'iss': issuer, 'sub': 'operator', 'aud': 'test-client', 'nonce': state['nonce'][0],
                'iat': int(time.time()), 'exp': int(time.time()) + 300}, private, algorithm='RS256', headers={'kid': 'test-signing-key'})
            return httpx.Response(200, json={'access_token': 'private-test-access-token', 'token_type': 'Bearer', 'expires_in': 300, 'id_token': token})
        if request.url.path == '/jwks':
            return httpx.Response(200, json={'keys': [key]})
        if request.url.path == '/userinfo':
            assert request.headers['authorization'] == 'Bearer private-test-access-token'
            return httpx.Response(200, json={'sub': 'operator', 'groups': ['admin']})
        raise AssertionError(request.url.path)

    registry = OAuth()
    registry.register('admin', client_id='test-client', client_secret='test-client-secret',
        server_metadata_url=issuer + '/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile groups', 'code_challenge_method': 'S256',
                       'token_endpoint_auth_method': 'client_secret_post', 'transport': httpx.MockTransport(provider)})
    monkeypatch.setattr(main, 'oauth', registry)
    monkeypatch.setattr(settings, 'oidc_issuer', issuer)
    monkeypatch.setattr(settings, 'oidc_client_id', 'test-client')
    monkeypatch.setattr(settings, 'admin_group', 'admin')
    monkeypatch.setattr(settings, 'admin_emails', set())
    response = client.get('/auth/admin', follow_redirects=False)
    assert response.status_code == 302
    state.update(parse_qs(urlsplit(response.headers['location']).query))
    assert state['code_challenge_method'] == ['S256'] and 'groups' in state['scope'][0].split()
    callback = client.get('/auth/admin/callback', params={'code': 'test-code', 'state': state['state'][0]}, follow_redirects=False)
    assert callback.status_code == 303, callback.text
    assert client.get('/api/admin').status_code == 200
    assert '/userinfo' in requests
