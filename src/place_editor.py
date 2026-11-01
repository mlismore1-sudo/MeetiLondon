import logging
from datetime import datetime, timezone

import streamlit as st

from src.db import CATEGORIES, COSTS, get_supabase
from src.geo import geocode_postcode
from src.enrichment import extract_hours, normalise_url

logger = logging.getLogger(__name__)


def public_link(value):
    if not value:
        return ""
    try:
        return normalise_url(value)
    except ValueError:
        return ""


def show_venue_information(place):
    website = public_link(place.get("website"))
    if website:
        st.link_button("🌐 Visit website", website)
    if place.get("opening_hours"):
        st.subheader("Opening hours")
        st.text(place["opening_hours"])
        st.caption("Saved hours, not live availability. Confirm with the venue for holidays and special events.")
        source = public_link(place.get("opening_hours_source"))
        if source:
            st.link_button("View hours source", source)
        if place.get("opening_hours_checked_at"):
            st.caption("Last checked: " + str(place["opening_hours_checked_at"])[:10])


@st.dialog("Edit a place", width="large")
def edit_place_dialog(place):
    pid = place["id"]
    prefix = f"edit_{pid}_"
    name = st.text_input("Place name", value=place["name"], key=prefix + "name")
    options = list(dict.fromkeys(CATEGORIES + (place.get("categories") or [])))
    categories = st.multiselect("Categories", options, default=place.get("categories") or [], key=prefix + "categories")
    postcode = st.text_input("Postcode", value=place.get("postcode") or "", key=prefix + "postcode")
    original_cost = place.get("cost", "£")
    cost = st.selectbox("Cost rating", COSTS, index=COSTS.index(original_cost) if original_cost in COSTS else 0, key=prefix + "cost")
    notes = st.text_area("Notes", value=place.get("notes") or "", key=prefix + "notes")
    website = st.text_input("Website — ideally the specific branch page", value=place.get("website") or "", placeholder="https://...", key=prefix + "website")
    hours_key = prefix + "hours"
    if hours_key not in st.session_state:
        st.session_state[hours_key] = place.get("opening_hours") or ""
    source_key = prefix + "source"
    if source_key not in st.session_state:
        st.session_state[source_key] = place.get("opening_hours_source") or ""
    checked_key = prefix + "checked"
    if checked_key not in st.session_state:
        st.session_state[checked_key] = place.get("opening_hours_checked_at")

    st.divider()
    st.subheader("Website opening-hours lookup")
    st.caption("Fetches structured data from this exact page. It does not browse the whole site or execute JavaScript. Review the branch and hours before saving.")
    if st.button("Find opening hours", key=prefix + "fetch"):
        try:
            with st.spinner("Checking the venue page…"):
                candidates = extract_hours(website)
            st.session_state[prefix + "candidates"] = candidates
            if not candidates:
                st.info("No structured opening hours found. Try the branch/contact page, or enter hours below. Existing hours have not been changed.")
        except Exception as error:
            logger.exception("Website opening-hours lookup failed")
            st.error(str(error) if isinstance(error, ValueError) else "This website could not be read. Try another venue page or enter the hours manually.")

    candidates = st.session_state.get(prefix + "candidates", [])
    if candidates:
        index = st.selectbox("Select the correct venue / service", range(len(candidates)), format_func=lambda i: candidates[i]["label"], key=prefix + "candidate")
        candidate = candidates[index]
        st.text(candidate["hours"])
        st.caption("00:00–00:00 can be ambiguous; confirm against the website. Overnight closing times may fall on the next day.")
        if st.button("Use these hours in the draft", key=prefix + "use"):
            st.session_state[hours_key] = candidate["hours"]
            st.session_state[source_key] = candidate["source"]
            st.session_state[checked_key] = datetime.now(timezone.utc).isoformat()

    hours = st.text_area("Opening hours — review or edit before saving", height=170, key=hours_key)
    source = st.text_input("Opening-hours source URL (optional)", key=source_key)
    confirmed = st.checkbox("I have checked that these hours belong to the correct venue and branch", key=prefix + "confirmed")
    if website != (place.get("website") or "") and (place.get("opening_hours") or "").strip():
        st.warning("The website has changed. Existing hours may refer to the old page; update or clear them before saving.")

    if st.button("Save changes", type="primary", key=prefix + "save"):
        if not name.strip() or not categories or not postcode.strip():
            st.error("Add a name, at least one category, and a postcode.")
            return
        if hours.strip() and not confirmed:
            st.error("Confirm the opening hours before saving, or clear them.")
            return
        try:
            website_url = normalise_url(website)
            source_url = normalise_url(source)
            coords = None
            if postcode.replace(" ", "").upper() != (place.get("postcode") or "").replace(" ", "").upper() or place.get("latitude") is None or place.get("longitude") is None:
                coords = geocode_postcode(postcode)
                if coords is None:
                    raise ValueError("The postcode could not be found. Check it and try again.")
            payload = {
                "name": name.strip(), "categories": categories,
                "postcode": postcode.strip().replace(" ", "").upper(),
                "cost": cost, "notes": notes,
                "website": website_url or None,
                "opening_hours": hours.strip() or None,
                "opening_hours_source": (source_url or None) if hours.strip() else None,
                "opening_hours_checked_at": datetime.now(timezone.utc).isoformat() if hours.strip() else None,
            }
            if coords:
                payload.update(latitude=coords[0], longitude=coords[1])
            response = get_supabase().table("places").update(payload).eq("id", pid).execute()
            if not response.data:
                raise ValueError("No updated row was returned. Check the place exists and your UPDATE permissions.")
        except Exception as error:
            logger.exception("Place edit failed")
            st.error(str(error) if isinstance(error, ValueError) else "Changes could not be saved. Check the Streamlit logs.")
        else:
            for key in list(st.session_state):
                if key.startswith(prefix):
                    del st.session_state[key]
            st.cache_data.clear()
            st.session_state["flash_message"] = "Place updated."
            st.rerun()


def place_editor_panel(places):
    with st.expander("✏️ Edit a place / add website / fetch opening hours"):
        if not places:
            st.info("Save a place first, then edit its details here.")
            return
        lookup = {p["id"]: p for p in places}
        pid = st.selectbox("Choose a place to edit", list(lookup),
            format_func=lambda pid: f"{lookup[pid]['name']} — {lookup[pid].get('postcode', '')}", key="editor_place_choice")
        if st.button("Edit selected place", key="open_place_editor"):
            edit_place_dialog(lookup[pid])
