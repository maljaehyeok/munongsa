"""Bounded private refresh runner. No collection, publication, credentials or network."""
import argparse
import json
from pathlib import Path
import sqlite3
import time

import rag_sync as sync

REQUIRED = {'state_dir','rights_file','served_feed','details_file','sync_dir'}
OPTIONAL = {'legacy_root','reader_group'}
DELAYS = (1, 3)
LOG_BYTES = 128 * 1024


def settings(path):
    value = sync.read(path)
    if not REQUIRED <= value.keys() or value.keys() - REQUIRED - OPTIONAL:
        raise sync.SyncError('exact_private_settings_required')
    for key in REQUIRED | {'legacy_root'}:
        if key in value and (not isinstance(value[key],str) or not Path(value[key]).is_absolute()):
            raise sync.SyncError('absolute_private_paths_required')
    return value


def log(directory, result):
    """Bounded counts/status only. Do not log input paths, IDs, questions or exceptions."""
    directory = Path(directory); path = directory/'refresh-status.jsonl'
    if path.exists() and path.stat().st_size >= LOG_BYTES:
        for number in (2,1):
            prior = directory/('refresh-status.jsonl.'+str(number))
            if prior.exists():
                prior.replace(directory/('refresh-status.jsonl.'+str(number+1)))
        path.replace(directory/'refresh-status.jsonl.1')
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    with path.open('ab') as stream:
        stream.write((json.dumps({'checked_at':sync.now_utc().isoformat(),**result})+'\n').encode())
    path.chmod(0o600)


def run(config, *, sleep=time.sleep, refresh=sync.refresh):
    if config.get('reader_group'):
        sync.configure_reader_group(config['sync_dir'],config['reader_group'])
    result = {'status':'failed','attempts':0,'code':'invalid_input'}
    for attempt in range(3):
        try:
            generated = refresh(*(config[k] for k in ('state_dir','rights_file','served_feed','details_file','sync_dir')),
                                legacy_root=config.get('legacy_root'))
            result={'status':'ok','attempts':attempt+1,'documents':generated['documents'],
                    'omitted':len(generated['omitted']),'reused':generated.get('reused',False)}
            break
        except FileExistsError:
            result={'status':'busy','attempts':attempt+1,'code':'already_running'}; break
        except (OSError, sqlite3.OperationalError):
            result={'status':'failed','attempts':attempt+1,'code':'temporary_io_or_db_error'}
            if attempt < 2:
                sleep(DELAYS[attempt]); continue
        except (ValueError,KeyError,TypeError,sync.monitor.MonitorError):
            result={'status':'failed','attempts':attempt+1,'code':'validation_failed'}
        break
    # Logging failure must not revoke successfully verified bindings.
    try: log(config['sync_dir'],result)
    except OSError: result['log_available']=False
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--settings',type=Path,required=True)
    args=parser.parse_args()
    try: result=run(settings(args.settings))
    except (OSError,ValueError,KeyError,TypeError): result={'status':'failed','code':'invalid_private_settings'}
    print(json.dumps(result))
    return 0 if result['status']=='ok' else 75 if result['status']=='busy' else 1


if __name__=='__main__': raise SystemExit(main())
