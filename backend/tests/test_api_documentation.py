import json
from fastapi.routing import APIWebSocketRoute
from app.main import app
from app.api_documentation import DETAILS, documented_routes


def test_documentation_requires_authentication(client):
    assert client.get('/api/docs').status_code == 401
    assert client.get('/api/openapi.json').status_code == 401


def test_catalog_documents_every_registered_api_auth_and_websocket_endpoint(owner):
    result = owner.get('/api/docs')
    assert result.status_code == 200,result.text
    catalog = result.json()
    expected = set()
    for route in documented_routes(app):
        assert route.endpoint.__name__ in DETAILS,route.path
        for method in ['WEBSOCKET'] if isinstance(route,APIWebSocketRoute) else route.methods:
            expected.add((method,route.path))
    actual = {(endpoint['method'],endpoint['path']) for endpoint in catalog['endpoints']}
    assert actual == expected
    assert len(actual) == len(catalog['endpoints'])
    assert all(endpoint['access'] and endpoint['description'] and endpoint['returns'] for endpoint in catalog['endpoints'])
    assert ('GET','/auth/admin/callback') in actual
    assert ('GET','/api/docs') in actual
    assert ('WEBSOCKET','/api/ws/trips/{trip_id}') in actual
    assert 'NavigationTelemetry' in catalog['openapi']['components']['schemas']
    assert 'Navigation' in catalog['openapi']['components']['schemas']


def test_openapi_describes_real_authentication_and_navigation_contracts(owner):
    schema = owner.get('/api/openapi.json').json()
    paths = schema['paths']
    assert paths['/api/me']['get']['security'] == [{'UserSession':[]},{'PersonalApiKey':[]}]
    assert paths['/api/admin']['get']['security'] == [{'AdminSession':[]}]
    assert paths['/api/admin/users']['get']['security'] == [{'AdminSession':[]}]
    assert paths['/api/guest/{key}/register']['post']['security'] == []
    assert 'AdminUser' in schema['components']['schemas']
    assert paths['/api/push/test']['post']['security'] == [{'UserSession':[]}]
    assert paths['/api/vehicles/{vehicle_id}/navigation']['put']['security'] == [{'PersonalApiKey':[]}]
    assert paths['/api/health']['get']['security'] == []
    assert '302' in paths['/auth/admin']['get']['responses']
    assert '303' in paths['/auth/tesla/callback']['get']['responses']
    assert paths['/api/vehicles/{vehicle_id}/navigation/refresh']['post']['responses']['200']['content']['application/json']['schema']['$ref'].endswith('/Navigation')
    assert owner.get('/api/docs').json()['openapi'] == schema


def test_llm_catalog_never_copies_actual_keys_or_private_account_values(owner):
    key = owner.post('/api/keys',json={'label':'SECRET_LABEL_NOT_FOR_DOCS','days':None}).json()['token']
    profile = owner.patch('/api/me',json={'username':'unique-private-account','display_name':'PRIVATE_DISPLAY_NOT_FOR_DOCS','plate':'SECRET-PLATE'}).json()
    encoded = json.dumps(owner.get('/api/docs').json())
    for private in [key,profile['id'],profile['display_name'],profile['username'],profile['plate']]:
        assert private not in encoded
    assert '<PERSONAL_API_KEY>' in encoded
    assert 'RouteLine' in encoded
