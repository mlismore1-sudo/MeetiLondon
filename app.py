from datetime import date

import streamlit as st

from src.db import (
    add_place,
    add_visit,
    get_place,
    get_places,
    get_visits_for_place,
    upload_photos,
)
from src.geo import find_nearby_places, geocode_postcode
from src.ui import category_multiselect, cost_select, show_place_card, show_place_map

st.set_page_config(
    page_title="London Date Nights",
    page_icon="💞",
    layout="wide",
)

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("💞 London Date Nights")
    password = st.text_input("Enter shared password", type="password")

    if st.button("Enter"):
        if password == st.secrets["APP_PASSWORD"]:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password.")

    st.stop()

st.title("💞 London Date Nights")
st.caption("Save places to try, find somewhere nearby, and keep a photo diary of your visits.")

tab_add, tab_map, tab_list, tab_diary = st.tabs(
    ["➕ Add place", "🗺️ Map & nearby", "📋 All places", "📔 Add visit"]
)

places = get_places()

with tab_add:
    st.subheader("Add a place you want to try")

    with st.form("add_place_form", clear_on_submit=True):
        name = st.text_input("Place name")
        categories = category_multiselect()
        postcode = st.text_input("Postcode", placeholder="e.g. SE20 8RD")
        cost = cost_select()
        notes = st.text_area("Why do you want to go? / notes")

        submitted = st.form_submit_button("Save place")

        if submitted:
            if not name or not categories or not postcode:
                st.error("Please add a name, at least one category, and a postcode.")
            else:
                coordinates = geocode_postcode(postcode)

                if coordinates is None:
                    st.error("Could not find that postcode.")
                else:
                    add_place(
                        name=name,
                        categories=categories,
                        postcode=postcode,
                        latitude=coordinates[0],
                        longitude=coordinates[1],
                        cost=cost,
                        notes=notes,
                    )
                    st.success(f"Saved {name}.")
                    st.rerun()

with tab_map:
    st.subheader("Find somewhere nearby")

    col1, col2 = st.columns([2, 1])

    with col1:
        current_postcode = st.text_input(
            "Your current postcode",
            placeholder="e.g. BR6 0JS",
        )

    with col2:
        radius = st.slider("Search radius", 1, 20, 5, help="Distance in kilometres")

    if current_postcode:
        nearby = find_nearby_places(places, current_postcode, radius)

        if nearby:
            st.success(f"Found {len(nearby)} saved places within {radius} km.")

            selected_name = st.selectbox(
                "Choose a place",
                options=[f"{p['name']} — {p['distance_km']} km" for p in nearby],
            )

            selected = nearby[
                [f"{p['name']} — {p['distance_km']} km" for p in nearby].index(selected_name)
            ]

            show_place_map(nearby, centre=(selected["latitude"], selected["longitude"]), zoom=14)
            show_place_card(selected, get_visits_for_place(selected["id"]))
        else:
            st.info("No saved places within that radius yet.")
            show_place_map(places)
    else:
        show_place_map(places)

with tab_list:
    st.subheader("All saved places")

    selected_categories = st.multiselect(
        "Filter by category",
        options=sorted({category for place in places for category in place["categories"]}),
    )

    filtered = [
        place
        for place in places
        if not selected_categories or set(selected_categories) & set(place["categories"])
    ]

    if not filtered:
        st.info("No places match this filter.")
    else:
        for place in filtered:
            show_place_card(place, get_visits_for_place(place["id"]))

with tab_diary:
    st.subheader("Record a visit")

    if not places:
        st.info("Add a place first.")
    else:
        place_names = [place["name"] for place in places]
        chosen_name = st.selectbox("Where did you go?", options=place_names)
        chosen_place = next(place for place in places if place["name"] == chosen_name)

        with st.form("visit_form", clear_on_submit=True):
            visit_date = st.date_input("Visit date", value=date.today())
            rating = st.slider("Rating", 1, 5, 5)
            diary = st.text_area("Diary entry", placeholder="What did you have? What was the vibe? Would you go back?")
            photos = st.file_uploader(
                "Upload photos",
                type=["jpg", "jpeg", "png", "webp"],
                accept_multiple_files=True,
            )

            save_visit = st.form_submit_button("Save visit")

            if save_visit:
                photo_urls = upload_photos(photos, chosen_place["name"]) if photos else []

                add_visit(
                    place_id=chosen_place["id"],
                    visit_date=visit_date,
                    rating=rating,
                    diary=diary,
                    photo_urls=photo_urls,
                )

                st.success("Visit saved.")
                st.rerun()
