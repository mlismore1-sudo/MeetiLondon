import math
from html import escape
from urllib.parse import urlencode, urlsplit

import folium
import streamlit as st
import streamlit.components.v1 as components

from src.db import CATEGORIES, CATEGORY_EMOJIS, COSTS, COST_EMOJI, delete_place
from src.place_editor import show_venue_information
from src.cover_images import cover_image_dialog


def category_multiselect(default=None):
    return st.multiselect("Categories", CATEGORIES, default=default or [], help="Choose as many as apply.")


def cost_select(default="£"):
    return st.selectbox("Cost rating", COSTS, index=COSTS.index(default) if default in COSTS else 0)


def get_place_emojis(place):
    return " ".join(CATEGORY_EMOJIS.get(c, "📍") for c in (place.get("categories") or []))


def get_cost_emojis(place):
    cost = place.get("cost", "£")
    return COST_EMOJI * (COSTS.index(cost) + 1 if cost in COSTS else 1)


def get_cover_photo(visits):
    return next((v["photos"][0] for v in visits if v.get("photos")), None)


def get_coordinates(place):
    try:
        lat, lon = float(place["latitude"]), float(place["longitude"])
    except (KeyError, TypeError, ValueError):
        return None
    if math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180:
        return [lat, lon]
    return None


def make_directions_links(place):
    coords = get_coordinates(place)
    if coords is None:
        return "Directions unavailable: no valid coordinates."
    dest = f"{coords[0]},{coords[1]}"
    google = "https://www.google.com/maps/dir/?" + urlencode({"api": 1, "destination": dest})
    apple = "https://maps.apple.com/?" + urlencode({"daddr": dest, "q": place.get("name", "")})
    return (
        f'<a href="{escape(google, quote=True)}" target="_blank" rel="noopener noreferrer">Google Maps directions</a><br>'
        f'<a href="{escape(apple, quote=True)}" target="_blank" rel="noopener noreferrer">Apple Maps directions</a>'
    )


def render_map(fmap, height):
    components.html(fmap.get_root().render(), height=height + 10, scrolling=False)


def show_photo_grid(photos):
    for start in range(0, len(photos), 3):
        columns = st.columns(3)
        for col, url in zip(columns, photos[start:start + 3]):
            with col:
                st.image(url, use_container_width=True)


def show_place_map(places, visited_place_ids=None, centre=None, zoom=11):
    visited = set(visited_place_ids or [])
    valid = [p for p in places if get_coordinates(p) is not None]
    centre_coords = None
    if centre is not None:
        try:
            centre_coords = get_coordinates({"latitude": centre[0], "longitude": centre[1]})
        except (TypeError, IndexError):
            pass
    location = centre_coords or (get_coordinates(valid[0]) if valid else [51.5074, -0.1278])
    height = 550
    fmap = folium.Map(location=location, zoom_start=zoom, tiles="OpenStreetMap", width="100%", height=height, control_scale=True)
    for place in valid:
        seen = place.get("id") in visited
        name = escape(str(place.get("name", "Unnamed place")))
        cats = escape(", ".join(place.get("categories") or []))
        postcode = escape(str(place.get("postcode") or ""))
        badge = "✅ Visited" if seen else "📍 Yet to visit"
        popup = (
            '<div style="font-family:Arial,sans-serif;min-width:210px;line-height:1.6">'
            f'<strong>{name} {get_place_emojis(place)}</strong><br>{cats}<br>'
            f'{get_cost_emojis(place)} • {postcode}<br>{badge}<br><br>'
            f'{make_directions_links(place)}</div>'
        )
        folium.Marker(get_coordinates(place), popup=folium.Popup(popup, max_width=300),
                      tooltip=f"{name} {get_place_emojis(place)}",
                      icon=folium.Icon(color="green" if seen else "blue", icon="ok" if seen else "info-sign")).add_to(fmap)
    if centre_coords is None and len(valid) > 1:
        fmap.fit_bounds([get_coordinates(p) for p in valid], padding=(35, 35), max_zoom=15)
    render_map(fmap, height)


