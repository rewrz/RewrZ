from rewrz.core.url_normalizer import normalize_local_asset_url, normalize_local_asset_url_lines


def test_normalize_local_static_asset_url_to_relative_path():
    assert normalize_local_asset_url("http://127.0.0.1:8000/static/images/bg/1.jpg") == "/static/images/bg/1.jpg"
    assert normalize_local_asset_url("http://localhost:9999/media/uploads/demo.png") == "/media/uploads/demo.png"


def test_keep_remote_and_relative_urls_unchanged():
    assert normalize_local_asset_url("/static/images/bg/1.jpg") == "/static/images/bg/1.jpg"
    assert normalize_local_asset_url("https://cdn.example.com/static/images/bg/1.jpg") == "https://cdn.example.com/static/images/bg/1.jpg"
    assert normalize_local_asset_url("https://example.com/anything") == "https://example.com/anything"


def test_normalize_multiline_local_asset_urls():
    raw = "http://127.0.0.1:8000/static/images/bg/1.jpg\nhttps://cdn.example.com/a.jpg\nhttp://localhost:9999/media/demo.png"
    assert normalize_local_asset_url_lines(raw) == "/static/images/bg/1.jpg\nhttps://cdn.example.com/a.jpg\n/media/demo.png"
