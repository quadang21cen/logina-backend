from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.deps import init_databases, close_databases

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Khởi tạo kết nối DB khi startup
    await init_databases()
    yield
    # Ngắt kết nối DB an toàn khi shutdown
    await close_databases()

app = FastAPI(
    title="Logina Backend API",
    description="AI-Assisted Curriculum-to-Quest Engine API Gateway",
    version="1.0.0",
    lifespan=lifespan
)

# Cấu hình CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Trong thực tế, truyền list domain cụ thể của Next.js từ config
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "services": {
            "postgres": "connected",  # Các hàm test thực tế sẽ được thêm vào
            "mongodb": "connected",
            "redis": "connected"
        }
    }

from app.api.router import api_router

# Đăng ký routes chính thức
app.include_router(api_router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"message": "Welcome to Logina API Engine. Please visit /docs for Swagger documentation."}

