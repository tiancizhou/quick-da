import asyncio
import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator

from sqlalchemy import func
from sqlalchemy.orm import Session

from config import Settings
from database import SessionLocal
from models import App, Conversation, OpenCodeEvent, Style, UsageRecord
from services import ai_service, code_service, llm_config_service, token_service

LEGACY_HTML_SYSTEM_PROMPT = (
    "You are an expert frontend developer. When the user describes an application, "
    "generate a complete, self-contained HTML file that implements it. "
    "Always wrap your HTML in a ```html code block. "
    "Include all CSS and JavaScript inline. Make it visually polished. "
    "The page must include <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"> "
    "and use responsive CSS (flexbox/grid, relative units, media queries) so it works well on mobile phones."
)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@dataclass
class GenerationState:
    chunks: list[str] = field(default_factory=list)
    events: list[tuple[str, dict]] = field(default_factory=list)
    queues: list[asyncio.Queue] = field(default_factory=list)
    done: bool = False
    status: str | None = None
    url: str | None = None
    error: str | None = None
    task: asyncio.Task | None = None


_generation_states: dict[str, GenerationState] = {}
_generation_semaphore: asyncio.Semaphore | None = None
_generation_semaphore_limit: int | None = None

VALID_DEVICE_PREFERENCES = {"mobile", "desktop", "responsive"}


def normalize_device_preference(value: str | None) -> str:
    return value if value in VALID_DEVICE_PREFERENCES else "mobile"


def _device_preference_prompt(device_preference: str) -> str:
    prompts = {
        "mobile": (
            "设备布局目标：手机端优先。请优先为手机竖屏和触控操作设计，375px 宽度下必须可读、可点、无横向滚动；"
            "桌面端只作为增强适配。"
        ),
        "desktop": (
            "设备布局目标：电脑端优先。请优先为桌面宽屏使用设计，合理利用横向空间、网格和多栏布局；"
            "同时保留基础响应式能力，确保手机端不出现横向滚动或不可用控件。"
        ),
        "responsive": (
            "设备布局目标：自适应。请同时兼顾手机端和电脑端体验，使用流式布局、弹性网格和清晰断点；"
            "手机端与桌面端都必须可读、可点、无横向滚动。"
        ),
    }
    return prompts[normalize_device_preference(device_preference)]


async def handle_chat(
    app: App,
    user_message: str,
    db: Session,
    settings: Settings,
    device_preference: str | None = None,
) -> AsyncIterator[str]:
    device_preference = normalize_device_preference(device_preference)
    user_message = user_message or ""

    state = _generation_states.get(app.id)
    if state and not state.done:
        async for chunk in _subscribe_generation(app.id, state):
            yield chunk
        return

    if not user_message.strip():
        yield _sse("result", {
            "url": _active_app_url(app.id, settings),
            "status": app.status,
            "error": None,
        })
        return

    is_first = app.version == 0
    app.status = "creating" if is_first else "editing"
    app.progress = "正在分析需求..."
    db.commit()

    existing_user_message = (
        db.query(Conversation)
        .filter(Conversation.app_id == app.id, Conversation.role == "user")
        .order_by(Conversation.created_at.desc())
        .first()
    )
    if user_message and (not existing_user_message or existing_user_message.content != user_message):
        db.add(Conversation(
            id=str(uuid.uuid4()),
            app_id=app.id,
            role="user",
            content=user_message,
        ))
        db.commit()

    state = GenerationState()
    _generation_states[app.id] = state
    state.task = asyncio.create_task(_run_html_generation(app.id, user_message, settings, state, device_preference))

    async for chunk in _subscribe_generation(app.id, state):
        yield chunk


async def _subscribe_generation(app_id: str, state: GenerationState) -> AsyncIterator[str]:
    if state.events:
        for event, data in state.events:
            yield _sse(event, data)
    else:
        for chunk in state.chunks:
            yield _sse("message", {"content": chunk})

    if state.done:
        yield _sse("result", {"url": state.url, "status": state.status, "error": state.error})
        return

    queue: asyncio.Queue = asyncio.Queue()
    state.queues.append(queue)
    try:
        while True:
            event, data = await queue.get()
            yield _sse(event, data)
            if event == "result":
                return
    finally:
        if queue in state.queues:
            state.queues.remove(queue)


async def _publish(state: GenerationState, event: str, data: dict) -> None:
    for queue in list(state.queues):
        await queue.put((event, data))


async def _record_and_publish(state: GenerationState, event: str, data: dict) -> None:
    state.events.append((event, data))
    await _publish(state, event, data)


