import importlib.util
import tempfile
import unittest
from pathlib import Path, PurePosixPath

import jinja2

MODULE = Path(__file__).resolve().parents[4] / "src" / "tools" / "docs" / "render.py"
spec = importlib.util.spec_from_file_location("docs_render", MODULE)
render = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render)


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "src" / "docs-src"
        self.stage = self.root / "stage"
        self.source.parent.mkdir(parents=True)
        self.source.mkdir()
        self.stage.mkdir()

    def test_page_urls_survive_a_project_prefix(self):
        self.assertEqual(
            render.page_url(PurePosixPath("index.html"), "design/tokens/"), "design/tokens/"
        )
        self.assertEqual(
            render.page_url(PurePosixPath("design/tokens/index.html"), "assets/app.js"),
            "../../assets/app.js",
        )
        self.assertEqual(render.page_url(PurePosixPath("design/tokens/index.html"), ""), "../../")
        for value in ("/assets/app.js", "../private.json"):
            with self.assertRaises(ValueError):
                render.page_url(PurePosixPath("index.html"), value)

    def test_engrave_renders_context_markdown_and_shared_templates_not_private_pages(self):
        private = self.source / "_layouts"
        private.mkdir()
        (private / "base.html").write_text("<main>{% block content %}{% endblock %}</main>")
        (self.source / "intro.md").write_text("**{{ title }}**")
        (self.source / "index.html").write_text(
            '{% extends "_layouts/base.html" %}{% block content %}'
            '<h1>{{ title }}</h1>{{ markdown("intro.md") }}{% endblock %}'
        )
        render.render_site(self.source, self.stage, {"title": "A & B"})
        html = (self.stage / "index.html").read_text()
        self.assertIn("<h1>A &amp; B</h1>", html)
        self.assertIn("<strong>A &amp; B</strong>", html)
        self.assertFalse((self.stage / "_layouts").exists())
        self.assertTrue((self.stage / ".nojekyll").is_file())

    def test_public_excludes_design_pages_and_showcase_assets_but_dev_preserves_them(self):
        (self.source / "design/tokens").mkdir(parents=True)
        (self.source / "design/tokens/index.html").write_text("<h1>Tokens</h1>")
        (self.source / "assets/design").mkdir(parents=True)
        (self.source / "assets/design/specimen.txt").write_text("development only")
        (self.source / "assets/shared.txt").write_text("shared")
        for name in ("open-menu.svg", "pan-end.svg", "copy.svg"):
            icon = self.source / "assets/icons/gnomicon" / name
            icon.parent.mkdir(parents=True, exist_ok=True)
            icon.write_text("<svg></svg>")
        license_file = self.source / "assets/licenses/gnomicon/NOTICE.md"
        license_file.parent.mkdir(parents=True)
        license_file.write_text("Shared upstream attribution")
        (self.source / "index.html").write_text(
            '{% if development %}<a href="design/tokens/">Tokens</a>{% endif %}'
        )
        render.render_site(self.source, self.stage, {})
        self.assertFalse((self.stage / "design").exists())
        self.assertFalse((self.stage / "assets/design").exists())
        self.assertEqual((self.stage / "assets/shared.txt").read_text(), "shared")
        for name in ("open-menu.svg", "pan-end.svg"):
            self.assertFalse((self.stage / "assets/icons/gnomicon" / name).exists())
        self.assertTrue((self.stage / "assets/icons/gnomicon/copy.svg").is_file())
        self.assertEqual((self.stage / "assets/licenses/gnomicon/NOTICE.md").read_text(),
                         "Shared upstream attribution")
        dev_stage = self.root / "dev-stage"
        dev_stage.mkdir()
        render.render_site(self.source, dev_stage, {}, development=True)
        self.assertTrue((dev_stage / "design/tokens/index.html").is_file())
        self.assertTrue((dev_stage / "assets/design/specimen.txt").is_file())
        for name in ("open-menu.svg", "pan-end.svg", "copy.svg"):
            self.assertTrue((dev_stage / "assets/icons/gnomicon" / name).is_file())
        self.assertTrue((dev_stage / "assets/licenses/gnomicon/NOTICE.md").is_file())

    def test_code_block_macro_escapes_literals_and_preserves_exact_text(self):
        from html.parser import HTMLParser

        class Code(HTMLParser):
            def __init__(self):
                super().__init__(convert_charrefs=True)
                self.inside = False
                self.text = ""
            def handle_starttag(self, tag, attrs):
                if tag == "code": self.inside = True
            def handle_endtag(self, tag):
                if tag == "code": self.inside = False
            def handle_data(self, value):
                if self.inside: self.text += value

        partial = self.source / "_partials"
        partial.mkdir()
        macro = MODULE.parents[2] / "docs-src/_partials/code-block.html"
        (partial / "code-block.html").write_text(macro.read_text())
        (self.source / "index.html").write_text(
            '{% from "_partials/code-block.html" import code_block %}'
            '{{ code_block(example, filename, "python") }}'
        )
        text = '  print("<tag> & café 👋")\r\n\r\n# trailing\n'
        render.render_site(self.source, self.stage, {"example": text, "filename": 'a"<b>.py'})
        html = (self.stage / "index.html").read_bytes().decode()
        self.assertNotIn('<tag>', html)
        self.assertIn('filename="a&#34;&lt;b&gt;.py"', html)
        parsed = Code(); parsed.feed(html)
        self.assertEqual(parsed.text, text)

    def test_missing_template_data_is_a_build_error(self):
        (self.source / "index.html").write_text("{{ missing }}")
        with self.assertRaises(jinja2.UndefinedError):
            render.render_site(self.source, self.stage, {})

    def test_valid_relative_links_and_anchors(self):
        (self.stage / "sub").mkdir()
        (self.stage / "index.html").write_text('<h1 id="home">Home</h1><a href="sub/">Sub</a>')
        (self.stage / "sub/index.html").write_text('<a href="../#home">Back</a>')
        render.validate_links(self.stage)

    def test_invalid_links_and_duplicate_ids_fail(self):
        for link in ("/index.html", "missing.html", "#absent", "../outside.html"):
            (self.stage / "index.html").write_text(f'<a href="{link}">Bad</a>')
            with self.assertRaises(ValueError, msg=link):
                render.validate_links(self.stage)
        (self.stage / "index.html").write_text('<p id="same"></p><p id="same"></p>')
        with self.assertRaises(ValueError):
            render.validate_links(self.stage)

    def test_publish_replaces_only_marked_generated_docs(self):
        output = self.root / "docs"
        output.mkdir()
        (output / "manual.txt").write_text("Do not overwrite")
        with self.assertRaises(ValueError):
            render.publish(self.stage, self.source, output)
        self.assertEqual((output / "manual.txt").read_text(), "Do not overwrite")
        (output / ".nojekyll").write_text("")
        (self.stage / "index.html").write_text("Built")
        render.publish(self.stage, self.source, output)
        self.assertFalse((output / "manual.txt").exists())
        self.assertEqual((output / "index.html").read_text(), "Built")
        with self.assertRaises(ValueError):
            render.publish(self.stage, self.source, self.source)


if __name__ == "__main__":
    unittest.main()
