"""Administrator authorization from an Authlib-verified OIDC identity."""
from collections.abc import Mapping
from .config import settings


def claim_value(claims, path):
    if path in claims:
        return claims[path]
    value = claims
    for component in path.split('.'):
        if not isinstance(value, Mapping) or component not in value:
            return None
        value = value[component]
    return value


async def admin_claims(client, token):
    # Authlib validates the ID token during authorize_access_token.
    identity = token.get('userinfo')
    if not token.get('id_token') or not isinstance(identity, Mapping) or not isinstance(identity.get('sub'), str) or not identity['sub']:
        raise ValueError('Missing verified OIDC subject')
    claims = dict(identity)
    metadata = await client.load_server_metadata()
    if metadata.get('userinfo_endpoint') and token.get('access_token'):
        profile = await client.userinfo(token=token)
        # OIDC requires UserInfo to describe the same subject as the ID token.
        if not isinstance(profile, Mapping) or profile.get('sub') != claims['sub']:
            raise ValueError('OIDC UserInfo subject mismatch')
        claims.update(profile)
    return claims


def admin_access(claims):
    raw_groups = claim_value(claims, settings.oidc_groups_claim)
    groups = [raw_groups] if isinstance(raw_groups, str) else raw_groups if isinstance(raw_groups, list) else []
    groups = [group for group in groups if isinstance(group, str)]
    group_allowed = bool(settings.admin_group and settings.admin_group in groups)
    email = claims.get('email', '')
    email_listed = isinstance(email, str) and email.strip().lower() in settings.admin_emails
    email_verified = claims.get('email_verified') is True
    # Diagnostic metadata only: never include tokens, subjects, emails or group lists.
    diagnostic = {
        'expected_group': settings.admin_group,
        'groups_claim': settings.oidc_groups_claim,
        'groups_present': raw_groups is not None,
        'group_count': len(groups),
        'email_verified': email_verified,
        'email_allowlisted': email_listed,
        'claim_names': sorted(str(key) for key in claims),
    }
    return group_allowed or (email_listed and email_verified), diagnostic
