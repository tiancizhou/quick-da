import json
import shutil
import uuid
from pathlib import Path
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import App, AppResponse, Conversation, ConversationResponse, OpenCodeEvent, Style, User
from services import code_service
from services.auth_service import get_current_user

router = APIRouter()


class AppCreateRequest(BaseModel):
    style_id: str | None = None


class AppStyleRequest(BaseModel):
    style_id: str | None = None


class OpenCodeEventResponse(BaseModel):
    sequence: int
    event_type: str
    payload: dict[str, Any]
    created_at: str


@router.get("/apps", response_model=List[AppResponse])
def list_apps(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    apps = db.query(App).filter(App.user_id == current_user.id).order_by(App.updated_at.desc()).all()
    return apps


@router.post("/apps", response_model=AppResponse, status_code=201)
def create_app(
    body: AppCreateRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    style_id = body.style_id if body else None
    if style_id and not db.query(Style).filter(Style.id == style_id, Style.is_active == True).first():
        raise HTTPException(status_code=400, detail="Style not found")
    new_app = App(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        style_id=style_id,
        name="新应用",
        status="creating",
        progress=None,
        entry_path="index.html",
        project_type="project",
        visibility="private",
        preview_token=None,
        version=0,
    )
    db.add(new_app)
    db.commit()
    db.refresh(new_app)
    return new_app


@router.patch("/apps/{app_id}/style", response_model=AppResponse)
def update_app_style(
    app_id: str,
    body: AppStyleRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    app = db.query(App).filter(App.id == app_id, App.user_id == current_user.id).first()
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    if body.style_id and not db.query(Style).filter(Style.id == body.style_id, Style.is_active == True).first():
        raise HTTPException(status_code=400, detail="Style not found")
    app.style_id = body.style_id
    db.commit()
    db.refresh(app)
    return app


@router.delete("/apps/{app_id}")
def delete_app(app_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    app = db.query(App).filter(App.id == app_id, App.user_id == current_user.id).first()
    if not app:
        raise HTTPException(status_code=404, detail="App not found")

    db.delete(app)
    db.commit()

    app_dir = Path(settings.DATA_DIR) / "apps" / app_id
    if app_dir.exists():
        shutil.rmtree(app_dir)

    return {"ok": True}


@router.get("/apps/{app_id}/conversations", response_model=List[ConversationResponse])
def list_conversations(app_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    app = db.query(App).filter(App.id == app_id, App.user_id == current_user.id).first()
    if not app:
        raise HTTPException(status_code=404, detail="App not found")

    return (
        db.query(Conversation)
        .filter(Conversation.app_id == app_id)
        .order_by(Conversation.created_at)
        .all()
    )


@router.get("/apps/{app_id}/opencode-events", response_model=List[OpenCodeEventResponse])
def list_opencode_events(app_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    app = db.query(App).filter(App.id == app_id, App.user_id == current_user.id).first()
    if not app:
        raise HTTPException(status_code=404, detail="App not found")

    rows = (
        db.query(OpenCodeEvent)
        .filter(OpenCodeEvent.app_id == app_id)
        .order_by(OpenCodeEvent.sequence)
        .all()
    )
    events = []
    for row in rows:
        try:
            payload = json.loads(row.payload)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        events.append({
            "sequence": row.sequence,
            "event_type": row.event_type,
            "payload": payload,
            "created_at": row.created_at.isoformat(),
        })
    return events


@router.get("/apps/{app_id}/preview")
def get_app_preview(app_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    app = db.query(App).filter(App.id == app_id, App.user_id == current_user.id).first()
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    if app.status not in {"active", "editing", "edit_failed"} or (app.version or 0) <= 0:
        raise HTTPException(status_code=404, detail="App is not active")
    project_index = code_service.project_dir_for(app_id, settings.DATA_DIR) / "index.html"
    if project_index.exists():
        return {"url": f"/generated/{app_id}/project/index.html"}
    legacy_index = Path(settings.DATA_DIR) / "apps" / app_id / "index.html"
    if legacy_index.exists():
        return {"url": f"/apps/{app_id}/"}
    raise HTTPException(status_code=404, detail="App has source code but no built preview")


@router.get("/apps/{app_id}", response_model=AppResponse)
def get_app(app_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    app = db.query(App).filter(App.id == app_id, App.user_id == current_user.id).first()
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    return app
