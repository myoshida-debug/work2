from __future__ import annotations

from ipaddress import ip_address, ip_network

from django.conf import settings
from django.http import HttpResponseForbidden


DEFAULT_NETWORK_POLICY = {
    'close_side': {
        'label': 'CloseSide',
        'paths': ['/close/'],
        'cidrs': ['192.168.50.0/24'],
    },
    'open_side': {
        'label': 'OpenSide',
        'paths': ['/open/'],
        'cidrs': ['192.168.110.0/24'],
    },
    'dmz': {
        'label': 'DMZ',
        'paths': [],
        'cidrs': ['192.168.150.0/24'],
    },
}

LOOPBACK_CIDRS = ['127.0.0.0/8', '::1/128']


def network_policy() -> dict:
    return getattr(settings, 'NETWORK_POLICY', DEFAULT_NETWORK_POLICY)


def get_client_ip(request) -> str:
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if getattr(settings, 'NETWORK_POLICY_TRUST_X_FORWARDED_FOR', True) and forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or ''


def normalize_ip(value: str):
    try:
        return ip_address(value)
    except ValueError:
        return None


def _networks(cidrs: list[str]):
    networks = []
    for cidr in cidrs:
        try:
            networks.append(ip_network(cidr))
        except ValueError:
            continue
    return networks


def side_for_path(path: str) -> str:
    for side, rule in network_policy().items():
        if any(path.startswith(prefix) for prefix in rule.get('paths', [])):
            return side
    return ''


def allowed_cidrs_for_side(side: str) -> list[str]:
    rule = network_policy().get(side, {})
    cidrs = list(rule.get('cidrs', []))
    if getattr(settings, 'NETWORK_POLICY_ALLOW_LOOPBACK', False):
        cidrs.extend(LOOPBACK_CIDRS)
    return cidrs


def is_client_allowed_for_side(client_ip: str, side: str) -> bool:
    parsed = normalize_ip(client_ip)
    if parsed is None:
        return False
    return any(parsed in network for network in _networks(allowed_cidrs_for_side(side)))


class NetworkSegmentPolicyMiddleware:
    """Restrict CloseSide/OpenSide URLs to their configured network segments."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        side = side_for_path(request.path_info)
        if not side or not getattr(settings, 'NETWORK_POLICY_ENFORCED', True):
            return self.get_response(request)

        client_ip = get_client_ip(request)
        if is_client_allowed_for_side(client_ip, side):
            request.network_segment = side
            request.client_ip = client_ip
            return self.get_response(request)

        self._log_denied_request(request, side, client_ip)
        label = network_policy().get(side, {}).get('label', side)
        return HttpResponseForbidden(f'{label} へのアクセス元ネットワークが許可されていません。')

    def _log_denied_request(self, request, side: str, client_ip: str) -> None:
        from .models import OperationLog

        user = getattr(request, 'user', None)
        parsed_ip = normalize_ip(client_ip)
        OperationLog.objects.create(
            actor=user if getattr(user, 'is_authenticated', False) else None,
            actor_username=user.get_username() if getattr(user, 'is_authenticated', False) else '',
            action='network_policy_denied',
            target_type='NetworkPolicy',
            target_id=side,
            source_ip=str(parsed_ip) if parsed_ip else None,
            result='failure',
            error_message=f'{client_ip} is not allowed for {side}',
            details={
                'path': request.path,
                'allowed_cidrs': allowed_cidrs_for_side(side),
            },
        )
