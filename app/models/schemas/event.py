# -*- coding: utf-8 -*-
# @Time   : 2025/8/12 13:57
# @Author : Galleons
# @File   : event.py

"""
timescaledb schema
"""

from datetime import datetime
from typing import List, Optional

# from pydantic import BaseModel, Field
from sqlmodel import SQLModel, Field
from timescaledb import TimescaleModel

# page visits at any given time


class EventModel(TimescaleModel, table=True):
    page: str = Field(index=True)  # /about, /contact, # pricing
    user_agent: Optional[str] = Field(default="", index=True)  # browser
    ip_address: Optional[str] = Field(default="", index=True)
    referrer: Optional[str] = Field(default="", index=True)
    session_id: Optional[str] = Field(index=True)
    duration: Optional[int] = Field(default=0)

    __chunk_time_interval__ = "INTERVAL 1 day"
    __drop_after__ = "INTERVAL 3 months"


class EventCreateSchema(SQLModel):
    page: str
    user_agent: Optional[str] = Field(default="", index=True)  # browser
    ip_address: Optional[str] = Field(default="", index=True)
    referrer: Optional[str] = Field(default="", index=True)
    session_id: Optional[str] = Field(index=True)
    duration: Optional[int] = Field(default=0)


# class EventUpdateSchema(SQLModel):
#     description: str


# {"id": 12}


class EventListSchema(SQLModel):
    results: List[EventModel]
    count: int


class EventBucketSchema(SQLModel):
    bucket: datetime
    page: str
    ua: Optional[str] = ""
    operating_system: Optional[str] = ""
    avg_duration: Optional[float] = 0.0
    count: int
