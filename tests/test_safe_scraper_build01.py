import pytest
from utils.safe_scraper import FetchError, _validate_destination, _public_ips, parse_html

@pytest.mark.parametrize('target', [
    'http://localhost/', 'http://127.0.0.1/', 'http://192.168.1.1/',
    'http://10.0.0.5/', 'http://example.com:8080/',
    'file:///etc/passwd', 'https://user:pass@example.com',
])
def test_reject_unsafe_targets(target):
    if target.startswith('http://192.') or target.startswith('http://10.') or target.startswith('http://127.'):
        # Numeric IP checks happen at resolved address stage.
        with pytest.raises(FetchError):
            _public_ips(target.split('/')[2], 80)
    else:
        with pytest.raises(FetchError):
            _validate_destination(target)


def test_reject_any_mixed_private_dns_answer(monkeypatch):
    import socket
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *_args, **_kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443))
    ])
    with pytest.raises(FetchError, match='restricted'):
        _public_ips('example.com', 443)


def test_html_extracts_metadata_and_headings():
    words = ' '.join(['A useful paragraph describes renewable energy plans for households.'] * 12)
    html = f'<html><head><title>Test title</title><meta name="description" content="Example description"></head><body><header>Menu</header><main><h1>Our services</h1><p>{words}</p><a href="/about">About</a></main><script>ignored</script></body></html>'
    result = parse_html('https://example.com/', html)
    assert result.success
    assert result.title == 'Test title'
    assert result.meta_description == 'Example description'
    assert result.headings['h1'] == ['Our services']
    assert 'https://example.com/about' in result.internal_links
    assert 'ignored' not in (result.body_text or '')
