
"""AuraCry AI Companion and private Baby Memory Diary."""

import os
import re
import json
import time
from datetime import date

import requests
from flask import Blueprint, jsonify, request

import db
from auth_utils import current_user, role_required


bp = Blueprint("companion", __name__, url_prefix="/api/companion")


# =========================================================
# 1. SAFE FALLBACK ANSWERS
# =========================================================

def _fallback_answer(message, latest=None):

    low = message.lower()

    if any(k in low for k in (
        "breath", "blue", "grey", "gray", "seizure",
        "unresponsive", "emergency"
    )):
        return (
            "This may need urgent medical attention. If your baby "
            "is struggling to breathe, is blue or grey, has a seizure, "
            "or is unresponsive, seek emergency medical care now."
        )

    if any(k in low for k in (
        "cry", "crying", "unsettled", "fussy"
    )):
        if latest:
            try:
                confidence = float(latest["confidence"]) * 100
            except (TypeError, ValueError, KeyError):
                confidence = 0

            return (
                f"Your latest AuraCry analysis estimated "
                f"{latest['predicted_category']} "
                f"({confidence:.1f}% model confidence). "
                "Cry patterns can have many causes. Please check "
                "feeding, temperature, diaper, burping and comfort. "
                "This result is an estimate, not a diagnosis."
            )

        return (
            "Crying can have several causes, including hunger, "
            "tiredness, discomfort or a need to burp. Check your "
            "baby's immediate needs and contact your pediatrician "
            "if you are concerned."
        )

    if any(k in low for k in (
        "sleep", "sleepy", "tired", "nap"
    )):
        return (
            "Try a calm, dim environment and a consistent soothing "
            "routine. For every sleep, place your baby on their back "
            "on a firm, flat sleep surface with no loose bedding "
            "or toys."
        )

    if any(k in low for k in (
        "feed", "hungry", "milk", "breastfeed"
    )):
        return (
            "Look for your baby's hunger cues and follow feeding "
            "guidance from your pediatrician. Contact a healthcare "
            "professional if feeding is difficult or wet diapers "
            "decrease."
        )

    if any(k in low for k in ("burp", "gas")):
        return (
            "You can try holding your baby upright against your "
            "chest and gently patting or rubbing their back."
        )

    return (
        "I'm here to help with your baby's care, development, "
        "special moments and AuraCry results. Tell me a little "
        "more about what happened, and I'll do my best to help."
    )


# =========================================================
# 2. GEMINI API AND MEMORY EXTRACTION
# =========================================================

