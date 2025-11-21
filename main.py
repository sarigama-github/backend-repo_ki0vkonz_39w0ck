import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr

from database import db, create_document, get_documents
from schemas import Profile, MoodEntry, Habit, Reminder, CycleEntry, SubscriptionEvent

app = FastAPI(title="MindFlow API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------
# Utility/helper methods
# ----------------------

def collection(name: str):
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    return db[name]


def now_utc():
    return datetime.now(timezone.utc)


# ----------------------
# Health + Root
# ----------------------
@app.get("/")
def read_root():
    return {"app": "MindFlow API", "status": "ok"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "❌ Not Set",
        "database_name": "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": [],
    }

    try:
        if db is not None:
            response["database"] = "✅ Connected & Working"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, "name") else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                response["collections"] = db.list_collection_names()[:10]
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:50]}"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    return response


# ----------------------
# Auth (email-only MVP)
# ----------------------
class EmailLoginRequest(BaseModel):
    email: EmailStr


class AuthResponse(BaseModel):
    user_id: str
    email: EmailStr
    period_tracking_enabled: bool
    language: str


@app.post("/api/auth/email-login", response_model=AuthResponse)
def email_login(payload: EmailLoginRequest):
    """MVP auth: create-or-return a user profile by email."""
    users = collection("profile")
    existing = users.find_one({"email": payload.email})
    if existing:
        return AuthResponse(
            user_id=str(existing.get("_id")),
            email=existing["email"],
            period_tracking_enabled=existing.get("period_tracking_enabled", False),
            language=existing.get("language", "en"),
        )

    default = Profile(
        email=payload.email,
        name=payload.email.split("@")[0],
        gender="male",
        age=18,
        language="en",
        period_tracking_enabled=False,
        plan="free",
        referrals=0,
    )
    users.insert_one({**default.model_dump(), "created_at": now_utc(), "updated_at": now_utc()})
    created = users.find_one({"email": payload.email})
    return AuthResponse(
        user_id=str(created.get("_id")),
        email=created["email"],
        period_tracking_enabled=created.get("period_tracking_enabled", False),
        language=created.get("language", "en"),
    )


# ----------------------
# Profile setup & update
# ----------------------
class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    gender: Optional[Literal["female", "male"]] = None
    age: Optional[int] = None
    language: Optional[str] = None


class ProfileResponse(BaseModel):
    email: EmailStr
    name: str
    gender: Literal["female", "male"]
    age: int
    language: str
    period_tracking_enabled: bool
    plan: Literal["free", "pro", "premium"]


@app.post("/api/profile/setup", response_model=ProfileResponse)
def profile_setup(email: EmailStr, body: ProfileUpdate):
    users = collection("profile")
    existing = users.find_one({"email": email})
    if not existing:
        raise HTTPException(404, "User not found")

    updates = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.gender is not None:
        updates["gender"] = body.gender
    if body.age is not None:
        updates["age"] = body.age
        # Enable period tracking if female and age >= 13
        if (body.gender or existing.get("gender")) == "female" and body.age >= 13:
            updates["period_tracking_enabled"] = True
        else:
            updates["period_tracking_enabled"] = False
    if body.language is not None:
        updates["language"] = body.language

    if updates:
        updates["updated_at"] = now_utc()
        users.update_one({"email": email}, {"$set": updates})

    updated = users.find_one({"email": email})
    return ProfileResponse(
        email=updated["email"],
        name=updated["name"],
        gender=updated["gender"],
        age=updated["age"],
        language=updated.get("language", "en"),
        period_tracking_enabled=updated.get("period_tracking_enabled", False),
        plan=updated.get("plan", "free"),
    )


# ----------------------
# Mood tracking
# ----------------------
class MoodCreate(BaseModel):
    email: EmailStr
    mood: Literal["great", "good", "ok", "low", "bad"]
    note: Optional[str] = None


@app.post("/api/mood/add")
def add_mood(entry: MoodCreate):
    users = collection("profile")
    u = users.find_one({"email": entry.email})
    if not u:
        raise HTTPException(404, "User not found")
    doc = MoodEntry(user_id=str(u["_id"]), mood=entry.mood, note=entry.note, created_at=now_utc())
    create_document("moodentry", doc)
    return {"ok": True}


@app.get("/api/mood/list")
def list_moods(email: EmailStr, limit: int = 30):
    users = collection("profile")
    u = users.find_one({"email": email})
    if not u:
        raise HTTPException(404, "User not found")
    items = get_documents("moodentry", {"user_id": str(u["_id"])}, limit=limit)
    for it in items:
        it["_id"] = str(it["_id"])  # make serializable
    return items


# ----------------------
# Habits (simple MVP)
# ----------------------
class HabitCreate(BaseModel):
    email: EmailStr
    title: str
    frequency: Literal["daily", "weekly", "custom"] = "daily"


@app.post("/api/habits/create")
def create_habit(payload: HabitCreate):
    users = collection("profile")
    u = users.find_one({"email": payload.email})
    if not u:
        raise HTTPException(404, "User not found")
    doc = Habit(user_id=str(u["_id"]), title=payload.title, frequency=payload.frequency)
    create_document("habit", doc)
    return {"ok": True}


