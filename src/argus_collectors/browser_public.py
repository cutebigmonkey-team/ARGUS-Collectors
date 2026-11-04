"""Reusable public parsing primitives; private orchestration is excluded."""
import asyncio

import json

from pathlib import Path

import re

import time

from urllib.parse import urlsplit, urlunsplit, urlencode, parse_qs, urljoin

def page_error(url,body):
    if '__jhash_' in body and '__jua_' in body:return 'challenge_required'
    if re.search(r'cf-chl-|/cdn-cgi/challenge-platform/|sorry, you have been blocked',body[:65536],re.I):return 'challenge_required'
    if re.search(r'captcha|verify you are human|just a moment|Р С—РЎР‚Р С•Р Р†Р ВµРЎР‚Р С”Р В° Р В±РЎР‚Р В°РЎС“Р В·Р ВµРЎР‚Р В°',body[:10000],re.I):return 'challenge_required'
    if re.search(r'/(?:login|accounts/login|checkpoint|auth)(?:/|\?|$)',url,re.I):return 'login_required'
    return None