async def _run_html_generation(
    app_id: str,
    user_message: str,
    settings: Settings,
    state: GenerationState,
    device_preference: str,
) -> None:
    db = SessionLocal()
    messages: list[dict] = []
    full_reply: list[str] = []
    stream_usage: ai_service.TokenUsage | None = None
    action = "generate"
    try:
        app = db.query(App).filter(App.id == app_id).first()
        if not app:
            state.done = True
            state.status = "failed"
            state.url = None
            state.error = "应用不存在，请刷新后重试。"
            await _publish(state, "result", {"url": None, "status": "failed", "error": state.error})
            return

        semaphore = _get_generation_semaphore(settings.GENERATION_MAX_CONCURRENT)
        if semaphore.locked():
            app.status = "failed" if (app.version or 0) == 0 else "edit_failed"
            app.progress = None
            state.status = "busy"
            state.error = "当前生成任务较多，请稍后再试。"
            db.commit()
            await _publish(state, "message", {"content": state.error})
            return

        async with semaphore:
            try:
                effective_llm_settings = llm_config_service.require_effective_llm_settings(db, settings)
            except llm_config_service.LLMConfigurationError as exc:
                app.status = "failed" if (app.version or 0) == 0 else "edit_failed"
                app.progress = None
                state.status = app.status
                state.error = str(exc)
                db.commit()
                await _publish(state, "message", {"content": state.error})
                return
            await _generate_with_limit(app, user_message, settings, effective_llm_settings, state, db, device_preference)
            return

    except asyncio.CancelledError:
        app = db.query(App).filter(App.id == app_id).first()
        if app:
            app.status = "failed" if (app.version or 0) == 0 else "edit_failed"
            app.progress = None
            state.error = "生成任务已中断，请重新发送。"
            db.commit()
    except Exception:
        app = db.query(App).filter(App.id == app_id).first()
        if app:
            if messages:
                _record_usage(
                    db=db,
                    app=app,
                    action=action,
                    messages=messages,
                    reply_text="".join(full_reply),
                    settings=settings,
                    usage=stream_usage,
                    status="failed",
                )
            app.status = "failed" if (app.version or 0) == 0 else "edit_failed"
            app.progress = None
            state.error = "生成过程中发生错误，请稍后重试。"
            db.commit()
    finally:
        app = db.query(App).filter(App.id == app_id).first()
        state.done = True
        state.status = state.status or (app.status if app else "failed")
        state.url = _active_app_url(app_id, settings) if app and app.status in {"active", "edit_failed"} and (app.version or 0) > 0 else None
        await _publish(state, "result", {"url": state.url, "status": state.status, "error": state.error})
        db.close()


def _get_generation_semaphore(limit: int) -> asyncio.Semaphore:
    global _generation_semaphore, _generation_semaphore_limit
    normalized_limit = max(0, limit)
    if _generation_semaphore is None or _generation_semaphore_limit != normalized_limit:
        _generation_semaphore = asyncio.Semaphore(normalized_limit)
        _generation_semaphore_limit = normalized_limit
    return _generation_semaphore


