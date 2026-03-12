from sqlalchemy import Column, String

from app.database import Base

class AdminState(Base):
    __tablename__ = "admin_state"

    key = Column(String, primary_key=True, index=True)
    value = Column(String, nullable=True)
