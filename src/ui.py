import math
from html import escape
from urllib.parse import urlencode

import folium
import streamlit as st
import streamlit.components.v1 as components

from src.db import (
    CATEGORIES,
    CATEGORY_EMOJIS,
    COSTS,
    COST_EMOJI,
    delete_place,
)


def category_multiselect(default=None):
    return st.multiselect(
        "Categories",
        options=CATEGORIES,
        default=default or [],
        help="Choose as many as apply.",
    )


def cost_select(default="£"):
    selected_default = default if default in COSTS else COSTS[0]

    return st.selectbox(
        "Cost rating",
        options=COSTS,
        index=COSTS.index(selected_default),
    )


def get_place_emojis(place):
    return " ".join(
        CATEGORY_EMOJIS.get(category, "📍")
        for category in (place.get("categories") or [])
    )


def get_cost_emojis(place):
    cost = place.get("cost", COSTS[0])

    try:
        level = COSTS.index(cost) + 1
    except ValueError:
        level = 1

    return COST_EMOJI * level


def get_cover_photo(visits):
    for visit in visits:
        photos = visit.get("photos") or []

        if photos:
            return photos[0]

    return None


def get_coordinates(place):
    try:
        latitude = float(place["latitude"])
        longitude = float(place["longitude"])
    except (KeyError, TypeError, ValueError):
        return None

    if not math.isfinite(latitude) or not math.isfinite(longitude):
        return None

    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None

    return [latitude, longitude]


def make_directions_links(place):
    coordinates = get_coordinates(place)

    if coordinates is None:
        return "Directions unavailable: this place has no valid coordinates."

    destination = f"{coordinates[0]},{coordinates[1]}"

    google_url = (
        "https://www.google.com/maps/dir/?"
        + urlencode(
            {
                "api": "1",
                "destination": destination,
            }
        )
    )

    apple_url = (
        "https://maps.apple.com/?"
        + urlencode(
            {
                "daddr": destination,
                "q": place.get("name", ""),
            }
        )
    )

    return (
        f'<a href="{escape(google_url, quote=True)}" '
        'target="_blank" rel="noopener noreferrer">'
        "Google Maps directions</a><br>"
        f'<a href="{escape(apple_url, quote=True)}" '
        'target="_blank" rel="noopener noreferrer">'
        "Apple Maps directions</a>"
    )


def render_map(fmap, height):
    components.html(
        fmap.get_root().render(),
        height=height + 10,
        scrolling=False,
    )


def show_photo_grid(photos):
    if not photos:
        return

    columns = st.columns(3)

    for index, url in enumerate(photos):
        with columns[index % 3]:
            st.image(url, use_container_width=True)


@st.dialog("Place details", width="large")
def place_details_dialog(place, visits):
    cover_photo = get_cover_photo(visits)

    if cover_photo:
        st.image(cover_photo, use_container_width=True)

    emojis = get_place_emojis(place)
    cost_emojis = get_cost_emojis(place)

    st.subheader(f"{place['name']} {emojis}")
    st.caption(f"{cost_emojis} • {place.get('postcode', '')}")

    categories = place.get("categories") or []

    if categories:
        st.caption(" • ".join(categories))

    if place.get("notes"):
        st.write(place["notes"])

    st.markdown(
        make_directions_links(place),
        unsafe_allow_html=True,
    )

    st.divider()
    st.subheader("Visit history")

    if not visits:
        st.info("No visits recorded yet.")
    else:
        for visit in visits:
            rating = visit.get("rating") or 0

            st.markdown(
                f"### {visit.get('visit_date', '')} — {'⭐' * rating}"
            )

            if visit.get("diary"):
                st.write(visit["diary"])

            show_photo_grid(visit.get("photos") or [])
            st.divider()


