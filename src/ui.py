import folium
import streamlit as st
from streamlit_folium import st_folium

from src.db import CATEGORIES, COSTS


def category_multiselect(default=None):
    return st.multiselect(
        "Categories",
        options=CATEGORIES,
        default=default or [],
        help="Choose as many as apply.",
    )


def cost_select(default="£"):
    return st.selectbox("Cost rating", options=COSTS, index=COSTS.index(default))


def show_place_map(places, centre=None, zoom=11):
    if centre:
        map_centre = [centre[0], centre[1]]
    elif places:
        map_centre = [places[0]["latitude"], places[0]["longitude"]]
    else:
        map_centre = [51.5074, -0.1278]

    fmap = folium.Map(location=map_centre, zoom_start=zoom, tiles="OpenStreetMap")

    for place in places:
        popup_html = f"""
            <b>{place['name']}</b><br>
            {', '.join(place['categories'])}<br>
            {place['cost']}<br>
            {place['postcode']}
        """

        folium.Marker(
            location=[place["latitude"], place["longitude"]],
            popup=folium.Popup(popup_html, max_width=250),
            tooltip=place["name"],
        ).add_to(fmap)

    st_folium(fmap, use_container_width=True, height=500)


def show_place_card(place, visits):
    with st.container(border=True):
        st.subheader(place["name"])
        st.caption(f"{', '.join(place['categories'])} • {place['cost']} • {place['postcode']}")

        if place.get("notes"):
            st.write(place["notes"])

        if visits:
            average = round(sum(v["rating"] or 0 for v in visits) / len(visits), 1)
            st.metric("Visits", len(visits))
            st.metric("Average rating", f"{average}/5")

        with st.expander("Visit history and photos"):
            if not visits:
                st.info("No visits recorded yet.")
            else:
                for visit in visits:
                    st.markdown(f"**{visit['visit_date']}** — {'⭐' * (visit['rating'] or 0)}")

                    if visit.get("diary"):
                        st.write(visit["diary"])

                    for url in visit.get("photos", []):
                        st.image(url, use_container_width=True)

                    st.divider()
