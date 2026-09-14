"""Read user-specified public pages with pinned DNS, bounded payloads and no secrets."""
import asyncio
import hashlib
import ipaddress
import socket
from html.parser import HTMLParser
from urllib.parse import urlsplit,urljoin
import httpx
from .db import now

MAX_BYTES=1024*1024
MAX_TEXT=20000

def is_public(value):
    ip=ipaddress.ip_address(value)
    if not ip.is_global or ip.is_multicast or ip.is_reserved:return False
    if ip.version==6 and (ip.sixtofour or ip.teredo or ip in ipaddress.ip_network('64:ff9b::/96') or ip in ipaddress.ip_network('64:ff9b:1::/48')):return False
    return True


def checked_url(value):
    if len(value)>2000 or any(ord(c)<32 or c.isspace() for c in value):raise ValueError('网页地址含空白或超过长度限制')
    try:
        parts=urlsplit(value);port=parts.port
        if parts.scheme not in ('http','https') or not parts.hostname or parts.username is not None or parts.password is not None:raise ValueError()
        if port not in (None,80 if parts.scheme=='http' else 443):raise ValueError()
        host=parts.hostname.encode('idna').decode('ascii').lower().rstrip('.')
        if not host or '%' in host or host=='localhost' or host.endswith(('.localhost','.local','.internal')):raise ValueError()
        try:address=ipaddress.ip_address(host)
        except ValueError:address=None
        if address and not is_public(host):raise ValueError()
    except (ValueError,UnicodeError):raise ValueError('仅允许不带凭据的公开 HTTP/HTTPS 网页及标准端口') from None
    try:return httpx.URL(value).copy_with(fragment=None)
    except httpx.InvalidURL:raise ValueError('网页地址格式无效') from None


async def public_addresses(host,port):
    try:
        rows=await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(host,port,type=socket.SOCK_STREAM),5)
        addresses=list(dict.fromkeys(row[4][0] for row in rows))
        if not addresses or any(not is_public(ip) for ip in addresses):raise ValueError('网页地址解析到了非公开网络，已停止读取')
        return addresses
    except (OSError,TimeoutError):raise ValueError('网页域名解析失败或超时') from None


class TextParser(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.skip=0;self.parts=[];self.title=[];self.in_title=False
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','noscript','template','svg'):self.skip+=1
        if tag=='title':self.in_title=True
        if not self.skip and tag in ('p','div','br','li','h1','h2','h3','tr','section','article'):self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript','template','svg') and self.skip:self.skip-=1
        if tag=='title':self.in_title=False
        if not self.skip and tag in ('p','div','li','h1','h2','h3','tr','section','article'):self.parts.append('\n')
    def handle_data(self,data):
        if self.in_title:self.title.append(data)
        if not self.skip:self.parts.append(data)


class PublicPages:
    def __init__(self,transport=None,resolver=public_addresses):self.transport=transport;self.resolve=resolver;self.limit=asyncio.Semaphore(2);self.timeout=20
    async def fetch(self,value):
        async with self.limit:
            try:
                async with asyncio.timeout(self.timeout):return await self._fetch(value)
            except TimeoutError:raise ValueError('网页读取超过 20 秒') from None
            except (httpx.HTTPError,UnicodeError,LookupError):raise ValueError('网页读取失败，请核对地址或改用上传材料') from None
    async def _fetch(self,value):
        url=checked_url(value);redirects=[]
        for hop in range(4):
            addresses=await self.resolve(url.host,url.port or (443 if url.scheme=='https' else 80))
            # Connect to the validated IP, but retain original host for HTTP and TLS verification.
            pinned=url.copy_with(host=addresses[0])
            async with httpx.AsyncClient(transport=self.transport,trust_env=False,follow_redirects=False,timeout=10) as client:
                async with client.stream('GET',pinned,headers={'Host':url.netloc.decode(),'User-Agent':'Ludraft/1.0 research-reader','Accept':'text/html,text/plain,text/markdown','Accept-Encoding':'identity'},extensions={'sni_hostname':url.host}) as response:
                    if response.status_code in (301,302,303,307,308):
                        location=response.headers.get('location')
                        if not location or hop==3:raise ValueError('网页重定向过多或缺少目标地址')
                        redirects.append(str(url));url=checked_url(urljoin(str(url),location));continue
                    if response.status_code!=200:raise ValueError(f'网页返回 HTTP {response.status_code}，未形成有效来源')
                    content_type=response.headers.get('content-type','').split(';',1)[0].strip().lower()
                    if content_type not in ('text/html','text/plain','text/markdown'):raise ValueError('网页类型不支持，请上传 PDF/文档材料')
                    if response.headers.get('content-encoding','identity').lower() not in ('','identity'):raise ValueError('网页未提供未压缩文本响应，请改用上传材料')
                    body=bytearray()
                    async for chunk in response.aiter_raw():
                        if len(body)+len(chunk)>MAX_BYTES:raise ValueError('网页正文超过 1 MB，请上传精简材料')
                        body.extend(chunk)
                    encoding=response.encoding or 'utf-8';raw=bytes(body).decode(encoding,errors='replace')
                    if raw.count('\ufffd')>max(2,len(raw)*.01):raise ValueError('网页编码无法可靠识别，请上传核对后的文字')
                    title=''
                    if content_type=='text/html':
                        parser=TextParser();parser.feed(raw);text=''.join(parser.parts);title=' '.join(''.join(parser.title).split())[:200]
                    else:text=raw
                    text='\n'.join(line for line in (' '.join(x.split()) for x in text.splitlines()) if line)
                    if len(text.strip())<20:raise ValueError('网页没有足够可读取文字，可能需要登录或脚本渲染')
                    truncated=len(text)>MAX_TEXT;text=text[:MAX_TEXT]
                    return {'label':title or str(url),'url':value,'final_url':str(url),'redirects':redirects,'fetched_at':now(),'text':text,
                        'sha256':hashlib.sha256(text.encode()).hexdigest(),'body_sha256':hashlib.sha256(body).hexdigest(),'truncated':truncated}
        raise ValueError('网页未形成有效来源')
