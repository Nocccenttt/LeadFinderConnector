"""Discover public business profiles without guessing handles or signing in."""
import ipaddress
import json
import re
import socket
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs, unquote, urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

USER_AGENT = 'LeadFinderSocial/1.0'
PLATFORMS = {
    'facebook.com': 'facebook', 'instagram.com': 'instagram',
    'linkedin.com': 'linkedin', 'youtube.com': 'youtube',
    'tiktok.com': 'tiktok', 'x.com': 'x', 'twitter.com': 'x',
    'pinterest.com': 'pinterest', 'threads.net': 'threads',
    'threads.com': 'threads', 'bsky.app': 'bluesky',
}
EMAIL = re.compile(r'[\w.%+\-]+@[\w.\-]+\.[A-Za-z]{2,}')
MAX_PROFILES = 12


def social_url(value, base=''):
    """Return (platform, canonical profile URL), excluding share/login/post URLs."""
    if not isinstance(value, str):
        return None
    try:
        parsed = urlparse(urljoin(base, value.strip()))
        host = (parsed.hostname or '').lower().rstrip('.')
        if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password or parsed.port not in (None, 80, 443):
            return None
        host = re.sub(r'^(www|m|mobile|mbasic|web)\.', '', host)
        if re.fullmatch(r'[a-z]{2,3}\.linkedin\.com', host):
            host = 'linkedin.com'
        if host not in PLATFORMS:
            return None
        platform = PLATFORMS[host]
        parts = [unquote(part) for part in parsed.path.split('/') if part]
        if not parts or any(not re.fullmatch(r'[\w.@\-]+', part) for part in parts):
            return None
        first = parts[0].lower()
        blocked = {'share', 'sharing', 'sharer', 'sharer.php', 'intent', 'login', 'login.php',
                   'signup', 'accounts', 'dialog', 'plugins', 'help', 'privacy', 'about',
                   'search', 'explore', 'hashtag', 'home', 'messages', 'settings',
                   'p', 'reel', 'reels', 'stories', 'watch', 'shorts', 'feed', 'groups', 'events',
                   'photo.php', 'permalink.php', 'story.php', 'share.php', 'l.php', 'marketplace',
                   'business', 'ads', 'policies', 'i', 'compose', 'notifications', 'oauth', 'tos', 'pin', 'create'}
        if first in blocked:
            return None
        query = ''
        if platform == 'facebook' and first == 'profile.php':
            identifier = parse_qs(parsed.query).get('id', [''])[0]
            if not identifier.isdigit():
                return None
            path, query = '/profile.php', 'id=' + identifier
        elif platform == 'facebook' and first == 'pages':
            if len(parts) < 3 or not parts[2].isdigit():
                return None
            path = '/' + '/'.join(parts[:3])
        elif platform == 'linkedin':
            if first not in ('company', 'showcase') or len(parts) < 2:
                return None
            path = '/' + '/'.join(parts[:2])
        elif platform == 'youtube':
            if first.startswith('@'):
                path = '/' + parts[0]
            elif first in ('channel', 'c', 'user') and len(parts) > 1:
                path = '/' + '/'.join(parts[:2])
            else:
                return None
        elif platform in ('tiktok', 'threads'):
            if not first.startswith('@') or len(first) < 2:
                return None
            path = '/' + parts[0]
        elif platform == 'bluesky':
            if first != 'profile' or len(parts) < 2:
                return None
            path = '/' + '/'.join(parts[:2])
        else:
            path = '/' + parts[0]
        if platform in ('facebook', 'instagram', 'x', 'tiktok', 'pinterest', 'threads', 'linkedin'):
            path = path.lower()
        canonical_host = {'x': 'x.com', 'threads': 'threads.com'}.get(platform, host)
        return platform, urlunparse(('https', canonical_host, path.rstrip('/'), '', query, ''))
    except (ValueError, TypeError):
        return None


