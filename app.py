from datetime import date

import streamlit as st

from src.db import (
    CATEGORY_GROUPS,
    add_place,
    add_visit,
    create_outing,
    get_all_visits,
    get_outings,
    get_place,
    get_places,
    get_visits_for_outing,
    get_visits_for_place,
    upload_photos,
)
from src.geo import find_nearby_places, geocode_postcode
from src.ui import (
    category_multiselect,
    cost_select,
    place_details_dialog,
    show_outing_card,
    show_place_card,
    show_place_map,
    show_route_map,
)

st.set_page_config(
    page_title="Matt & Preeti's London Adventures",
    page_icon="🗺️",
    layout="wide",
)

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🗺️ Matt & Preeti's London Adventures")
    password = st.text_input("Enter shared password", type="password")

    if st.button("Enter"):
        if password == st.secrets["APP_PASSWORD"]:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password.")

    st.stop()

st.title("🗺️ Matt & Preeti's London Adventures")
st.caption(
    "Save places to try, plan adventures by area, and keep a shared photo diary."
)

tab_home, tab_add, tab_map, tab_list, tab_diary, tab_plan, tab_memories = st.tabs(
    [
        "🏠 Home",
        "➕ Add place",
        "🗺️ Map & nearby",
        "📋 All places",
        "📔 Add visit",
        "🧭 Plan adventure",
        "📸 Memories",
    ]
)

places = get_places()
all_visits = get_all_visits()
outings = get_outings()

visited_place_ids = {
    visit["place_id"]
    for visit in all_visits
}

unvisited_places = [
    place for place in places if place["id"] not in visited_place_ids
]

with tab_home:
    st.subheader("Welcome back")

    total_photos = sum(
        len(visit.get("photos", []))
        for visit in all_visits
    )

    average_rating = None

    rated_visits = [
        visit for visit in all_visits if visit.get("rating")
    ]

    if rated_visits:
        average_rating = round(
            sum(visit["rating"] for visit in rated_visits)
            / len(rated_visits),
            1,
        )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Places saved", len(places))

    with col2:
        st.metric("Places visited", len(visited_place_ids))

    with col3:
        st.metric("Photos", total_photos)

    with col4:
        st.metric(
            "Average rating",
            f"{average_rating}/5" if average_rating else "—",
        )

    st.divider()

    if unvisited_places:
        st.subheader("✨ Next adventure idea")

        try:
            home_postcode = st.secrets.get("HOME_POSTCODE", "")
        except Exception:
            home_postcode = ""

        if home_postcode:
            nearby_unvisited = find_nearby_places(
                unvisited_places,
                home_postcode,
                15,
            )

            if nearby_unvisited:
                next_place = nearby_unvisited[0]
            else:
                next_place = unvisited_places[0]
        else:
            next_place = unvisited_places[0]

        show_place_card(
            next_place,
            get_visits_for_place(next_place["id"]),
            show_delete=False,
            key_prefix="home_",
        )
    else:
        st.info("You have visited every saved place. Time to add more!")

    st.divider()

    st.subheader("📸 Recent memories")

    if outings:
        recent_outings = outings[:2]

        for outing in recent_outings:
            outing_visits = get_visits_for_outing(outing["id"])
            show_outing_card(outing, outing_visits)
    else:
        st.info("No outings yet. Create one in the Memories tab.")

with tab_add:
    st.subheader("Add a place you want to try")

    with st.form("add_place_form", clear_on_submit=True):
        name = st.text_input("Place name")
        categories = category_multiselect()
        postcode = st.text_input(
            "Postcode",
            placeholder="e.g. SE20 8RD",
        )
        cost = cost_select()
        notes = st.text_area("Why do you want to go? / notes")

        submitted = st.form_submit_button("Save place")

        if submitted:
            if not name or not categories or not postcode:
                st.error(
                    "Please add a name, at least one category, and a postcode."
                )
            else:
                coordinates = geocode_postcode(postcode)

                if coordinates is None:
                    st.error("Could not find that postcode.")
                else:
                    try:
                        add_place(
                            name=name,
                            categories=categories,
                            postcode=postcode,
                            latitude=coordinates[0],
                            longitude=coordinates[1],
                            cost=cost,
                            notes=notes,
                        )

                        st.cache_data.clear()
                        st.success(f"Saved {name}.")
                        st.rerun()
                    except Exception as error:
                        st.error(f"Could not save place: {error}")

