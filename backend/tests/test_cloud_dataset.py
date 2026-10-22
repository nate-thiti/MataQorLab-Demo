import pytest

from app.services.cloud_dataset import microsoft_share_id, normalize_download_url


def test_google_sheet_link_becomes_xlsx_export():
    url = normalize_download_url(
        "google",
        "https://docs.google.com/spreadsheets/d/abc123/edit#gid=42",
    )
    assert url == "https://docs.google.com/spreadsheets/d/abc123/export?format=xlsx&gid=42"


def test_google_sheet_name_is_preserved_for_export():
    url = normalize_download_url(
        "google",
        "https://docs.google.com/spreadsheets/d/abc123/edit",
        "ยอดขาย 2026",
    )
    assert "format=xlsx" in url
    assert "%E0%B8%A2%E0%B8%AD%E0%B8%94" in url


def test_microsoft_link_requests_download():
    url = normalize_download_url(
        "microsoft",
        "https://tenant.sharepoint.com/:x:/r/sites/Finance/report.xlsx?web=1",
    )
    assert "web=1" in url
    assert "download=1" in url


@pytest.mark.parametrize(
    "provider,url",
    [
        ("google", "http://docs.google.com/spreadsheets/d/abc/edit"),
        ("google", "https://example.com/report.xlsx"),
        ("microsoft", "https://127.0.0.1/report.csv"),
        ("microsoft", "file:///tmp/report.csv"),
    ],
)
def test_untrusted_cloud_links_are_rejected(provider, url):
    with pytest.raises(ValueError):
        normalize_download_url(provider, url)


def test_graph_share_id_is_url_safe():
    token = microsoft_share_id("https://1drv.ms/x/s!example")
    assert token.startswith("u!")
    assert "=" not in token