async def _generate_with_limit(
    app: App,
    user_message: str,
    settings: Settings,
    llm_settings: llm_config_service.EffectiveLLMSettings,
    state: GenerationState,
    db: Session,
    device_preference: str,
) -> None:
    messages: list[dict] = []
    full_reply: list[str] = []
    stream_usage: ai_service.TokenUsage | None = None
    action = "generate"
    app_id = app.id
    try:
        is_first = app.version == 0
        action = "generate" if is_first else "edit"
        if is_first:
            await _set_app_name(app, user_message, llm_settings, db)

        prior_conversations = (
            db.query(Conversation)
            .filter(Conversation.app_id == app.id)
            .order_by(Conversation.created_at)
            .all()
        )

        messages = _build_project_messages(app, user_message, prior_conversations, settings, db, device_preference)

        await _record_and_publish(state, "progress", {"content": "正在启动 OpenCode 智能体..."})
        loop = asyncio.get_running_loop()

        def publish_agent_event(event: str, payload: object) -> None:
            if not payload:
                return
            if event == "progress":
                asyncio.run_coroutine_threadsafe(_record_and_publish(state, "progress", {"content": str(payload)}), loop)
            elif event == "opencode" and isinstance(payload, dict):
                _persist_opencode_event(app.id, payload)
                if payload.get("kind") == "session" and isinstance(payload.get("sessionID"), str):
                    _set_app_opencode_session(app.id, str(payload["sessionID"]), settings)
                asyncio.run_coroutine_threadsafe(_record_and_publish(state, "opencode", payload), loop)
            else:
                content = str(payload)
                state.chunks.append(content)
                asyncio.run_coroutine_threadsafe(_record_and_publish(state, "message", {"content": content}), loop)

        try:
            files = await asyncio.to_thread(
                code_service.generate_static_frontend_with_opencode,
                app_id=app.id,
                prompt=_opencode_generation_prompt(app, user_message, prior_conversations, settings, db, device_preference),
                data_dir=settings.DATA_DIR,
                base_url=llm_settings.LLM_BASE_URL,
                model=llm_settings.LLM_MODEL,
                api_key=llm_settings.LLM_API_KEY,
                on_event=publish_agent_event,
                reset_workspace=is_first,
            )
            await _record_and_publish(state, "progress", {"content": "正在保存 React 前端源码..."})
            saved_url = _save_opencode_frontend_result(app, files, settings)
            final_note = f"源码已保存：OpenCode 生成了 {len(files)} 个 React 前端项目文件。"
            state.chunks.append(final_note)
            await _record_and_publish(state, "opencode", {
                "kind": "publish",
                "fileCount": len(files),
                "previewUrl": saved_url,
                "message": final_note,
            })
            reply_text = _opencode_transcript_summary(state.events, files)
            generation_succeeded = True
        except code_service.ProjectValidationError as exc:
            saved_url = None
            generation_succeeded = False
            state.error = str(exc)
            reply_text = _opencode_transcript_summary(state.events, [])

        if generation_succeeded:
            app.status = "active"
            state.error = None
            app.version = (app.version or 0) + 1
            usage_status = "success"
        else:
            app.status = "failed" if is_first else "edit_failed"
            if not state.error:
                state.error = "模型返回的项目格式无法解析，请调整需求后重试。"
            usage_status = "failed"

        _record_usage(
            db=db,
            app=app,
            action=action,
            messages=messages,
            reply_text=reply_text,
            settings=llm_settings,
            usage=stream_usage,
            status=usage_status,
        )
        app.progress = None
        db.add(Conversation(
            id=str(uuid.uuid4()),
            app_id=app.id,
            role="assistant",
            content=reply_text if app.status == "active" and reply_text else _assistant_conversation_summary(app.status, state.error),
        ))
        db.commit()

    except asyncio.CancelledError:
        app = db.query(App).filter(App.id == app_id).first()
        if app:
            app.status = "failed" if (app.version or 0) == 0 else "edit_failed"
            app.progress = None
            state.error = "生成任务已中断，请重新发送。"
            db.commit()
    except Exception:
        app = db.query(App).filter(App.id == app_id).first()
        if app:
            if messages:
                _record_usage(
                    db=db,
                    app=app,
                    action=action,
                    messages=messages,
                    reply_text="".join(full_reply),
                    settings=llm_settings,
                    usage=stream_usage,
                    status="failed",
                )
            app.status = "failed" if (app.version or 0) == 0 else "edit_failed"
            app.progress = None
            state.error = "生成过程中发生错误，请稍后重试。"
            db.commit()


def _build_project_messages(
    app: App,
    user_message: str,
    prior_conversations: list[Conversation],
    settings: Settings,
    db: Session,
    device_preference: str | None = None,
) -> list[dict]:
    if app.version == 0:
        messages: list[dict] = [{"role": "system", "content": ai_service.PROJECT_GENERATE_SYSTEM_PROMPT}]
    else:
        messages = [{"role": "system", "content": ai_service.PROJECT_MODIFY_SYSTEM_PROMPT}]
        project_files = code_service.read_source_files(app.id, settings.DATA_DIR)
        if project_files:
            messages.append({"role": "system", "content": f"当前 Next.js 源项目文件：\n{json.dumps(project_files, ensure_ascii=False)}"})
        else:
            html_path = Path(settings.DATA_DIR) / "apps" / app.id / "index.html"
            if html_path.exists():
                current_html = html_path.read_text(encoding="utf-8")
                messages = [{"role": "system", "content": LEGACY_HTML_SYSTEM_PROMPT}]
                messages.append({"role": "system", "content": f"Current HTML:\n{current_html}"})

    messages.append({"role": "system", "content": _device_preference_prompt(normalize_device_preference(device_preference))})

    style_prompt = _get_style_prompt(app, db)
    if style_prompt:
        messages.append({"role": "system", "content": style_prompt})

    for conv in prior_conversations:
        messages.append({"role": conv.role, "content": conv.content})
    if user_message and (not messages or messages[-1].get("content") != user_message):
        messages.append({"role": "user", "content": user_message})
    return messages


