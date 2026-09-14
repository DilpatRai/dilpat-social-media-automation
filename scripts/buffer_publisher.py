import csv
import json
import os
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "data" / "posts.json"
CSV_FILE = ROOT / "data" / "posts.csv"
BUFFER_URL = "https://api.buffer.com"
TARGET_SERVICES = ("instagram", "facebook", "linkedin")


def buffer_request(query):
    key = os.getenv("BUFFER_API_KEY")
    if not key:
        raise RuntimeError("BUFFER_API_KEY GitHub secret is required")
    response = requests.post(
        BUFFER_URL,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        json={"query": query},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise RuntimeError("; ".join(e.get("message", "Buffer API error") for e in payload["errors"]))
    return payload.get("data", {})


def discover_channels():
    organizations = buffer_request("""
      query { account { organizations { id name } } }
    """)["account"]["organizations"]
    requested = os.getenv("BUFFER_ORGANIZATION_ID")
    if requested:
        organizations = [o for o in organizations if o["id"] == requested]
    if len(organizations) != 1:
        names = ", ".join(f"{o['name']} ({o['id']})" for o in organizations)
        raise RuntimeError(f"Set BUFFER_ORGANIZATION_ID. Available: {names or 'none'}")

    org_id = organizations[0]["id"]
    channels = buffer_request(f"""
      query {{ channels(input: {{ organizationId: \"{org_id}\" }}) {{ id name displayName service isQueuePaused }} }}
    """)["channels"]
    result = {}
    for service in TARGET_SERVICES:
        matches = [c for c in channels if c.get("service") == service]
        if len(matches) != 1:
            raise RuntimeError(f"Expected one Buffer {service} channel; found {len(matches)}")
        if matches[0].get("isQueuePaused"):
            raise RuntimeError(f"Buffer {service} queue is paused")
        result[service] = matches[0]
    return result


def create_image_post(channel_id, text, image_url):
    text_json = json.dumps(text, ensure_ascii=False)
    url_json = json.dumps(image_url)
    query = f"""
      mutation {{
        createPost(input: {{
          text: {text_json}
          channelId: \"{channel_id}\"
          schedulingType: automatic
          mode: addToQueue
          aiAssisted: true
          assets: [{{ image: {{ url: {url_json} }} }}]
        }}) {{
          ... on PostActionSuccess {{ post {{ id text dueAt channelId }} }}
          ... on MutationError {{ message }}
        }}
      }}
    """
    result = buffer_request(query).get("createPost", {})
    if "message" in result:
        raise RuntimeError(result["message"])
    if "post" not in result:
        raise RuntimeError(f"Unexpected Buffer response: {result}")
    return result["post"]


def update_csv(history):
    fields = [
        "request_id", "topic", "image_file_id", "image_path",
        "instagram_caption", "facebook_caption", "linkedin_caption", "alt_text",
        "mode", "status", "created_at", "published_at", "error",
        "buffer_instagram_id", "buffer_facebook_id", "buffer_linkedin_id",
    ]
    with CSV_FILE.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k: p.get(k, "") for k in fields} for p in history)


def main():
    history = json.loads(HISTORY.read_text(encoding="utf-8"))
    if not history:
        raise RuntimeError("No generated post found")
    post = history[-1]
    if post.get("status") == "buffer_queued":
        print(f"Already queued: {post.get('request_id')}")
        return

    repo = os.getenv("GITHUB_REPOSITORY", "DilpatRai/dilpat-social-media-automation")
    branch = os.getenv("GITHUB_REF_NAME", "main")
    image_url = f"https://raw.githubusercontent.com/{repo}/{branch}/{post['image_path']}"
    channels = discover_channels()
    captions = {
        "instagram": post["instagram_caption"],
        "facebook": post["facebook_caption"],
        "linkedin": post["linkedin_caption"],
    }
    ids = {}
    try:
        for service in TARGET_SERVICES:
            ids[service] = create_image_post(channels[service]["id"], captions[service], image_url)["id"]
    except Exception as exc:
        post["status"] = "failed"
        post["error"] = f"Buffer failed after {len(ids)} channel(s): {exc}"
        for service in TARGET_SERVICES:
            post[f"buffer_{service}_id"] = ids.get(service, "")
        HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        update_csv(history)
        raise

    post["status"] = "buffer_queued"
    post["error"] = ""
    for service in TARGET_SERVICES:
        post[f"buffer_{service}_id"] = ids[service]
    HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    update_csv(history)
    print(f"BUFFER QUEUED: {post['request_id']}")


if __name__ == "__main__":
    main()
