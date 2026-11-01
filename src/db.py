import uuid
from datetime import date

import streamlit as st
from supabase import create_client

CATEGORIES = [
    "Breakfast",
    "Brunch",
    "Lunch",
    "Dinner",
    "Bakery",
    "Sweet treat",
    "Bar",
    "Pub",
    "Wine Bar",
    "Coffee shop",
    "Park",
    "Market",
    "Experience",
]

CATEGORY_EMOJIS = {
    "Breakfast": "🥞",
    "Brunch": "🍳",
    "Lunch": "🥗",
    "Dinner": "🥘",
    "Bakery": "🧁",
    "Sweet treat": "🍩",
    "Bar": "🍸",
    "Pub": "🍻",
    "Wine Bar": "🍷",
    "Coffee shop": "☕️",
    "Park": "🌳",
    "Market": "🍲",
    "Experience": "🪂",
}

CATEGORY_GROUPS = {
    "Meal": [
        "Breakfast",
        "Brunch",
        "Lunch",
        "Dinner",
        "Market",
    ],
    "Snack": [
        "Bakery",
        "Sweet treat",
        "Coffee shop",
    ],
    "Grab a drink": [
        "Bar",
        "Pub",
        "Wine Bar",
    ],
    "Something to do": [
        "Park",
        "Experience",
    ],
}

COSTS = ["£", "££", "£££", "££££", "£££££"]

COST_EMOJI = "💷"


@st.cache_resource
def get_supabase():
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_ANON_KEY"],
    )


@st.cache_data(ttl=300)
def get_places():
    response = (
        get_supabase()
        .table("places")
        .select("*")
        .order("name", desc=False)
        .execute()
    )
    return response.data


def get_place(place_id):
    response = (
        get_supabase()
        .table("places")
        .select("*")
        .eq("id", place_id)
        .single()
        .execute()
    )
    return response.data


def get_visits_for_place(place_id):
    response = (
        get_supabase()
        .table("visits")
        .select("*")
        .eq("place_id", place_id)
        .order("visit_date", desc=True)
        .execute()
    )
    return response.data


@st.cache_data(ttl=300)
def get_outings():
    response = (
        get_supabase()
        .table("outings")
        .select("*")
        .order("outing_date", desc=True)
        .execute()
    )
    return response.data


def get_visits_for_outing(outing_id):
    response = (
        get_supabase()
        .table("visits")
        .select("*, places(name, categories, cost, postcode)")
        .eq("outing_id", outing_id)
        .order("created_at", desc=False)
        .execute()
    )
    return response.data


def add_place(name, categories, postcode, latitude, longitude, cost, notes):
    response = (
        get_supabase()
        .table("places")
        .insert(
            {
                "name": name,
                "categories": categories,
                "postcode": postcode.upper().replace(" ", ""),
                "latitude": latitude,
                "longitude": longitude,
                "cost": cost,
                "notes": notes,
            }
        )
        .execute()
    )

    if hasattr(response, "error") and response.error:
        raise Exception(response.error.message)

    return response


def add_visit(place_id, visit_date, rating, diary, photo_urls, outing_id=None):
    payload = {
        "place_id": place_id,
        "visit_date": str(visit_date),
        "rating": rating,
        "diary": diary,
        "photos": photo_urls,
    }

    if outing_id:
        payload["outing_id"] = outing_id

    response = (
        get_supabase()
        .table("visits")
        .insert(payload)
        .execute()
    )

    if hasattr(response, "error") and response.error:
        raise Exception(response.error.message)

    return response


def create_outing(title, outing_date, notes):
    response = (
        get_supabase()
        .table("outings")
        .insert(
            {
                "title": title,
                "outing_date": str(outing_date),
                "notes": notes,
            }
        )
        .execute()
    )

    if hasattr(response, "error") and response.error:
        raise Exception(response.error.message)

    return response.data[0]["id"]


def delete_place(place_id):
    get_supabase().table("places").delete().eq("id", place_id).execute()


def upload_photos(files, place_name):
    supabase = get_supabase()
    urls = []

    for file in files:
        extension = file.name.split(".")[-1].lower()
        file_name = f"{uuid.uuid4()}.{extension}"
        path = f"{place_name.replace(' ', '-').lower()}/{file_name}"

        supabase.storage.from_("date-night-photos").upload(
            path=path,
            file=file,
            file_options={"content-type": file.type},
        )

        public_url = supabase.storage.from_("date-night-photos").get_public_url(path)
        urls.append(public_url)

    return urls
