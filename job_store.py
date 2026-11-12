"""Small local journal; never resumes paid work automatically."""
import json
from uuid import uuid4


FIELDS = ('kind', 'status', 'priority', 'client_id', 'started_at', 'preserve_content', 'interrupted', 'phase', 'phase_started_at', 'finished_at')


def save_jobs(root, jobs):
    folder = root / 'outputs'
    folder.mkdir(exist_ok=True)
    output = folder / 'workspace-jobs.json'
    temporary = folder / f'.jobs-{uuid4().hex}.tmp'
    try:
        data = {key: {field: job[field] for field in FIELDS if field in job}
                for key, job in jobs.items() if job.get('kind') in ('website', 'leads', 'social')}
        temporary.write_text(json.dumps(data), encoding='utf-8')
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def load_jobs(root):
    try:
        data = json.loads((root / 'outputs' / 'workspace-jobs.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    recovered = {}
    if not isinstance(data, dict):
        return recovered
    for key, value in data.items():
        if not isinstance(value, dict) or value.get('kind') not in ('website', 'leads', 'social'):
            continue
        if value.get('status') not in ('queued', 'running') and not value.get('interrupted'):
            # Keep terminal attempts so an older interruption cannot reappear
            # after a newer retry has already completed and the app restarts.
            if value.get('status') in ('complete', 'error'):
                recovered[key] = {field: value[field] for field in FIELDS if field in value}
            continue
        job = {field: value[field] for field in FIELDS if field in value}
        job.update(status='error', interrupted=True,
                   message='Interrupted: LeadFinder stopped before this work finished. Saved files and build backups were kept. Review the current preview before starting another attempt.')
        if job.get('kind') == 'website':
            from build_recovery import recover_build
            priority, name = job.get('priority'), job.get('client_id')
            if priority in ('HIGH', 'MEDIUM', 'LOW') and isinstance(name, str) and name not in ('.', '..') and not any(c in name for c in '/\\:\0'):
                folder = root / 'codex_handoffs' / priority / name
                if folder.is_dir() and folder.resolve() == folder.absolute():
                    try:
                        recover_build(folder)
                    except (OSError, ValueError) as error:
                        job['message'] = 'Interrupted: previous website recovery needs attention. Backups were kept. Retry after checking the saved folder.'
        recovered[key] = job
    return recovered
