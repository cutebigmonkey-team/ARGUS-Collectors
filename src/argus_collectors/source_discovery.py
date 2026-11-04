"""Reusable public parsing primitives; private orchestration is excluded."""
from collections import Counter

from hashlib import sha256

import json

from itertools import zip_longest

from datetime import datetime, timedelta, timezone

from email.utils import parsedate_to_datetime

from urllib.error import HTTPError

import re

import time

from urllib.parse import parse_qsl, urljoin, urlsplit

from .import_sheet import normalize

from .url_identity import same_site, url_ok

PROFILES = {
    'facebook': r'/(?:[A-Za-z0-9_.-]+|profile\.php\?id=\d+)',
    'instagram': r'/[A-Za-z0-9_.]{1,30}', 'x': r'/[A-Za-z0-9_]{1,15}',
    'threads': r'/@[A-Za-z0-9_.]+', 'tiktok': r'/@[A-Za-z0-9_.]+',
    'telegram': r'/[A-Za-z][A-Za-z0-9_]{3,63}',
    'youtube': r'/(?:@[\w.%+-]+|channel/UC[A-Za-z0-9_-]{22}|(?:c|user)/[\w.%+-]+)',
    'rutube': r'/channel/\d+', 'vk': r'/[\w.]+', 'ok': r'/(?:group|profile)/\d+',
}

RESERVED = {'share','sharer','sharer.php','p','reel','reels','intent','i','search','home','login',
            'explore','accounts','dialog','stories','groups','watch','plugins','settings','help',
            'joinchat','share.php','login.php','iv','proxy','socks','addstickers','contact','privacy'}

def profile(url):
    if not isinstance(url,str) or len(url)>2048 or not url_ok(url):
        return None
    # A login redirect or an invite with a start token is not a public profile.
    if any(k.lower() in ('next','start','startgroup','invite','token') for k,_ in parse_qsl(urlsplit(url).query)):
        return None
    try:
        platform, canonical = normalize(url)
        p = urlsplit(canonical)
        path = p.path + ('?' + p.query if p.query else '')
        if (p.hostname in ('youtu.be','vt.tiktok.com','vm.tiktok.com') or p.path.strip('/').lower() in RESERVED or
                not re.fullmatch(PROFILES.get(platform, r'(?!)'), path)):
            return None
        return platform, canonical
    except (ValueError, UnicodeError, AttributeError):
        return None