with tab_map:
    st.subheader("Find somewhere nearby")

    all_categories = sorted(
        {
            category
            for place in places
            for category in place["categories"]
        }
    )

    col_filter1, col_filter2 = st.columns(2)

    with col_filter1:
        map_categories = st.multiselect(
            "What are you looking for?",
            options=all_categories,
            placeholder="e.g. Dinner, Pub, Market",
        )

    with col_filter2:
        visited_filter = st.radio(
            "Visit status",
            options=[
                "All places",
                "Not visited yet",
                "Visited",
            ],
            horizontal=True,
        )

    filtered_places = places

    if map_categories:
        filtered_places = [
            place
            for place in filtered_places
            if set(map_categories) & set(place["categories"])
        ]

    if visited_filter == "Not visited yet":
        filtered_places = [
            place
            for place in filtered_places
            if place["id"] not in visited_place_ids
        ]
    elif visited_filter == "Visited":
        filtered_places = [
            place
            for place in filtered_places
            if place["id"] in visited_place_ids
        ]

    col1, col2 = st.columns([2, 1])

    with col1:
        current_postcode = st.text_input(
            "Your current postcode",
            placeholder="e.g. BR6 0JS",
        )

    with col2:
        radius = st.slider(
            "Search radius",
            1,
            20,
            5,
            help="Distance in kilometres",
        )

    if current_postcode:
        nearby = find_nearby_places(
            filtered_places,
            current_postcode,
            radius,
        )

        if nearby:
            st.success(
                f"Found {len(nearby)} places within {radius} km."
            )

            place_labels = [
                f"{place['name']} — {place['distance_km']} km"
                for place in nearby
            ]

            selected_label = st.selectbox(
                "Choose a place",
                options=place_labels,
            )

            selected = nearby[place_labels.index(selected_label)]

            show_place_map(
                nearby,
                visited_place_ids=visited_place_ids,
                centre=(
                    selected["latitude"],
                    selected["longitude"],
                ),
                zoom=14,
            )

            show_place_card(
                selected,
                get_visits_for_place(selected["id"]),
                key_prefix="map_",
            )
        else:
            st.info("No matching places within that radius.")

            show_place_map(
                filtered_places,
                visited_place_ids=visited_place_ids,
            )
    else:
        st.caption(
            "Enter your postcode to find saved places nearby, or browse the full map below."
        )

        show_place_map(
            filtered_places,
            visited_place_ids=visited_place_ids,
        )

with tab_list:
    st.subheader("All saved places")

    selected_categories = st.multiselect(
        "Filter by category",
        options=sorted(
            {
                category
                for place in places
                for category in place["categories"]
            }
        ),
    )

    filtered = [
        place
        for place in places
        if not selected_categories
        or set(selected_categories) & set(place["categories"])
    ]

    if not filtered:
        st.info("No places match this filter.")
    else:
        for place in filtered:
            show_place_card(
                place,
                get_visits_for_place(place["id"]),
                key_prefix="list_",
            )

