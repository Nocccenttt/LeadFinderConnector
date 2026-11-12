"""Website availability, current QA, and delivery review share one state model."""
import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path

LABELS = {'missing': 'Not built', 'incomplete': 'Incomplete files', 'building': 'Building website',
          'draft': 'Draft — QA not verified', 'needs_attention': 'Needs attention',
          'qa_passed': 'QA passed — review pending', 'approved': 'Reviewed for delivery'}


def read_json(path):
    try:
        if path.resolve() != path.absolute():
            return {}
        value = path.read_text(encoding='utf-8')
        data = json.loads(value)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, RuntimeError):
        return {}


@lru_cache(maxsize=4096)
def _file_digest(path, size, modified, changed):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''):
            digest.update(chunk)
    stat = os.stat(path)
    if (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns) != (size, modified, changed):
        raise OSError('Website changed while its files were being checked.')
    return digest.hexdigest()


def website_snapshot(folder):
    website = Path(folder) / 'website'
    missing = []
    for name in ('index.html', 'styles.css', 'script.js'):
        file = website / name
        try:
            if website.resolve() != website.absolute() or file.resolve() != file.absolute() or not file.is_file() or file.stat().st_size == 0:
                missing.append(name)
        except (OSError, RuntimeError):
            missing.append(name)
    snapshot = {'available': not missing, 'missing_assets': missing, 'fingerprint': ''}
    if missing:
        return snapshot
    try:
        files = []
        def unreadable(error):
            raise error
        for root, directories, names in os.walk(website, followlinks=False, onerror=unreadable):
            for name in directories + names:
                file = Path(root) / name
                if file.is_symlink() or file.resolve() != file.absolute():
                    raise OSError('Website contains linked assets.')
            files.extend(Path(root) / name for name in names)
        digest = hashlib.sha256()
        for file in sorted(files):
            stat = file.stat()
            digest.update(file.relative_to(website).as_posix().encode('utf-8') + b'\0')
            digest.update(_file_digest(str(file), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns).encode('ascii') + b'\0')
        snapshot['fingerprint'] = digest.hexdigest()
    except (OSError, RuntimeError):
        pass
    return snapshot


def website_status(folder, *, building=False):
    folder = Path(folder)
    snapshot = website_snapshot(folder)
    report = read_json(folder / 'quality_report.json')
    report_hash = hashlib.sha256(json.dumps(report, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest() if report else ''
    recorded = str(report.get('status', 'NOT RUN')).upper()
    qa = {'status': recorded, 'checks_passed': 0, 'checks_total': 0, 'issues': []}
    checks = report.get('checks', {})
    for value in checks.values() if isinstance(checks, dict) else []:
        check = value.get('status') if isinstance(value, dict) else value
        if check:
            qa['checks_total'] += 1
            qa['checks_passed'] += check == 'PASS'
        if isinstance(value, dict) and isinstance(value.get('issues'), list):
            qa['issues'].extend(str(issue) for issue in value['issues'] if issue)
    warnings = report.get('warnings', [])
    if isinstance(warnings, list):
        qa['issues'].extend(str(issue) for issue in warnings if issue)
    qa['issues'] = qa['issues'][:5]
    fingerprint = snapshot['fingerprint']
    qa_matches = bool(fingerprint and report.get('website_fingerprint') == fingerprint)
    if recorded == 'PASS' and not qa_matches:
        qa['status'] = 'STALE' if report.get('website_fingerprint') else 'UNVERIFIED'
    if recorded == 'PASS' and (qa['checks_total'] == 0 or qa['checks_passed'] != qa['checks_total']):
        qa['status'] = 'UNVERIFIED'
    failed = str(read_json(folder / 'STATUS.json').get('status', '')).upper() in ('RUNNING', 'FAILED', 'NEEDS REVIEW') or recorded in ('FAIL', 'FAILED', 'NEEDS REVIEW')
    qa_passed = bool(snapshot['available'] and qa_matches and recorded == 'PASS' and qa['checks_total'] > 0 and
                     qa['checks_passed'] == qa['checks_total'] and not failed and not building)
    delivery = read_json(folder / 'DELIVERY.json')
    approved = bool(qa_passed and delivery.get('approval_status') == 'APPROVED' and
                    delivery.get('website_fingerprint') == fingerprint and delivery.get('qa_report_hash') == report_hash)
    state = ('building' if building else 'needs_attention' if failed or snapshot['available'] and not fingerprint else
             'missing' if not (folder / 'website').exists() else 'incomplete' if not snapshot['available'] else
             'approved' if approved else 'qa_passed' if qa_passed else 'draft')
    messages = {
        'missing': 'No website has been built for this business yet.',
        'incomplete': 'Website files are incomplete. Build again to create a complete draft.',
        'building': 'A website build is running. Downloads and delivery review are paused.',
        'needs_attention': 'Review the quality checks or retry the build. Available files are a draft.',
        'draft': 'Files are available as a draft. Recheck QA before delivery review.',
        'qa_passed': 'Automated QA passed for these files. Review the copy, links, and desktop/mobile preview before delivery.',
        'approved': 'These files passed QA and were explicitly reviewed for delivery.',
    }
    return {**snapshot, 'state': state, 'label': LABELS[state], 'message': messages[state], 'qa': qa,
            'qa_passed': qa_passed, 'qa_report_hash': report_hash, 'approved': approved,
            'can_download_draft': bool(snapshot['available'] and fingerprint and not building),
            'can_review': qa_passed, 'reviewed_at': delivery.get('reviewed_at', '') if approved else ''}