def _gemini_chat(message, context, fallback):

    key = os.getenv("GEMINI_API_KEY", "").strip()

    if not key:
        print("[AuraCry] GEMINI_API_KEY is not configured.")

        return {
            "answer": fallback,
            "memory_suggestion": None
        }

    model = os.getenv(
        "GEMINI_MODEL",
        "gemini-2.5-flash"
    ).strip()

    prompt = f"""
You are AuraCry AI, a kind, natural and helpful assistant
for parents of babies and infants.

Your responsibilities:

1. Answer the parent's actual question.
2. Understand the meaning and context of their message.
3. Recognize when a parent shares a special or memorable
   experience about their baby.
4. Suggest a diary entry when appropriate.

IMPORTANT MEMORY RECOGNITION:

A memorable experience is not limited to first milestones.

Recognize meaningful experiences such as:

- First steps, first words and first smiles.
- Favourite food or trying a new food.
- Enjoying mango or another favourite meal.
- Playing with parents, grandparents or siblings.
- Visiting a park, beach or another new place.
- Birthday celebrations and family gatherings.
- Funny, sweet or surprising experiences.
- Learning something new.
- Achievements and developmental milestones.
- Special interactions with family.
- Any other meaningful experience the parent wants to remember.

Do not restrict memory recognition to a fixed list
of keywords.

For example:

"My baby just enjoyed his favourite food."

"My baby played with his grandfather today."

"My baby smiled when I came home."

"My baby enjoyed his first visit to the park."

"My baby danced when music was playing."

These are possible memorable experiences.

If the parent clearly shares a special experience,
create a memory suggestion.

Do not create a memory for ordinary questions,
cry analysis questions or general medical discussions.

If the message is ambiguous, ask a follow-up question
instead of inventing a memory.

MEMORY FORMAT:

title:
A short, meaningful title.

story:
Preserve the parent's original details. Do not invent
events, names, ages or emotions.

event_date:
Use the date supplied by the parent if available.
Otherwise use today's date.

Today's date: {date.today().isoformat()}

MEDICAL SAFETY:

- Never diagnose a medical condition.
- Never prescribe medicine.
- Never recommend unsafe sleep practices.
- Never recommend honey for babies under 12 months.
- For breathing difficulty, blue/grey colour, seizures
  or unresponsiveness, advise emergency medical care.
- Recommend a pediatrician for medical concerns.
- Treat AuraCry model predictions as estimates,
  not medical facts.

BABY CONTEXT:
{json.dumps(context, default=str)}

PARENT MESSAGE:
{message}

SAFE FALLBACK GUIDANCE:
{fallback}

Return ONLY valid JSON.

If there is no memorable experience:

{{
  "answer": "Your natural and relevant response",
  "memory_suggestion": null
}}

If the parent shares a memorable experience:

{{
  "answer": "Your natural and relevant response",
  "memory_suggestion": {{
    "title": "A short memory title",
    "story": "A description based only on the parent's message",
    "event_date": "{date.today().isoformat()}"
  }}
}}
"""

    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"models/{model}:generateContent"
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.4,
            "responseMimeType": "application/json"
        }
    }

    headers = {
        "x-goog-api-key": key,
        "Content-Type": "application/json"
    }

    # Retry temporary API failures.
    max_attempts = 3
    response = None

    for attempt in range(max_attempts):

        try:
            print(
                f"[AuraCry] Calling Gemini model: {model} "
                f"(attempt {attempt + 1}/{max_attempts})"
            )

            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=90
            )

            if response.status_code in (
                429, 500, 502, 503, 504
            ):

                if attempt < max_attempts - 1:

                    retry_delay = 2 ** (attempt + 1)

                    retry_after = response.headers.get(
                        "Retry-After"
                    )

                    if retry_after:
                        try:
                            retry_delay = min(
                                float(retry_after), 30
                            )
                        except ValueError:
                            pass

                    print(
                        f"[AuraCry] Gemini returned "
                        f"{response.status_code}. "
                        f"Retrying in {retry_delay} seconds."
                    )

                    time.sleep(retry_delay)
                    continue

            response.raise_for_status()
            break

        except requests.exceptions.Timeout as e:

            print("[AuraCry] Gemini request timed out:", str(e))

            if attempt < max_attempts - 1:
                time.sleep(2 ** (attempt + 1))
                continue

            return {
                "answer": fallback,
                "memory_suggestion": None
            }

        except requests.exceptions.RequestException as e:

            status = (
                response.status_code
                if response is not None
                else "No response"
            )

            error_body = (
                response.text[:1000]
                if response is not None
                else str(e)
            )

            print(
                f"[AuraCry Gemini Error] HTTP {status}: "
                f"{error_body}"
            )

            return {
                "answer": fallback,
                "memory_suggestion": None
            }

    # -----------------------------------------------------
    # Parse Gemini response
    # -----------------------------------------------------

    try:

        result = response.json()

        candidates = result.get("candidates", [])

        if not candidates:
            raise ValueError(
                "Gemini returned no candidates."
            )

        parts = (
            candidates[0]
            .get("content", {})
            .get("parts", [])
        )

        generated_text = "".join(
            part.get("text", "")
            for part in parts
        ).strip()

        if not generated_text:
            raise ValueError(
                "Gemini returned an empty response."
            )

        # Remove Markdown code fences if present.
        generated_text = re.sub(
            r"^```(?:json)?\s*|\s*```$",
            "",
            generated_text,
            flags=re.IGNORECASE
        ).strip()

        data = json.loads(generated_text)

        answer = data.get("answer")

        if not isinstance(answer, str) or not answer.strip():
            answer = fallback

        memory = data.get("memory_suggestion")

        # Validate memory suggestion.
        if isinstance(memory, dict):

            title = str(
                memory.get("title") or ""
            ).strip()

            story = str(
                memory.get("story") or ""
            ).strip()

            event_date = str(
                memory.get("event_date")
                or date.today().isoformat()
            ).strip()

            try:
                date.fromisoformat(event_date)
            except ValueError:
                event_date = date.today().isoformat()

            if (
                not title
                or not story
                or len(title) > 100
                or len(story) > 2000
            ):
                memory = None

            else:
                memory = {
                    "title": title,
                    "story": story,
                    "event_date": event_date
                }

        else:
            memory = None

        return {
            "answer": answer.strip(),
            "memory_suggestion": memory
        }

    except (ValueError, KeyError, TypeError, IndexError) as e:

        print(
            "[AuraCry] Could not parse Gemini response:",
            str(e)
        )

        return {
            "answer": fallback,
            "memory_suggestion": None
        }