with tab_diary:
    st.subheader("Record a visit")

    if not places:
        st.info("Add a place first.")
    else:
        place_names = [place["name"] for place in places]

        chosen_name = st.selectbox(
            "Where did you go?",
            options=place_names,
        )

        chosen_place = next(
            place for place in places if place["name"] == chosen_name
        )

        with st.form("create_outing_form", border=True):
            st.markdown("**Create a new outing**")

            new_outing_title = st.text_input(
                "Outing title",
                placeholder="e.g. Saturday in Soho",
            )

            new_outing_date = st.date_input(
                "Outing date",
                value=date.today(),
            )

            new_outing_notes = st.text_area(
                "Outing notes",
                placeholder="Optional: what was the plan?",
            )

            create_outing_clicked = st.form_submit_button(
                "Create outing"
            )

            if create_outing_clicked:
                if not new_outing_title:
                    st.error("Please add an outing title.")
                else:
                    try:
                        create_outing(
                            title=new_outing_title,
                            outing_date=new_outing_date,
                            notes=new_outing_notes,
                        )

                        st.cache_data.clear()
                        st.success("Outing created.")
                        st.rerun()
                    except Exception as error:
                        st.error(f"Could not create outing: {error}")

        st.divider()

        current_outings = get_outings()

        outing_options = ["No outing"] + [
            f"{outing['title']} — {outing['outing_date']}"
            for outing in current_outings
        ]

        with st.form("visit_form", clear_on_submit=True):
            visit_date = st.date_input(
                "Visit date",
                value=date.today(),
            )

            rating = st.slider("Rating", 1, 5, 5)

            diary = st.text_area(
                "Diary entry",
                placeholder=(
                    "What did you have? What was the vibe? "
                    "Would you go back?"
                ),
            )

            photos = st.file_uploader(
                "Upload photos",
                type=["jpg", "jpeg", "png", "webp"],
                accept_multiple_files=True,
                help="Upload as many photos as you like.",
            )

            selected_outing = st.selectbox(
                "Was this part of an outing?",
                options=outing_options,
            )

            save_visit = st.form_submit_button("Save visit")

            if save_visit:
                photo_urls = (
                    upload_photos(photos, chosen_place["name"])
                    if photos
                    else []
                )

                outing_id = None

                if selected_outing != "No outing":
                    selected_index = outing_options.index(selected_outing) - 1
                    outing_id = current_outings[selected_index]["id"]

                try:
                    add_visit(
                        place_id=chosen_place["id"],
                        visit_date=visit_date,
                        rating=rating,
                        diary=diary,
                        photo_urls=photo_urls,
                        outing_id=outing_id,
                    )

                    st.cache_data.clear()
                    st.success("Visit saved.")
                    st.rerun()
                except Exception as error:
                    st.error(f"Could not save visit: {error}")

