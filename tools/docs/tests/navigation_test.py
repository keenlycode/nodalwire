"""SSR navigation contracts against canonical renderer output, not source wording."""
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, unquote, urljoin

ROOT = Path(__file__).resolve().parents[3]

class Navigation(HTMLParser):
    def __init__(self):
        super().__init__(); self.nav = None; self.links = {}; self.ids = []; self.duplicates = []; self.groups = {}; self.parents = {}
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if 'id' in a:
            if a['id'] in self.ids: self.duplicates.append(a['id'])
            self.ids.append(a['id'])
        if tag == 'nav':
            self.nav = a.get('aria-label')
            if self.nav in ['Design']:
                self.links[self.nav] = []; self.groups[self.nav] = []; self.parents[self.nav] = []
        if self.nav in ['Design']:
            if tag == 'details': self.groups[self.nav].append('open' in a)
            if 'data-current-parent' in a: self.parents[self.nav].append(a['data-current-parent'])
        if tag == 'a' and self.nav in ['Design']:
            self.links[self.nav].append((a['href'], a.get('aria-current')))
    def handle_endtag(self, tag):
        if tag == 'nav': self.nav = None

class DesignNavigationTests(unittest.TestCase):
    def test_every_actual_design_page_has_identical_native_navigation(self):
        sources = [p.relative_to(ROOT/'docs-src') for p in (ROOT/'docs-src/design').rglob('*.html')
                   if not any(s.startswith('_') for s in p.relative_to(ROOT/'docs-src').parts)]
        self.assertTrue(sources)
        actual_pages = {(ROOT/'docs'/p).resolve() for p in sources}
        landing = (ROOT/'docs/design/index.html').resolve()
        self.assertIn(landing, actual_pages)
        navigable_pages = actual_pages - {landing}
        for relative in sources:
            with self.subTest(page=str(relative)):
                page = ROOT/'docs'/relative; parser = Navigation(); parser.feed(page.read_text())
                self.assertFalse(parser.duplicates)
                top = parser.links['Design']; self.assertEqual(list(parser.links), ['Design'])
                self.assertNotIn('<nw-top-navigation', page.read_text())
                self.assertNotIn('<nw-bottom-navigation', page.read_text())
                self.assertEqual(page.read_text().count('data-design-navigation'), 1)
                is_landing = page.resolve() == landing
                expected_parent = [] if is_landing else [relative.parts[1]]
                for nav in ['Design']:
                    self.assertEqual(parser.groups[nav], [True, True])
                    self.assertEqual(parser.parents[nav], expected_parent)
                targets = []
                for href, current in top:
                    self.assertFalse(urlsplit(href).fragment, 'Shared navigation must use real page URLs')
                    for prefix in ['/', '/nodalwire/']:
                        resolved = urljoin('https://example.test'+prefix+relative.as_posix(), href)
                        self.assertTrue(urlsplit(resolved).path.startswith(prefix+'design/'))
                    target = (page.parent/unquote(urlsplit(href).path)).resolve()
                    if target.is_dir(): target /= 'index.html'
                    targets.append(target)
                    self.assertTrue(target.is_file())
                    self.assertIn(target, actual_pages)
                    if current == 'page': self.assertEqual(target, page.resolve())
                self.assertTrue(navigable_pages.issubset(targets))
                self.assertEqual(sum(current == 'page' for _, current in top), 0 if is_landing else 1)

    def test_private_includes_not_published_as_pages(self):
        self.assertFalse((ROOT/'docs/design/_include/navigation.html').exists())
        self.assertFalse((ROOT/'docs/design/_include/layout.html').exists())
