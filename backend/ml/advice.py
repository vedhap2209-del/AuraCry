"""Soothing suggestions, massage guides, lullabies and videos.

Design:
  * KB (below) is the SAFE baseline and always available (works offline).
  * If GEMINI_API_KEY is set, Gemini personalises the steps using the measured
    evidence. Its answer is validated; on ANY problem we silently use the KB.
  * Red-flag / safety text ALWAYS comes from the KB, never from the LLM.
  * Videos: curated_videos.json  ->  YouTube Data API (YOUTUBE_API_KEY)  ->  search links.
To use another LLM, only change `_call_llm`.
"""
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import quote_plus

import requests

HERE = Path(__file__).resolve().parent
LULLABY_LANG = os.getenv("LULLABY_LANGUAGE", "").strip()      # e.g. "Telugu", "Hindi"

GENERAL_RED_FLAGS = [
    "Fever of 38.0 C / 100.4 F or higher in a baby under 3 months: get medical care right away.",
    "Crying that is very weak, unusually high-pitched, or different from your baby's normal cry.",
    "Breathing difficulty, blue/grey lips, unusual floppiness or hard-to-wake sleepiness.",
    "Repeated or green/bloody vomiting, blood in stool, swollen hard belly, or refusing several feeds.",
    "Inconsolable crying for more than about 2 hours despite trying the steps above.",
    "If you feel overwhelmed: lay the baby safely on their back in the cot, step away for a few minutes. Never shake a baby.",
]

LULLABY_WHEN = {"Sleepy", "Fussy", "Uncertain"}   # cry types where singing/humming is the right next step