def business_entities(soup):
    """Read organization structured data; never treat article/comment authors as businesses."""
    def walk(value):
        if isinstance(value, list):
            for item in value:
                yield from walk(item)
        elif isinstance(value, dict):
            types = value.get('@type', [])
            types = [types] if isinstance(types, str) else types
            types = [item.rsplit('/', 1)[-1] for item in types if isinstance(item, str)] if isinstance(types, list) else []
            if isinstance(types, list) and any(item in types for item in (
                'Organization', 'LocalBusiness', 'Corporation', 'ProfessionalService',
                'Dentist', 'MedicalBusiness', 'Restaurant', 'Store', 'HomeAndConstructionBusiness',
                'Plumber', 'RoofingContractor', 'Electrician', 'AutomotiveBusiness', 'HealthAndBeautyBusiness',
            )):
                yield value
            yield from walk(value.get('@graph', []))
            yield from walk(value.get('mainEntity', []))
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            yield from walk(json.loads(script.string or script.get_text()))
        except (ValueError, TypeError, RecursionError):
            continue


def extract_profiles(html, source_url):
    soup = BeautifulSoup(html, 'html.parser')
    candidates = [link.get('href', '') for link in soup.select('a[href]')]
    for entity in business_entities(soup):
        same_as = entity.get('sameAs', [])
        candidates.extend(same_as if isinstance(same_as, list) else [same_as])
    profiles = {}
    for value in candidates:
        normalized = social_url(value, source_url)
        if normalized:
            platform, url = normalized
            profiles.setdefault(url, {'platform': platform, 'url': url, 'source_url': source_url,
                                      'status': 'not_checked', 'details': {}})
    return list(profiles.values())


def saved_profiles(business):
    profiles = business.get('social_profiles', [])
    profiles = list(profiles) if isinstance(profiles, list) else []
    for key in ('facebook', 'instagram', 'linkedin', 'youtube', 'tiktok', 'x', 'pinterest', 'threads', 'bluesky'):
        if business.get(key):
            profiles.append({'url': business[key], 'source_url': business.get('website', '')})
    other = business.get('other_socials', '')
    if isinstance(other, str):
        profiles.extend({'url': url.strip(), 'source_url': business.get('website', '')} for url in other.split(';'))
    return merge_profiles([], profiles)


def merge_profiles(previous, discovered):
    result = {}
    for item in [*(previous if isinstance(previous, list) else []), *(discovered if isinstance(discovered, list) else [])]:
        if not isinstance(item, dict):
            continue
        normalized = social_url(item.get('url'))
        if not normalized:
            continue
        platform, url = normalized
        old = result.get(url, {})
        details = item.get('details') if isinstance(item.get('details'), dict) else {}
        result[url] = {**old, **item, 'platform': platform, 'url': url,
                       'details': {**old.get('details', {}), **details}}
        if item.get('status') == 'not_checked' and old.get('status'):
            result[url]['status'] = old['status']
    return list(result.values())[:MAX_PROFILES]


def legacy_social_fields(profiles):
    result = {'facebook': '', 'instagram': '', 'linkedin': '', 'other_socials': ''}
    others = []
    for item in merge_profiles([], profiles):
        platform = item['platform']
        if platform in ('facebook', 'instagram', 'linkedin') and not result[platform]:
            result[platform] = item['url']
        else:
            others.append(item['url'])
    result['other_socials'] = '; '.join(others)
    return result


def public_url(value, base=''):
    try:
        parsed = urlparse(urljoin(base, value))
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 80, 443):
            return ''
        if parsed.hostname.lower().rstrip('.') == 'localhost':
            return ''
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80), type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
            return ''
        return urlunparse(parsed._replace(fragment=''))
    except (ValueError, TypeError, OSError):
        return ''


