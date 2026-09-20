import json
import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "data" / "posts.json"
TOPICS = ROOT / "data" / "topics.json"

REQUEST_ID_PATTERN = re.compile(r"^dilpat-\d{4}-\d{2}-\d{2}-\d{4}-PKT$")
IMAGE_WIDTH = 1080
IMAGE_HEIGHT = 1350
MAX_IMAGE_BYTES = 5_000_000
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def validate_png(image: Path) -> None:
    if image.suffix.lower() != ".png":
        raise RuntimeError(
            f"Social visual must be PNG for new posts; found: {image.suffix or 'no extension'}"
        )

    size = image.stat().st_size
    if size > MAX_IMAGE_BYTES:
        raise RuntimeError(
            f"PNG exceeds the 5 MB cross-platform upload limit: {size} bytes"
        )

    with image.open("rb") as f:
        header = f.read(33)

    if len(header) < 33 or header[:8] != PNG_SIGNATURE:
        raise RuntimeError("Image is not a valid PNG file")

    width, height, bit_depth, color_type = struct.unpack(">IIBB", header[16:26])
    if (width, height) != (IMAGE_WIDTH, IMAGE_HEIGHT):
        raise RuntimeError(
            f"PNG must be exactly {IMAGE_WIDTH}x{IMAGE_HEIGHT}; found {width}x{height}")

    if bit_depth not in {1,2,4,8} or color_type != 3:
        raise RuntimeError("PNG must use indexed-color PNG encoding")


def validate_request_ids(history):
    ids = [post.get("request_id", "") for post in history]
    duplicates = sorted({request_id for request_id in ids if ids.count(request_id) > 1})
    if duplicates:
        raise RuntimeError("Duplicate request_id values found: " + ", ".join(duplicates))

    for request_id in ids:
        if not REQUEST_ID_PATTERN.fullmatch(request_id):
            raise RuntimeError(f"Invalid request_id format: {request_id}")


def validate_topic_rotation(history):
    if not TOPICS.exists():
        raise RuntimeError("data/topics.json does not exist")

    configured_topics = json.loads(TOPICS.read_text(encoding="utf-8")).get("topics", [])
    if not configured_topics:
        raise RuntimeError("data/topics.json contains no topics")

    latest = history[-1]
    if latest.get("status") != "ready":
        return

    previous_topics = {
        post.get("topic")
        for post in history[:-1]
        if post.get("topic")
    }
    if latest.get("topic") in previous_topics:
        # Allow reuse only after the configured topic list has been exhausted.
        recent_topics = [post.get("topic") for post in history[-len(configured_topics):]]
        if len(set(recent_topics)) < len(configured_topics):
            raise RuntimeError(
                f"Topic '{latest.get('topic')}' was already used before the topic rotation completed"
            )

    if latest.get("topic") not in configured_topics:
        raise RuntimeError(f"Topic is not configured in data/topics.json: {latest.get('topic')}")


def main():
    if not HISTORY.exists():
        raise RuntimeError("data/posts.json does not exist")

    history = json.loads(HISTORY.read_text(encoding="utf-8"))
    if not history:
        raise RuntimeError("No generated posts found in data/posts.json")

    validate_request_ids(history)
    validate_topic_rotation(history)

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

    status = post.get("status")
    if status not in {"ready", "failed", "posted"}:
        raise RuntimeError(f"Unsupported post status: {status}")

    if status == "ready":
        if post.get("mode") != "queue":
            raise RuntimeError("A ready post must use mode=queue")
        if post.get("published_at", ""):
            raise RuntimeError("A ready post must have blank published_at")
        if post.get("error", ""):
            raise RuntimeError("A ready post must have blank error")

    image = ROOT / post["image_path"]
    if not image.exists():
        raise RuntimeError(f"Image file does not exist: {post['image_path']}")

    # New generated posts must be PNG. Older already-queued history may keep its
    # original legacy SVG asset so the validator does not break historical records.
    if status == "ready":
        validate_png(image)

    print(f"VALID: {post['request_id']} | {post['topic']} | status={status}")


if __name__ == "__main__":
    main()
