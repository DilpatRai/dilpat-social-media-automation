import base64
import csv
import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Asia/Karachi")
HISTORY = ROOT / "data" / "posts.json"
CSV_FILE = ROOT / "data" / "posts.csv"
TOPICS_FILE = ROOT / "data" / "topics.json"
SETTINGS_FILE = ROOT / "data" / "settings.json"


def read_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def choose_topic(history, topics):
    counts = Counter(p.get("topic") for p in history if p.get("topic"))
    recent = [p.get("topic") for p in history[-4:] if p.get("topic")]
    ranked = sorted(topics, key=lambda t: (counts[t], topics.index(t)))
    for topic in ranked:
        if topic not in recent:
            return topic
    return ranked[0]


def request_id(now):
    return now.strftime("dilpat-%Y-%m-%d-%H%M-PKT")


def generate_content(client, topic, history):
    recent_topics = [p.get("topic", "") for p in history[-10:]]
    recent_hooks = [p.get("instagram_caption", "")[:180] for p in history[-10:]]
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "instagram_caption": {"type": "string"},
            "facebook_caption": {"type": "string"},
            "linkedin_caption": {"type": "string"},
            "alt_text": {"type": "string"},
            "image_prompt": {"type": "string"},
            "image_title": {"type": "string"}
        },
        "required": ["instagram_caption", "facebook_caption", "linkedin_caption", "alt_text", "image_prompt", "image_title"]
    }
    prompt = f"""
You are the daily technical content writer for Dilpat Rai, Software Engineer.
Create ONE original social-media post about: {topic}.

Brand rules:
- Use only the identity Dilpat Rai / Software Engineer.
- Do not invent employers, clients, certifications, achievements, statistics, projects, or experience.
- Professional, practical, technically accurate, clear English.
- No motivational filler, clickbait, fake statistics, or excessive emojis.
- The three captions must be genuinely adapted to their platforms, not copies.
- Do not repeat recent topics/hooks. Recent topics: {recent_topics}
- Recent hook samples: {recent_hooks}

Instagram: strong hook, accessible explanation, practical takeaway, CTA, restrained hashtags.
Facebook: strong hook, simple technical explanation, practical takeaway, discussion CTA, relevant hashtags.
LinkedIn: strongest professional version with an engineering observation, technical insight, practical lesson, and thoughtful CTA; small number of professional hashtags.

Image: create a premium original technical illustration concept. Dark background, white typography, one restrained accent color, minimal geometric elements, subtle technical patterns, strong hierarchy, clean spacing. Include only a short accurate title if text is needed. No logos, fake metrics, random text, or decorative clutter.

Return only the requested JSON fields.
"""
    response = client.responses.create(
        model=os.getenv("OPENAI_TEXT_MODEL", "gpt-5.6-luna"),
        input=prompt,
        text={"format": {"type": "json_schema", "name": "daily_post", "strict": True, "schema": schema}},
    )
    return json.loads(response.output_text)


def generate_image(client, image_prompt, image_title):
    prompt = f"""
Create a premium editorial technology visual for a professional Software Engineer social-media post.
Topic concept: {image_prompt}
Short title to render accurately: {image_title}

Visual direction: dark background, professional typography, white text, exactly one restrained accent color,
minimal geometric elements, subtle technical patterns, clean spacing, strong hierarchy, technically relevant
illustration. No company logos, no brand logos, no fake statistics, no random words, no watermark, no people,
and no clutter. Ensure all visible text is spelled correctly and remains highly readable.
"""
    result = client.images.generate(
        model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2"),
        prompt=prompt,
        size="1536x1024",
        quality="high",
    )
    return base64.b64decode(result.data[0].b64_json)