with tab_plan:
    st.subheader("🧭 Plan an adventure")

    st.caption(
        "Choose a starting point and build a route from nearby places across "
        "different types of activity."
    )

    current_postcode = st.text_input(
        "Starting postcode",
        placeholder="e.g. SE1 7PB",
    )

    radius = st.slider(
        "Maximum distance from starting point",
        1,
        10,
        3,
        help="Distance in kilometres",
    )

    if current_postcode:
        nearby = find_nearby_places(places, current_postcode, radius)

        if not nearby:
            st.info("No saved places within this radius yet.")
        else:
            st.success(
                f"Found {len(nearby)} places within {radius} km."
            )

            suggestions = {}

            for group_name, group_categories in CATEGORY_GROUPS.items():
                group_places = [
                    place
                    for place in nearby
                    if set(group_categories) & set(place["categories"])
                ]

                if group_places:
                    suggestions[group_name] = group_places

            if not suggestions:
                st.info(
                    "No matching places found across the adventure categories."
                )
            else:
                chosen = {}

                for group_name, group_places in suggestions.items():
                    st.subheader(group_name)

                    labels = [
                        f"{place['name']} — {place['distance_km']} km"
                        for place in group_places
                    ]

                    selected_label = st.selectbox(
                        f"Choose a {group_name.lower()} stop",
                        options=["None"] + labels,
                        key=f"plan_{group_name}",
                    )

                    if selected_label != "None":
                        chosen[group_name] = group_places[
                            labels.index(selected_label)
                        ]

                if chosen:
                    st.divider()
                    st.subheader("Your adventure")

                    ordered_groups = [
                        "Meal",
                        "Snack",
                        "Grab a drink",
                        "Something to do",
                    ]

                    route_places = []
                    stop_number = 1

                    for group_name in ordered_groups:
                        if group_name not in chosen:
                            continue

                        place = chosen[group_name]
                        route_places.append(place)

                        emojis = " ".join(
                            f"`{category}`"
                            for category in place["categories"]
                        )

                        st.markdown(
                            f"**Stop {stop_number}: {place['name']}** {emojis}"
                        )
                        st.caption(
                            f"{group_name} • {place['cost']} • "
                            f"{place['distance_km']} km away"
                        )

                        stop_number += 1

                    st.subheader("🗺️ Route preview")
                    show_route_map(route_places)

                    if len(route_places) > 1:
                        origin = route_places[0]
                        destination = route_places[-1]
                        waypoints = route_places[1:-1]

                        google_url = (
                            "https://www.google.com/maps/dir/?api=1"
                            f"&origin={origin['latitude']},{origin['longitude']}"
                            f"&destination={destination['latitude']},{destination['longitude']}"
                            "&travelmode=walking"
                        )

                        if waypoints:
                            waypoint_text = "|".join(
                                f"{place['latitude']},{place['longitude']}"
                                for place in waypoints
                            )
                            google_url += f"&waypoints={waypoint_text}"

                        st.markdown(
                            f"[🗺️ Open full route in Google Maps]({google_url})"
                        )

                    if st.button("Save this adventure as an outing"):
                        stop_names = " → ".join(
                            place["name"] for place in route_places
                        )

                        try:
                            create_outing(
                                title=f"Adventure idea: {stop_names}",
                                outing_date=date.today(),
                                notes=(
                                    f"Planned adventure from {current_postcode}. "
                                    f"Stops: {stop_names}."
                                ),
                            )

                            st.cache_data.clear()
                            st.success("Adventure saved to Memories.")
                            st.rerun()
                        except Exception as error:
                            st.error(f"Could not save adventure: {error}")

with tab_memories:
    st.subheader("📸 Memories")

    with st.form("create_outing_form_memories", border=True):
        st.markdown("**Create a new outing**")

        new_outing_title = st.text_input(
            "Outing title",
            placeholder="e.g. Saturday in Soho",
            key="memories_outing_title",
        )

        new_outing_date = st.date_input(
            "Outing date",
            value=date.today(),
            key="memories_outing_date",
        )

        new_outing_notes = st.text_area(
            "Outing notes",
            placeholder="Optional: what was the plan?",
            key="memories_outing_notes",
        )

        create_outing_clicked = st.form_submit_button("Create outing")

        if create_outing_clicked:
            if not new_outing_title:
                st.error("Please add an outing title.")
            else:
                try:
                    create_outing(
                        title=new_outing_title,
                        outing_date=new_outing_date,
                        notes=new_outing_notes,
                    )

                    st.cache_data.clear()
                    st.success("Outing created.")
                    st.rerun()
                except Exception as error:
                    st.error(f"Could not create outing: {error}")

    st.divider()

    current_outings = get_outings()

    if not current_outings:
        st.info(
            "No outings yet. Create one above, then link visits to it from "
            "the Add Visit tab."
        )
    else:
        for outing in current_outings:
            outing_visits = get_visits_for_outing(outing["id"])
            show_outing_card(outing, outing_visits)

if st.session_state.get("selected_place_id"):
    selected_place = get_place(st.session_state["selected_place_id"])
    selected_visits = get_visits_for_place(selected_place["id"])

    place_details_dialog(selected_place, selected_visits)

    if st.button("Close place details"):
        del st.session_state["selected_place_id"]
        st.rerun()
