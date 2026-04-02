"""
Run: python -m app.seed
Seeds the database with sample users, tokens, and crowd counts.
"""
import random
from datetime import datetime, timedelta

from app.database import SessionLocal, engine, Base
from app.models import User, Token, TokenStatus, IssueCategory, CrowdCount, UserRole
from app.auth import hash_password

Base.metadata.create_all(bind=engine)


def seed():
    db = SessionLocal()

    # ── Users ─────────────────────────────────────────
    if not db.query(User).first():
        users = [
            User(email="admin@queue.ai", full_name="Admin User", hashed_password=hash_password("admin123"), role=UserRole.admin),
            User(email="staff@queue.ai", full_name="Staff Member", hashed_password=hash_password("staff123"), role=UserRole.staff),
            User(email="customer@queue.ai", full_name="John Customer", hashed_password=hash_password("customer123"), role=UserRole.customer),
        ]
        db.add_all(users)
        db.commit()
        print(f"✅ Seeded {len(users)} users")

    # ── Tokens ────────────────────────────────────────
    if not db.query(Token).first():
        categories = [IssueCategory.quick, IssueCategory.standard, IssueCategory.complex]
        est_map = {IssueCategory.quick: 5, IssueCategory.standard: 10, IssueCategory.complex: 15}
        now = datetime.utcnow().replace(hour=8, minute=0, second=0, microsecond=0)
        tokens = []

        for i in range(1, 26):
            issued = now + timedelta(minutes=i * 7)
            cat = random.choice(categories)

            if i <= 8:
                status = TokenStatus.completed
                served = issued + timedelta(minutes=random.randint(1, 3))
                completed = served + timedelta(minutes=random.randint(3, 15))
                svc_time = (completed - served).total_seconds() / 60.0
            elif i <= 10:
                status = TokenStatus.serving
                served = issued + timedelta(minutes=random.randint(1, 5))
                completed = None
                svc_time = None
            else:
                status = TokenStatus.waiting
                served = None
                completed = None
                svc_time = None

            tokens.append(Token(
                token_number=f"T-{i:03d}",
                customer_name=f"Customer {i}",
                status=status,
                category=cat,
                estimated_minutes=est_map[cat],
                counter=random.randint(1, 4) if status in (TokenStatus.serving, TokenStatus.completed) else None,
                service_time=round(svc_time, 1) if svc_time else None,
                issued_at=issued,
                served_at=served,
                completed_at=completed,
            ))

        db.add_all(tokens)
        db.commit()
        print(f"✅ Seeded {len(tokens)} tokens")

    # ── Crowd Counts ──────────────────────────────────
    if not db.query(CrowdCount).first():
        now = datetime.utcnow()
        counts = []
        for i in range(70):
            ts = now - timedelta(hours=i)
            counts.append(CrowdCount(count=random.randint(5, 40), timestamp=ts))
        db.add_all(counts)
        db.commit()
        print(f"✅ Seeded {len(counts)} crowd counts")

    db.close()
    print("🎉 Database seeding complete!")


if __name__ == "__main__":
    seed()
