"""Bounded collection API; the caller owns persistence and acknowledgement."""
from dataclasses import dataclass
from datetime import datetime, timezone
import time

from . import candidate_audit, core, feed_history, telegram_history, youtube_feed
from .source_health import retry_hints

SUPPORTED = frozenset({'rss', 'mailru', 'telegram', 'youtube'})
SUCCESS = frozenset({'ok', 'no_new_posts', 'no_public_posts', 'public_history_exhausted'})


@dataclass(frozen=True)
class CollectionResult:
    posts: list[dict]
    status: str
    attempts: list[dict]
    checkpoint: dict | None
    checked_at: str
    seconds: float
    retry_after: str | None = None


def collect(source, previous=None, *, max_pages=3, max_posts=1000, seconds=45,
            window_hours=48, telegram_parser=None):
    """Return legacy-shaped records and an uncommitted checkpoint.

    `telegram_parser` may supply the private deployment's enhanced parser chain.
    The standalone default is the existing public HTML fallback parser.
    Never treat a failed/partial result as a successful cursor advancement.
    """
    if not isinstance(source, dict) or not core.source_valid(source) or not source.get('id'):
        raise ValueError('invalid_source')
    if source['platform'] not in SUPPORTED:
        raise ValueError('unsupported_platform')
    if (type(max_pages) is not int or not 1 <= max_pages <= 200 or
            type(max_posts) is not int or not 1 <= max_posts <= 10000 or
            not 1 <= seconds <= 300 or window_hours < 0):
        raise ValueError('invalid_budget')
    previous = previous or {}
    if previous.get('url') not in (None, source['url']):
        previous = {}
    started = time.monotonic()
    checked = datetime.now(timezone.utc).isoformat()
    hints = []
    token = retry_hints.set(hints)
    counts_token = candidate_audit.current.set(None)
    try:
        if source['platform'] in ('rss', 'mailru'):
            rows, status, attempts, cursor = feed_history.collect(
                source, previous, window_hours=window_hours, max_pages=max_pages,
                max_posts=max_posts, seconds=seconds)
        elif source['platform'] == 'telegram':
            rows, status, attempts, cursor = telegram_history.collect(
                source, previous, max_pages=max_pages, max_posts=max_posts,
                seconds=seconds, live=True, parser=telegram_parser)
        else:
            rows = youtube_feed.collect(source, max_posts, core.fetch)
            status = 'ok' if rows else 'no_new_posts'
            attempts = [{'tool':'youtube_native_atom', 'status':status, 'posts':len(rows)}]
            cursor = {'url':source['url'], 'updated_at':checked}
        for row in rows:
            # Additive alias: never replace canonical_key or any legacy field.
            row['external_id'] = row['canonical_key']
        if cursor is not None:
            cursor = {**cursor, 'url':source['url']}
        return CollectionResult(rows, status, attempts, cursor if status in SUCCESS else None,
                                checked, time.monotonic()-started, max(hints) if hints else None)
    except Exception as error:
        status = core.error_code(error)
        return CollectionResult([], status, [], None, checked, time.monotonic()-started,
                                max(hints) if hints else None)
    finally:
        retry_hints.reset(token)
        candidate_audit.current.reset(counts_token)