def show_place_map(
    places,
    visited_place_ids=None,
    centre=None,
    zoom=11,
):
    visited_place_ids = set(visited_place_ids or [])
    map_height = 550

    valid_places = [
        place
        for place in places
        if get_coordinates(place) is not None
    ]

    centre_coordinates = None

    if centre is not None:
        try:
            centre_coordinates = get_coordinates(
                {
                    "latitude": centre[0],
                    "longitude": centre[1],
                }
            )
        except (IndexError, TypeError):
            centre_coordinates = None

    if centre_coordinates:
        map_centre = centre_coordinates
    elif valid_places:
        map_centre = get_coordinates(valid_places[0])
    else:
        map_centre = [51.5074, -0.1278]

    fmap = folium.Map(
        location=map_centre,
        zoom_start=zoom,
        tiles="OpenStreetMap",
        width="100%",
        height=map_height,
        control_scale=True,
    )

    for place in valid_places:
        is_visited = place.get("id") in visited_place_ids
        emojis = get_place_emojis(place)
        cost_emojis = get_cost_emojis(place)

        badge = "✅ Visited" if is_visited else "📍 Not visited yet"
        marker_colour = "green" if is_visited else "blue"

        name = escape(str(place.get("name", "Unnamed place")))
        categories = escape(
            ", ".join(place.get("categories") or [])
        )
        postcode = escape(str(place.get("postcode") or ""))

        popup_html = f"""
        <div style="
            font-family: Arial, sans-serif;
            min-width: 210px;
            line-height: 1.6;
            padding: 4px;
        ">
            <strong>{name} {emojis}</strong><br>
            {categories}<br>
            {cost_emojis} • {postcode}<br>
            {badge}<br><br>
            <strong>Get directions</strong><br>
            {make_directions_links(place)}
        </div>
        """

        folium.Marker(
            location=get_coordinates(place),
            popup=folium.Popup(
                popup_html,
                max_width=300,
            ),
            tooltip=(
                f"{name} {emojis} "
                f"{'✅' if is_visited else ''}"
            ),
            icon=folium.Icon(
                color=marker_colour,
                icon="ok" if is_visited else "info-sign",
            ),
        ).add_to(fmap)

    if centre_coordinates is None and len(valid_places) > 1:
        fmap.fit_bounds(
            [
                get_coordinates(place)
                for place in valid_places
            ],
            padding=(35, 35),
            max_zoom=15,
        )

    render_map(fmap, map_height)


def show_route_map(places):
    valid_places = [
        place
        for place in places
        if get_coordinates(place) is not None
    ]

    if not valid_places:
        st.info("No valid map coordinates are available for these stops.")
        return

    map_height = 450

    fmap = folium.Map(
        location=get_coordinates(valid_places[0]),
        zoom_start=14,
        tiles="OpenStreetMap",
        width="100%",
        height=map_height,
        control_scale=True,
    )

    route_points = []

    for index, place in enumerate(valid_places, start=1):
        location = get_coordinates(place)
        route_points.append(location)

        name = escape(str(place.get("name", "Unnamed place")))
        categories = escape(
            ", ".join(place.get("categories") or [])
        )

        marker_html = f"""
        <div style="
            width: 32px;
            height: 32px;
            border-radius: 50%;
            background: #e85670;
            border: 3px solid white;
            color: white;
            font: bold 15px Arial, sans-serif;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
        ">
            {index}
        </div>
        """

        folium.Marker(
            location=location,
            tooltip=f"{index}. {name}",
            popup=folium.Popup(
                f"<strong>{index}. {name}</strong><br>"
                f"{categories}<br><br>"
                f"{make_directions_links(place)}",
                max_width=300,
            ),
            icon=folium.DivIcon(
                html=marker_html,
                icon_size=(38, 38),
                icon_anchor=(19, 19),
            ),
        ).add_to(fmap)

    if len(route_points) > 1:
        folium.PolyLine(
            route_points,
            color="#e85670",
            weight=4,
            opacity=0.8,
            dash_array="8, 8",
        ).add_to(fmap)

        fmap.fit_bounds(
            route_points,
            padding=(40, 40),
            max_zoom=16,
        )

    render_map(fmap, map_height)

    if len(route_points) > 1:
        st.caption(
            "The dotted lines connect your stops in order; "
            "they are not walking routes. Open Google Maps "
            "for navigable directions."
        )


