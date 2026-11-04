"""Reusable public parsing primitives; private orchestration is excluded."""
import argparse

import asyncio

from email.utils import parsedate_to_datetime

import collections

import datetime as dt

import hashlib

import ipaddress

import json

import os

from pathlib import Path

import re

import socket

import ssl

import sys

import time

import urllib.error

import urllib.parse

import urllib.request

from functools import lru_cache

from bs4 import BeautifulSoup

import feedparser

from .record_quality import merge_observations

from .source_health import instant, reader_history, platform_status

from . import candidate_audit
from .url_identity import url_ok

PLATFORMS = ('telegram','youtube','x','facebook','instagram','rss','tiktok','threads','vk','ok','max','reddit','rutube','mailru','whatsapp')

HOSTS = {
    'telegram': ('t.me',), 'youtube': ('youtube.com','www.youtube.com','m.youtube.com'),
    'x': ('x.com','www.x.com','twitter.com','www.twitter.com'),
    'facebook': ('facebook.com','www.facebook.com','m.facebook.com','mbasic.facebook.com'),
    'instagram': ('instagram.com','www.instagram.com'),
    'tiktok': ('tiktok.com','www.tiktok.com','vt.tiktok.com','vm.tiktok.com'), 'threads': ('threads.net','www.threads.net','threads.com','www.threads.com'),
    'vk': ('vk.com','www.vk.com','m.vk.com','vk.ru','www.vk.ru'),
    'ok': ('ok.ru','www.ok.ru','m.ok.ru'), 'max': ('max.ru','web.max.ru','www.max.ru'),
    'reddit': ('reddit.com','www.reddit.com','old.reddit.com'),
    'rutube': ('rutube.ru','www.rutube.ru'), 'whatsapp': ('whatsapp.com','www.whatsapp.com'),
}

IDENTITIES = {
    'facebook': r'(?:/(?:posts|permalink|videos|reel|reels)/|[?&](?:story_fbid|fbid)=)([A-Za-z0-9_-]+)',
    'instagram': r'/(?:p|reel)/([A-Za-z0-9_-]+)', 'x': r'/status/(\d+)',
    'threads': r'/post/([A-Za-z0-9_-]+)', 'tiktok': r'/video/(\d+)',
    'vk': r'/wall(-?\d+_\d+)', 'ok': r'/(?:topic|statuses)/(\d+)',
    'max': r'/c/(-?\d+/[A-Za-z0-9_-]+)',
}

def now(): return dt.datetime.now(dt.timezone.utc).isoformat()

@lru_cache(maxsize=4096)
def public_host(host):
    addresses = socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise ValueError('private_destination')

def safe_url(url):
    if not url_ok(url): raise ValueError('invalid_url')
    public_host(urllib.parse.urlsplit(url).hostname)

class Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        safe_url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def fetch(url, timeout=12):
    safe_url(url)
    request = urllib.request.Request(url, headers={'User-Agent':'ArgusPRO/1.0 public-feed-reader','Accept':'application/atom+xml,application/rss+xml,text/html;q=0.8,*/*;q=0.5'})
    with urllib.request.build_opener(Redirects()).open(request,timeout=timeout) as response:
        data = response.read(8*1024**2+1)
        if len(data)>8*1024**2: raise ValueError('response_too_large')
        return data, response.url

def plain(value): return BeautifulSoup(str(value),'html.parser').get_text(' ',strip=True)[:100000]

def date(value):
    if not value: return None
    try:
        parsed=dt.datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if parsed.tzinfo is None: return None
        return parsed.astimezone(dt.timezone.utc).isoformat()
    except (ValueError,TypeError): return None

def post(source, key, url, text, published=None, media=()):
    if not url_ok(url): raise ValueError('invalid_post_url')
    observed = now()
    return {'canonical_key':key,'platform':source['platform'],'post_url':url,'text':text[:100000],
            'published_at':date(published),'observed_at':observed,'collected_at':observed,
            'discovered_at':observed,'media':[],
            'media_urls':list(dict.fromkeys(u for u in media if isinstance(u,str) and url_ok(u)))[:12],
            'origin':source.get('origin') if source.get('origin') in ('general','dsns') else 'unknown',
            'source_id':str(source.get('id','')),'source_name':source.get('name',''),'source_url':source['url']}

def social_url(url):
    parsed=urllib.parse.urlsplit(url)
    # Preserve identity parameters; tracking is never identity.
    query=urllib.parse.urlencode([(k,v) for k,v in urllib.parse.parse_qsl(parsed.query) if k in ('story_fbid','fbid','id')])
    return urllib.parse.urlunsplit((parsed.scheme,parsed.netloc,parsed.path,query,''))

