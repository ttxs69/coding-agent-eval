from cae.render_markdown import render_markdown


def test_renders_heading():
    html = render_markdown("# Title\n")
    assert "<h1>" in html and "Title" in html


def test_renders_paragraph():
    html = render_markdown("hello world\n")
    assert "<p>" in html and "hello world" in html


def test_renders_code_block():
    md = "```\nfoo\n```\n"
    html = render_markdown(md)
    assert "<pre>" in html and "<code>" in html and "foo" in html


def test_renders_inline_code():
    html = render_markdown("run `cae run` now")
    assert "<code>cae run</code>" in html


def test_renders_link():
    html = render_markdown("see [docs](https://x.com)")
    assert '<a href="https://x.com">docs</a>' in html


def test_renders_doctype_and_body():
    html = render_markdown("# t\n")
    assert html.startswith("<!doctype html>")
    assert "</body>" in html
