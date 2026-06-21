from typing import Optional
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.sql_models import User
from app.utils.security import verify_password, create_access_token

class AuthService:
    @staticmethod
    async def authenticate_user(
        session: AsyncSession, 
        email: str, 
        password: str
    ) -> Optional[User]:
        """Xác thực thông tin đăng nhập của user."""
        statement = select(User).where(User.email == email)
        result = await session.execute(statement)
        user = result.scalar_one_or_none()
        
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    @staticmethod
    def generate_token(user: User) -> str:
        """Sinh JWT Token từ user profile."""
        return create_access_token(subject=user.email)