def qa_image(client, image_bytes, topic, captions):
    import base64
    data_url = "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")
    response = client.responses.create(
        model=os.getenv("OPENAI_TEXT_MODEL", "gpt-5.6-luna"),
        input=[{
            "role": "user",
            "content": [
                {"type": "input_text", "text": f"Review this generated social-media image for topic '{topic}'. Check technical relevance, readability, spelling, obvious visual artifacts, contrast, and whether it follows a premium professional technology style. Respond with JSON only: {{\"approved\": true/false, \"reason\": \"short reason\"}}. Captions context: {captions[:1000]}"},
                {"type": "input_image", "image_url": data_url},
            ],
        }],
        text={"format": {"type": "json_schema", "name": "image_qa", "strict": True, "schema": {"type": "object", "additionalProperties": False, "properties": {"approved": {"type": "boolean"}, "reason": {"type": "string"}}, "required": ["approved", "reason"]}}},
    )
    return json.loads(response.output_text)


def update_csv(history):
    fields = ["request_id", "topic", "image_file_id", "image_path", "instagram_caption", "facebook_caption", "linkedin_caption", "alt_text", "mode", "status", "created_at", "published_at", "error"]
    with CSV_FILE.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k: p.get(k, "") for k in fields} for p in history)


def main():
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY GitHub secret is required")

    settings = read_json(SETTINGS_FILE, {})
    history = read_json(HISTORY, [])
    topics = read_json(TOPICS_FILE, {}).get("topics", [])
    if not topics:
        raise RuntimeError("No topics configured")

    now = datetime.now(TZ)
    rid = request_id(now)
    if any(p.get("request_id") == rid for p in history):
        print(f"Duplicate request_id {rid}; nothing to do.")
        return

    client = OpenAI()
    topic = choose_topic(history, topics)

    content = generate_content(client, topic, history)
    image_bytes = generate_image(client, content["image_prompt"], content["image_title"])

    qa = qa_image(client, image_bytes, topic, content["linkedin_caption"])
    if not qa["approved"]:
        print("First image failed QA; regenerating once.")
        image_bytes = generate_image(client, content["image_prompt"] + " Improve readability and remove any possible visual artifacts.", content["image_title"])
        qa = qa_image(client, image_bytes, topic, content["linkedin_caption"])
        if not qa["approved"]:
            raise RuntimeError("Generated image failed visual QA twice: " + qa["reason"])

    year_month = now.strftime("%Y/%m")
    media_dir = ROOT / "media" / year_month
    content_dir = ROOT / "content" / year_month
    media_dir.mkdir(parents=True, exist_ok=True)
    content_dir.mkdir(parents=True, exist_ok=True)

    image_path = media_dir / f"{rid}.png"
    image_path.write_bytes(image_bytes)

    record = {
        "request_id": rid,
        "topic": topic,
        "image_file_id": rid + ".png",
        "image_path": str(image_path.relative_to(ROOT)).replace("\\", "/"),
        "instagram_caption": content["instagram_caption"],
        "facebook_caption": content["facebook_caption"],
        "linkedin_caption": content["linkedin_caption"],
        "alt_text": content["alt_text"],
        "mode": settings.get("mode", "queue"),
        "status": "ready",
        "created_at": now.isoformat(),
        "published_at": "",
        "error": "",
    }
    history.append(record)
    HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    update_csv(history)

    package = f"""# {topic}\n\n- Request ID: `{rid}`\n- Status: `ready`\n- Mode: `queue`\n- Created: `{now.isoformat()}`\n- Image: `{record['image_path']}`\n\n## Instagram\n\n{content['instagram_caption']}\n\n## Facebook\n\n{content['facebook_caption']}\n\n## LinkedIn\n\n{content['linkedin_caption']}\n\n## Alt text\n\n{content['alt_text']}\n\n## Image QA\n\nApproved: `{qa['approved']}` — {qa['reason']}\n"""
    (content_dir / f"{rid}.md").write_text(package, encoding="utf-8")
    print(f"READY: {rid} | {topic}")


if __name__ == "__main__":
    main()
