import importlib.util
import tempfile
import unittest
from pathlib import Path, PurePosixPath

import jinja2

MODULE = Path(__file__).resolve().parents[1] / "render.py"
spec = importlib.util.spec_from_file_location("docs_render", MODULE)
render = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render)


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "docs-src"
        self.stage = self.root / "stage"
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
