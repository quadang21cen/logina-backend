from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel.ext.asyncio.session import AsyncSession
from pydantic import BaseModel, EmailStr

from app.api.deps import get_db_session, get_current_user
from app.models.sql_models import User
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])

class Token(BaseModel):
    access_token: str
    token_type: str
    role: str

class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    role: str
    is_active: bool

@router.post("/login", response_model=Token)
async def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db_session)
):
    """Đăng nhập bằng Email và Password, trả về JWT Token và cấu hình HTTP-Only cookie."""
    user = await AuthService.authenticate_user(
        session=db, 
        email=form_data.username, 
        password=form_data.password
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect email or password"
        )
    
    access_token = AuthService.generate_token(user)
    
    # Thiết lập cookie HTTP-Only cho môi trường production/web client bảo mật hơn
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=3600,
        samesite="lax",
        secure=False  # Chuyển sang True trong production (với https)
    )
    
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "role": user.role
    }

@router.post("/logout")
async def logout(response: Response):
    """Đăng xuất, xóa HTTP-Only cookie."""
    response.delete_cookie(key="access_token")
    return {"message": "Successfully logged out"}

@router.get("/me", response_model=UserOut)
async def read_users_me(current_user: User = Depends(get_current_user)):
    """Lấy profile và Role của user hiện tại đang đăng nhập."""
    return current_user