def show_route_map(places):
    valid = [p for p in places if get_coordinates(p) is not None]
    if not valid:
        st.info("No valid map coordinates are available for these stops.")
        return
    height = 450
    fmap = folium.Map(location=get_coordinates(valid[0]), zoom_start=14, tiles="OpenStreetMap", width="100%", height=height, control_scale=True)
    points = []
    for i, place in enumerate(valid, 1):
        coords = get_coordinates(place)
        points.append(coords)
        name = escape(str(place.get("name", "Unnamed place")))
        icon = (
            '<div style="width:32px;height:32px;border-radius:50%;background:#e85670;'
            'border:3px solid white;color:white;font:bold 15px Arial;display:flex;'
            'align-items:center;justify-content:center;box-shadow:0 2px 6px #777">'
            f'{i}</div>'
        )
        folium.Marker(coords, tooltip=f"{i}. {name}",
                      popup=folium.Popup(f"<strong>{i}. {name}</strong><br>{make_directions_links(place)}", max_width=300),
                      icon=folium.DivIcon(html=icon, icon_size=(38, 38), icon_anchor=(19, 19))).add_to(fmap)
    if len(points) > 1:
        folium.PolyLine(points, color="#e85670", weight=4, dash_array="8, 8").add_to(fmap)
        fmap.fit_bounds(points, padding=(40, 40), max_zoom=16)
    render_map(fmap, height)
    if len(points) > 1:
        st.caption("Dotted lines connect stops, not walking routes. Open Google Maps for navigable directions.")


def delete_controls(place, prefix):
    with st.expander("⚠️ Delete this place"):
        st.warning("Permanently deletes this place and all linked visit diary entries. Uploaded image files remain in Storage. This cannot be undone.")
        confirmed = st.checkbox(f"Yes, permanently delete {place['name']}", key=f"{prefix}_confirm")
        if st.button("Delete place permanently", key=f"{prefix}_delete", disabled=not confirmed, type="primary"):
            try:
                delete_place(place["id"])
            except Exception:
                st.error("Could not delete this place. Check the app logs for details.")
            else:
                st.session_state.pop("selected_place_id", None)
                st.cache_data.clear()
                st.rerun()


@st.dialog("Place details", width="large")
def place_details_dialog(place, visits):
    cover = place.get("cover_image_url") or get_cover_photo(visits)
    if cover:
        st.image(cover, use_container_width=True)
    st.subheader(f"{place['name']} {get_place_emojis(place)}")
    status = "✅ Visited" if visits else "📍 Yet to visit"
    st.caption(f"{get_cost_emojis(place)} • {place.get('postcode', '')} • {status}")
    st.caption(" • ".join(place.get("categories") or []))
    if place.get("notes"):
        st.write(place["notes"])
    st.markdown(make_directions_links(place), unsafe_allow_html=True)
    show_venue_information(place)
    if get_coordinates(place) is not None:
        with st.expander("🗺️ Location"):
            show_place_map([place], {place["id"]} if visits else set(), centre=get_coordinates(place), zoom=15)
    if place.get("cover_image_source"):
        st.caption("Tile image source: " + str(place["cover_image_source"]))
    st.divider()
    st.subheader("Visit history")
    if not visits:
        st.info("No visits recorded yet.")
    for visit in visits:
        st.subheader(str(visit.get("visit_date", "")))
        st.caption("⭐" * (visit.get("rating") or 0))
        if visit.get("diary"):
            st.write(visit["diary"])
        show_photo_grid(visit.get("photos") or [])
        st.divider()
    delete_controls(place, f"dialog_{place['id']}")