@app.get("/api/habits/list")
def list_habits(email: EmailStr):
    users = collection("profile")
    u = users.find_one({"email": email})
    if not u:
        raise HTTPException(404, "User not found")
    items = get_documents("habit", {"user_id": str(u["_id"])})
    for it in items:
        it["_id"] = str(it["_id"])  # make serializable
    return items


# ----------------------
# Reminders (simple MVP)
# ----------------------
class ReminderCreate(BaseModel):
    email: EmailStr
    title: str
    remind_at_iso: str


@app.post("/api/reminders/create")
def create_reminder(payload: ReminderCreate):
    users = collection("profile")
    u = users.find_one({"email": payload.email})
    if not u:
        raise HTTPException(404, "User not found")
    doc = Reminder(user_id=str(u["_id"]), title=payload.title, remind_at_iso=payload.remind_at_iso)
    create_document("reminder", doc)
    return {"ok": True}


@app.get("/api/reminders/list")
def list_reminders(email: EmailStr):
    users = collection("profile")
    u = users.find_one({"email": email})
    if not u:
        raise HTTPException(404, "User not found")
    items = get_documents("reminder", {"user_id": str(u["_id"])})
    for it in items:
        it["_id"] = str(it["_id"])  # make serializable
    return items


# ----------------------
# Cycle tracking + recs
# ----------------------
class CycleCreate(BaseModel):
    email: EmailStr
    date_iso: str
    entry_type: Literal["period_start", "symptom"] = "period_start"
    cycle_length_days: Optional[int] = None


@app.post("/api/cycle/add")
def add_cycle(payload: CycleCreate):
    users = collection("profile")
    u = users.find_one({"email": payload.email})
    if not u:
        raise HTTPException(404, "User not found")
    if not u.get("period_tracking_enabled"):
        raise HTTPException(403, "Period tracking not enabled for this user")
    doc = CycleEntry(
        user_id=str(u["_id"]),
        date_iso=payload.date_iso,
        entry_type=payload.entry_type,
        cycle_length_days=payload.cycle_length_days,
    )
    create_document("cycleentry", doc)
    return {"ok": True}


@app.get("/api/cycle/recommendations")
def cycle_recs(email: EmailStr):
    """Simple phase-based recs using last period_start and cycle length."""
    users = collection("profile")
    u = users.find_one({"email": email})
    if not u:
        raise HTTPException(404, "User not found")
    if not u.get("period_tracking_enabled"):
        return {"enabled": False, "message": "Period tracking disabled"}

    entries = get_documents("cycleentry", {"user_id": str(u["_id"]), "entry_type": "period_start"})
    if not entries:
        return {"enabled": True, "phase": "unknown", "workout": "Light walks and stretching", "food": "Balanced meals, hydration"}

    # Use last entry
    last = sorted(entries, key=lambda e: e.get("created_at", now_utc()))[-1]
    start_date_str = last.get("date_iso")
    cycle_len = last.get("cycle_length_days") or 28
    try:
        start_date = datetime.fromisoformat(start_date_str)
    except Exception:
        # fallback: date only
        start_date = datetime.fromisoformat(start_date_str + "T00:00:00")

    days = (datetime.utcnow() - start_date).days % cycle_len

    if days <= 5:
        phase = "menstrual"
        workout = "Gentle yoga, restorative movement"
        food = "Iron-rich foods, warm soups, hydration"
    elif days <= 13:
        phase = "follicular"
        workout = "Build intensity: strength and cardio"
        food = "Lean protein, fresh veggies, complex carbs"
    elif days <= 16:
        phase = "ovulation"
        workout = "High-intensity or power sessions if comfortable"
        food = "Anti-inflammatory foods, hydration"
    else:
        phase = "luteal"
        workout = "Moderate intensity, prioritize recovery"
        food = "Magnesium-rich foods, balanced meals"

    return {"enabled": True, "phase": phase, "workout": workout, "food": food}


# ----------------------
# AI Wellness Assistant
# ----------------------
@app.get("/api/ai/daily-tip")
def daily_tip(email: EmailStr, language: str = "en"):
    """Rule-based MVP tips using latest mood and optional cycle phase."""
    users = collection("profile")
    u = users.find_one({"email": email})
    if not u:
        raise HTTPException(404, "User not found")

    moods = get_documents("moodentry", {"user_id": str(u["_id"])}, limit=1)
    latest_mood = moods[0]["mood"] if moods else "ok"

    tip_by_mood = {
        "great": "Leverage your momentum: schedule a deep-focus block and a short gratitude note.",
        "good": "Set one high-impact task and a 5-minute mindfulness break.",
        "ok": "Keep it simple: one task, one walk, and steady hydration.",
        "low": "Be kind to yourself: tiny steps count. Try 3 deep breaths and a 10-minute stroll.",
        "bad": "Prioritize rest and support. Reach out to a friend and schedule light tasks only.",
    }

    cycle_message = None
    if u.get("period_tracking_enabled"):
        recs = cycle_recs(email)
        if isinstance(recs, dict) and recs.get("enabled"):
            cycle_message = f"Cycle phase: {recs.get('phase')}. Workout: {recs.get('workout')}. Food: {recs.get('food')}."

    message = tip_by_mood.get(latest_mood, tip_by_mood["ok"])
    if cycle_message:
        message += " " + cycle_message

    return {"mood": latest_mood, "tip": message, "language": language}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
