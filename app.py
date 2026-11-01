from datetime import date
from urllib.parse import urlencode

import streamlit as st

from src.db import (
    CATEGORY_GROUPS, add_place, add_visit, create_outing, get_all_visits,
    get_outings, get_places, upload_photos,
)
from src.geo import find_nearby_places, geocode_postcode
from src.ui import (
    category_multiselect, cost_select, get_coordinates, get_place_emojis,
    show_outing_card, show_place_card, show_place_map, show_place_tile,
    show_route_map,
)

st.set_page_config(page_title="Matt & Preeti's London Adventures", page_icon="🗺️", layout="wide")


def finish_write(message):
    st.cache_data.clear()
    st.session_state["flash_message"] = message
    st.rerun()


def outing_form(prefix):
    with st.form(f"{prefix}_create_outing", clear_on_submit=True):
        st.subheader("Create a new outing")
        title = st.text_input("Outing title", placeholder="e.g. Saturday in Soho", key=f"{prefix}_title")
        outing_date = st.date_input("Outing date", value=date.today(), key=f"{prefix}_date")
        notes = st.text_area("Outing notes", key=f"{prefix}_notes")
        submitted = st.form_submit_button("Create outing")
    if submitted:
        if not title.strip():
            st.error("Please add an outing title.")
        else:
            try:
                create_outing(title.strip(), outing_date, notes)
            except Exception:
                st.error("Could not create the outing. Check the app logs for details.")
                st.exception(Exception("Outing creation failed; inspect server logs if the problem persists."))
            else:
                finish_write("Outing created.")


if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🗺️ Matt & Preeti's London Adventures")
    with st.form("login"):
        password = st.text_input("Enter shared password", type="password")
        login = st.form_submit_button("Enter")
    if login:
        if password == st.secrets["APP_PASSWORD"]:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    st.stop()

st.title("🗺️ Matt & Preeti's London Adventures")
st.caption("Save places to try, plan adventures by area, and keep a shared photo diary.")
if "flash_message" in st.session_state:
    st.success(st.session_state.pop("flash_message"))

if st.button("Refresh saved data", key="refresh_data"):
    st.cache_data.clear()
    st.rerun()

places = get_places()
all_visits = get_all_visits()
outings = get_outings()
places_by_id = {p["id"]: p for p in places}
visits_by_place = {}
visits_by_outing = {}
for visit in all_visits:
    visits_by_place.setdefault(visit["place_id"], []).append(visit)
    if visit.get("outing_id"):
        visits_by_outing.setdefault(visit["outing_id"], []).append(visit)
visited_ids = set(visits_by_place)
unvisited = [p for p in places if p["id"] not in visited_ids]

home, add, map_tab, collection, diary_tab, planner, memories = st.tabs([
    "🏠 Home", "➕ Add place", "🗺️ Map & nearby", "📋 All places",
    "📔 Add visit", "🧭 Plan adventure", "📸 Memories",
])

with home:
    st.subheader("Welcome back")
    rated = [v["rating"] for v in all_visits if v.get("rating") is not None]
    metrics = st.columns(4)
    metrics[0].metric("Places saved", len(places))
    metrics[1].metric("Places visited", len(visited_ids))
    metrics[2].metric("Photos", sum(len(v.get("photos") or []) for v in all_visits))
    metrics[3].metric("Average rating", f"{sum(rated) / len(rated):.1f}/5" if rated else "—")
    st.divider()
    st.subheader("✨ Next adventure idea")
    if unvisited:
        next_place = unvisited[0]
        home_postcode = st.secrets.get("HOME_POSTCODE", "")
        if home_postcode:
            try:
                nearby = find_nearby_places(unvisited, home_postcode, 15)
                if nearby:
                    next_place = nearby[0]
            except Exception:
                st.caption("Nearby suggestions are temporarily unavailable.")
        show_place_card(next_place, visits_by_place.get(next_place["id"], []),
                        show_delete=False, key_prefix="home_")
    else:
        st.info("Add somewhere new to start your next adventure.")
    st.divider()
    st.subheader("📸 Recent memories")
    if not outings:
        st.info("Create your first outing in Memories.")
    for outing in outings[:2]:
        show_outing_card(outing, visits_by_outing.get(outing["id"], []))

