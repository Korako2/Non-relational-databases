from pathlib import Path
from secrets import token_hex
import os

path = Path(__file__).resolve().parents[1] / '.env'
example = path.with_name('.env.example').read_text()
try:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    print('.env already exists; keeping existing settings')
else:
    with os.fdopen(fd, 'w') as file:
        for name in ('ADMIN', 'WRITER', 'READER', 'GRAFANA'):
            example = example.replace(f'CHANGE_ME_{name}', token_hex(24))
        file.write(example)
    print('Created .env (mode 0600)')