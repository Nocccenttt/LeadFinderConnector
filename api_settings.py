"""Local credential settings and bounded, explicit provider authentication checks."""
import os
import re
import tempfile
from pathlib import Path
from threading import Lock

import requests

PROVIDERS = {
    'deepseek': ('DEEPSEEK_API_KEY', 'DeepSeek'),
    'google': ('GOOGLE_MAPS_API_KEY', 'Google Maps'),
    'pexels': ('PEXELS_API_KEY', 'Pexels'),
}
settings_lock = Lock()


def key_status():
    return {provider: {'configured': bool(os.getenv(name)),
                       'ending': os.getenv(name, '')[-4:] if len(os.getenv(name, '')) >= 8 else ''}
            for provider, (name, _) in PROVIDERS.items()}


def validate_key(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError('Enter an API key as text.')
    value = value.strip()
    if value and (len(value) > 1024 or not value.isascii() or re.search(r'''[\s"'\\$*]''', value)):
        raise ValueError('Paste the full API key only, without quotes, spaces or masking characters.')
    return value


def save_keys(path, replacements):
    if not isinstance(replacements, dict) or not replacements or any(key not in PROVIDERS for key in replacements):
        raise ValueError('Choose a supported API key to update.')
    changes = {PROVIDERS[provider][0]: validate_key(value) for provider, value in replacements.items()}
    changes = {name: value for name, value in changes.items() if value != ''}
    if not changes:
        raise ValueError('Enter a replacement key, or choose Remove saved key.')
    path = Path(path)
    with settings_lock:
        text = path.read_text(encoding='utf-8-sig') if path.exists() else ''
        lines, written = [], set()
        for line in text.splitlines():
            match = re.match(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z_0-9]*)\s*=', line)
            name = match[1] if match else None
            if name in changes:
                if name not in written:
                    lines.append(f"{name}='{changes[name] or ''}'")
                    written.add(name)
            else:
                lines.append(line)
        for name, value in changes.items():
            if name not in written:
                lines.append(f"{name}='{value or ''}'")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                             prefix='.api-settings-', delete=False) as handle:
                temporary = Path(handle.name)
                handle.write('\n'.join(lines) + '\n')
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()
        # New searches/builds read these values directly; no app restart is needed.
        for name, value in changes.items():
            os.environ[name] = value or ''
    return key_status()


def test_key(provider, value=None):
    if not isinstance(provider, str) or provider not in PROVIDERS:
        raise ValueError('Choose a supported API provider.')
    name, label = PROVIDERS[provider]
    candidate = validate_key(value)
    key = candidate or os.getenv(name, '')
    if not key:
        return {'ok': False, 'code': 'missing_key', 'message': f'Enter a {label} key first.'}
    options = {'timeout': (5, 10), 'allow_redirects': False}
    if provider == 'deepseek':
        method, url = 'GET', 'https://api.deepseek.com/models'
        options['headers'] = {'Authorization': f'Bearer {key}'}
    elif provider == 'google':
        method, url = 'POST', 'https://places.googleapis.com/v1/places:searchText'
        options['headers'] = {'X-Goog-Api-Key': key, 'X-Goog-FieldMask': 'places.id'}
        options['json'] = {'textQuery': 'cafe', 'pageSize': 1}
    else:
        method, url = 'GET', 'https://api.pexels.com/v1/search'
        options['headers'] = {'Authorization': key}
        options['params'] = {'query': 'nature', 'per_page': 1}
    try:
        response = requests.request(method, url, **options)
    except requests.RequestException:
        return {'ok': False, 'code': 'connection_error', 'message': f'Could not reach {label}. Check your connection and try again.'}
    if response.status_code == 200:
        try:
            data = response.json()
            valid = isinstance(data, dict)
            if valid and provider == 'google':
                valid = 'error' not in data
            elif valid:
                valid = isinstance(data.get({'deepseek': 'data', 'pexels': 'photos'}[provider]), list)
        except ValueError:
            valid = False
        if valid:
            next_step = 'Save it to use it in LeadFinder.' if candidate else 'Your saved key is ready for new requests.'
            return {'ok': True, 'code': 'authenticated', 'message': f'{label} accepted this key. {next_step}'}
        return {'ok': False, 'code': 'unexpected_response', 'message': f'{label} returned an unexpected response. Try again.'}
    if response.status_code == 401:
        message = f'{label} rejected this key (401). Create or copy a valid key from your {label} account and test it again.'
        code = 'authentication_error'
    elif response.status_code in (400, 403):
        message = f'{label} denied this request ({response.status_code}). Check the key, API permissions, account billing and any key restrictions.'
        code = 'access_denied'
    elif response.status_code == 402:
        message, code = f'{label} requires available account credit (402). Check the account balance.', 'billing_error'
    elif response.status_code == 429:
        message, code = f'{label} is rate-limiting requests (429). Wait and try again.', 'rate_limited'
    else:
        message, code = f'{label} could not complete the check ({response.status_code}). Try again later.', 'provider_error'
    return {'ok': False, 'code': code, 'message': message}


def safe_job_error(error, provider):
    response = getattr(error, 'response', None)
    status = getattr(error, 'status_code', None) or (getattr(response, 'status_code', None) if response is not None else None)
    if status == 401:
        return f'{PROVIDERS[provider][1]} rejected the API key (401). Open API keys, replace and test the key, then retry this task.'
    message = str(error)
    for name, _ in PROVIDERS.values():
        key = os.getenv(name, '')
        if key:
            message = message.replace(key, '[redacted]')
    return message