class PublicCrawler:
    def __init__(self, budget_seconds=35):
        self.deadline = time.monotonic() + budget_seconds
        self.robots = {}
        self.last_request = {}

    def read(self, url, html_only=True, follow_redirects=True):
        for _ in range(4):
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                return {'status': 'not_checked', 'note': 'Scan time limit reached.', 'url': url}
            if not public_url(url):
                return {'status': 'unavailable', 'note': 'Only public web addresses can be checked.', 'url': url}
            try:
                with requests.get(url, headers={'User-Agent': USER_AGENT}, timeout=min(4, remaining),
                                  allow_redirects=False, stream=True) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        url = urljoin(url, response.headers.get('Location', ''))
                        if not follow_redirects:
                            return {'status': 'redirect', 'url': url}
                        continue
                    if response.status_code in (401, 403, 429):
                        return {'status': 'blocked', 'note': f'Public request returned HTTP {response.status_code}.', 'url': url}
                    if response.status_code >= 400:
                        return {'status': 'unavailable', 'note': f'Public request returned HTTP {response.status_code}.', 'url': url,
                                'http_status': response.status_code}
                    content_type = response.headers.get('Content-Type', '').lower()
                    if html_only and content_type and not any(kind in content_type for kind in ('text/html', 'application/xhtml+xml')):
                        return {'status': 'unavailable', 'note': 'The address did not return an HTML page.', 'url': url}
                    body = bytearray()
                    for chunk in response.iter_content(16384):
                        body.extend(chunk)
                        if len(body) > 512000 or time.monotonic() > self.deadline:
                            return {'status': 'unavailable', 'note': 'Page exceeded the scan size or time limit.', 'url': url}
                    return {'status': 'public', 'url': url, 'html': body.decode(response.encoding or 'utf-8', errors='replace')}
            except (requests.RequestException, LookupError):
                return {'status': 'unavailable', 'note': 'The public page could not be reached.', 'url': url}
        return {'status': 'unavailable', 'note': 'Too many redirects.', 'url': url}

    def get(self, url):
        if time.monotonic() >= self.deadline:
            return {'status': 'not_checked', 'note': 'Scan time limit reached.', 'url': url}
        for _ in range(4):
            result = self.get_once(url)
            if result['status'] != 'redirect':
                return result
            url = result['url']
        return {'status': 'unavailable', 'note': 'Too many redirects.', 'url': url}

    def get_once(self, url):
        parsed = urlparse(url)
        origin = f'{parsed.scheme}://{parsed.netloc}'
        if origin not in self.robots:
            response = self.read(origin + '/robots.txt', html_only=False)
            parser = RobotFileParser()
            if response.get('http_status') == 404:
                parser.parse([])
            elif response['status'] == 'public' and '<html' not in response['html'][:1000].lower():
                parser.parse(response['html'].splitlines())
            else:
                self.robots[origin] = None
                return {'status': 'unavailable', 'note': 'Crawl permissions could not be read.', 'url': url}
            self.robots[origin] = parser
        parser = self.robots[origin]
        if parser is None or not parser.can_fetch(USER_AGENT, url):
            return {'status': 'blocked', 'note': 'Automated access is not allowed by this site.', 'url': url}
        delay = max(0.5, parser.crawl_delay(USER_AGENT) or 0)
        wait = delay - (time.monotonic() - self.last_request.get(origin, 0))
        if wait > 0:
            if time.monotonic() + wait >= self.deadline:
                return {'status': 'not_checked', 'note': 'Crawl delay exceeds the remaining scan time.', 'url': url}
            time.sleep(wait)
        self.last_request[origin] = time.monotonic()
        return self.read(url, follow_redirects=False)


def profile_details(html):
    soup = BeautifulSoup(html, 'html.parser')
    def meta(*names):
        for name in names:
            tag = soup.find('meta', attrs={'property': name}) or soup.find('meta', attrs={'name': name})
            if tag and isinstance(tag.get('content'), str) and tag['content'].strip():
                return tag['content'].strip()[:1200]
        return ''
    title = meta('og:title', 'twitter:title') or (soup.title.get_text(' ', strip=True)[:240] if soup.title else '')
    if re.search(r'^(log\s?in|sign\s?in|join\s+(facebook|instagram|linkedin)|security check|just a moment)', title, re.I):
        return None
    details = {'name': title[:240], 'description': meta('og:description', 'description', 'twitter:description')}
    emails, phones = EMAIL.findall(details['description']), []
    for anchor in soup.select('a[href]'):
        href = anchor.get('href', '')
        if href.lower().startswith('mailto:'):
            address = unquote(href[7:].split('?')[0]).strip()
            if EMAIL.fullmatch(address):
                emails.append(address)
        elif href.lower().startswith('tel:'):
            phone = unquote(href[4:]).strip()
            if 6 <= len(re.sub(r'\D', '', phone)) <= 18:
                phones.append(phone)
    for entity in business_entities(soup):
        for key in ('name', 'description'):
            if isinstance(entity.get(key), str) and entity[key].strip():
                details[key] = entity[key].strip()[:1200 if key == 'description' else 240]
        email = entity.get('email', '')
        if isinstance(email, str) and EMAIL.fullmatch(email.removeprefix('mailto:')):
            emails.append(email.removeprefix('mailto:'))
        if isinstance(entity.get('telephone'), str):
            phones.append(entity['telephone'][:80])
        address = entity.get('address')
        if isinstance(address, dict):
            details['address'] = ', '.join(str(address[key])[:200] for key in (
                'streetAddress', 'addressLocality', 'addressRegion', 'postalCode', 'addressCountry')
                if isinstance(address.get(key), str))[:800]
        elif isinstance(address, str):
            details['address'] = address[:800]
    details['emails'], details['phones'] = list(dict.fromkeys(emails))[:5], list(dict.fromkeys(phones))[:5]
    return {key: value for key, value in details.items() if value}


