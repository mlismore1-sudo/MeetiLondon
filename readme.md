# London Date Nights

A private Streamlit app for saving London date-night ideas, finding saved places nearby, and keeping a photo diary after each visit.

## Features

- Add places with multiple categories, postcode, cost rating, and notes
- View all saved places on an interactive map
- Find saved places near your current postcode
- Record visits with a date, rating, diary entry, and photos
- Shared password protection

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Supabase setup

1. Create a Supabase project.
2. Run the SQL in `supabase_setup.sql`.
3. Create a public Storage bucket called `date-night-photos`.
4. Add your project URL and anon key to `.streamlit/secrets.toml`.

## Deployment

1. Push this repository to GitHub.
2. Deploy it on Streamlit Community Cloud.
3. Set `app.py` as the main file.
4. Add the contents of `.streamlit/secrets.toml` in the app’s Secrets settings.