def show_place_card(
    place,
    visits,
    show_delete=True,
    key_prefix="",
):
    widget_prefix = f"{key_prefix}{place['id']}"

    with st.container(border=True):
        cover_photo = get_cover_photo(visits)

        if cover_photo:
            st.image(cover_photo, use_container_width=True)

        is_visited = bool(visits)
        emojis = get_place_emojis(place)
        cost_emojis = get_cost_emojis(place)

        st.subheader(
            f"{place['name']} {emojis} "
            f"{'✅' if is_visited else ''}"
        )

        st.caption(
            f"{cost_emojis} • {place.get('postcode', '')}"
        )

        categories = place.get("categories") or []

        if categories:
            st.caption(" • ".join(categories))

        if place.get("notes"):
            st.write(place["notes"])

        if visits:
            rated_visits = [
                visit
                for visit in visits
                if visit.get("rating") is not None
            ]

            average = (
                round(
                    sum(visit["rating"] for visit in rated_visits)
                    / len(rated_visits),
                    1,
                )
                if rated_visits
                else None
            )

            col1, col2 = st.columns(2)

            with col1:
                st.metric("Visits", len(visits))

            with col2:
                st.metric(
                    "Average rating",
                    f"{average}/5" if average is not None else "—",
                )

        button_columns = st.columns(2)

        with button_columns[0]:
            if st.button(
                "View details",
                key=f"{widget_prefix}_view_details",
                use_container_width=True,
            ):
                st.session_state["selected_place_id"] = place["id"]

        with button_columns[1]:
            show_inline_map = st.checkbox(
                "Show location",
                key=f"{widget_prefix}_show_location",
            )

        if show_inline_map:
            if get_coordinates(place) is None:
                st.info("This place does not have valid map coordinates.")
            else:
                show_place_map(
                    [place],
                    visited_place_ids=(
                        {place["id"]} if is_visited else set()
                    ),
                    centre=get_coordinates(place),
                    zoom=15,
                )

        if show_delete:
            with st.expander("⚠️ Delete this place"):
                st.warning(
                    "This permanently deletes the place and all "
                    "linked visit diary entries. Uploaded photo "
                    "files remain in Storage. This cannot be undone."
                )

                confirm_delete = st.checkbox(
                    f"Yes, permanently delete {place['name']}",
                    key=f"{widget_prefix}_confirm_delete",
                )

                delete_clicked = st.button(
                    "Delete place",
                    key=f"{widget_prefix}_delete",
                    disabled=not confirm_delete,
                    type="primary",
                )

                if delete_clicked:
                    try:
                        delete_place(place["id"])
                    except Exception:
                        st.error(
                            "The place could not be deleted. "
                            "Check the app logs for details."
                        )
                    else:
                        if (
                            st.session_state.get("selected_place_id")
                            == place["id"]
                        ):
                            st.session_state.pop(
                                "selected_place_id",
                                None,
                            )

                        st.cache_data.clear()
                        st.rerun()


def show_outing_card(outing, visits):
    with st.container(border=True):
        cover_photo = get_cover_photo(visits)

        if cover_photo:
            st.image(cover_photo, use_container_width=True)

        place_count = len(
            {
                visit.get("place_id")
                for visit in visits
                if visit.get("place_id")
            }
        )

        st.subheader(f"{outing['title']} 🗓️")
        st.caption(
            f"{outing.get('outing_date', '')} • "
            f"{place_count} places visited"
        )

        if outing.get("notes"):
            st.write(outing["notes"])

        if not visits:
            st.info(
                "No visits linked yet. Add a visit and select "
                "this outing to start building its memories."
            )
            return

        all_photos = []
        route_places = []

        for visit in visits:
            place = visit.get("places") or {}
            place_name = place.get("name", "Unknown place")
            emojis = get_place_emojis(place)
            rating = visit.get("rating") or 0

            st.markdown(f"### {place_name} {emojis}")
            st.caption(
                f"{visit.get('visit_date', '')} • "
                f"{'⭐' * rating}"
            )

            if visit.get("diary"):
                st.write(visit["diary"])

            all_photos.extend(visit.get("photos") or [])

            if get_coordinates(place) is not None:
                route_places.append(place)

        if all_photos:
            st.subheader("📸 Photos")
            show_photo_grid(all_photos)

        if route_places:
            with st.expander("🗺️ View this outing on a map"):
                show_route_map(route_places)
