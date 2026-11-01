import urllib.parse

import folium
import streamlit as st
from streamlit_folium import st_folium

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
    return st.selectbox(
        "Cost rating",
        options=COSTS,
        index=COSTS.index(default),
    )


def get_place_emojis(place):
    return " ".join(
        CATEGORY_EMOJIS.get(category, "📍")
        for category in place["categories"]
    )


def get_cost_emojis(place):
    try:
        cost_index = COSTS.index(place["cost"])
    except ValueError:
        cost_index = 1

    return COST_EMOJI * (cost_index + 1)


def make_directions_links(place):
    lat = place["latitude"]
    lon = place["longitude"]
    destination = f"{lat},{lon}"
    name = urllib.parse.quote(place["name"])

    google_url = (
        "https://www.google.com/maps/dir/?api=1"
        f"&destination={destination}"
    )

    apple_url = (
        "https://maps.apple.com/"
        f"?daddr={destination}"
        f"&q={name}"
    )

    return (
        f'<a href="{google_url}" target="_blank">Google Maps directions</a><br>'
        f'<a href="{apple_url}" target="_blank">Apple Maps directions</a>'
    )


def show_place_map(places, visited_place_ids=None, centre=None, zoom=11):
    visited_place_ids = visited_place_ids or set()

    places = [
        place
        for place in places
        if place.get("latitude") is not None
        and place.get("longitude") is not None
    ]

    if centre:
        map_centre = [centre[0], centre[1]]
    elif places:
        map_centre = [places[0]["latitude"], places[0]["longitude"]]
    else:
        map_centre = [51.5074, -0.1278]

    fmap = folium.Map(
        location=map_centre,
        zoom_start=zoom,
        tiles="OpenStreetMap",
    )

    for place in places:
        is_visited = place["id"] in visited_place_ids
        emojis = get_place_emojis(place)
        cost_emojis = get_cost_emojis(place)

        if is_visited:
            badge = "✅ Visited"
            marker_colour = "green"
        else:
            badge = "📍 Not visited yet"
            marker_colour = "blue"

        popup_html = f"""
            <div style="font-family: Arial, sans-serif; min-width: 240px;">
                <b>{place['name']} {emojis} {'✅' if is_visited else ''}</b><br>
                {', '.join(place['categories'])}<br>
                {cost_emojis} • {place['postcode']}<br>
                {badge}<br><br>
                {make_directions_links(place)}
            </div>
        """

        folium.Marker(
            location=[place["latitude"], place["longitude"]],
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"{place['name']} {emojis} {'✅' if is_visited else ''}",
            icon=folium.Icon(color=marker_colour, icon="info-sign"),
        ).add_to(fmap)

    st_folium(fmap, use_container_width=True, height=550)


def show_place_card(place, visits):
    with st.container(border=True):
        is_visited = len(visits) > 0

        emojis = get_place_emojis(place)
        cost_emojis = get_cost_emojis(place)

        title = (
            f"{place['name']} {emojis} "
            f"{'✅' if is_visited else ''}"
        )

        st.subheader(title)
        st.caption(f"{cost_emojis} • {place['postcode']}")

        st.markdown(
            " ".join(
                f"`{category}`"
                for category in place["categories"]
            )
        )

        if place.get("notes"):
            st.write(place["notes"])

        if visits:
            average = round(
                sum(visit["rating"] or 0 for visit in visits) / len(visits),
                1,
            )

            col1, col2 = st.columns(2)

            with col1:
                st.metric("Visits", len(visits))

            with col2:
                st.metric("Average rating", f"{average}/5")

        with st.expander("Visit history and photos"):
            if not visits:
                st.info("No visits recorded yet.")
            else:
                for visit in visits:
                    st.markdown(
                        f"**{visit['visit_date']}** — "
                        f"{'⭐' * (visit['rating'] or 0)}"
                    )

                    if visit.get("diary"):
                        st.write(visit["diary"])

                    for url in visit.get("photos", []):
                        st.image(url, use_container_width=True)

                    st.divider()

        with st.expander("⚠️ Delete this place"):
            st.warning(
                "This will permanently delete the place and all of its visit "
                "diary entries. This cannot be undone."
            )

            confirm_delete = st.checkbox(
                f"Yes, permanently delete {place['name']}",
                key=f"confirm_delete_{place['id']}",
            )

            if st.button(
                "Delete place",
                key=f"delete_place_{place['id']}",
                disabled=not confirm_delete,
                type="primary",
            ):
                delete_place(place["id"])
                st.cache_data.clear()
                st.success(f"Deleted {place['name']}.")
                st.rerun()
