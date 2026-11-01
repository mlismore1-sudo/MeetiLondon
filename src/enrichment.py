import http.client
import ipaddress
import json
import socket
import ssl
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

MAX_BYTES = 2_000_000


def normalise_url(value):
    value = value.strip()
    if not value:
        return ""
    if "://" not in value:
        value = "https://" + value
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("Use a valid http:// or https:// website address.")
    if parts.username or parts.password:
        raise ValueError("Website addresses cannot contain login details.")
    if parts.port not in (None, 80, 443):
        raise ValueError("Only standard website ports are supported.")
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", parts.query, ""))


def fetch_page(value):
    url = normalise_url(value)
    if not url:
        raise ValueError("Add the venue's website first.")
    for _ in range(4):
        parts = urlsplit(url)
        host = parts.hostname.encode("idna").decode("ascii")
        port = parts.port or (443 if parts.scheme == "https" else 80)
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        if not addresses:
            raise ValueError("The website could not be found.")
        for address in addresses:
            if not ipaddress.ip_address(address[4][0]).is_global:
                raise ValueError("Only public internet websites can be fetched.")
        ip = addresses[0][4][0]
        raw_socket = socket.create_connection((ip, port), timeout=10)
        conn = None
        try:
            if parts.scheme == "https":
                conn = http.client.HTTPSConnection(host, port, timeout=10)
                conn.sock = ssl.create_default_context().wrap_socket(raw_socket, server_hostname=host)
            else:
                conn = http.client.HTTPConnection(host, port, timeout=10)
                conn.sock = raw_socket
            path = parts.path or "/"
            if parts.query:
                path += "?" + parts.query
            conn.request("GET", path, headers={
                "User-Agent": "LondonAdventuresHoursChecker/1.0",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Encoding": "identity",
            })
            response = conn.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                if not location:
                    raise ValueError("The website returned an invalid redirect.")
                url = normalise_url(urljoin(url, location))
                continue
            if response.status != 200:
                raise ValueError(f"The website returned HTTP {response.status}. Try its branch page instead.")
            content_type = response.getheader("Content-Type", "").lower()
            if "html" not in content_type:
                raise ValueError("This link is not an HTML web page.")
            if response.getheader("Content-Encoding", "identity").lower() not in ("", "identity"):
                raise ValueError("This website uses an unsupported response encoding.")
            data = response.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ValueError("This page is too large. Try a simpler branch/contact page.")
            return url, data.decode("utf-8", errors="replace")
        finally:
            if conn is not None:
                conn.close()
            raw_socket.close()
    raise ValueError("Too many website redirects.")


class StructuredDataParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.active = False
        self.buffer = []
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.active = dict(attrs).get("type", "").lower().split(";")[0].strip() == "application/ld+json"
            self.buffer = []

    def handle_data(self, data):
        if self.active:
            self.buffer.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.active:
            self.scripts.append("".join(self.buffer))
            self.active = False


def walk(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def hours_text(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(filter(None, (hours_text(item) for item in value)))
    if not isinstance(value, dict):
        return ""
    days = value.get("dayOfWeek", [])
    if isinstance(days, str):
        days = [days]
    days = ", ".join(str(d).rstrip("/").split("/")[-1].split("#")[-1] for d in days)
    opens, closes = value.get("opens"), value.get("closes")
    if opens is None and closes is None:
        return ""
    text = f"{days or 'Days not specified'}: {opens or '?'} – {closes or '?'}"
    if value.get("validFrom") or value.get("validThrough"):
        text += f" (valid {value.get('validFrom', '?')} to {value.get('validThrough', '?')})"
    return text


def extract_hours(website):
    source, html = fetch_page(website)
    parser = StructuredDataParser()
    parser.feed(html)
    candidates, seen = [], set()
    for script in parser.scripts:
        try:
            data = json.loads(script.strip())
        except (ValueError, TypeError):
            continue
        for node in walk(data):
            regular = hours_text(node.get("openingHoursSpecification")) or hours_text(node.get("openingHours"))
            special = hours_text(node.get("specialOpeningHoursSpecification"))
            if not regular and not special:
                continue
            text = regular
            if special:
                text += "\n\nSpecial/date-specific hours (may override regular hours):\n" + special
            name = str(node.get("name") or "Unnamed venue/service")
            address = node.get("address") or {}
            if isinstance(address, dict):
                address = ", ".join(str(address.get(k)) for k in ("streetAddress", "addressLocality", "postalCode") if address.get(k))
            label = name + (f" — {address}" if address else "")
            signature = (label, text)
            if signature not in seen:
                seen.add(signature)
                candidates.append({"label": label, "hours": text.strip(), "source": source})
    return candidates
