import http.client
import ipaddress
import json
import logging
import socket
import ssl
import uuid
import warnings
from datetime import datetime, timezone
from html.parser import HTMLParser
from io import BytesIO
from urllib.parse import urljoin, urlsplit

import streamlit as st
from PIL import Image, ImageOps, UnidentifiedImageError
from src.db import get_supabase
from src.enrichment import fetch_page, normalise_url

logger = logging.getLogger(__name__)
BUCKET = "date-night-photos"
MAX_BYTES = 8_000_000


def image_urls(value):
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [url for item in value for url in image_urls(item)]
    if isinstance(value, dict):
        return image_urls(value.get("contentUrl") or value.get("url") or [])
    return []


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


class LogoParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.candidates = []
        self.scripts = []
        self.buffer = []
        self.active = False
        self.header_depth = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "header":
            self.header_depth += 1
        if tag == "script":
            self.active = a.get("type", "").lower().split(";")[0].strip() == "application/ld+json"
            self.buffer = []
        if tag == "img":
            text = " ".join(a.get(k, "") for k in ("alt", "class", "id", "src", "data-src")).lower()
            src = a.get("data-src") or a.get("data-lazy-src") or a.get("src")
            if src and "logo" in text:
                self.candidates.append((1 if self.header_depth else 2, "Website logo candidate", src))
        if tag == "link":
            rel = a.get("rel", "").lower().split()
            href = a.get("href")
            if href and any(r in rel for r in ("apple-touch-icon", "apple-touch-icon-precomposed")):
                self.candidates.append((3, "Touch icon fallback", href))
            elif href and "icon" in rel:
                self.candidates.append((4, "Site icon fallback", href))
        if tag == "meta":
            name = (a.get("property") or a.get("name") or "").lower()
            if name in ("og:image", "og:image:url", "og:image:secure_url", "twitter:image", "twitter:image:src") and a.get("content"):
                self.candidates.append((5, "General image fallback — may not be a logo", a["content"]))

    def handle_data(self, value):
        if self.active:
            self.buffer.append(value)

    def handle_endtag(self, tag):
        if tag == "script" and self.active:
            self.scripts.append("".join(self.buffer))
            self.active = False
        if tag == "header":
            self.header_depth = max(0, self.header_depth - 1)


def discover_images(website):
    source, html = fetch_page(website)
    parser = LogoParser()
    parser.feed(html)
    candidates = list(parser.candidates)
    for script in parser.scripts:
        try:
            data = json.loads(script)
        except (ValueError, TypeError):
            continue
        for node in walk(data):
            for url in image_urls(node.get("logo")):
                candidates.append((0, "Structured-data logo", url))
    results, seen = [], set()
    for priority, label, value in sorted(candidates, key=lambda item: item[0]):
        try:
            url = normalise_url(urljoin(source, value.strip()))
        except (ValueError, TypeError):
            continue
        if url and url not in seen:
            seen.add(url)
            results.append({"url": url, "label": label})
    return source, results[:16]


def download_image(url):
    url = normalise_url(url)
    for _ in range(4):
        parts = urlsplit(url)
        host = parts.hostname.encode("idna").decode("ascii")
        port = parts.port or (443 if parts.scheme == "https" else 80)
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ValueError("Only public internet image addresses are allowed.")
        raw = socket.create_connection((addresses[0][4][0], port), timeout=10)
        conn = None
        try:
            if parts.scheme == "https":
                conn = http.client.HTTPSConnection(host, port, timeout=10)
                conn.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
            else:
                conn = http.client.HTTPConnection(host, port, timeout=10)
                conn.sock = raw
            path = parts.path or "/"
            if parts.query:
                path += "?" + parts.query
            conn.request("GET", path, headers={"User-Agent": "LondonAdventuresLogoChecker/1.0", "Accept": "image/*", "Accept-Encoding": "identity"})
            response = conn.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                if not location:
                    raise ValueError("Invalid image redirect.")
                url = normalise_url(urljoin(url, location))
                continue
            if response.status != 200:
                raise ValueError(f"The image server returned HTTP {response.status}.")
            content_type = response.getheader("Content-Type", "").lower()
            if "svg" in content_type:
                raise ValueError("This logo is an SVG. This version supports raster images only; select another suggestion.")
            if not content_type.startswith("image/"):
                raise ValueError("The URL did not return an image.")
            data = response.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ValueError("The image is too large (maximum 8 MB).")
            return data
        finally:
            if conn is not None:
                conn.close()
            raw.close()
    raise ValueError("Too many image redirects.")


def prepare_image(data, background="White"):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as original:
                if original.width * original.height > 20_000_000:
                    raise ValueError("The image has too many pixels.")
                if min(original.size) < 32:
                    raise ValueError("This icon is too small for a useful tile image.")
                small = original.width < 160 or original.height < 80
                image = ImageOps.exif_transpose(original).convert("RGBA")
                # Keep the entire logo; reserve the lower area for the tile text.
                image.thumbnail((900, 360), Image.Resampling.LANCZOS)
                canvas = Image.new("RGBA", (1200, 750), "#ffffff" if background == "White" else "#202733")
                x = (canvas.width - image.width) // 2
                y = 80 + (360 - image.height) // 2
                canvas.alpha_composite(image, (x, y))
                result = BytesIO()
                canvas.convert("RGB").save(result, format="JPEG", quality=90, optimize=True)
                return result.getvalue(), small
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ValueError("This image format could not be safely processed. Try another suggestion.") from error


