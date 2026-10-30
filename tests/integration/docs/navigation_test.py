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

class PageStructure(HTMLParser):
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}
    def __init__(self):
        super().__init__(); self.stack = []; self.mains = 0; self.containers = 0; self.headers = 0; self.titles = 0; self.valid = True; self.paths = 0; self.path_lists = 0; self.path_links = []
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'main':
            self.mains += 1; self.valid &= a.get('id') == 'main'
        if tag == 'nw-container':
            self.containers += 1; self.valid &= bool(self.stack) and self.stack[-1][0] == 'main'
        if 'page-header' in a.get('class', '').split():
            self.headers += 1; self.valid &= tag == 'header' and bool(self.stack) and self.stack[-1][0] == 'nw-container'
        if tag == 'nw-page-path':
            self.paths += 1; self.valid &= bool(self.stack) and 'page-header' in self.stack[-1][1].get('class', '').split()
        if any(t == 'nw-page-path' for t, _ in self.stack):
            if tag == 'ol': self.path_lists += 1
            if tag == 'a': self.path_links.append((a['href'], a.get('aria-current')))
            if tag == 'nav': self.valid &= bool(a.get('aria-label', '').strip())
            if tag == 'svg': self.valid &= a.get('aria-hidden') == 'true'
        if tag == 'h1':
            self.titles += 1; self.valid &= any('page-header' in p.get('class', '').split() for _, p in self.stack)
        if 'data-design-navigation' in a:
            self.valid &= not any(t == 'nw-container' for t, _ in self.stack)
        if tag not in self.VOID: self.stack.append((tag, a))
    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]; break

PUBLIC_ROUTES = ['', 'getting-started/', 'guides/networks/', 'guides/request-reply/',
                 'guides/security/', 'reference/api/', 'reference/cli/',
                 'reference/config/', 'reference/admin/']

class ProductNavigationTests(unittest.TestCase):
    def test_product_routes_share_semantic_structure_and_native_current_navigation(self):
        class Product(HTMLParser):
            def __init__(self):
                super().__init__(); self.in_nav = False; self.links = []; self.headings = []
            def handle_starttag(self, tag, attrs):
                a = dict(attrs)
                if tag == 'nav' and a.get('aria-label') == 'Documentation': self.in_nav = True
                if self.in_nav and tag == 'a': self.links.append((a['href'], a.get('aria-current')))
            def handle_endtag(self, tag):
                if tag == 'nav': self.in_nav = False
        for route in PUBLIC_ROUTES:
            page = ROOT/'docs'/route/'index.html'
            with self.subTest(route=route):
                html = page.read_text()
                structure = PageStructure(); structure.feed(html)
                self.assertTrue(structure.valid)
                self.assertEqual((structure.mains, structure.containers, structure.headers,
                                  structure.titles, structure.paths), (1, 1, 1, 1, 1))
                menu = Product(); menu.feed(html)
                targets = []
                for href, current in menu.links:
                    for prefix in ['/', '/nodalwire/']:
                        resolved = urlsplit(urljoin('https://example.test'+prefix+route, href)).path
                        self.assertTrue(resolved.startswith(prefix))
                    target = (page.parent/unquote(urlsplit(href).path)).resolve()
                    if target.is_dir(): target /= 'index.html'
                    self.assertTrue(target.is_file())
                    targets.append(target)
                    if current == 'page': self.assertEqual(target, page.resolve())
                self.assertTrue({(ROOT/'docs'/r/'index.html').resolve() for r in PUBLIC_ROUTES}.issubset(targets))
                self.assertEqual(sum(current == 'page' for _, current in menu.links), 1)


class DesignNavigationTests(unittest.TestCase):
    def test_every_actual_design_page_has_identical_native_navigation(self):
        sources = [p.relative_to(ROOT/'src/docs-src') for p in (ROOT/'src/docs-src/design').rglob('*.html')
                   if not any(s.startswith('_') for s in p.relative_to(ROOT/'src/docs-src').parts)]
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

    def test_every_design_page_has_one_main_container_and_semantic_header(self):
        for page in (ROOT/'docs/design').rglob('index.html'):
            with self.subTest(page=str(page.relative_to(ROOT/'docs'))):
                parser = PageStructure(); parser.feed(page.read_text())
                self.assertTrue(parser.valid)
                self.assertEqual((parser.mains, parser.containers, parser.headers, parser.titles, parser.paths, parser.path_lists), (1, 1, 1, 1, 1, 1))
                relative = page.relative_to(ROOT/'docs')
                expected = [(ROOT/'docs'/Path(*relative.parts[:i])/'index.html').resolve() for i in range(1, len(relative.parts))]
                actual = []
                for href, current in parser.path_links:
                    target = (page.parent/unquote(urlsplit(href).path)).resolve()
                    if target.is_dir(): target /= 'index.html'
                    actual.append(target)
                    self.assertTrue(target.is_file())
                    for prefix in ['/', '/nodalwire/']:
                        resolved = urlsplit(urljoin('https://example.test'+prefix+relative.as_posix(), href)).path
                        self.assertEqual(resolved, prefix+target.parent.relative_to(ROOT/'docs').as_posix()+'/')
                self.assertEqual(actual, expected)
                self.assertEqual([current for _, current in parser.path_links], [None]*(len(expected)-1)+['page'])

    def test_private_includes_not_published_as_pages(self):
        self.assertFalse((ROOT/'docs/design/_include/navigation.html').exists())
        self.assertFalse((ROOT/'docs/design/_include/layout.html').exists())
