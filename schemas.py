"""
MindFlow Database Schemas

Each Pydantic model maps to a MongoDB collection (lowercased class name).
Use these schemas for validating input/output in API routes.
"""
from __future__ import annotations
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, Literal
from datetime import datetime

# -----------------
# Core User Profile
# -----------------
class Profile(BaseModel):
    email: EmailStr
    name: str = Field(..., min_length=1, max_length=120)
    gender: Literal["female", "male"]
    age: int = Field(..., ge=0, le=120)
    language: str = Field("en", description="IETF language tag, default en")
    period_tracking_enabled: bool = Field(False)
    plan: Literal["free", "pro", "premium"] = Field("free")
    referrals: int = Field(0, ge=0)

# -------------
# Mood Tracking
# -------------
class MoodEntry(BaseModel):
    user_id: str
    mood: Literal["great", "good", "ok", "low", "bad"]
    note: Optional[str] = None
    created_at: Optional[datetime] = None

# --------------
# Habit Tracking
# --------------
class Habit(BaseModel):
    user_id: str
    title: str = Field(..., min_length=1, max_length=160)
    frequency: Literal["daily", "weekly", "custom"] = "daily"
    active: bool = True
    streak: int = 0
    last_completed_at: Optional[datetime] = None

# --------------
# Smart Reminders
# --------------
class Reminder(BaseModel):
    user_id: str
    title: str
    remind_at_iso: str = Field(..., description="ISO datetime string in user's locale/timezone")
    enabled: bool = True

# ------------------
# Menstrual Tracking
# ------------------
class CycleEntry(BaseModel):
    user_id: str
    date_iso: str = Field(..., description="ISO date string YYYY-MM-DD")
    entry_type: Literal["period_start", "symptom"] = "period_start"
    cycle_length_days: Optional[int] = Field(None, ge=20, le=60)

# -------------
# Subscriptions
# -------------
class SubscriptionEvent(BaseModel):
    user_id: str
    plan: Literal["free", "pro", "premium"]
    period: Literal["monthly", "annual"] = "monthly"
    started_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
