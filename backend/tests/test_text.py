from app.core.text import html_to_text, truncate


def test_greenhouse_style_escaped_html_is_unescaped_and_stripped():
    raw = "&lt;p&gt;We are hiring.&lt;/p&gt;&lt;ul&gt;&lt;li&gt;Python&lt;/li&gt;&lt;li&gt;SQL&lt;/li&gt;&lt;/ul&gt;"
    text = html_to_text(raw)
    assert "<" not in text and "&lt;" not in text
    assert "We are hiring." in text
    assert "• Python" in text and "• SQL" in text


def test_plain_text_passes_through():
    assert html_to_text("Just text\n\n\n\nmore") == "Just text\n\nmore"


def test_scripts_and_styles_are_dropped():
    assert html_to_text("<p>Hi</p><script>alert(1)</script><style>p{}</style>") == "Hi"


def test_none_and_empty():
    assert html_to_text(None) == ""
    assert html_to_text("") == ""


def test_markup_overhead_is_really_removed():
    raw = "&lt;div class=\"x\"&gt;&lt;p&gt;" + "word " * 50 + "&lt;/p&gt;&lt;/div&gt;"
    text = html_to_text(raw)
    assert text == ("word " * 50).strip()
    assert len(raw) - len(text) >= 40       # the markup is gone


def test_truncate_prefers_boundaries():
    text = "A" * 50 + ". " + "B" * 50
    out = truncate(text, 60)
    assert out.startswith("A" * 50) and "B" not in out and out.endswith("[truncated]")
    assert truncate("short", 100) == "short"