def _assistant_conversation_summary(status: str, error: str | None = None) -> str:
    if status == "active":
        return "应用已生成或更新，可以在右侧预览。"
    if status == "edit_failed":
        return error or "应用修改失败，已保留上一个可用版本。"
    if status == "failed":
        return error or "应用生成失败，请调整需求后重试。"
    return "应用生成已结束。"


def _save_generation_result(app: App, reply_text: str, is_first: bool, settings: Settings) -> str | None:
    if is_first:
        files = code_service.parse_project_json_or_raise(reply_text)
        code_service.save_project(app.id, files, settings.DATA_DIR)
        app.entry_path = "index.html"
        app.project_type = "project"
        return f"/generated/{app.id}/project/index.html"

    changes = code_service.parse_changes_json_or_raise(reply_text)
    code_service.save_changes(app.id, changes, settings.DATA_DIR)
    app.entry_path = "index.html"
    app.project_type = "project"
    return f"/generated/{app.id}/project/index.html"


def _save_static_frontend_result(app: App, files: list[dict[str, str]], settings: Settings) -> str:
    code_service.save_static_frontend(app.id, files, settings.DATA_DIR)
    app.entry_path = "index.html"
    app.project_type = "project"
    return f"/generated/{app.id}/project/index.html"


def _save_opencode_frontend_result(app: App, files: list[dict[str, str]], settings: Settings) -> str | None:
    code_service.save_frontend_source(app.id, files, settings.DATA_DIR)
    app.entry_path = "source/package.json"
    app.project_type = "project"

    project_safe_files = [file for file in files if code_service.is_safe_project_path(file["path"])]
    project_paths = {file["path"] for file in project_safe_files}
    has_source_runtime = any(file["path"].endswith((".ts", ".tsx", ".jsx")) for file in files)
    if "index.html" in project_paths and not has_source_runtime and "package.json" not in project_paths:
        code_service.save_static_frontend(app.id, project_safe_files, settings.DATA_DIR)
        app.entry_path = "index.html"
        return f"/generated/{app.id}/project/index.html"
    return None


def _opencode_transcript_summary(events: list[tuple[str, dict]], files: list[dict[str, str]]) -> str:
    lines = ["OpenCode 智能体会话已完成。"]
    session_event = next((data for event, data in events if event == "opencode" and data.get("kind") == "session"), None)
    if session_event:
        lines.append(f"Session: {session_event.get('sessionID')}")
        lines.append(f"Agent: {session_event.get('agent')} · Model: {session_event.get('providerID')}/{session_event.get('modelID')}")

    touched_files: list[str] = []
    for event, data in events:
        if event != "opencode":
            continue
        if data.get("kind") == "file" and data.get("file") not in touched_files:
            touched_files.append(str(data.get("file")))
        if data.get("kind") == "patch":
            for file in data.get("files") or []:
                if file not in touched_files:
                    touched_files.append(str(file))

    if touched_files:
        lines.append("Files: " + ", ".join(touched_files[:8]))
    if files:
        lines.append(f"Source files: {len(files)}.")
    return "\n".join(lines)


def _active_app_url(app_id: str, settings: Settings) -> str | None:
    project_index = code_service.project_dir_for(app_id, settings.DATA_DIR) / "index.html"
    if project_index.exists():
        return f"/generated/{app_id}/project/index.html"
    legacy_index = Path(settings.DATA_DIR) / "apps" / app_id / "index.html"
    if legacy_index.exists():
        return f"/apps/{app_id}/"
    return None


def _persist_opencode_event(app_id: str, payload: dict) -> None:
    db = SessionLocal()
    try:
        current_max = (
            db.query(func.max(OpenCodeEvent.sequence))
            .filter(OpenCodeEvent.app_id == app_id)
            .scalar()
        )
        db.add(OpenCodeEvent(
            id=str(uuid.uuid4()),
            app_id=app_id,
            sequence=(current_max or 0) + 1,
            event_type=str(payload.get("kind") or "event")[:50],
            payload=json.dumps(payload, ensure_ascii=False),
        ))
        db.commit()
    finally:
        db.close()


def _set_app_opencode_session(app_id: str, session_id: str, settings: Settings) -> None:
    db = SessionLocal()
    try:
        app = db.query(App).filter(App.id == app_id).first()
        if not app:
            return
        app.opencode_session_id = session_id
        app.opencode_workspace = str(Path(settings.DATA_DIR) / "apps" / app_id / "opencode-workspace")
        db.commit()
    finally:
        db.close()


