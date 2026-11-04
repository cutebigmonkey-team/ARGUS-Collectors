"""Authenticated HTTPS import contract. No private endpoint is built in."""
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import json
import urllib.error
import urllib.request
from urllib.parse import urlsplit


class DeliveryError(Exception):
    def __init__(self, code, retry_after=None):
        super().__init__(code)
        self.code, self.retry_after = code, retry_after


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise DeliveryError('import_redirect_rejected')


class HttpsSink:
    def __init__(self, endpoint, token):
        url = urlsplit(endpoint)
        if (url.scheme != 'https' or not url.hostname or url.username or url.password or
                url.fragment or url.query or url.port not in (None,443) or not token or '\n' in token or '\r' in token):
            raise ValueError('invalid_import_configuration')
        self.endpoint, self.token = endpoint, token

    def send(self, payload):
        # A registry, cursor, URL list or diagnostic report is never sent to the sink.
        body={'schema':payload['schema'],'batch_id':payload['batch_id'],
              'posts':payload['result']['posts']}
        request=urllib.request.Request(self.endpoint, data=json.dumps(body).encode(), method='POST',
            headers={'Content-Type':'application/json', 'Authorization':'Bearer '+self.token,
                     'Idempotency-Key':payload['batch_id']})
        try:
            with urllib.request.build_opener(NoRedirect()).open(request,timeout=30) as response:
                raw=response.read(2*1024*1024+1)
                if len(raw)>2*1024*1024:
                    raise DeliveryError('import_response_too_large')
                return json.loads(raw)
        except urllib.error.HTTPError as error:
            until=None
            value=error.headers.get('Retry-After','') if error.headers else ''
            if error.code in (429,503) and value:
                try:
                    until=(datetime.now(timezone.utc)+timedelta(seconds=int(value))) if value.isdigit() else parsedate_to_datetime(value)
                    if until.tzinfo is None:until=None
                except (ValueError,OverflowError):pass
            raise DeliveryError('import_http_'+str(error.code),until) from None
        except (urllib.error.URLError,TimeoutError):
            raise DeliveryError('import_unavailable') from None
        except (ValueError,TypeError):
            raise DeliveryError('invalid_import_response') from None
