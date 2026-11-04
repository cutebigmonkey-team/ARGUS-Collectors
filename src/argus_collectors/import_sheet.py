"""Reusable public parsing primitives; private orchestration is excluded."""
import argparse

import collections

import hashlib

import json

from pathlib import Path

import posixpath

import re

import urllib.parse as U

import xml.etree.ElementTree as E

from zipfile import ZipFile

def normalize(url):
    p=U.urlsplit(url.strip());host=(p.hostname or '').encode('idna').decode().lower().removeprefix('www.')
    if p.scheme not in ('http','https') or not host or p.username or p.password or p.port not in (None,80,443):raise ValueError('invalid_url')
    path=U.unquote(p.path).rstrip('/') or '/';q=U.parse_qsl(p.query,keep_blank_values=True)
    if host=='web.telegram.org':
        if re.fullmatch(r'@[A-Za-z0-9_]{3,64}',p.fragment):host='t.me';path='/'+p.fragment[1:]
        else:raise ValueError('telegram_public_username_required')
    if host=='telegram.me':host='t.me'
    if host=='twitter.com':host='x.com'
    if host=='threads.net':host='threads.com'
    if host=='t.me':
        path=re.sub(r'^/s/','/',path).lower()
        if path.startswith(('/+','/joinchat/')):raise ValueError('private_invite')
        platform='telegram'
    elif host in ('facebook.com','m.facebook.com','mbasic.facebook.com'):
        platform='facebook';host='www.facebook.com'
        if not re.search(r'/(?:share|posts|permalink|reels?|videos)/',path,re.I):path=path.lower()
        m=re.fullmatch(r'/p/.*-(\d+)',path)
        if m:path='/profile.php';q=[('id',m[1])]
    elif host in ('youtube.com','m.youtube.com','youtu.be'):platform='youtube';host='www.youtube.com' if host!='youtu.be' else host
    elif host in ('vt.tiktok.com','vm.tiktok.com'):platform='tiktok'
    elif host in ('instagram.com','x.com','tiktok.com','threads.com','vk.com','vk.ru','ok.ru','max.ru','web.max.ru','reddit.com'):
        platform={'vk.ru':'vk','vk.com':'vk','web.max.ru':'max','max.ru':'max','ok.ru':'ok','reddit.com':'reddit'}.get(host,host.split('.')[0])
        if platform=='instagram' and path.lower()=='/accounts/login':
            targets=[v for k,v in q if k=='next']
            if len(targets)!=1 or not re.fullmatch(r'/[A-Za-z0-9_.]{1,30}/?',targets[0]):
                raise ValueError('instagram_public_profile_required')
            path=targets[0].rstrip('/')
        if not re.search(r'/(?:p|reel|post|c)/',path,re.I):path=path.lower()
        if platform in ('instagram','tiktok','threads'):host='www.'+host
    elif host=='rutube.ru':platform='rutube'
    elif host=='mail.ru' or host.endswith('.mail.ru'):platform='mailru'
    elif host in ('whatsapp.com','whatsapp.net'):platform='whatsapp';host='www.whatsapp.com'
    else:platform='rss'
    # Source identity parameters, not locale or tracking. Website queries can be functional.
    if platform in ('facebook','youtube'):q=[(k,v) for k,v in q if k in ('id','story_fbid','v','list')]
    elif platform=='x' and path=='/search':
        q=[(k,v) for k,v in q if k=='q' and v.strip()]
        if len(q)!=1:raise ValueError('x_search_query_required')
    elif platform not in ('rss','mailru'):q=[]
    else:q=[(k,v) for k,v in q if not k.lower().startswith(('utm_','fbclid','yclid','gclid','__cf_'))]
    return platform,U.urlunsplit(('https',host,U.quote(path,safe="/@:!$&'()*+,;=-._~"),U.urlencode(q),''))

def is_operator_source(source):
    return any(ref.get('kind') == 'operator_supplied_source' for ref in source.get('references', []))