with add:
    st.subheader("Add a place you want to try")
    with st.form("add_place_form"):
        name = st.text_input("Place name")
        categories = category_multiselect()
        postcode = st.text_input("Postcode", placeholder="e.g. SE1 7PB")
        cost = cost_select()
        notes = st.text_area("Why do you want to go? / notes")
        save = st.form_submit_button("Save place")
    if save:
        if not name.strip() or not categories or not postcode.strip():
            st.error("Please add a name, at least one category, and a postcode.")
        else:
            try:
                coords = geocode_postcode(postcode.strip())
                if coords is None:
                    st.error("Could not find that postcode. Check it and try again.")
                else:
                    add_place(name.strip(), categories, postcode.strip(), coords[0], coords[1], cost, notes)
            except Exception as error:
                st.error(f"Could not save the place: {type(error).__name__}. Check the app logs.")
            else:
                if coords is not None:
                    finish_write(f"Saved {name.strip()}.")

with map_tab:
    st.subheader("Find somewhere nearby")
    filters = st.columns(2)
    cats = filters[0].multiselect("What are you looking for?",
        sorted({c for p in places for c in (p.get("categories") or [])}), key="map_categories")
    status = filters[1].radio("Visit status", ["All places", "Not visited yet", "Visited"],
                              horizontal=True, key="map_status")
    selected_places = [p for p in places if not cats or set(cats) & set(p.get("categories") or [])]
    if status == "Visited":
        selected_places = [p for p in selected_places if p["id"] in visited_ids]
    elif status == "Not visited yet":
        selected_places = [p for p in selected_places if p["id"] not in visited_ids]
    inputs = st.columns([2, 1])
    origin = inputs[0].text_input("Your current postcode", key="map_postcode")
    radius = inputs[1].slider("Search radius (km)", 1, 20, 5, key="map_radius")
    if origin.strip():
        try:
            nearby = find_nearby_places(selected_places, origin.strip(), radius)
        except Exception:
            nearby = []
            st.error("Could not look up this postcode. Please try again.")
        if nearby:
            lookup = {p["id"]: p for p in nearby}
            selected_id = st.selectbox("Choose a place", list(lookup),
                format_func=lambda pid: f"{lookup[pid]['name']} — {lookup[pid]['distance_km']} km",
                key="map_selected_place")
            selected = lookup[selected_id]
            show_place_map(nearby, visited_ids, centre=get_coordinates(selected), zoom=14)
            show_place_card(selected, visits_by_place.get(selected_id, []), key_prefix="map_")
        else:
            st.info("No matching places within this radius, or the postcode could not be found.")
    else:
        show_place_map(selected_places, visited_ids)

with collection:
    st.subheader("Your London collection")
    filter_cols = st.columns([2, 2, 1])
    search = filter_cols[0].text_input("Search places", placeholder="Name or postcode", key="grid_search")
    categories = filter_cols[1].multiselect("Categories",
        sorted({c for p in places for c in (p.get("categories") or [])}), key="grid_categories")
    status = filter_cols[2].selectbox("Visit status", ["All places", "Yet to visit", "Visited"], key="grid_status")
    search = search.strip().casefold()
    filtered = []
    for place in places:
        seen = place["id"] in visited_ids
        matches_search = (not search or search in place["name"].casefold()
            or search.replace(" ", "") in (place.get("postcode") or "").replace(" ", "").casefold())
        matches_categories = not categories or bool(set(categories) & set(place.get("categories") or []))
        matches_status = status == "All places" or (status == "Visited" and seen) or (status == "Yet to visit" and not seen)
        if matches_search and matches_categories and matches_status:
            filtered.append(place)
    st.caption(f"Showing {len(filtered)} of {len(places)} saved places. Select Explore place for full details.")
    if not filtered:
        st.info("No places match. Clear the search or change your filters.")
    for start in range(0, len(filtered), 3):
        columns = st.columns(3)
        for column, place in zip(columns, filtered[start:start + 3]):
            with column:
                show_place_tile(place, visits_by_place.get(place["id"], []), key_prefix="collection_")