KB = {
    "Hungry": {
        "intro": "This sounds like a hunger cry. Try feeding first, then re-check.",
        "steps": [
            {"title": "Check the clock", "detail": "If it has been roughly 2-3 hours since the last feed (or your paediatrician's schedule says it's time), offer a feed."},
            {"title": "Look for early hunger cues", "detail": "Rooting, hand-to-mouth, lip smacking and turning toward your chest/bottle mean hunger; crying is a late cue."},
            {"title": "Feed calmly and responsively", "detail": "Hold baby semi-upright. For bottles, use paced feeding: keep the bottle nearly horizontal and pause every few sucks."},
            {"title": "Burp mid-feed and after", "detail": "Pause halfway to burp, and again at the end, so swallowed air doesn't cause a second bout of crying."},
            {"title": "Soothe while you prepare", "detail": "Hold baby close and speak softly; a fed baby is calmer than a baby who is rocked while hungry."},
        ],
        "massage": None,
        "lullaby": {"style": "Calm humming after the feed", "tempo": "slow, about 60-80 beats per minute", "tips": ["Sing or hum softly once baby has fed to help them settle.", "Keep your voice low and even."]},
        "videos": [{"label": "Paced bottle feeding", "query": "paced bottle feeding baby how to"}, {"label": "Baby hunger cues", "query": "newborn hunger cues early signs"}],
    },
    "Sleepy": {
        "intro": "This sounds like an over-tired / sleepy cry. Reduce stimulation and help baby wind down.",
        "steps": [
            {"title": "Dim the room and quiet things down", "detail": "Low light, no screens, one calm voice. Overstimulation makes tired babies cry harder."},
            {"title": "Add gentle, rhythmic soothing", "detail": "Slow rocking, patting the back or bottom, or holding baby close while walking slowly."},
            {"title": "Sing a lullaby or play soft white noise", "detail": "Steady low-volume sound (well below conversation level) helps many babies settle."},
            {"title": "Swaddle only if it's safe", "detail": "Snug around the arms with hips free to move, on the back, and stop swaddling once baby shows signs of rolling."},
            {"title": "Put baby down drowsy but awake", "detail": "Place on their back on a firm, flat sleep surface with nothing else in the cot: no pillows, bumpers or loose blankets."},
        ],
        "massage": {"name": "Calming back and foot strokes", "body_part": "Back and feet",
                    "how_to": ["Lay baby on your lap or a soft mat while you are watching them.", "With a warm, flat palm make slow strokes from the neck down to the bottom (about 10 times).", "Hold one foot and use your thumb to make slow, small circles on the sole, then gently squeeze each toe.", "Keep pressure very light and stop when baby relaxes or looks away."],
                    "caution": "Only massage a calm, awake baby. Always place baby on their back for sleep."},
        "lullaby": {"style": "Soft lullaby with a steady rhythm", "tempo": "slow, about 60-70 beats per minute", "tips": ["Sing low and slow; repeat the same tune.", "Slowly fade your voice as baby's eyes close."]},
        "videos": [{"label": "Lullaby to help baby sleep", "query": "lullaby for babies to go to sleep", "lullaby": True}, {"label": "Safe swaddling", "query": "how to swaddle a baby safely"}, {"label": "Soft white noise", "query": "white noise for babies sleep"}],
    },
    "Fussy": {
        "intro": "This sounds like a fussy, mild-protest cry. Check comfort basics, then soothe.",
        "steps": [
            {"title": "Run the comfort checklist", "detail": "Wet or dirty diaper, clothing that is too tight/itchy, labels, and whether baby feels too hot or too cold (check the chest/back of the neck, not hands)."},
            {"title": "Hold baby close", "detail": "Skin-to-skin or a snug upright hold often settles fussiness and can be the only thing needed."},
            {"title": "Change the scene", "detail": "Move to another room or go outside for a few minutes; new sights often reset a fussy mood."},
            {"title": "Sing a lullaby or shush softly", "detail": "A gentle 'shhh' or a repeated tune while swaying slowly."},
            {"title": "Try a gentle hand and foot massage", "detail": "See the massage guide below; light touch can calm a baby who wants attention or comfort."},
        ],
        "massage": {"name": "Gentle hand massage", "body_part": "Hands (then feet)",
                    "how_to": ["Hold baby's hand in yours with baby comfortable and awake.", "With your thumbs, stroke the palm from the heel of the hand toward the fingers.", "Gently roll each finger between your thumb and forefinger from base to tip.", "Make tiny circles on the back of the hand, then repeat on the other hand (1-2 minutes each).", "Finish with the same slow strokes on the soles of the feet."],
                    "caution": "Use light pressure. Stop if baby cries harder, stiffens or turns away."},
        "lullaby": {"style": "Gentle, repetitive lullaby", "tempo": "slow, about 70-80 beats per minute", "tips": ["Sway side to side in time with the song.", "If baby is very upset, start louder and softer gradually."]},
        "videos": [{"label": "Soothing lullaby for a fussy baby", "query": "soothing lullaby for fussy baby", "lullaby": True}, {"label": "Baby hand massage", "query": "baby hand massage tutorial"}, {"label": "The 5 S's to soothe a baby", "query": "5 S's soothe crying baby Harvey Karp"}],
    },
    "Burp": {
        "intro": "This sounds like trapped-air discomfort. Burp baby, then try gentle tummy massage.",
        "steps": [
            {"title": "Hold baby upright and burp", "detail": "Over your shoulder with head supported, or sitting on your lap supporting the chin and chest. Pat or rub the back gently for 1-2 minutes."},
            {"title": "Try another position", "detail": "Lay baby face-down across your lap with the head higher than the chest (only while awake and supervised) and rub the back."},
            {"title": "Massage the tummy clockwise", "detail": "After 30 minutes or more since a feed, make gentle clockwise circles around the belly button (see the guide below)."},
            {"title": "Bicycle the legs", "detail": "Lay baby on their back and slowly pedal the legs, then hold the knees toward the tummy for about 10 seconds."},
            {"title": "Keep baby upright", "detail": "Stay upright for 10-15 minutes after feeds, and burp midway through the next feed."},
        ],
        "massage": {"name": "Clockwise tummy massage for gas and burps", "body_part": "Tummy",
                    "how_to": ["Wait until at least 30 minutes after a feed, with baby lying on their back and warm hands.", "Using two or three fingertips, make slow, gentle circles clockwise around the belly button (as you look down at the tummy).", "Or use the 'I-L-U' stroke: down the baby's left side (I), across the top then down (L), then up the right side, across and down the left (U).", "Do this for 3-5 minutes, then bicycle the legs.", "Avoid the belly button area until the cord stump has healed."],
                    "caution": "Very light pressure only. Stop if baby cries harder, spits up, or the belly feels hard or swollen."},
        "lullaby": {"style": "Soft humming while you hold baby upright", "tempo": "slow, about 60-80 beats per minute", "tips": ["Hum while walking slowly; the vibration and rhythm can help baby relax and burp."]},
        "videos": [{"label": "How to burp a baby (3 positions)", "query": "how to burp a baby 3 positions"}, {"label": "Tummy massage for gas", "query": "baby tummy massage for gas and burping I love you"}, {"label": "Bicycle legs for gas", "query": "baby gas relief bicycle legs"}],
    },
    "Distress": {
        "intro": "This sounds like a pain or strong-discomfort cry. Check for causes first and stay close.",
        "steps": [
            {"title": "Check for simple physical causes", "detail": "Take off clothing to look for a hair or thread wrapped round a finger or toe (hair tourniquet), diaper rash, tight clothing, or an insect bite."},
            {"title": "Check temperature", "detail": "Take baby's temperature. Under 3 months: 38.0 C / 100.4 F or higher needs urgent medical care."},
            {"title": "Feed and burp if it's been a while", "detail": "Hunger and trapped air can both cause loud, urgent crying."},
            {"title": "Try the colic hold or a gentle tummy massage", "detail": "Hold baby face-down along your forearm with the head supported in the crook of your elbow (awake, supervised), or use the clockwise tummy massage below."},
            {"title": "Soothe with calm, steady input", "detail": "Skin-to-skin, slow swaying, shushing or a low lullaby. Stay calm; babies pick up on tension."},
            {"title": "Know when to call for help", "detail": "If crying doesn't ease, or any red-flag sign below appears, call your paediatrician or emergency services."},
        ],
        "massage": {"name": "Clockwise tummy massage (colic / gas)", "body_part": "Tummy and legs",
                    "how_to": ["Baby on their back, at least 30 minutes after a feed, with warm hands.", "Slow, gentle clockwise circles around the belly button with 2-3 fingertips for 3-5 minutes.", "Follow with bicycle legs, then hold the knees to the tummy for about 10 seconds.", "Finish with slow long strokes down the legs."],
                    "caution": "Very light pressure. Do NOT massage if the tummy is hard/swollen, baby is vomiting, has fever or blood in the stool: seek medical care instead."},
        "lullaby": {"style": "Low, slow, steady lullaby or shushing", "tempo": "slow, about 60 beats per minute", "tips": ["Match the rhythm to your sway.", "Keep the volume low; loud sound can escalate a distressed baby."]},
        "videos": [{"label": "Colic hold and soothing", "query": "colic hold baby football hold soothe"}, {"label": "Tummy massage for colic", "query": "baby colic tummy massage I love you technique"}, {"label": "Calming lullaby", "query": "calming lullaby for crying baby", "lullaby": True}],
    },
    "Uncertain": {
        "intro": "The cry pattern isn't clear enough to name one cause. Work through this checklist in order.",
        "steps": [
            {"title": "Feed?", "detail": "Offer a feed if it has been 2-3 hours or baby shows hunger cues."},
            {"title": "Burp?", "detail": "Hold baby upright and pat or rub the back gently."},
            {"title": "Diaper and comfort?", "detail": "Check the diaper, clothing, and whether baby is too hot or cold."},
            {"title": "Tired?", "detail": "Dim the lights, reduce noise, rock and sing softly."},
            {"title": "Cuddle and soothe", "detail": "Skin-to-skin, slow swaying, shushing or a lullaby."},
        ],
        "massage": {"name": "Gentle hand massage", "body_part": "Hands",
                    "how_to": ["Stroke the palm from heel to fingers with your thumbs.", "Roll each finger gently, then make tiny circles on the back of the hand.", "Repeat on the other hand (1-2 minutes each)."],
                    "caution": "Light pressure. Stop if baby dislikes it."},
        "lullaby": {"style": "Soft lullaby", "tempo": "slow, about 60-80 beats per minute", "tips": ["Repeat one simple tune."]},
        "videos": [{"label": "Lullaby to soothe baby", "query": "soothing lullaby for babies", "lullaby": True}, {"label": "The 5 S's to soothe a baby", "query": "5 S's soothe crying baby Harvey Karp"}],
    },
}