def tile_html(place, visits):
    image = place.get("cover_image_url") or ""
    if image:
        try:
            parsed = urlsplit(image)
            if parsed.scheme not in ("https", "http") or not parsed.hostname:
                image = ""
        except ValueError:
            image = ""
    image_html = (
        f'<img src="{escape(image, quote=True)}" alt="" loading="lazy" '
        'style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;" '
        'onerror="this.style.display=String.fromCharCode(110,111,110,101)">'
    ) if image else ""
    name = escape(str(place.get("name", "")))
    postcode = escape(str(place.get("postcode") or ""))
    badge = "✅ Visited" if visits else "📍 Yet to visit"
    return (
        '<div style="position:relative;height:230px;border-radius:12px;overflow:hidden;'
        'background:linear-gradient(135deg,#243b55,#573b61);font-family:Arial,sans-serif;color:white;">'
        + image_html +
        '<div style="position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,.02),rgba(0,0,0,.08) 30%,rgba(0,0,0,.90));"></div>'
        '<div style="position:absolute;top:12px;right:12px;background:rgba(0,0,0,.65);'
        f'border-radius:20px;padding:6px 10px;font-size:12px;">{badge}</div>'
        '<div style="position:absolute;bottom:16px;left:16px;right:16px;">'
        f'<div style="font-size:22px;font-weight:700;line-height:1.2;overflow-wrap:anywhere;">{name}</div>'
        f'<div style="font-size:19px;margin-top:5px;">{get_place_emojis(place)}</div>'
        f'<div style="font-size:13px;margin-top:7px;">{get_cost_emojis(place)} • {postcode}</div>'
        '</div></div>'
    )


def show_place_tile(place, visits, key_prefix="grid_"):
    with st.container(border=True):
        components.html(tile_html(place, visits), height=240, scrolling=False)
        if st.button("Explore place ↗", key=f"{key_prefix}{place['id']}_explore", use_container_width=True):
            place_details_dialog(place, visits)
        if st.button("🖼️ Change background" if place.get("cover_image_url") else "🖼️ Choose background",
                     key=f"{key_prefix}{place['id']}_background", use_container_width=True):
            cover_image_dialog(place)


def show_place_card(place, visits, show_delete=True, key_prefix=""):
    prefix = f"{key_prefix}{place['id']}"
    with st.container(border=True):
        cover = place.get("cover_image_url") or get_cover_photo(visits)
        if cover:
            st.image(cover, use_container_width=True)
        st.subheader(f"{place['name']} {get_place_emojis(place)} {'✅' if visits else ''}")
        st.caption(f"{get_cost_emojis(place)} • {place.get('postcode', '')}")
        st.caption(" • ".join(place.get("categories") or []))
        if place.get("notes"):
            st.write(place["notes"])
        rated = [v["rating"] for v in visits if v.get("rating") is not None]
        if visits:
            st.caption(f"{len(visits)} visits" + (f" • Average {sum(rated) / len(rated):.1f}/5" if rated else ""))
        if st.button("View details ↗", key=f"{prefix}_details", use_container_width=True):
            place_details_dialog(place, visits)
        if st.checkbox("Show location", key=f"{prefix}_location"):
            show_place_map([place], {place["id"]} if visits else set(), centre=get_coordinates(place), zoom=15)
        if show_delete:
            delete_controls(place, prefix)


def show_outing_card(outing, visits):
    with st.container(border=True):
        cover = get_cover_photo(visits)
        if cover:
            st.image(cover, use_container_width=True)
        st.subheader(f"{outing['title']} 🗓️")
        count = len({v["place_id"] for v in visits if v.get("place_id")})
        st.caption(f"{outing.get('outing_date', '')} • {count} places visited")
        if outing.get("notes"):
            st.write(outing["notes"])
        if not visits:
            st.info("No visits linked yet. Select this outing when recording a visit.")
            return
        photos, route = [], []
        for visit in visits:
            place = visit.get("places") or {}
            st.subheader(f"{place.get('name', 'Unknown place')} {get_place_emojis(place)}")
            st.caption(f"{visit.get('visit_date', '')} • {'⭐' * (visit.get('rating') or 0)}")
            if visit.get("diary"):
                st.write(visit["diary"])
            photos.extend(visit.get("photos") or [])
            if get_coordinates(place) is not None:
                route.append(place)
        if photos:
            st.subheader("📸 Photos")
            show_photo_grid(photos)
        if route:
            with st.expander("🗺️ View this outing on a map"):
                show_route_map(route)
