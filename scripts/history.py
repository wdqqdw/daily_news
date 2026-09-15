"""Persistent publication ledger shared by selection and static publication."""
from __future__ import annotations
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit


def normalized_title(title):
    return ''.join(c for c in unicodedata.normalize('NFKC', title).casefold() if c.isalnum())


def canonical_doi(doi):
    value = unquote(doi).strip().casefold()
    return re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)', '', value)


def canonical_url(url):
    parts = urlsplit(url)
    host = (parts.hostname or '').casefold().removeprefix('www.')
    if parts.port and parts.port not in (80, 443):
        host += f':{parts.port}'
    # Keep semantic query fields (e.g. Qwen's article id), remove trackers.
    query = sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                   if not k.casefold().startswith('utm_') and k.casefold() not in
                   {'fbclid', 'gclid', 'mc_cid', 'mc_eid', 'ref'})
    return urlunsplit(('https', host, unquote(parts.path).rstrip('/'), urlencode(query), ''))


def item_keys(item, kind):
    keys = set()
    if kind == 'papers' and item.get('doi'):
        keys.add('doi:' + canonical_doi(item['doi']))
    for url in [item.get('url', ''), *item.get('url_aliases', [])]:
        if url:
            keys.add('url:' + canonical_url(url))
    for title in [item.get('title', ''), item.get('title_zh', ''),
                  item.get('original_title', ''), *item.get('title_aliases', [])]:
        if title and normalized_title(title):
            keys.add('title:' + normalized_title(title))
    return keys


def history_keys(history, kind):
    return {key for record in history[kind] for key in record['keys']}


def record_issue(history, issue):
    for kind in ('papers', 'news'):
        for item in issue[kind]:
            keys = item_keys(item, kind)
            matches = [record for record in history[kind] if keys.intersection(record['keys'])]
            if matches:
                record = matches[0]
                record['keys'] = sorted(set(record['keys']) | keys)
                record['first_pushed'] = min(record['first_pushed'], issue['date'])
            else:
                record = {'first_pushed': issue['date'], 'title': item['title'],
                          'url': item['url'], 'keys': sorted(keys)}
                if kind == 'papers':
                    record['doi'] = canonical_doi(item['doi'])
                else:
                    record['company'] = item['company']
                history[kind].append(record)
    return history


def load_history(data_dir):
    path = data_dir.parent / 'history.json'
    history = json.loads(path.read_text()) if path.exists() else {'version': 1, 'papers': [], 'news': []}
    if history.get('version') != 1:
        raise ValueError('Unsupported publication ledger version')
    # Include all saved editions, even if dated today. Missing/deleted edition
    # files never remove entries from the ledger or make old content eligible.
    for path in sorted(data_dir.glob('????-??-??.json')):
        record_issue(history, json.loads(path.read_text()))
    return history


def save_history(data_dir, history):
    path = data_dir.parent / 'history.json'
    temp = path.with_suffix('.json.tmp')
    temp.write_text(json.dumps(history, ensure_ascii=False, indent=2) + '\n')
    temp.replace(path)


def assert_unseen(issue, history):
    for kind in ('papers', 'news'):
        used = history_keys(history, kind)
        for item in issue[kind]:
            keys = item_keys(item, kind)
            if used.intersection(keys):
                raise ValueError(f'Already published or duplicate {kind}: {item["title"]}')
            used.update(keys)


def validate_edition_history(issues):
    history = {'version': 1, 'papers': [], 'news': []}
    for issue in issues:
        assert_unseen(issue, history)
        record_issue(history, issue)