# --- added for the 9-class CSV (hu, dk, ti, bp, sc, dc, ch, bu, lo) --------------------------------
KB["Scared"] = {
    "intro": "This sounds like a startled or frightened cry. Comfort first, then lower the stimulation.",
    "steps": [
        {"title": "Pick baby up and hold close", "detail": "Skin-to-skin or a snug chest-to-chest hold. Your heartbeat and warmth are the fastest calmers."},
        {"title": "Speak softly and stay calm", "detail": "A slow, low voice. Babies read your tension, so breathe slowly while you hold them."},
        {"title": "Remove the trigger", "detail": "Switch off loud TV or music, dim bright lights, or move to a quieter room."},
        {"title": "Use gentle rhythm", "detail": "Slow swaying or patting on the back at about one pat per second, with soft shushing."},
        {"title": "Check the basics afterwards", "detail": "Once calm, check the diaper, temperature and whether a feed is due."},
    ],
    "massage": {"name": "Calming back strokes", "body_part": "Back",
                "how_to": ["Hold baby against your chest with one hand supporting the head.", "With the other palm, make slow downward strokes along the back, about 10 times.", "Keep pressure very light and stop when baby settles."],
                "caution": "Stop if baby cries harder or turns away."},
    "lullaby": {"style": "Soft, slow humming", "tempo": "slow, about 60 beats per minute", "tips": ["Hum close to baby's ear at low volume.", "Repeat one simple tune."]},
    "videos": [{"label": "Calming a startled baby", "query": "how to calm a startled newborn baby"}, {"label": "Soft lullaby", "query": "soothing lullaby for scared crying baby", "lullaby": True}],
}
KB["Cold / Hot"] = {
    "intro": "This sounds like a temperature-discomfort cry. Check whether baby is too hot or too cold.",
    "steps": [
        {"title": "Feel the chest or back of the neck", "detail": "Hands and feet are often cool in healthy babies. The chest and neck tell you more: sweaty or hot means too warm, cool means too cold."},
        {"title": "Adjust one layer at a time", "detail": "Remove or add a single thin layer, then wait a few minutes. Dress baby in about one more layer than you are wearing."},
        {"title": "Check the room", "detail": "A comfortable room is usually about 18-22 C (64-72 F). Avoid direct heat or draughts."},
        {"title": "Check for fever", "detail": "Take baby's temperature. Under 3 months: 38.0 C / 100.4 F or higher needs urgent medical care."},
        {"title": "Keep sleep safe", "detail": "No hats, heavy blankets or extra bedding in the cot. Baby on their back."},
    ],
    "massage": None,
    "lullaby": None,
    "videos": [{"label": "Dressing baby for the room temperature", "query": "how to dress baby for sleep room temperature safe"}],
}
KB["Lonely"] = {
    "intro": "This sounds like a 'pick me up' cry: baby may want closeness and company.",
    "steps": [
        {"title": "Pick baby up and make eye contact", "detail": "Hold baby 20-30 cm from your face and smile or talk softly."},
        {"title": "Offer skin-to-skin or a snug hold", "detail": "Closeness regulates breathing, heart rate and mood."},
        {"title": "Talk, sing or hum", "detail": "Name what you are doing in a calm voice. Babies settle to familiar voices."},
        {"title": "Change the scene together", "detail": "Walk to a window or another room; a new view often helps."},
        {"title": "Check the basics", "detail": "If still fussing, check feed, burp, diaper and tiredness."},
    ],
    "massage": {"name": "Gentle hand massage", "body_part": "Hands (then feet)",
                "how_to": ["Hold baby's hand and stroke the palm from heel to fingers with your thumbs.", "Roll each finger gently from base to tip.", "Repeat on the other hand and the soles of the feet."],
                "caution": "Light pressure only. Stop if baby cries harder or stiffens."},
    "lullaby": {"style": "Gentle, repetitive lullaby", "tempo": "slow, about 70 beats per minute", "tips": ["Sway side to side in time with the song."]},
    "videos": [{"label": "Soothing a baby who wants to be held", "query": "soothe baby who wants to be held tips"}, {"label": "Gentle lullaby", "query": "gentle lullaby for babies", "lullaby": True}],
}
LULLABY_WHEN.update({"Scared", "Lonely"})


