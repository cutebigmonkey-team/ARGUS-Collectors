"""Combine observations of one verified identity at collection and archive boundaries."""
from datetime import datetime
from urllib.parse import urlsplit


def full_text(row):
    return bool(row.get('text') and row.get('text_may_be_truncated') is False)


def video_caption(text, analysis):
    if not analysis or text.endswith(analysis):
        return text
    combined = text + '\n\n' + analysis if text else analysis
    # The analysis is also stored separately. Preserve a long original caption.
    return combined if len(combined) <= 100000 else text


def merge_observations(previous, incoming):
    if not previous:
        return incoming
    def observed(row):
        return datetime.fromisoformat(row['observed_at'].replace('Z', '+00:00'))
    older, newer = sorted((previous, incoming), key=observed)
    result = dict(newer)
    result['discovered_at'] = min((row.get('discovered_at') or row['observed_at']
                                   for row in (older, newer)), key=datetime.fromisoformat)
    result['collected_at'] = newer.get('collected_at') or newer['observed_at']
    # A confirmed edit can shorten a post. An excerpt cannot replace its full body.
    teaser=newer.get('text','').rstrip('…. ').strip()
    shorter_preview=(newer.get('text_may_be_truncated') is True and bool(teaser) and
                     older.get('text','').startswith(teaser) and len(older['text'])>len(newer['text']))
    native_before_embed=(newer.get('capture_mode')=='publisher_tiktok_embed' and
                         older.get('capture_mode')!='publisher_tiktok_embed' and bool(older.get('text')))
    if older.get('text') and (not newer.get('text') or shorter_preview or native_before_embed or
            (full_text(older) and newer.get('text_may_be_truncated') is True)):
        result['retained_text_observed_at']=older['observed_at']
        for field in ('text', 'text_may_be_truncated', 'facebook_text_source'):
            if field in older:
                result[field] = older[field]
        if native_before_embed:
            for field in ('capture_mode','tool'):
                if field in older: result[field]=older[field]
                else: result.pop(field,None)
    if not newer.get('published_at') and older.get('published_at') and not older.get('published_at_is_estimated'):
        result['published_at'] = older['published_at']
        result['retained_date_observed_at']=older['observed_at']
        if older.get('facebook_date_source'):
            result['facebook_date_source'] = older['facebook_date_source']
    for field, limit in (('media_urls', 12), ('outbound_social_links', 100), ('outbound_profile_links', 100), ('media', 100), ('identity_aliases',100)):
        if field in newer or field in older:
            result[field] = list(dict.fromkeys(newer.get(field, []) + older.get(field, [])))[:limit]
    for field in ('source_name', 'source_id', 'source_url', 'facebook_story_id', 'tool', 'instagram_comments', 'x_references'):
        if older.get(field) and not newer.get(field):
            result[field] = older[field]
    if (newer.get('platform')=='x' and urlsplit(newer.get('source_url') or '').path.rstrip('/')=='/search'
            and older.get('source_url') and urlsplit(older['source_url']).path.rstrip('/')!='/search'):
        # A second sighting in search should not move a known publisher to a different feed.
        for field in ('source_id','source_name','source_url','origin'):
            if field in older:
                result[field]=older[field]
    if older.get('files'):
        result['files'] = list({f['sha256']: f for f in older['files'] + newer.get('files', [])}.values())
    if older.get('public_comments') or newer.get('public_comments'):
        result['public_comments']=list({c['id']:c for c in
            older.get('public_comments',[])+newer.get('public_comments',[])}.values())[:20]
    return result
