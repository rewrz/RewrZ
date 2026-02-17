from rewrz.core.media_attachments import (
    summarize_media_attachments,
    detect_media_flags,
    register_media_attachment_detector,
    unregister_media_attachment_detector,
    list_registered_media_attachment_keys,
    get_default_media_navigation,
)


def test_media_attachment_summary_detects_all_default_types():
    html = """
    <p>text</p>
    <img src="/media/a.jpg">
    <img src="/media/b.jpg">
    <img src="/media/c.jpg">
    <video src="/media/v.mp4"></video>
    <audio src="/media/a.mp3"></audio>
    <a href="https://example.com/article">外链</a>
    """
    summary = summarize_media_attachments(html, featured_image_url="/media/cover.jpg", gallery_threshold=4)
    flags = detect_media_flags(summary)

    assert summary.image_count == 4
    assert flags["images"] is True
    assert flags["gallery"] is True
    assert flags["videos"] is True
    assert flags["audio"] is True
    assert flags["link"] is True


def test_media_attachment_detector_registry_supports_custom_key():
    custom_key = "custom_note"
    try:
        register_media_attachment_detector(custom_key, lambda s: s.has_link and s.has_images)
        assert custom_key in list_registered_media_attachment_keys()

        summary = summarize_media_attachments(
            '<img src="/media/a.jpg"><a href="https://example.com/x">x</a>'
        )
        flags = detect_media_flags(summary)
        assert flags[custom_key] is True
    finally:
        unregister_media_attachment_detector(custom_key)

    assert custom_key not in list_registered_media_attachment_keys()


def test_default_media_navigation_contains_required_keys():
    nav = get_default_media_navigation()
    keys = [item["key"] for item in nav]
    assert keys == ["images", "gallery", "videos", "link", "audio"]