def clear_draft(prefix):
    for key in list(st.session_state):
        if key.startswith(prefix):
            del st.session_state[key]


@st.dialog("Choose a venue logo", width="large")
def cover_image_dialog(place):
    prefix = f"logo_{place['id']}_"
    st.subheader(place["name"])
    st.caption("Logo-first lookup. Preview and approve before changing the tile. Existing backgrounds stay unchanged until you save.")
    if place.get("cover_image_url"):
        st.image(place["cover_image_url"], use_container_width=True)
        st.caption("Current approved tile background")
    website = place.get("website") or ""
    if not website:
        st.info("Add and save the branch website through All Places → Edit a place first.")
    else:
        st.write("Website: " + website)
        if st.button("Find website logos", key=prefix + "find"):
            try:
                with st.spinner("Looking for logos and site icons…"):
                    source, candidates = discover_images(website)
                st.session_state[prefix + "candidates"] = candidates
                st.session_state.pop(prefix + "preview", None)
                if not candidates:
                    st.info("No logo candidates were found on this page. Try the venue homepage as its saved website. Nothing has been changed.")
            except Exception as error:
                logger.exception("Logo discovery failed")
                st.error(str(error) if isinstance(error, ValueError) else "The website could not be read. It may block automated access.")
        candidates = st.session_state.get(prefix + "candidates", [])
        if candidates:
            selected = st.selectbox("Suggested logos and fallbacks", range(len(candidates)),
                format_func=lambda i: f"{i + 1}. {candidates[i]['label']} — {urlsplit(candidates[i]['url']).hostname}", key=prefix + "candidate")
            candidate = candidates[selected]
            background = st.radio("Logo background", ["White", "Charcoal"], horizontal=True, key=prefix + "background")
            st.caption(candidate["url"])
            if st.button("Load logo preview", key=prefix + "preview_button"):
                try:
                    with st.spinner("Preparing an uncropped logo preview…"):
                        preview, small = prepare_image(download_image(candidate["url"]), background)
                    st.session_state[prefix + "preview"] = preview
                    st.session_state[prefix + "signature"] = (candidate["url"], background)
                    st.session_state[prefix + "small"] = small
                except Exception as error:
                    logger.exception("Logo preview failed")
                    st.error(str(error) if isinstance(error, ValueError) else "The logo could not be loaded. Try another suggestion.")
            preview = st.session_state.get(prefix + "preview")
            if preview and st.session_state.get(prefix + "signature") == (candidate["url"], background):
                st.image(preview, use_container_width=True)
                if st.session_state.get(prefix + "small"):
                    st.warning("This icon is small and may not fill much of the tile. A higher-resolution logo will look better.")
                st.caption("The logo is preserved with padding. The tile will add a dark gradient and its text overlay. Preview is not proof of correct venue identity.")
                approved = st.checkbox("I approve this logo and have permission to reuse it", key=prefix + "permission")
                if st.button("Approve and save logo background", type="primary", disabled=not approved, key=prefix + "save"):
                    path = f"covers/{place['id']}/{uuid.uuid4()}.jpg"
                    client = get_supabase()
                    uploaded = False
                    try:
                        with st.spinner("Saving your approved logo…"):
                            client.storage.from_(BUCKET).upload(path=path, file=preview, file_options={"content-type": "image/jpeg"})
                            uploaded = True
                            url = client.storage.from_(BUCKET).get_public_url(path)
                            response = client.table("places").update({
                                "cover_image_url": url, "cover_image_source": candidate["url"],
                                "cover_image_approved_at": datetime.now(timezone.utc).isoformat(),
                            }).eq("id", place["id"]).execute()
                            if not response.data:
                                raise ValueError("No updated row returned. Check the place exists and UPDATE permissions.")
                    except Exception as error:
                        logger.exception("Logo save failed")
                        if uploaded:
                            try:
                                client.storage.from_(BUCKET).remove([path])
                            except Exception:
                                logger.warning("Unattached logo could not be removed", exc_info=True)
                        st.error(str(error) if isinstance(error, ValueError) else "Could not save the logo. Check Storage uploads and database UPDATE permissions in the logs.")
                    else:
                        clear_draft(prefix)
                        st.cache_data.clear()
                        st.session_state["flash_message"] = "Approved logo background saved."
                        st.rerun()
    if place.get("cover_image_url"):
        st.divider()
        confirmed = st.checkbox("Remove this place's approved background", key=prefix + "remove_confirm")
        if st.button("Remove background", disabled=not confirmed, key=prefix + "remove"):
            try:
                response = get_supabase().table("places").update({"cover_image_url": None, "cover_image_source": None, "cover_image_approved_at": None}).eq("id", place["id"]).execute()
                if not response.data:
                    raise ValueError("No updated row returned.")
            except Exception:
                logger.exception("Background removal failed")
                st.error("The background could not be removed.")
            else:
                clear_draft(prefix)
                st.cache_data.clear()
                st.session_state["flash_message"] = "Background removed; stored image files retained."
                st.rerun()