def telegram_html(source,limit,body):
    channel=urllib.parse.urlsplit(source['url']).path.strip('/').removeprefix('s/').split('/')[0]
    soup=BeautifulSoup(body,'html.parser'); items=[]
    for node in soup.select('.tgme_widget_message[data-post]'):
        identity=node.get('data-post','')
        if not re.fullmatch(re.escape(channel)+r'/\d+',identity,re.I): continue
        text=node.select_one('.tgme_widget_message_text')
        stamp=node.select_one('.tgme_widget_message_date time[datetime]') or node.select_one('time[datetime]')
        parts=[text.get_text('\n',strip=True)] if text else []
        for detail in node.select('.tgme_widget_message_document_title,.tgme_widget_message_poll_question,.tgme_widget_message_poll_option_text'):
            value=detail.get_text(' ',strip=True)
            if value and value not in parts:parts.append(value)
        media=[]
        for element in node.select('[style]'):
            media.extend(re.findall(r"url\(['\"]?(https?://[^)'\"]+)",element.get('style','')))
        media += [element.get('src') for element in node.select('video[src],audio[src],video source[src],audio source[src],img.tgme_widget_message_sticker[src]')]
        media += [element['href'] for element in node.select('a.tgme_widget_message_document[href]') if url_ok(element['href']) and urllib.parse.urlsplit(element['href']).hostname!='t.me']
        if not any(parts) and not media: continue
        item=post(source,'telegram:'+identity.lower(),'https://t.me/'+identity,
                  '\n'.join(parts),stamp.get('datetime') if stamp else None,media)
        from .social_links import outbound
        item.update(outbound(str(text) if text else ''))
        items.append(item)
    return items[-limit:]

def feed_posts(source, body, limit, *, base_url=None):
    return feed_entries(source,feedparser.parse(body).entries,limit,base_url=base_url)

def feed_entries(source, entries, limit, *, base_url=None):
    candidate_audit.count('raw_input',len(entries))
    items=[]
    seen = set()
    for entry in entries:
        url=entry.get('link','')
        if url and base_url and source['platform'] in ('rss','mailru'):
            url=urllib.parse.urljoin(base_url,url)
        if not url_ok(url):
            candidate_audit.reject('invalid_feed_permalink',url)
            continue
        platform=source['platform']
        if platform in ('rss','mailru'):
            from .url_identity import clean_permalink
            url=clean_permalink(url)
        identity=entry.get('yt_videoid') if platform=='youtube' else None
        if platform=='reddit':
            path=urllib.parse.urlsplit(url)
            owner=re.match(r'/r/([\w]+)/?',urllib.parse.urlsplit(source['url']).path,re.I)
            target=re.fullmatch(r'/r/([\w]+)/comments/([a-z0-9]+)(?:/[^/]*)?/?',path.path,re.I)
            if not owner or not target or path.hostname not in HOSTS['reddit'] or owner[1].lower()!=target[1].lower():continue
            identity=target[2].lower()
            url='https://www.reddit.com/r/'+target[1]+'/comments/'+identity+'/'
        key=platform+':'+(identity or hashlib.sha256(url.split('#')[0].encode()).hexdigest())
        if key in seen:
            candidate_audit.reject('repeated_feed_identity',key)
            continue
        published=feed_date(entry)
        content=next(iter(entry.get('content',[])),{}).get('value','') or entry.get('summary','')
        text='\n\n'.join(dict.fromkeys(s for s in (plain(entry.get('title','')),plain(content)) if s))
        media=[e.get('href','') for e in entry.get('enclosures',[])]+[e.get('url','') for e in entry.get('media_content',[])]
        media.extend(e.get('url','') for e in entry.get('media_thumbnail',[]))
        item=post(source,key,url,text,published,media)
        if not text and not item['media_urls']:
            candidate_audit.reject('no_public_content',key)
            continue
        item['capture_mode']='native_feed'
        item['text_may_be_truncated']=not bool(entry.get('content') and plain(content)) or text.rstrip().endswith(('вЂ¦','...'))
        from .social_links import outbound
        item.update(outbound(content,url))
        items.append(item)
        seen.add(key)
        if len(items)>=limit: break
    return items

def feed_date(entry):
    raw=entry.get('published')
    if not raw:return None
    iso=date(raw)
    if iso:return iso
    try:return date(parsedate_to_datetime(raw).isoformat())
    except (ValueError,TypeError,OverflowError):return None

def source_valid(source):
    platform=source.get('platform'); url=source.get('url','')
    if platform not in PLATFORMS or not url_ok(url): return False
    host=urllib.parse.urlsplit(url).hostname
    if platform=='instagram' and urllib.parse.urlsplit(url).path.strip('/').split('/')[0] in ('accounts','explore','direct'):return False
    return platform=='rss' or (platform=='mailru' and (host=='mail.ru' or host.endswith('.mail.ru'))) or host in HOSTS.get(platform,())

def error_code(error):
    if isinstance(error,urllib.error.HTTPError):
        if error.code in (429,503) and error.headers:
            from .source_health import note_retry_after
            note_retry_after(error.headers.get('Retry-After'),dt.datetime.now(dt.timezone.utc))
        return 'http_'+str(error.code)
    if isinstance(error,(TimeoutError,asyncio.TimeoutError)): return 'timeout'
    if type(error).__module__.startswith('playwright') and type(error).__name__=='TimeoutError':return 'timeout'
    if isinstance(error,ValueError) and re.fullmatch(r'[a-z0-9_]{1,70}',str(error)): return str(error)
    if isinstance(error,urllib.error.URLError):
        reason=error.reason
        if isinstance(reason,ssl.SSLCertVerificationError):return 'tls_certificate_error'
        if isinstance(reason,ssl.SSLError):return 'tls_error'
        if isinstance(reason,socket.gaierror):return 'dns_error'
        if isinstance(reason,TimeoutError):return 'timeout'
        if isinstance(reason,ConnectionResetError):return 'connection_reset'
        if isinstance(reason,ConnectionRefusedError):return 'connection_refused'
        return 'network_error'
    return 'collection_failed'
