import redis.asyncio as aioredis
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie

from app.config import settings
from app.models.mongo_models import Quest, EventLog  # Sẽ import models thực tế khi khởi tạo xong

# Async Engine cho PostgreSQL
postgres_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=True,
    future=True
)

# Sessionmaker cho PostgreSQL
async_session_maker = sessionmaker(
    postgres_engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Clients cho MongoDB và Redis
mongo_client: AsyncIOMotorClient = None
redis_client: aioredis.Redis = None

async def init_databases():
    global mongo_client, redis_client
    
    # 1. Khởi tạo MongoDB (Beanie ODM)
    mongo_client = AsyncIOMotorClient(settings.MONGO_URI)
    await init_beanie(
        database=mongo_client[settings.MONGO_DB],
        document_models=[Quest, EventLog]
    )
    
    # 2. Khởi tạo Redis Cache client
    redis_client = aioredis.from_url(
        f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}",
        encoding="utf-8",
        decode_responses=True
    )

async def close_databases():
    global mongo_client, redis_client
    if mongo_client:
        mongo_client.close()
    if redis_client:
        await redis_client.close()

# Dependency inject Postgres session
async def get_db_session() -> AsyncSession:
    async with async_session_maker() as session:
        yield session

# Dependency inject Redis client
async def get_redis_client() -> aioredis.Redis:
    yield redis_client

# --- JWT Authentication & Dependency Injection ---
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy import select
from app.models.sql_models import User
from app.utils.security import ALGORITHM

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")

async def get_current_user(
    db: AsyncSession = Depends(get_db_session),
    token: str = Depends(oauth2_scheme)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    statement = select(User).where(User.email == email)
    result = await db.execute(statement)
    user = result.scalar_one_or_none()
    
    if user is None:
        raise credentials_exception
    return user

class RoleChecker:
    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have enough permissions to access this resource"
            )
        return current_user

