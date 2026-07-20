"""Pydantic request models (Pydantic v2)."""
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class RegisterIn(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=6)
    full_name: Optional[str] = None


class LoginIn(BaseModel):
    email: str
    password: str


class ClassIn(BaseModel):
    name: str = Field(min_length=1)
    description: Optional[str] = None


class StudentIn(BaseModel):
    full_name: str = Field(min_length=1)
    gender: Optional[str] = None
    birth_date: Optional[str] = None
    note: Optional[str] = None


class SurveyIn(BaseModel):
    title: str = Field(min_length=1)
    conducted_on: Optional[str] = None
    questions: Optional[List[dict]] = None


class SurveyPatch(BaseModel):
    title: Optional[str] = None
    conducted_on: Optional[str] = None
    is_open: Optional[bool] = None
    questions: Optional[List[dict]] = None


class NoteIn(BaseModel):
    body: str = Field(min_length=1)


class MeetingIn(BaseModel):
    met_on: Optional[str] = None
    summary: Optional[str] = None


class InterventionIn(BaseModel):
    title: str = Field(min_length=1)
    description: Optional[str] = None
    started_on: Optional[str] = None
    ended_on: Optional[str] = None
    effectiveness: Optional[int] = None
    outcome: Optional[str] = None


class SurveyStartIn(BaseModel):
    code: str = Field(min_length=1)


class SurveySubmitIn(BaseModel):
    code: str = Field(min_length=1)
    # { "cinema": [id, ...], "project": [...], "alone": [...] }
    answers: Dict[str, List[int]]
