import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "data" / "posts.json"


def main():
    if not HISTORY.exists():
        raise RuntimeError("data/posts.json does not exist")

    history = json.loads(HISTORY.read_text(encoding="utf-8"))
    if not history:
        raise RuntimeError("No generated posts found in data/posts.json")

    post = history[-1]
    required = [
        "request_id",
        "topic",
        "image_path",
        "instagram_caption",
        "facebook_caption",
        "linkedin_caption",
        "alt_text",
        "status",
    ]

    missing = [field for field in required if not post.get(field)]
    if missing:
        raise RuntimeError("Latest post is missing fields: " + ", ".join(missing))

    if post.get("status") not in {"ready", "failed", "buffer_queued"}:
        raise RuntimeError(f"Unsupported post status: {post.get('status')}")

    image = ROOT / post["image_path"]
    if not image.exists():
        raise RuntimeError(f"Image file does not exist: {post['image_path']}")

    print(f"VALID: {post['request_id']} | {post['topic']} | status={post['status']}")


if __name__ == "__main__":
    main()
