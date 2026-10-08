from dataclasses import dataclass, field
import os
import re


@dataclass(frozen=True)
class Settings:
    database_url: str = field(repr=False)
    schema: str = 'locagent'

    def __post_init__(self):
        if not self.database_url.startswith(('postgresql://', 'postgres://')):
            raise ValueError('LOCAGENT_DATABASE_URL must be a PostgreSQL URL')
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,62}', self.schema):
            raise ValueError('LOCAGENT_SCHEMA must be a simple lowercase identifier')

    @classmethod
    def from_env(cls):
        return cls(os.environ.get('LOCAGENT_DATABASE_URL', ''),
                   os.environ.get('LOCAGENT_SCHEMA', 'locagent'))
