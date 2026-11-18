"""Explicit local env loading; only presence flags are printed, never values."""
import argparse
import os
from pathlib import Path


def load_env_file(path):
    from dotenv import dotenv_values
    path=Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Expected an ordinary local configuration file')
    if path.stat().st_mode & 0o077:
        raise ValueError('Run chmod 600 on the configuration file before loading it')
    values=dotenv_values(path,interpolate=False)
    if set(values)-{'DEEPSEEK_API_KEY','LOCAGENT_ALLOW_PAID'}:
        raise ValueError('Only DEEPSEEK_API_KEY and LOCAGENT_ALLOW_PAID are allowed')
    for name,value in values.items():
        if value is not None:
            os.environ[name]=value


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file')
    args=parser.parse_args()
    if args.env_file:
        try:load_env_file(args.env_file)
        except (OSError,ValueError):
            raise SystemExit('Config could not be loaded; check file path, mode 0600 and allowed names') from None
    import json
    print(json.dumps({'DEEPSEEK_API_KEY_present':bool(os.environ.get('DEEPSEEK_API_KEY')),
                      'paid_explicitly_enabled':os.environ.get('LOCAGENT_ALLOW_PAID')=='1'}))


if __name__=='__main__':
    main()