# ----------------------------------------------------------------------------
# Gemini (optional)
# ----------------------------------------------------------------------------
def _call_llm(prompt: str):
    """Return parsed JSON from Gemini, or None. Swap this function to use another API."""
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return None
    models = [os.getenv("GEMINI_MODEL", "gemini-3.5-flash"), os.getenv("GEMINI_FALLBACK_MODEL", "gemini-flash-latest")]
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json"}}
    for model in dict.fromkeys(m for m in models if m):
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": key, "Content-Type": "application/json"}, json=body, timeout=25)
            r.raise_for_status()
            parts = r.json()["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts).strip()
            text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
            return json.loads(text)
        except Exception:
            continue
    return None


def _build_prompt(cry_type, confidence, evidence, base):
    return (
        "You are helping a parent soothe a baby. A classifier labelled the baby's cry as "
        f"'{cry_type}' (confidence {confidence * 100:.0f}%).\n"
        "Measured evidence from the recording (use ONLY this, never invent measurements):\n- "
        + "\n- ".join(evidence or ["none available"]) + "\n\n"
        "Baseline safe guidance to refine (keep it consistent with this):\n"
        + json.dumps({"steps": base["steps"], "massage": base["massage"]}) + "\n\n"
        "Rules: no diagnoses; no medicines, herbs, gripe water or honey; safe sleep only "
        "(baby on back, empty cot); gentle pressure for massage; never shake a baby; "
        "keep each detail under 30 words; use plain, kind language.\n"
        "Return ONLY JSON with this shape:\n"
        '{"intro": str, "steps": [{"title": str, "detail": str}] (4-6 items, most useful first), '
        '"massage": {"name": str, "body_part": str, "how_to": [str], "caution": str} or null, '
        '"lullaby": {"style": str, "tempo": str, "tips": [str]}}'
    )


def _valid(g):
    try:
        ok = isinstance(g["intro"], str) and 3 <= len(g["steps"]) <= 8
        ok = ok and all(isinstance(s["title"], str) and isinstance(s["detail"], str) for s in g["steps"])
        m = g.get("massage")
        if m is not None:
            ok = ok and isinstance(m["how_to"], list) and all(isinstance(x, str) for x in m["how_to"])
            ok = ok and all(isinstance(m[k], str) for k in ("name", "body_part", "caution"))
        lu = g.get("lullaby")
        if lu is not None:
            ok = ok and all(isinstance(lu[k], str) for k in ("style", "tempo")) and isinstance(lu["tips"], list)
        return bool(ok)
    except Exception:
        return False


# ----------------------------------------------------------------------------
# Videos
# ----------------------------------------------------------------------------
_cache = {}


def _search_link(query):
    return f"https://www.youtube.com/results?search_query={quote_plus(query)}"


def _youtube_api(query, n=1):
    key = os.getenv("YOUTUBE_API_KEY")
    if not key:
        return []
    hit = _cache.get(query)
    if hit and time.time() - hit[0] < 6 * 3600:
        return hit[1]
    try:
        r = requests.get("https://www.googleapis.com/youtube/v3/search", timeout=10, params={
            "part": "snippet", "type": "video", "q": query, "maxResults": n, "videoEmbeddable": "true",
            "safeSearch": "strict", "key": key})
        r.raise_for_status()
        vids = [{"title": it["snippet"]["title"], "url": f"https://www.youtube.com/watch?v={it['id']['videoId']}"}
                for it in r.json().get("items", [])]
    except Exception:
        vids = []
    _cache[query] = (time.time(), vids)
    return vids


def _curated(cry_type):
    try:
        data = json.loads((HERE / "curated_videos.json").read_text(encoding="utf-8"))
        return [v for v in data.get(cry_type, []) if v.get("url")]
    except Exception:
        return []


def find_videos(cry_type, video_specs):
    out = [{"kind": "video", "label": v.get("title", "Recommended video"), "title": v.get("title", ""), "url": v["url"]}
           for v in _curated(cry_type)]
    for spec in video_specs:
        q = spec["query"] + (f" {LULLABY_LANG}" if LULLABY_LANG and spec.get("lullaby") else "")
        found = _youtube_api(q)
        if found:
            out.append({"kind": "video", "label": spec["label"], "title": found[0]["title"], "url": found[0]["url"]})
        out.append({"kind": "search", "label": f"Search YouTube: {spec['label']}", "title": "", "url": _search_link(q)})
    return out


# ----------------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------------
def get_advice(cry_type, confidence, evidence_lines, uncertain=False):
    key = "Uncertain" if uncertain or cry_type not in KB else cry_type
    base = KB[key]
    advice = {"intro": base["intro"], "steps": base["steps"], "massage": base["massage"],
              "lullaby": base["lullaby"], "source": "builtin"}

    g = _call_llm(_build_prompt(key, confidence, evidence_lines, base))
    if g and _valid(g):
        advice.update(intro=g["intro"], steps=g["steps"], source="gemini")
        if g.get("massage") is not None or base["massage"] is None:
            advice["massage"] = g.get("massage")
        if g.get("lullaby"):
            advice["lullaby"] = g["lullaby"]

    # Lullaby is only useful for calming cries (sleepy / fussy / unclear). For hunger, burping or
    # pain the first job is a feed, a burp or a check-up, so the lullaby card and lullaby videos are hidden.
    advice["show_lullaby"] = key in LULLABY_WHEN
    specs = base["videos"] if advice["show_lullaby"] else [v for v in base["videos"] if not v.get("lullaby")]
    if not advice["show_lullaby"]:
        advice["lullaby"] = None
    advice["videos"] = find_videos(key, specs)
    advice["red_flags"] = GENERAL_RED_FLAGS                     # always from the KB, never the LLM
    advice["disclaimer"] = ("This tool is an aid, not a medical device. It cannot diagnose. "
                            "If you are worried about your baby, contact a doctor.")
    return advice
