from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.sql import text

from .base import Base


class ContactInquiry(Base):
    __tablename__ = "contact_inquiry"

    ci_id = Column(Integer, primary_key=True, autoincrement=True)
    ci_name = Column(String(100), nullable=False)
    ci_email = Column(String(255), nullable=False)
    ci_category = Column(String(50), nullable=False, server_default=text("'GENERAL'"))
    ci_message = Column(Text, nullable=False)
    ci_status = Column(String(20), nullable=False, server_default=text("'RECEIVED'"))
    ci_created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