with diary_tab:
    st.subheader("Record a visit")
    if not places:
        st.info("Add a place first.")
    else:
        chosen_id = st.selectbox("Where did you go?", list(places_by_id),
            format_func=lambda pid: f"{places_by_id[pid]['name']} — {places_by_id[pid].get('postcode', '')}", key="visit_place")
        with st.expander("Create a new outing"):
            outing_form("diary")
        outing_lookup = {o["id"]: o for o in outings}
        with st.form("visit_form"):
            visit_date = st.date_input("Visit date", value=date.today(), key="visit_date")
            rating = st.slider("Rating", 1, 5, 5, key="visit_rating")
            entry = st.text_area("Diary entry", key="visit_diary")
            photos = st.file_uploader("Upload photos", type=["jpg", "jpeg", "png", "webp"],
                                      accept_multiple_files=True, key="visit_photos")
            outing_id = st.selectbox("Was this part of an outing?", [None] + list(outing_lookup),
                format_func=lambda oid: "No outing" if oid is None else f"{outing_lookup[oid]['title']} — {outing_lookup[oid]['outing_date']}", key="visit_outing")
            save = st.form_submit_button("Save visit")
        if save:
            try:
                photo_urls = upload_photos(photos, places_by_id[chosen_id]["name"]) if photos else []
                add_visit(chosen_id, visit_date, rating, entry, photo_urls, outing_id=outing_id)
            except Exception as error:
                st.error(f"Could not save this visit: {type(error).__name__}. Check the app logs.")
            else:
                finish_write("Visit saved.")

with planner:
    st.subheader("🧭 Plan an adventure")
    st.caption("Choose nearby stops from different activity groups. Each place can appear once.")
    origin = st.text_input("Starting postcode", key="planner_postcode")
    radius = st.slider("Maximum distance from starting point (km)", 1, 10, 3, key="planner_radius")
    route = []
    if origin.strip():
        try:
            nearby = find_nearby_places(places, origin.strip(), radius)
        except Exception:
            nearby = []
            st.error("Could not look up this postcode. Please try again.")
        used = set()
        for group, group_categories in CATEGORY_GROUPS.items():
            candidates = {p["id"]: p for p in nearby if p["id"] not in used and set(group_categories) & set(p.get("categories") or [])}
            if candidates:
                pid = st.selectbox(group, [None] + list(candidates),
                    format_func=lambda pid, candidates=candidates: "Skip this stop" if pid is None else f"{candidates[pid]['name']} — {candidates[pid]['distance_km']} km",
                    key=f"planner_{group}")
                if pid:
                    route.append(candidates[pid])
                    used.add(pid)
        if not nearby:
            st.info("No saved places found in this radius.")
    if route:
        st.subheader("Your adventure")
        for i, place in enumerate(route, 1):
            st.write(f"{i}. {place['name']} {get_place_emojis(place)}")
        show_route_map(route)
        if len(route) > 1:
            coords = [f"{p['latitude']},{p['longitude']}" for p in route]
            params = {"api": 1, "origin": coords[0], "destination": coords[-1], "travelmode": "walking"}
            if len(coords) > 2:
                params["waypoints"] = "|".join(coords[1:-1])
            st.link_button("Open full route in Google Maps", "https://www.google.com/maps/dir/?" + urlencode(params))
        if st.button("Save this adventure as an outing", key="save_plan"):
            names = " → ".join(p["name"] for p in route)
            try:
                create_outing(f"Adventure idea: {names}", date.today(), f"Planned from {origin}. Stops: {names}. No visits logged yet.")
            except Exception as error:
                st.error(f"Could not save the plan: {type(error).__name__}.")
            else:
                finish_write("Plan saved as an outing. Link visits to it after your adventure.")

with memories:
    st.subheader("📸 Memories")
    with st.expander("➕ Create a new outing"):
        outing_form("memories")
    if not outings:
        st.info("Create an outing, then select it when logging visits.")
    for outing in outings:
        show_outing_card(outing, visits_by_outing.get(outing["id"], []))
