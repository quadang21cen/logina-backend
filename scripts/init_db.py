import sys
import os
import asyncio
import argparse
from sqlmodel import SQLModel
from passlib.context import CryptContext
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime

# Đưa thư mục src vào path của Python để chạy độc lập
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from app.config import settings
from app.api.deps import postgres_engine, async_session_maker
from app.models.sql_models import User, UserRole, Class, ClassStudentLink, QuestRun

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

async def init_postgres():
    print("\n--- INITIALIZING POSTGRESQL (Neon.tech) ---")
    print(f"Connecting to: {settings.POSTGRES_HOST} / Database: {settings.POSTGRES_DB}")
    async with postgres_engine.begin() as conn:
        # Trong quá trình dev local, có thể reset nếu muốn
        # await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    print("PostgreSQL tables created successfully!")

    print("Seeding initial users and classes into PostgreSQL...")
    async with async_session_maker() as session:
        from sqlalchemy import select
        result = await session.execute(select(User).where(User.email == "teacher@logina.edu.vn"))
        existing_teacher = result.scalar_one_or_none()
        
        if not existing_teacher:
            # 1. Seed Teacher Account
            teacher = User(
                email="teacher@logina.edu.vn",
                full_name="Nguyễn Văn Giáo Viên",
                role=UserRole.TEACHER,
                hashed_password=get_password_hash("teacher123"),
                is_active=True
            )
            session.add(teacher)
            
            # 2. Seed Student Account
            student = User(
                email="student@logina.edu.vn",
                full_name="Trần Văn Học Sinh",
                role=UserRole.STUDENT,
                hashed_password=get_password_hash("student123"),
                is_active=True
            )
            session.add(student)
            await session.commit()
            await session.refresh(teacher)
            await session.refresh(student)

            # 3. Seed Class
            new_class = Class(
                name="Lớp Địa Lý 11A1",
                description="Lớp học nâng cao về địa lý tự nhiên Đồng bằng sông Cửu Long",
                teacher_id=teacher.id
            )
            session.add(new_class)
            await session.commit()
            await session.refresh(new_class)

            # 4. Enroll Student to Class
            link = ClassStudentLink(
                class_id=new_class.id,
                student_id=student.id
            )
            session.add(link)
            await session.commit()
            
            print("Successfully seeded initial accounts:")
            print("  - Teacher: teacher@logina.edu.vn / teacher123")
            print("  - Student: student@logina.edu.vn / student123")
            print(f"  - Class: {new_class.name} (Teacher ID: {teacher.id})")
        else:
            print("Database already has seed data. Skipping seed step.")


async def init_mongodb():
    print("\n--- INITIALIZING MONGODB (MongoDB Atlas) ---")
    print(f"Connecting to URI: {settings.MONGO_URI.split('@')[-1]} (Credentials hidden)")
    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.MONGO_DB]
    
    # Tạo các collection và index mẫu
    print("Creating collections and indexes in MongoDB...")
    # MongoDB tự động tạo collection khi ghi document, tuy nhiên ta có thể tạo index trước
    quests_collection = db["quests"]
    await quests_collection.create_index("creator_id")
    await quests_collection.create_index("is_published")
    
    event_logs_collection = db["event_logs"]
    await event_logs_collection.create_index([("run_id", 1), ("timestamp", -1)])
    await event_logs_collection.create_index("student_id")
    
    # Tạo Quest mẫu đầu tiên nếu chưa có
    existing_quest = await quests_collection.find_one({"title": "Quest Khởi Đầu"})
    if not existing_quest:
        quest_sample = {
            "title": "Quest Khởi Đầu",
            "description": "Quest mẫu hướng dẫn làm quen với hệ thống Logina",
            "creator_id": 1,  # Tương ứng với ID của Teacher sau khi seed
            "is_published": True,
            "knowledge_pack": {
                "title": "Giới thiệu Logina",
                "content": "Nội dung học tập mẫu về việc đưa ra quyết định dựa trên bằng chứng.",
                "resources": []
            },
            "role_card": {
                "role_name": "Nhà Phân Tích Trẻ",
                "description": "Vai trò phân tích dữ liệu và tìm kiếm bằng chứng.",
                "objectives": ["Tìm bằng chứng phù hợp", "Đưa ra quyết định tối ưu"]
            },
            "scenario_nodes": [
                {
                    "node_id": "node_1",
                    "title": "Tình huống số 1",
                    "description": "Bạn cần chọn một nguồn năng lượng cho khu phố xanh.",
                    "decisions": [
                        {"id": "solar", "text": "Lắp đặt Pin năng lượng mặt trời"},
                        {"id": "coal", "text": "Sử dụng nhiệt điện than"}
                    ],
                    "evidence_options": [
                        {"id": "ev_solar_clean", "text": "Pin mặt trời giảm 90% lượng khí thải carbon"},
                        {"id": "ev_coal_cheap", "text": "Nhiệt điện than có chi phí đầu tư ban đầu thấp"}
                    ]
                }
            ],
            "rules": [
                {
                    "rule_id": "rule_1",
                    "decision_id": "solar",
                    "required_evidence_ids": ["ev_solar_clean"],
                    "severity": "INFO",
                    "message": "Lựa chọn chính xác, bằng chứng nhất quán!"
                }
            ],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        await quests_collection.insert_one(quest_sample)
        print("Successfully seeded a sample Quest into MongoDB!")
    else:
        print("Quest collections already initialized.")
    
    client.close()

async def clean_postgres():
    print("\n--- CLEANING POSTGRESQL (Neon.tech) ---")
    async with postgres_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    print("PostgreSQL tables dropped successfully!")

async def clean_mongodb():
    print("\n--- CLEANING MONGODB (MongoDB Atlas) ---")
    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.MONGO_DB]
    collections = await db.list_collection_names()
    for col in collections:
        await db[col].drop()
        print(f"Dropped MongoDB collection: {col}")
    client.close()
    print("MongoDB databases cleared successfully!")

async def main():
    parser = argparse.ArgumentParser(description="Logina Database Management Script")
    parser.add_argument("--postgres", action="store_true", help="Initialize PostgreSQL schemas and seed data only")
    parser.add_argument("--mongodb", action="store_true", help="Initialize MongoDB indexes and seed data only")
    parser.add_argument("--all", action="store_true", help="Initialize both PostgreSQL and MongoDB databases")
    parser.add_argument("--clean", action="store_true", help="Drop/Clear all PostgreSQL tables and MongoDB collections")
    
    args = parser.parse_args()
    
    if args.clean:
        await clean_postgres()
        await clean_mongodb()
        print("\nAll database tables and collections have been successfully cleared!")
        return

    # Nếu không truyền tham số nào, in ra hướng dẫn
    if not (args.postgres or args.mongodb or args.all):
        parser.print_help()
        sys.exit(1)
        
    if args.all or args.postgres:
        await init_postgres()
        
    if args.all or args.mongodb:
        await init_mongodb()

if __name__ == "__main__":
    asyncio.run(main())
