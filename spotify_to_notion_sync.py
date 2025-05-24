import os
from dotenv import load_dotenv
import requests
import json
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import time

# Environment file related
load_dotenv()
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
DATABASE_ID = os.getenv("DATABASE_ID")

headers = {
    "Notion-Version": "2022-06-28",
    "Authorization": "Bearer " + NOTION_API_KEY,
    "Content-Type": "application/json",
}

sp = spotipy.Spotify(
    auth_manager=SpotifyOAuth(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri="http://localhost:8888/callback",
        scope="user-library-read",
    )
)


def get_liked_songs():
    """
    Get Spotify Liked Songs
    """
    liked_songs = []
    results = sp.current_user_saved_tracks(limit=50)

    while results:
        liked_songs.extend(results["items"])
        print(f"Fetched {len(liked_songs)} songs so far...")

        if results["next"]:
            results = sp.next(results)
        else:
            break

    return liked_songs


def check_songs_by_spotify_url(liked_songs, notion_items):
    """
    Check if songs are already registered in Notion by Spotify URL
    """
    notion_spotify_urls = set()
    notion_url_to_page = {}

    for item in notion_items:
        try:
            if "URL" in item["properties"]:
                url_property = item["properties"]["URL"]
                if url_property["type"] == "url" and url_property["url"]:
                    spotify_url = url_property["url"]
                    notion_spotify_urls.add(spotify_url)
                    notion_url_to_page[spotify_url] = {
                        "id": item["id"],
                        "notion_url": item.get("url", ""),
                        "title": get_page_title(item),
                    }
        except (KeyError, IndexError, TypeError):
            continue

    print(f"Found {len(notion_spotify_urls)} Spotify URLs in Notion.")

    results = {"registered": [], "not_registered": []}

    for song in liked_songs:
        track_name = song["track"]["name"]
        track_id = song["track"]["id"]
        artists = [artist["name"] for artist in song["track"]["artists"]]

        spotify_url = f"https://open.spotify.com/track/{track_id}"

        song_info = {
            "name": track_name,
            "id": track_id,
            "artists": artists,
            "spotify_url": spotify_url,
            "spotify_data": song,
        }

        if spotify_url in notion_spotify_urls:
            song_info["notion_page"] = notion_url_to_page[spotify_url]
            results["registered"].append(song_info)
            print(f"✓ Registered: {track_name} by {', '.join(artists)}")
        else:
            results["not_registered"].append(song_info)
            print(f"✗ Not found: {track_name} by {', '.join(artists)}")

    return results


def get_page_title(item):
    """
    Get Notion page title
    """
    try:
        return item["properties"]["Title"]["title"][0]["text"]["content"]
    except (KeyError, IndexError):
        return "No Title"


def fetch_notion_pages():
    """
    Fetch all pages from Notion database
    """
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    all_items = []
    has_more = True
    start_cursor = None

    payload = {}

    while has_more:
        if start_cursor:
            payload["start_cursor"] = start_cursor

        response = requests.post(url, headers=headers, json=payload)

        if response.status_code != 200:
            print(f"Failed to fetch Notion pages: {response.status_code}")
            print(response.text)
            break

        data = response.json()
        all_items.extend(data["results"])

        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")

    print(f"Fetched {len(all_items)} pages from Notion database.")
    return all_items


def add_cover_image_to_notion_page(page_id, cover_url):
    """
    Add cover image to Notion page
    """
    update_data = {"cover": {"type": "external", "external": {"url": cover_url}}}
    update_url = f"https://api.notion.com/v1/pages/{page_id}"
    response = requests.patch(update_url, headers=headers, data=json.dumps(update_data))

    if response.status_code == 200:
        print(f"Page {page_id} updated successfully with cover image")
        return True
    else:
        print(
            f"Failed to update page {page_id}: {response.status_code}, {response.text}"
        )
        return False


def create_notion_page_for_song(song):
    """
    Create a new Notion page for a song
    """
    track_name = song["name"]
    artists = ", ".join(song["artists"])
    spotify_url = song["spotify_url"]

    # Get album art URL safely
    try:
        cover_url = song["spotify_data"]["track"]["album"]["images"][0]["url"]
    except (KeyError, IndexError):
        cover_url = None
        print(f"No album art found for {track_name}")

    # Create Notion page data
    create_data = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "Title": {"title": [{"text": {"content": track_name}}]},
            "Album": {
                "rich_text": [
                    {
                        "text": {
                            "content": song["spotify_data"]["track"]["album"]["name"]
                        }
                    }
                ]
            },
            "Artists": {"rich_text": [{"text": {"content": artists}}]},
            "URL": {"url": spotify_url},
        },
    }

    create_url = "https://api.notion.com/v1/pages"
    create_response = requests.post(create_url, headers=headers, json=create_data)

    if create_response.status_code == 200:
        page_id = create_response.json()["id"]
        print(f"✓ Added: {track_name} by {artists}")

        # Add cover image if available
        if cover_url:
            add_cover_image_to_notion_page(page_id, cover_url)

        return True
    else:
        print(f"✗ Failed to add page for {track_name}: {create_response.status_code}")
        print(create_response.text)
        return False


def main():
    try:
        print("Starting Spotify to Notion sync...")

        # Get Spotify Liked Songs
        print("\n1. Fetching Spotify liked songs...")
        liked_songs = get_liked_songs()
        print(f"Found {len(liked_songs)} liked songs.")

        # Get registered pages from Notion database
        print("\n2. Fetching Notion database pages...")
        items = fetch_notion_pages()

        # Check by URL
        print("\n3. Comparing songs with Notion database...")
        results = check_songs_by_spotify_url(liked_songs, items)

        # Display statistics
        print(f"\n--- Statistics ---")
        print(f"Total liked songs: {len(liked_songs)}")
        print(f"Already registered: {len(results['registered'])}")
        print(f"Not registered: {len(results['not_registered'])}")

        # Add unregistered songs to Notion
        if results["not_registered"]:
            print(
                f"\n4. Adding {len(results['not_registered'])} new songs to Notion..."
            )

            success_count = 0
            for i, song in enumerate(results["not_registered"], 1):
                print(f"\nProcessing ({i}/{len(results['not_registered'])})...")

                if create_notion_page_for_song(song):
                    success_count += 1

                # Add delay to avoid rate limiting
                time.sleep(0.5)

                # Remove this break to process all songs
                # Currently set to process only first song for testing
                # if i == 1:
                #     print(
                #         "\n⚠️  Test mode: Only processing first song. Remove the break to process all songs."
                #     )
                #     break

            print(f"\n--- Final Results ---")
            print(f"Successfully added: {success_count} songs")
            print(
                f"Failed to add: {len(results['not_registered']) - success_count} songs"
            )
        else:
            print("\n✓ All liked songs are already registered in Notion!")

    except Exception as e:
        print(f"[Error] {e}")
        raise


if __name__ == "__main__":
    main()
