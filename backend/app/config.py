import os
from urllib.parse import urlsplit
from dataclasses import dataclass, field


@dataclass
class Settings:
    app_url: str = field(default_factory=lambda: os.getenv('APP_URL', 'http://localhost:8780').rstrip('/'))
    secret: str = field(default_factory=lambda: os.getenv('APP_SECRET', ''))
    db_path: str = field(default_factory=lambda: os.getenv('DB_PATH', '/data/teslatalk.sqlite'))
    demo: bool = field(default_factory=lambda: os.getenv('DEMO_MODE', 'false').lower() == 'true')
    tesla_client_id: str = field(default_factory=lambda: os.getenv('TESLA_CLIENT_ID', ''))
    tesla_client_secret: str = field(default_factory=lambda: os.getenv('TESLA_CLIENT_SECRET', ''))
    fleet_url: str = field(default_factory=lambda: os.getenv('TESLA_FLEET_URL', 'https://fleet-api.prd.eu.vn.cloud.tesla.com').rstrip('/'))
    navigation_commands: bool = field(default_factory=lambda: os.getenv('TESLA_NAVIGATION_COMMANDS', 'false').lower() == 'true')
    group_controls: bool = field(default_factory=lambda: os.getenv('TESLA_GROUP_CONTROLS', 'false').lower() == 'true')
    command_proxy_url: str = field(default_factory=lambda: os.getenv('TESLA_COMMAND_PROXY_URL', '').rstrip('/'))
    command_proxy_ca: str = field(default_factory=lambda: os.getenv('TESLA_COMMAND_PROXY_CA', ''))
    livekit_url: str = field(default_factory=lambda: os.getenv('LIVEKIT_URL', 'ws://localhost:7880'))
    livekit_internal_url: str = field(default_factory=lambda: os.getenv('LIVEKIT_INTERNAL_URL', 'http://livekit:7880'))
    livekit_key: str = field(default_factory=lambda: os.getenv('LIVEKIT_API_KEY', ''))
    livekit_secret: str = field(default_factory=lambda: os.getenv('LIVEKIT_API_SECRET', ''))
    poll_interval: int = field(default_factory=lambda: max(60, int(os.getenv('FLEET_POLL_INTERVAL', '120'))))
    oidc_issuer: str = field(default_factory=lambda: os.getenv('OIDC_ISSUER', '').rstrip('/'))
    oidc_client_id: str = field(default_factory=lambda: os.getenv('OIDC_CLIENT_ID', ''))
    oidc_client_secret: str = field(default_factory=lambda: os.getenv('OIDC_CLIENT_SECRET', ''))
    oidc_token_auth_method: str = field(default_factory=lambda: os.getenv('OIDC_TOKEN_AUTH_METHOD', 'client_secret_basic').strip() or 'client_secret_basic')
    oidc_scopes: str = field(default_factory=lambda: ' '.join(dict.fromkeys(['openid', *os.getenv('OIDC_SCOPES', 'openid email profile').split()])))
    oidc_groups_claim: str = field(default_factory=lambda: os.getenv('OIDC_GROUPS_CLAIM', 'groups').strip() or 'groups')
    admin_emails: set = field(default_factory=lambda: {x.strip().lower() for x in os.getenv('ADMIN_EMAILS', '').split(',') if x.strip()})
    admin_group: str = field(default_factory=lambda: os.getenv('ADMIN_GROUP', 'teslatalk-admin').strip())
    frontend_dir: str = field(default_factory=lambda: os.getenv('FRONTEND_DIR', '/app/frontend'))
    timezone: str = field(default_factory=lambda: os.getenv('APP_TIMEZONE', 'Europe/Berlin'))
    public_key_path: str = field(default_factory=lambda: os.getenv('TESLA_PUBLIC_KEY_PATH', '/app/keys/tesla-public-key.pem'))
    vapid_private_key: str = field(default_factory=lambda: os.getenv('VAPID_PRIVATE_KEY', ''))
    vapid_public_key: str = field(default_factory=lambda: os.getenv('VAPID_PUBLIC_KEY', ''))
    vapid_subject: str = field(default_factory=lambda: os.getenv('VAPID_SUBJECT', 'mailto:admin@example.com'))

    @property
    def group_controls_ready(self):
        try:
            url = urlsplit(self.command_proxy_url)
            return bool(self.group_controls and url.scheme == 'https' and url.hostname and
                        not url.username and not url.password and not url.query and not url.fragment and not url.path)
        except ValueError:
            return False

    @property
    def tesla_ready(self):
        return bool(self.tesla_client_id and self.tesla_client_secret)

    @property
    def voice_ready(self):
        return bool(self.livekit_key and len(self.livekit_secret) >= 32)

    @property
    def push_ready(self):
        return bool(self.vapid_private_key and self.vapid_public_key)

    @property
    def secure(self):
        return self.app_url.startswith('https://')


settings = Settings()
