from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Token, TokenStatus, IssueCategory
from app.schemas import TokenIssueRequest, ServeRequest, TokenOut, QueueStatusOut, UpdateTimeRequest

router = APIRouter(prefix="/tokens", tags=["Tokens"])


def _next_token_number(db: Session) -> str:
    """Generate daily token numbers (e.g., 0423-1, 0423-2 for April 23) to avoid unique constraint issues."""
    from sqlalchemy import func
    
    today = datetime.utcnow()
    date_prefix = today.strftime("%m%d")  # e.g., "0423" for April 23
    
    # Find the highest token number for today (format: MMDD-N)
    pattern = f"{date_prefix}-%"
    result = db.query(func.max(Token.token_number)).filter(
        Token.token_number.like(pattern)
    ).scalar()
    
    if not result:
        return f"{date_prefix}-1"
    
    try:
        # Extract the number after the dash
        current_num = int(result.split('-')[1])
        return f"{date_prefix}-{current_num + 1}"
    except (ValueError, TypeError, IndexError):
        return f"{date_prefix}-1"


@router.post("/", response_model=TokenOut)
def issue_token(body: TokenIssueRequest, db: Session = Depends(get_db)):
    """Customer scans QR → issues a new waiting token."""
    token = Token(
        token_number=_next_token_number(db),
        customer_name=body.customer_name,
        customer_phone=body.customer_phone,
        status=TokenStatus.waiting,
    )
    db.add(token)
    db.commit()
    db.refresh(token)
    return token


@router.get("/", response_model=list[TokenOut])
def get_all_tokens(db: Session = Depends(get_db)):
    # Exclude cancelled tokens from staff view
    return db.query(Token).filter(Token.status != TokenStatus.cancelled).order_by(Token.issued_at.desc()).all()


@router.get("/{token_id}", response_model=TokenOut)
def get_token(token_id: str, db: Session = Depends(get_db)):
    token = db.query(Token).filter((Token.id == token_id) | (Token.token_number == token_id)).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    return token


@router.patch("/{token_id}/serve", response_model=TokenOut)
def serve_token(token_id: str, body: ServeRequest, db: Session = Depends(get_db)):
    """Staff categorizes issue and starts serving."""
    token = db.query(Token).filter((Token.id == token_id) | (Token.token_number == token_id)).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")

    token.status = TokenStatus.serving
    token.category = IssueCategory(body.category)
    token.estimated_minutes = body.estimated_minutes
    token.issue_description = body.issue_description
    token.counter = body.counter
    token.served_at = datetime.utcnow()
    db.commit()
    db.refresh(token)
    return token


@router.patch("/{token_id}/complete", response_model=TokenOut)
def complete_token(token_id: str, db: Session = Depends(get_db)):
    """Mark current token complete and auto-call next waiting customer."""
    token = db.query(Token).filter((Token.id == token_id) | (Token.token_number == token_id)).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")

    # Mark current as complete
    token.status = TokenStatus.completed
    token.completed_at = datetime.utcnow()
    if token.served_at:
        token.service_time = (token.completed_at - token.served_at).total_seconds() / 60.0
    
    db.commit()
    db.refresh(token)
    
    # Note: Next customer will see "Your turn!" notification when they are first in line
    # Staff will then click "Serve" to start service and ask for time
    
    return token


@router.patch("/{token_id}/cancel", response_model=TokenOut)
def cancel_token(token_id: str, db: Session = Depends(get_db)):
    """Customer cancels their token (leaves queue)."""
    token = db.query(Token).filter((Token.id == token_id) | (Token.token_number == token_id)).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    
    if token.status not in [TokenStatus.waiting, TokenStatus.serving]:
        raise HTTPException(status_code=400, detail="Token cannot be cancelled")
    
    token.status = TokenStatus.cancelled
    token.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(token)
    return token


def _expire_old_tokens(db: Session):
    """Auto-cancel tokens waiting for more than 30 minutes."""
    cutoff = datetime.utcnow() - timedelta(minutes=30)
    old_tokens = db.query(Token).filter(
        Token.status == TokenStatus.waiting,
        Token.issued_at < cutoff,
    ).all()
    
    for token in old_tokens:
        token.status = TokenStatus.cancelled
        token.completed_at = datetime.utcnow()
    
    if old_tokens:
        db.commit()
    return len(old_tokens)


@router.get("/{token_id}/status", response_model=QueueStatusOut)
def get_queue_status(token_id: str, db: Session = Depends(get_db)):
    token = db.query(Token).filter((Token.id == token_id) | (Token.token_number == token_id)).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")

    # Auto-expire old waiting tokens
    _expire_old_tokens(db)

    # Count how many waiting tokens are ahead (excluding cancelled)
    ahead = db.query(Token).filter(
        Token.status == TokenStatus.waiting,
        Token.issued_at < token.issued_at,
    ).count()

    # Calculate estimated wait time for waiting customers
    estimated_wait = 0
    if token.status == TokenStatus.waiting:
        # Get all currently serving tokens (assume half their time remaining)
        serving_tokens = db.query(Token).filter(Token.status == TokenStatus.serving).all()
        serving_remaining = sum(
            (t.estimated_minutes or 10) / 2 for t in serving_tokens
        )
        
        # Get all waiting tokens ahead of this one
        waiting_ahead = db.query(Token).filter(
            Token.status == TokenStatus.waiting,
            Token.issued_at < token.issued_at,
        ).order_by(Token.issued_at.asc()).all()
        
        # Sum up time for each person ahead (use default 10 min if not set)
        waiting_time = sum(
            (t.estimated_minutes or 10) for t in waiting_ahead
        )
        
        estimated_wait = int(serving_remaining + waiting_time)
        
        # Cap at reasonable max (2 hours)
        estimated_wait = min(estimated_wait, 120)

    return QueueStatusOut(
        position=ahead + 1 if token.status == TokenStatus.waiting else 0,
        estimated_wait=estimated_wait,
        status=token.status.value,
        counter=token.counter,
    )


@router.patch("/{token_id}/update-time", response_model=TokenOut)
def update_service_time(token_id: str, body: UpdateTimeRequest, db: Session = Depends(get_db)):
    """Update estimated time for a serving token (staff asks customer after calling them)."""
    token = db.query(Token).filter((Token.id == token_id) | (Token.token_number == token_id)).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    
    if token.status != TokenStatus.serving:
        raise HTTPException(status_code=400, detail="Can only update time for serving tokens")
    
    token.estimated_minutes = body.estimated_minutes
    if body.issue_description:
        token.issue_description = body.issue_description
    
    db.commit()
    db.refresh(token)
    return token
