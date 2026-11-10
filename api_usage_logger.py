import json
import os
import tempfile
from pathlib import Path
from datetime import datetime
from threading import Lock


usage_lock = Lock()


def log_usage(client, usage):
    if usage is None:
        return
    entry = {
        'client': client,
        'prompt_tokens': usage.prompt_tokens,
        'completion_tokens': usage.completion_tokens,
        'total_tokens': usage.total_tokens,
        'date': datetime.now().isoformat(),
    }
    # Different businesses can finish API requests together. Serialize the
    # read/append/write and replace atomically so readers never see partial JSON.
    with usage_lock:
        folder = Path('logs')
        folder.mkdir(exist_ok=True)
        target = folder / 'api_usage.json'
        data = json.loads(target.read_text(encoding='utf-8')) if target.exists() else []
        if not isinstance(data, list):
            raise ValueError('The API usage log is not a list.')
        data.append(entry)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=folder, suffix='.tmp', delete=False) as file:
                temporary = file.name
                json.dump(data, file, indent=2)
            os.replace(temporary, target)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