# =========================================================
# 3. CHAT API
# =========================================================

@bp.post("/chat")
@role_required("USER")
def chat():

    data = request.get_json(silent=True) or {}

    msg = data.get("message", "")

    if not isinstance(msg, str):
        return jsonify(
            error="validation",
            message="Message must be text."
        ), 400

    msg = msg.strip()

    if not msg or len(msg) > 2000:
        return jsonify(
            error="validation",
            message="Enter a message up to 2,000 characters."
        ), 400

    user = current_user()

    latest = db.one(
        """
        SELECT predicted_category, confidence, created_at
        FROM analyses
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 1
        """,
        (user["id"],)
    )

    context = {
        "parent_name": user["name"],
        "latest_analysis": latest
    }

    fallback = _fallback_answer(msg, latest)

    result = _gemini_chat(
        msg,
        context,
        fallback
    )

    return jsonify(
        answer=result["answer"],
        memory_suggestion=result["memory_suggestion"],
        ai_enabled=bool(
            os.getenv("GEMINI_API_KEY", "").strip()
        )
    )


# =========================================================
# 4. GET ALL BABY MEMORIES
# =========================================================

@bp.get("/memories")
@role_required("USER")
def memories():

    rows = db.q(
        """
        SELECT id, title, story, event_date, created_at
        FROM baby_memories
        WHERE user_id=?
        ORDER BY event_date DESC, id DESC
        """,
        (current_user()["id"],)
    )

    return jsonify(memories=rows)


# =========================================================
# 5. SAVE A BABY MEMORY
# =========================================================

@bp.post("/memories")
@role_required("USER")
def create_memory():

    data = request.get_json(silent=True) or {}

    title = str(
        data.get("title") or ""
    ).strip()

    story = str(
        data.get("story") or ""
    ).strip()

    event_date = str(
        data.get("event_date")
        or date.today().isoformat()
    ).strip()

    if (
        not title
        or len(title) > 100
        or not story
        or len(story) > 2000
        or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}",
            event_date
        )
    ):
        return jsonify(
            error="validation",
            message="Enter a title, valid date and a short memory."
        ), 400

    try:
        date.fromisoformat(event_date)

    except ValueError:
        return jsonify(
            error="validation",
            message="Invalid memory date."
        ), 400

    memory_id = db.execute(
        """
        INSERT INTO baby_memories
        (user_id, title, story, event_date)
        VALUES (?, ?, ?, ?)
        """,
        (
            current_user()["id"],
            title,
            story,
            event_date
        )
    )

    saved = db.one(
        """
        SELECT id, title, story, event_date, created_at
        FROM baby_memories
        WHERE id=?
        """,
        (memory_id,)
    )

    return jsonify(
        memory=saved
    ), 201


# =========================================================
# 6. DELETE A BABY MEMORY
# =========================================================

@bp.delete("/memories/<int:mid>")
@role_required("USER")
def delete_memory(mid):

    row = db.one(
        """
        SELECT id
        FROM baby_memories
        WHERE id=? AND user_id=?
        """,
        (
            mid,
            current_user()["id"]
        )
    )

    if not row:
        return jsonify(
            error="not_found",
            message="Memory not found."
        ), 404

    db.execute(
        """
        DELETE FROM baby_memories
        WHERE id=?
        """,
        (mid,)
    )

    return jsonify(ok=True)
