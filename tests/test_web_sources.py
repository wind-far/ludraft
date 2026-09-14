import asyncio
import hashlib
import socket
import httpx
import pytest
from studio.web_sources import PublicPages,checked_url,public_addresses,MAX_BYTES,MAX_TEXT

class Body(httpx.AsyncByteStream):
    def __init__(self,data):self.data=data
    async def __aiter__(self):yield self.data

async def public(host,port):return ['93.184.216.34']

@pytest.mark.parametrize('url',['file:///etc/passwd','https://user:pass@example.org','http://127.0.0.1','http://[::1]','http://10.0.0.1','http://169.254.169.254','http://localhost','https://test.local','https://example.org:8080','https://example.org\n/header','http://224.0.0.1','http://[2002:7f00:1::]'])
def test_rejects_non_public_url_forms(url):
    with pytest.raises(ValueError):checked_url(url)

@pytest.mark.asyncio
async def test_dns_mixed_private_answers_block_entire_host(monkeypatch):
    async def resolve(*args,**kwargs):return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('93.184.216.34',443)),(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))]
    monkeypatch.setattr(asyncio.get_running_loop(),'getaddrinfo',resolve)
    with pytest.raises(ValueError,match='非公开'):await public_addresses('example.org',443)

@pytest.mark.asyncio
async def test_pins_ip_preserves_host_tls_and_extracts_only_text():
    requests=[]
    async def handler(req):
        requests.append(req)
        return httpx.Response(200,headers={'Content-Type':'text/html; charset=utf-8'},stream=Body('<html><title>三消资料</title><script>SECRET SCRIPT</script><style>HIDDEN CSS</style><p>三消方向比较资料，包含明确的来源与设计建议。</p></html>'.encode()))
    pages=PublicPages(httpx.MockTransport(handler),public);r=await pages.fetch('https://example.org/design#part')
    assert requests[0].url.host=='93.184.216.34' and requests[0].headers['host']=='example.org'
    assert requests[0].extensions['sni_hostname']=='example.org'
    assert not any(k in requests[0].headers for k in ['authorization','cookie'])
    assert 'SECRET' not in r['text'] and 'HIDDEN' not in r['text'] and '三消方向比较' in r['text']
    assert r['sha256']==hashlib.sha256(r['text'].encode()).hexdigest() and r['final_url']=='https://example.org/design'

@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['redirect_private','redirect_loop','error','type','compressed','large','empty'])
async def test_failed_web_reads_never_create_sources(failure):
    requests=[]
    async def handler(req):
        requests.append(req)
        if failure.startswith('redirect'):return httpx.Response(302,headers={'Location':'http://127.0.0.1/secret' if failure=='redirect_private' else '/loop'},stream=Body(b''))
        headers={'Content-Type':'text/plain'};data=b'public reference text for match3 design'
        if failure=='type':headers['Content-Type']='application/pdf'
        if failure=='compressed':headers['Content-Encoding']='gzip'
        if failure=='large':data=b'x'*(MAX_BYTES+1)
        if failure=='empty':data=b' '
        return httpx.Response(403 if failure=='error' else 200,headers=headers,stream=Body(data))
    with pytest.raises(ValueError):await PublicPages(httpx.MockTransport(handler),public).fetch('https://example.org/')
    assert len(requests)==(4 if failure=='redirect_loop' else 1)

@pytest.mark.asyncio
async def test_redirect_does_not_forward_cookies_and_truncation_is_explicit():
    requests=[]
    async def handler(req):
        requests.append(req)
        if len(requests)==1:return httpx.Response(302,headers={'Location':'https://other.example/design','Set-Cookie':'session=secret'},stream=Body(b''))
        return httpx.Response(200,headers={'Content-Type':'text/plain'},stream=Body(b'x'*(MAX_TEXT+1)))
    r=await PublicPages(httpx.MockTransport(handler),public).fetch('https://example.org/')
    assert r['truncated'] and len(r['text'])==MAX_TEXT and len(r['redirects'])==1
    assert 'cookie' not in requests[1].headers and requests[1].headers['host']=='other.example'

@pytest.mark.asyncio
async def test_cancel_closes_active_response():
    entered=asyncio.Event();closed=asyncio.Event()
    class Pending(httpx.AsyncByteStream):
        async def __aiter__(self):
            entered.set();await asyncio.Event().wait();yield b''
        async def aclose(self):closed.set()
    async def handler(req):return httpx.Response(200,headers={'Content-Type':'text/plain'},stream=Pending())
    task=asyncio.create_task(PublicPages(httpx.MockTransport(handler),public).fetch('https://example.org/'))
    await asyncio.wait_for(entered.wait(),2);task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    assert closed.is_set()


@pytest.mark.asyncio
async def test_wall_timeout_closes_slow_response():
    closed=asyncio.Event()
    class Slow(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'initial text';await asyncio.Event().wait()
        async def aclose(self):closed.set()
    async def handler(req):return httpx.Response(200,headers={'Content-Type':'text/plain'},stream=Slow())
    pages=PublicPages(httpx.MockTransport(handler),public);pages.timeout=.05
    with pytest.raises(ValueError,match='超过 20 秒'):await pages.fetch('https://example.org/')
    assert closed.is_set()
