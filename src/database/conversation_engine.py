from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from src.config.setting import settings


# Base class that all our table models will inherit from.
class Base(DeclarativeBase):
    pass


# The engine manages the actual connection(s) to the .db file.
# echo=False -> set to True temporarily if you want to see every SQL query in the terminal (debugging).
engine = create_async_engine(settings.CONVERSATION_DB_URL, echo=False)

# session_maker gives us a new "workspace" each time we talk to the database.
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def get_db_session():
    """
    FastAPI dependency: gives each request its own database session
    and makes sure it's closed properly afterwards.

    Usage in an endpoint:
        async def some_endpoint(session: AsyncSession = Depends(get_db_session)):
            ...
    """
    async with async_session_maker() as session:
        yield session


async def init_conversation_db():
    """
    Creates the tables in the .db file if they don't exist yet.
    Call this once when the app starts up (in chat.py or dependencies.py).
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)