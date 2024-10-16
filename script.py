import os
from dotenv import load_dotenv
import requests
import json
import base64

# 環境ファイル関連
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


def fetch_notion_pages():
    """
    Notion データベースからすべてのページを取得する
    """
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    all_items = []
    has_more = True
    start_cursor = None

    # ペイロードの設定
    payload = {}

    while has_more:
        if start_cursor:
            payload["start_cursor"] = start_cursor

        # データベースクエリを送信
        response = requests.post(url, headers=headers, json=payload)
        data = response.json()

        # アイテムをリストに追加
        all_items.extend(data["results"])

        # ページネーションのためのカーソルを更新
        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")

    return all_items


def extract_track_id(item):
    """
    NotionのページからSpotifyのトラックIDを抽出
    """
    try:
        url = item["properties"]["URL"]["url"]
        if url:
            return url.split("/")[-1]
    except KeyError:
        print("URL property not found in item:", item)
    return None


def get_spotify_token(client_id, client_secret):
    """
    Spotify API からアクセストークンを取得する
    """

    url = "https://accounts.spotify.com/api/token"
    auth_str = f"{client_id}:{client_secret}"
    b64_auth_str = base64.b64encode(auth_str.encode()).decode()
    headers = {
        "Authorization": f"Basic {b64_auth_str}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {"grant_type": "client_credentials"}
    response = requests.post(url, headers=headers, data=data)
    if response.status_code == 200:
        return response.json().get("access_token")
    else:
        print("Spotify token request failed:", response.status_code, response.text)
        return None


def get_album_art(track_id, token):
    """
    Spotify API からトラックのアルバムアートを取得する
    """

    url = f"https://api.spotify.com/v1/tracks/{track_id}"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get("album", {}).get("images", [{}])[0].get("url")
    else:
        return None


def main():
    try:
        items = fetch_notion_pages()

        # itemsの中からカバー画像がないものを抽出
        items_without_cover = [item for item in items if not item.get("cover")]

        spotify_token = get_spotify_token(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)

        for item in items_without_cover:
            page_id = item["id"]
            track_id = extract_track_id(item)
            album_art_url = get_album_art(track_id, spotify_token)

            if album_art_url:
                # カバー画像を変更するリクエストのボディ
                update_data = {
                    "cover": {"type": "external", "external": {"url": album_art_url}}
                }
                # ページIDを使ってカバー画像を変更するリクエストを送信
                update_url = f"https://api.notion.com/v1/pages/{page_id}"
                update_response = requests.patch(
                    update_url, headers=headers, data=json.dumps(update_data)
                )

                if update_response.status_code == 200:
                    print(f"Page {page_id} updated successfully")
                else:
                    print(
                        f"Failed to update page {page_id}: {update_response.status_code}, {update_response.text}"
                    )
            else:
                print(f"Failed to get album art for track {track_id}")

    except Exception as e:
        print("[Error]", e)
        raise


if __name__ == "__main__":
    main()
