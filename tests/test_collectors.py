import unittest
from unittest.mock import patch

from argus_collectors import collect
from argus_collectors import core, feed_history, youtube_feed, telegram_history
from argus_collectors.web_pages import structured_rows
from argus_collectors.url_identity import clean_permalink

RSS = b'''<rss version="2.0"><channel><title>Example</title>
<item><title>A publication</title><link>https://example.org/news/1?utm_source=test</link>
<description>Public text</description><pubDate>Wed, 04 Nov 2026 08:00:00 GMT</pubDate></item>
<item><title>Duplicate</title><link>https://example.org/news/1</link></item>
</channel></rss>'''
TELEGRAM = b'''<div class="tgme_widget_message" data-post="example/42">
<div class="tgme_widget_message_text">Public message</div>
<a class="tgme_widget_message_date"><time datetime="2026-11-04T08:00:00+00:00"></time></a></div>'''
SOURCE = {'id':'fixture','platform':'rss','url':'https://example.org/feed','name':'Example'}


class Parsers(unittest.TestCase):
    def test_all_internal_imports_are_self_contained(self):
        import ast
        import importlib
        from pathlib import Path
        for path in Path(core.__file__).parent.glob('*.py'):
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if isinstance(node,ast.ImportFrom) and node.level==1 and node.module:
                    module=importlib.import_module('argus_collectors.'+node.module)
                    for name in node.names:
                        self.assertTrue(hasattr(module,name.name),(path.name,node.module,name.name))

    def test_offline_feed_collection_end_to_end(self):
        from argus_collectors.crawl_common import CrawlState
        source={**SOURCE,'references':[{'kind':'discovered_public_feed'}]}
        with patch.object(CrawlState,'robots_allowed'), patch.object(CrawlState,'read',return_value=(RSS,SOURCE['url'])):
            result=collect(source,window_hours=0)
        self.assertEqual(result.status,'ok')
        self.assertEqual(len(result.posts),1)
        self.assertEqual(result.checkpoint['pending'],[])

    def test_offline_telegram_collection_end_to_end(self):
        source={'id':'tg','platform':'telegram','url':'https://t.me/example'}
        with patch.object(core,'fetch',return_value=(TELEGRAM,'https://t.me/s/example')), patch.object(telegram_history.time,'sleep'):
            result=collect(source,max_pages=1)
        self.assertEqual(result.status,'ok')
        self.assertEqual(result.checkpoint['head_id'],42)
        self.assertEqual(result.posts[0]['canonical_key'],'telegram:example/42')

    def test_feed_identity_and_dates(self):
        posts=core.feed_posts(SOURCE,RSS,10,base_url=SOURCE['url'])
        self.assertEqual(len(posts),1)
        self.assertEqual(posts[0]['post_url'],'https://example.org/news/1')
        self.assertEqual(posts[0]['published_at'],'2026-11-04T08:00:00+00:00')
        self.assertEqual(posts[0]['text'],'A publication\n\nPublic text')

    def test_telegram_ownership(self):
        source={'id':'tg','platform':'telegram','url':'https://t.me/example'}
        self.assertEqual(core.telegram_html(source,10,TELEGRAM)[0]['canonical_key'],'telegram:example/42')
        self.assertEqual(core.telegram_html({**source,'url':'https://t.me/other'},10,TELEGRAM),[])

    def test_pinned_card_does_not_skip_history(self):
        body=TELEGRAM+b'<a class="tme_messages_more" href="/s/example?before=40">More</a>'
        source={'id':'tg','platform':'telegram','url':'https://t.me/example'}
        self.assertEqual(telegram_history.next_before(source,body),(40,'more_public_history'))

    def test_article_identity_rejects_foreign_canonical(self):
        body=b'''<script type="application/ld+json">{"@type":"NewsArticle",
        "url":"https://foreign.example/news/1","headline":"Foreign","articleBody":"Content"}</script>'''
        self.assertEqual(structured_rows(body,'https://example.org/news/1'),[])

    def test_youtube_rejects_wrong_owner(self):
        with self.assertRaisesRegex(ValueError,'feed_owner_mismatch'):
            youtube_feed.parse({'platform':'youtube'},b'<feed/>','UC'+'a'*22,10)

    def test_youtube_resolves_without_private_pins(self):
        source={'url':'https://www.youtube.com/channel/UC'+'a'*22}
        self.assertEqual(youtube_feed.resolve(source,None),'UC'+'a'*22)

    def test_partial_results_never_advance_cursor(self):
        rows=core.feed_posts(SOURCE,RSS,10)
        with patch.object(feed_history,'collect',return_value=(rows,'http_429',[],{'pending':[]})):
            result=collect(SOURCE,{'pending':['https://example.org/older']})
        self.assertIsNone(result.checkpoint)
        self.assertEqual(result.posts[0]['external_id'],result.posts[0]['canonical_key'])

    def test_retry_after_propagates(self):
        import urllib.error
        error=urllib.error.HTTPError(SOURCE['url'],429,'limit',{'Retry-After':'120'},None)
        with patch.object(feed_history,'collect',side_effect=error):
            result=collect(SOURCE)
        self.assertEqual(result.status,'http_429')
        self.assertIsNotNone(result.retry_after)

    def test_invalid_platform_and_budget(self):
        with self.assertRaisesRegex(ValueError,'unsupported_platform'):
            collect({'id':'x','platform':'x','url':'https://x.com/example'})
        with self.assertRaisesRegex(ValueError,'invalid_budget'):
            collect(SOURCE,max_pages=0)

    def test_tracking_removal_keeps_identity(self):
        self.assertEqual(clean_permalink('https://example.org/post?id=42&utm_medium=test#part'),
                         'https://example.org/post?id=42')


if __name__=='__main__':unittest.main()