def list_opencode_event_payloads(app_id: str, db: Session) -> list[dict]:
    rows = (
        db.query(OpenCodeEvent)
        .filter(OpenCodeEvent.app_id == app_id)
        .order_by(OpenCodeEvent.sequence)
        .all()
    )
    payloads: list[dict] = []
    for row in rows:
        try:
            payload = json.loads(row.payload)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


async def _set_app_name(app: App, user_message: str, settings: object, db: Session) -> None:
    naming_messages = [
        {
            "role": "user",
            "content": f"请根据用户需求生成一个简短中文应用名称，最多 8 个汉字，不要使用英文，不要加引号或解释：{user_message}",
        }
    ]
    try:
        result = await ai_service.non_streaming_chat_with_usage(naming_messages, settings)
        clean_name = result.content.strip().strip('"').strip("'")
        app.name = clean_name if re.search(r"[\u4e00-\u9fff]", clean_name) else "新应用"
        _record_usage(db, app, "name", naming_messages, result.content, settings, result.usage, "success")
        db.commit()
        db.refresh(app)
    except Exception:
        pass


def _provider_from_base_url(base_url: str) -> str:
    lowered = base_url.lower()
    if "deepseek" in lowered:
        return "deepseek"
    if "openai" in lowered:
        return "openai"
    return "unknown"


def _record_usage(
    db: Session,
    app: App,
    action: str,
    messages: list[dict],
    reply_text: str,
    settings: object,
    usage: ai_service.TokenUsage | None,
    status: str,
) -> None:
    if usage:
        prompt_tokens = usage.prompt_tokens
        completion_tokens = usage.completion_tokens
        total_tokens = usage.total_tokens or prompt_tokens + completion_tokens
        is_estimated = False
    else:
        prompt_tokens = token_service.estimate_messages_tokens(messages)
        completion_tokens = token_service.estimate_text_tokens(reply_text)
        total_tokens = prompt_tokens + completion_tokens
        is_estimated = True
    db.add(UsageRecord(
        id=str(uuid.uuid4()),
        user_id=app.user_id,
        app_id=app.id,
        action=action,
        provider=_provider_from_base_url(settings.LLM_BASE_URL),
        model=settings.LLM_MODEL,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost=0,
        is_estimated=is_estimated,
        status=status,
    ))


def _get_style_prompt(app: App, db: Session) -> str | None:
    if not app.style_id:
        return None
    style = db.query(Style).filter(Style.id == app.style_id, Style.is_active == True).first()
    return style.prompt if style else None


def _opencode_generation_prompt(
    app: App,
    user_message: str,
    prior_conversations: list[Conversation],
    settings: Settings,
    db: Session,
    device_preference: str | None,
) -> str:
    parts = [
        "请作为一个真实的前端代码智能体，直接在当前目录生成或修改一个工程化 React 前端项目。",
        "技术目标：Vite + React + TypeScript。必须创建或维护 package.json、index.html、src/main.tsx、src/App.tsx，并按需要拆分 src/components、src/lib、src/styles.css 等文件。",
        "只生成前端源码，不要运行 npm、不要安装依赖、不要执行构建、不要生成后端服务。",
        "后端能力使用 Appwrite 云开发平台：需要登录、数据库、文件、实时同步等能力时，在前端通过 Appwrite Web SDK 或 HTTPS API 调用实现。",
        "Appwrite 配置必须从 VITE_APPWRITE_ENDPOINT、VITE_APPWRITE_PROJECT_ID、VITE_APPWRITE_DATABASE_ID 等环境变量读取；可以创建 .env.example，但不要写入任何真实密钥。",
        "如果需要数据访问，请把 Appwrite Client/Account/Databases/Storage 等封装到 src/lib/appwrite.ts，并在 UI 里处理加载、空状态和错误状态。",
        "生成结果会作为源码保存，平台不会在本轮执行构建；请保证代码结构清晰、可由用户后续自行部署。",
        "请确保移动端优先，375px 宽度下可读、可点、无横向滚动，同时保留桌面端增强布局。",
        _device_preference_prompt(normalize_device_preference(device_preference)),
    ]
    style_prompt = _get_style_prompt(app, db)
    if style_prompt:
        parts.append(f"视觉风格要求：\n{style_prompt}")

    existing_files = code_service.read_project_files(app.id, settings.DATA_DIR)
    if existing_files:
        parts.append("当前已有 React 前端源码，请在此基础上修改：")
        parts.append(json.dumps(existing_files, ensure_ascii=False))

    if prior_conversations:
        parts.append("历史对话：")
        for conv in prior_conversations[-8:]:
            parts.append(f"{conv.role}: {conv.content}")

    parts.append(f"本次用户需求：{user_message}")
    return "\n\n".join(parts)