def crawl_socials(business, *, crawl_website=True, budget_seconds=35, progress=None):
    crawler = PublicCrawler(budget_seconds)
    checked_at = datetime.now(timezone.utc).isoformat()
    profiles = saved_profiles(business)
    website = business.get('website', '')
    notes = []
    direct = social_url(website)
    if direct:
        profiles = merge_profiles(profiles, [{'platform': direct[0], 'url': direct[1], 'source_url': website,
                                              'status': 'not_checked', 'details': {}}])
    elif crawl_website and isinstance(website, str) and website:
        pages, seen = [website], set()
        while pages and len(seen) < 3:
            url = pages.pop(0)
            if url in seen:
                continue
            seen.add(url)
            if progress:
                progress('Checking the business website for social profiles…')
            response = crawler.get(url)
            if response['status'] != 'public':
                notes.append(response.get('note', 'Business website unavailable.'))
                continue
            source = response['url']
            direct = social_url(source)
            if direct:
                profiles = merge_profiles(profiles, [{'platform': direct[0], 'url': direct[1], 'source_url': url,
                                                      'status': 'not_checked', 'details': {}}])
                continue
            profiles = merge_profiles(profiles, extract_profiles(response['html'], source))
            if len(seen) == 1:
                soup = BeautifulSoup(response['html'], 'html.parser')
                for anchor in soup.select('a[href]'):
                    href = urljoin(source, anchor['href'])
                    parsed = urlparse(href)
                    if parsed.hostname == urlparse(source).hostname and re.search(r'contact|about', parsed.path, re.I):
                        candidate = urlunparse(parsed._replace(query='', fragment=''))
                        if candidate not in pages and candidate not in seen:
                            pages.append(candidate)
                        if len(pages) >= 2:
                            break
    for profile in sorted(profiles, key=lambda item: (item.get('status') != 'not_checked', item.get('checked_at', ''))):
        if progress:
            progress(f'Checking the public {profile["platform"]} profile…')
        response = crawler.get(profile['url'])
        if response['status'] != 'not_checked':
            profile['checked_at'] = checked_at
        profile['status'] = response['status']
        profile['note'] = response.get('note', '')
        if response['status'] == 'public':
            redirected = social_url(response['url'])
            details = profile_details(response['html']) if redirected and redirected[0] == profile['platform'] else None
            if details is None:
                profile.update(status='blocked', note='This profile requires sign-in or redirected away from its public profile.')
            elif not details:
                profile.update(status='unavailable', note='No public profile details were exposed in the page.')
            else:
                profile['details'] = {**profile.get('details', {}), **details}
                profile['observed_at'] = checked_at
    public = sum(profile.get('status') == 'public' for profile in profiles)
    note = f'Found {len(profiles)} linked profiles; public details available for {public}.' if profiles else (
        'No linked social profiles found.' if website else 'Add a business website or a saved social profile to start discovery.')
    if notes:
        note += ' ' + notes[0]
    return {'profiles': profiles, 'checked_at': checked_at, 'status': 'complete', 'note': note,
            'scope': 'Business website links and organization sameAs data; public profile HTML only. Handles are never guessed.'}
