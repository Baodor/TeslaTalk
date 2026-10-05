"""Administrator authorization from an Authlib-verified OIDC identity."""
from collections.abc import Mapping
from .config import settings


class IdentityVerificationError(ValueError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


class OIDCUpstreamError(Exception):
    def __init__(self, stage, cause):
        self.stage, self.cause = stage, cause
        super().__init__(stage)


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
        raise IdentityVerificationError('missing_verified_subject')
    claims = dict(identity)
    # A verified ID token can already prove the configured administrator policy.
    # Only depend on UserInfo when the required claims are still missing.
    if admin_access(claims)[0]:
        return claims
    try:
        metadata = await client.load_server_metadata()
    except Exception as error:
        raise OIDCUpstreamError('discovery', error) from None
    if metadata.get('userinfo_endpoint') and token.get('access_token'):
        try:
            profile = await client.userinfo(token=token)
        except Exception as error:
            raise OIDCUpstreamError('userinfo', error) from None
        # OIDC requires UserInfo to describe the same subject as the ID token.
        if not isinstance(profile, Mapping) or profile.get('sub') != claims['sub']:
            raise IdentityVerificationError('subject_mismatch')
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


def admin_denial(diagnostic):
    prefix = 'Keine Administrator-Berechtigung. '
    if not diagnostic['groups_present']:
        return prefix + f"Der Gruppen-Claim {settings.oidc_groups_claim!r} fehlt. Für Pocket ID OIDC_SCOPES=openid email profile groups setzen, den Container neu erstellen und erneut anmelden."
    if not diagnostic['group_count']:
        return prefix + 'Der Gruppen-Claim enthält keine verwertbaren Gruppen. Prüfe die Mitgliedschaft deines Benutzers in Pocket ID.'
    return prefix + f"Die Anmeldung bestätigt keine Mitgliedschaft in der freigegebenen Gruppe {settings.admin_group!r}. In Pocket ID zählt der tatsächliche Gruppenname, nicht der Anzeigename oder die Client-Freigabe."


def verification_failure(error, stage):
    if isinstance(error, OIDCUpstreamError):
        stage, error = error.stage, error.cause
    # Never expose exception messages, callback URLs, tokens or provider responses.
    diagnostic = {'stage':stage, 'error_type':type(error).__name__, 'token_auth_method':settings.oidc_token_auth_method}
    messages = {
        'mismatching_state':'Die Anmeldesitzung fehlt oder ist abgelaufen. Starte die Anmeldung erneut über /auth/admin und erlaube Website-Cookies.',
        'invalid_client':'Der OIDC-Anbieter lehnt die Client-Anmeldung ab. Client-ID, Client-Secret und OIDC_TOKEN_AUTH_METHOD prüfen; für Pocket ID client_secret_post verwenden.',
        'invalid_grant':'Der Anmeldecode ist ungültig oder bereits verwendet. Neu anmelden und die Redirect-URI im OIDC-Client prüfen.',
        'invalid_scope':'Der OIDC-Anbieter erlaubt die angeforderten Scopes nicht. OIDC_SCOPES und Client-Freigaben prüfen.',
        'access_denied':'Der OIDC-Anbieter hat die Anmeldung abgelehnt. Benutzer- und Client-Freigaben prüfen.',
        'expired_token':'Der ID-Token ist abgelaufen. Serverzeit und Zeitsynchronisation prüfen und neu anmelden.',
        'bad_signature':'Die Signatur des ID-Tokens konnte nicht geprüft werden. Issuer und Signaturschlüssel des OIDC-Anbieters prüfen.',
        'invalid_claim':'Ein ID-Token-Claim ist ungültig. Issuer, Client-ID, Serverzeit und eine frische Anmeldung prüfen.',
        'missing_claim':'Im ID-Token fehlt eine Pflichtangabe. OIDC-Anwendung und angeforderte Scopes prüfen.',
    }
    code = getattr(error, 'error', None)
    if isinstance(code, str) and code in messages:
        diagnostic['error_code'] = code
        message = messages[code]
    elif isinstance(error, IdentityVerificationError):
        diagnostic['reason'] = error.reason
        message = 'ID-Token und UserInfo bestätigen unterschiedliche Benutzer.' if error.reason == 'subject_mismatch' else 'Der Anbieter hat keine verifizierte OIDC-Identität geliefert. Den openid-Scope und die OIDC-Anwendung prüfen.'
    else:
        message = f'OIDC-Anmeldung konnte im Schritt {stage} nicht verifiziert werden. Die Serverdiagnose nennt die Fehlerklasse.'
    claim = getattr(error, 'claim_name', None)
    if isinstance(claim, str) and claim in {'iss','aud','exp','iat','nbf','nonce','sub'}:
        diagnostic['claim'] = claim
    response = getattr(error, 'response', None)
    if response is not None and isinstance(getattr(response, 'status_code', None), int):
        diagnostic['http_status'] = response.status_code
        message = f'Der OIDC-Anbieter antwortet im Schritt {stage} mit HTTP {response.status_code}. Erreichbarkeit und Client-Konfiguration prüfen.'
    return message, diagnostic
