import importlib
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[1]


def load_app(tmpdir: str):
    old_cwd = os.getcwd()
    os.chdir(tmpdir)
    sys.path.insert(0, str(BACKEND_DIR))
    os.environ["LLM_API_KEY"] = "test-key"
    os.environ["LLM_BASE_URL"] = "https://example.test"
    os.environ["LLM_MODEL"] = "test-model"
    os.environ["DATA_DIR"] = str(Path(tmpdir) / "data")

    for name in list(sys.modules):
        if name in {"main", "database", "models", "config"} or name.startswith("routers") or name.startswith("services"):
            sys.modules.pop(name, None)

    try:
        alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
        command.upgrade(alembic_cfg, "head")
        main = importlib.import_module("main")
        database = importlib.import_module("database")
        models = importlib.import_module("models")
        return main.app, database, models
    finally:
        os.chdir(old_cwd)


class AuthTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        app, database, models = load_app(self.tmp.name)
        self.client = TestClient(app)
        self.database = database
        self.models = models

    def tearDown(self):
        self.database.engine.dispose()
        self.tmp.cleanup()

    def test_apps_require_login(self):
        response = self.client.get("/api/apps")
        self.assertEqual(401, response.status_code)

    def test_unknown_employee_cannot_set_password(self):
        response = self.client.post(
            "/api/auth/register",
            json={"employee_no": "64022", "password": "123456"},
        )
        self.assertEqual(403, response.status_code)

    def test_default_admin_can_login_after_database_initialization(self):
        response = self.client.post(
            "/api/auth/login",
            json={"employee_no": "64003", "password": "123456"},
        )
        self.assertEqual(200, response.status_code)
        self.assertTrue(response.json()["is_admin"])

    def test_admin_can_create_employee_after_login(self):
        login = self.client.post(
            "/api/auth/login",
            json={"employee_no": "64003", "password": "123456"},
        )
        self.assertEqual(200, login.status_code)

        created = self.client.post(
            "/api/admin/employees",
            json={"employee_no": "64022", "name": "测试用户"},
        )
        self.assertEqual(201, created.status_code)
        self.assertEqual("64022", created.json()["employee_no"])

    def test_disabled_employee_existing_session_cannot_authenticate(self):
        db = self.database.SessionLocal()
        try:
            db.add(self.models.Employee(employee_no="64021", name="用户一", status="active"))
            db.add(self.models.User(employee_no="64021", password_hash=self.models.hash_password("123456"), is_admin=False))
            db.commit()
        finally:
            db.close()

        user_client = TestClient(self.client.app)
        response = user_client.post("/api/auth/login", json={"employee_no": "64021", "password": "123456"})
        self.assertEqual(200, response.status_code)
        response = user_client.get("/api/auth/me")
        self.assertEqual(200, response.status_code)

        admin_client = TestClient(self.client.app)
        admin_login = admin_client.post("/api/auth/login", json={"employee_no": "64003", "password": "123456"})
        self.assertEqual(200, admin_login.status_code)
        disabled = admin_client.post("/api/admin/employees/64021/disable")
        self.assertEqual(200, disabled.status_code)

        response = user_client.get("/api/auth/me")
        self.assertEqual(401, response.status_code)

    def test_login_stores_session_ip_and_user_agent(self):
        response = self.client.post(
            "/api/auth/login",
            json={"employee_no": "64003", "password": "123456"},
            headers={"User-Agent": "QuickAppTest/1.0"},
        )
        self.assertEqual(200, response.status_code)

        db = self.database.SessionLocal()
        try:
            session = db.query(self.models.SessionToken).first()
            self.assertIsNotNone(session)
            self.assertIsNotNone(session.ip_address)
            self.assertEqual("QuickAppTest/1.0", session.user_agent)
        finally:
            db.close()

    def test_expired_session_cannot_authenticate(self):
        db = self.database.SessionLocal()
        try:
            user = db.query(self.models.User).filter(self.models.User.employee_no == "64003").first()
            session = self.models.SessionToken(
                id="expired-session",
                user_id=user.id,
                expires_at=datetime.utcnow() - timedelta(days=1),
            )
            db.add(session)
            db.commit()
        finally:
            db.close()

        self.client.cookies.set("quickapp_session", "expired-session")
        response = self.client.get("/api/auth/me")
        self.assertEqual(401, response.status_code)

        db = self.database.SessionLocal()
        try:
            session = db.query(self.models.SessionToken).filter(self.models.SessionToken.id == "expired-session").first()
            self.assertIsNone(session)
        finally:
            db.close()

    def create_two_users_and_one_app(self):
        db = self.database.SessionLocal()
        try:
            db.add(self.models.Employee(employee_no="64021", name="用户一", status="active"))
            db.add(self.models.Employee(employee_no="64022", name="用户二", status="active"))
            db.add(self.models.User(employee_no="64021", password_hash=self.models.hash_password("123456"), is_admin=False))
            db.add(self.models.User(employee_no="64022", password_hash=self.models.hash_password("123456"), is_admin=False))
            db.commit()
        finally:
            db.close()

        self.client.post("/api/auth/login", json={"employee_no": "64021", "password": "123456"})
        app_response = self.client.post("/api/apps")
        self.assertEqual(201, app_response.status_code)
        app_id = app_response.json()["id"]
        db = self.database.SessionLocal()
        try:
            app = db.query(self.models.App).filter(self.models.App.id == app_id).first()
            app.status = "active"
            db.commit()
        finally:
            db.close()
        self.client.post("/api/auth/logout")
        return app_id

    def test_user_only_sees_own_apps(self):
        app_id = self.create_two_users_and_one_app()

        self.client.post("/api/auth/login", json={"employee_no": "64022", "password": "123456"})
        apps = self.client.get("/api/apps")
        self.assertEqual([], apps.json())
        other_app = self.client.get(f"/api/apps/{app_id}")
        self.assertEqual(404, other_app.status_code)

    def test_generated_app_page_is_public_after_generation(self):
        app_id = self.create_two_users_and_one_app()
        html_dir = Path(self.tmp.name) / "data" / "apps" / app_id
        html_dir.mkdir(parents=True)
        (html_dir / "index.html").write_text("<html>owned</html>", encoding="utf-8")

        anonymous = self.client.get(f"/apps/{app_id}/")
        self.assertEqual(200, anonymous.status_code)
        self.assertIn("owned", anonymous.text)

        self.client.post("/api/auth/login", json={"employee_no": "64022", "password": "123456"})
        other_user = self.client.get(f"/apps/{app_id}/")
        self.assertEqual(200, other_user.status_code)
        self.assertIn("owned", other_user.text)

    def test_generated_project_files_are_public_after_generation(self):
        app_id = self.create_two_users_and_one_app()
        project_dir = Path(self.tmp.name) / "data" / "apps" / app_id / "project"
        project_dir.mkdir(parents=True)
        (project_dir / "index.html").write_text("<html><link rel='stylesheet' href='css/style.css'></html>", encoding="utf-8")
        (project_dir / "css").mkdir()
        (project_dir / "css" / "style.css").write_text("body { color: red; }", encoding="utf-8")

        anonymous_index = self.client.get(f"/generated/{app_id}/project/index.html")
        self.assertEqual(200, anonymous_index.status_code)
        self.assertIn("stylesheet", anonymous_index.text)

        anonymous_css = self.client.get(f"/generated/{app_id}/project/css/style.css")
        self.assertEqual(200, anonymous_css.status_code)
        self.assertEqual("no-store", anonymous_css.headers["cache-control"])
        self.assertEqual("body { color: red; }", anonymous_css.text)

        self.client.post("/api/auth/login", json={"employee_no": "64022", "password": "123456"})
        other_user = self.client.get(f"/generated/{app_id}/project/index.html")
        self.assertEqual(200, other_user.status_code)
        self.assertIn("stylesheet", other_user.text)

        traversal = self.client.get(f"/generated/{app_id}/project/../index.html")
        self.assertEqual(404, traversal.status_code)

    def test_generated_project_files_remain_accessible_while_editing_or_edit_failed(self):
        app_id = self.create_two_users_and_one_app()
        project_dir = Path(self.tmp.name) / "data" / "apps" / app_id / "project"
        project_dir.mkdir(parents=True)
        (project_dir / "index.html").write_text("<html>last good</html>", encoding="utf-8")

        self.client.post("/api/auth/login", json={"employee_no": "64003", "password": "123456"})
        db = self.database.SessionLocal()
        try:
            app = db.query(self.models.App).filter(self.models.App.id == app_id).first()
            app.version = 1
            app.status = "editing"
            db.commit()
        finally:
            db.close()

        editing_response = self.client.get(f"/generated/{app_id}/project/index.html")
        self.assertEqual(200, editing_response.status_code)
        self.assertIn("last good", editing_response.text)

        db = self.database.SessionLocal()
        try:
            app = db.query(self.models.App).filter(self.models.App.id == app_id).first()
            app.status = "edit_failed"
            db.commit()
        finally:
            db.close()

        failed_edit_response = self.client.get(f"/generated/{app_id}/project/index.html")
        self.assertEqual(200, failed_edit_response.status_code)
        self.assertIn("last good", failed_edit_response.text)

    def test_user_can_delete_own_app_with_conversations_and_files(self):
        app_id = self.create_two_users_and_one_app()
        db = self.database.SessionLocal()
        try:
            app = db.query(self.models.App).filter(self.models.App.id == app_id).first()
            db.add(self.models.Conversation(
                id="delete-conversation-1",
                app_id=app_id,
                role="user",
                content="删除测试",
            ))
            db.add(self.models.UsageRecord(
                id="delete-usage-1",
                user_id=app.user_id,
                app_id=app_id,
                action="generate",
                model="test-model",
                prompt_tokens=1,
                completion_tokens=2,
                total_tokens=3,
                is_estimated=True,
                status="success",
            ))
            db.commit()
        finally:
            db.close()

        html_dir = Path(self.tmp.name) / "data" / "apps" / app_id
        html_dir.mkdir(parents=True)
        (html_dir / "index.html").write_text("<html>delete me</html>", encoding="utf-8")

        self.client.post("/api/auth/login", json={"employee_no": "64021", "password": "123456"})
        response = self.client.delete(f"/api/apps/{app_id}")
        self.assertEqual(200, response.status_code)
        self.assertEqual({"ok": True}, response.json())

        db = self.database.SessionLocal()
        try:
            self.assertIsNone(db.query(self.models.App).filter(self.models.App.id == app_id).first())
            self.assertEqual(0, db.query(self.models.Conversation).filter(self.models.Conversation.app_id == app_id).count())
            usage = db.query(self.models.UsageRecord).filter(self.models.UsageRecord.id == "delete-usage-1").first()
            self.assertIsNotNone(usage)
            self.assertIsNone(usage.app_id)
        finally:
            db.close()
        self.assertFalse(html_dir.exists())

    def test_user_cannot_delete_other_users_app(self):
        app_id = self.create_two_users_and_one_app()

        self.client.post("/api/auth/login", json={"employee_no": "64022", "password": "123456"})
        response = self.client.delete(f"/api/apps/{app_id}")
        self.assertEqual(404, response.status_code)

        db = self.database.SessionLocal()
        try:
            self.assertIsNotNone(db.query(self.models.App).filter(self.models.App.id == app_id).first())
        finally:
            db.close()

    def test_background_generation_saves_project_files(self):
        db = self.database.SessionLocal()
        try:
            db.add(self.models.Employee(employee_no="64014", name="项目测试", status="active"))
            db.add(self.models.User(
                employee_no="64014",
                password_hash=self.models.hash_password("123456"),
                is_admin=False,
            ))
            db.commit()
        finally:
            db.close()

        self.client.post("/api/auth/login", json={"employee_no": "64014", "password": "123456"})
        create_resp = self.client.post("/api/apps")
        self.assertEqual(201, create_resp.status_code)
        app_id = create_resp.json()["id"]

        import asyncio
        from unittest.mock import patch
        from config import Settings
        from services import ai_service, app_service

        react_files = [
            {
                "path": "package.json",
                "content": '{"scripts":{"dev":"vite","build":"vite build","preview":"vite preview"},"dependencies":{"@vitejs/plugin-react":"latest","vite":"latest","typescript":"latest","react":"latest","react-dom":"latest","appwrite":"latest"},"devDependencies":{}}',
            },
            {"path": "index.html", "content": "<div id=\"root\"></div><script type=\"module\" src=\"/src/main.tsx\"></script>"},
            {"path": "src/main.tsx", "content": "import React from 'react'; import { createRoot } from 'react-dom/client'; import App from './App'; createRoot(document.getElementById('root')!).render(<App />);"},
            {"path": "src/App.tsx", "content": "export default function App() { return <main>ok</main>; }"},
            {"path": "src/styles.css", "content": "body { color: green; }"},
            {"path": ".env.example", "content": "VITE_APPWRITE_ENDPOINT=\nVITE_APPWRITE_PROJECT_ID=\nVITE_APPWRITE_DATABASE_ID=\n"},
        ]

        db_gen = self.database.SessionLocal()
        try:
            app = db_gen.query(self.models.App).filter(self.models.App.id == app_id).first()

            def fake_opencode(**kwargs):
                self.assertTrue(kwargs["reset_workspace"])
                on_event = kwargs["on_event"]
                on_event("opencode", {"kind": "session", "sessionID": "session-1", "providerID": "quickda", "modelID": "test-model"})
                on_event("opencode", {"kind": "assistant_delta", "content": "我会生成 React 项目。"})
                on_event("opencode", {"kind": "tool", "tool": "write", "status": "completed", "input": {"filePath": "src/App.tsx"}})
                on_event("opencode", {"kind": "file", "file": "src/App.tsx", "event": "edited"})
                return react_files

            with patch.object(app_service.code_service, "generate_static_frontend_with_opencode", side_effect=fake_opencode):
                with patch.object(
                    ai_service,
                    "non_streaming_chat_with_usage",
                    return_value=ai_service.ChatResult(
                        content="项目",
                        usage=ai_service.TokenUsage(prompt_tokens=3, completion_tokens=2, total_tokens=5),
                    ),
                ):
                    events = []
                    async def _run():
                        async for event in app_service.handle_chat(app, "生成多页面项目", db_gen, Settings()):
                            events.append(event)
                    asyncio.run(_run())
        finally:
            db_gen.close()

        app_dir = Path(self.tmp.name) / "data" / "apps" / app_id
        source_dir = app_dir / "source"
        project_dir = app_dir / "project"
        self.assertEqual("body { color: green; }", (source_dir / "src" / "styles.css").read_text(encoding="utf-8"))
        self.assertTrue((source_dir / "src" / "App.tsx").is_file())
        self.assertFalse(project_dir.exists())
        self.assertTrue(any('"event": "opencode"' in event or event.startswith("event: opencode") for event in events))
        self.assertTrue(any('"status": "active"' in event for event in events))

        db = self.database.SessionLocal()
        try:
            usage = db.query(self.models.UsageRecord).filter(self.models.UsageRecord.app_id == app_id).all()
            self.assertEqual(2, len(usage))
            self.assertEqual({"name", "generate"}, {record.action for record in usage})
            self.assertTrue(all(record.total_tokens > 0 for record in usage))
            usage_by_action = {record.action: record for record in usage}
            self.assertEqual(5, usage_by_action["name"].total_tokens)
            self.assertGreater(usage_by_action["generate"].total_tokens, 0)
            self.assertFalse(usage_by_action["name"].is_estimated)
            self.assertTrue(usage_by_action["generate"].is_estimated)
            for record in usage:
                self.assertEqual("unknown", record.provider)
                self.assertEqual(0, float(record.cost))

            generated_app = db.query(self.models.App).filter(self.models.App.id == app_id).first()
            self.assertEqual("active", generated_app.status)
            self.assertEqual("session-1", generated_app.opencode_session_id)
            self.assertEqual("source/package.json", generated_app.entry_path)
            self.assertEqual(4, db.query(self.models.OpenCodeEvent).filter(self.models.OpenCodeEvent.app_id == app_id).count())

            assistant_message = db.query(self.models.Conversation).filter(
                self.models.Conversation.app_id == app_id,
                self.models.Conversation.role == "assistant",
            ).first()
            self.assertIsNotNone(assistant_message)
            self.assertIn("OpenCode 智能体会话已完成", assistant_message.content)
            self.assertIn("src/App.tsx", assistant_message.content)
            self.assertNotIn('"files"', assistant_message.content)
            self.assertNotIn("css/style.css", assistant_message.content)
        finally:
            db.close()

        opencode_events_response = self.client.get(f"/api/apps/{app_id}/opencode-events")
        self.assertEqual(200, opencode_events_response.status_code)
        payloads = [record["payload"] for record in opencode_events_response.json()]
        self.assertEqual(["session", "assistant_delta", "tool", "file"], [payload["kind"] for payload in payloads])

    def test_project_messages_include_device_preference_prompt(self):
        from config import Settings
        from services import app_service

        db = self.database.SessionLocal()
        try:
            app = self.models.App(id="device-pref-app", user_id=1, version=0)
            messages = app_service._build_project_messages(app, "做一个活动页", [], Settings(), db, "desktop")
            contents = [message["content"] for message in messages if message["role"] == "system"]
            self.assertTrue(any("设备布局目标：电脑端优先" in content for content in contents))
            self.assertTrue(any("宽屏" in content for content in contents))

            messages = app_service._build_project_messages(app, "做一个活动页", [], Settings(), db, "responsive")
            contents = [message["content"] for message in messages if message["role"] == "system"]
            self.assertTrue(any("设备布局目标：自适应" in content for content in contents))

            messages = app_service._build_project_messages(app, "做一个活动页", [], Settings(), db, "bad-value")
            contents = [message["content"] for message in messages if message["role"] == "system"]
            self.assertTrue(any("设备布局目标：手机端优先" in content for content in contents))
        finally:
            db.close()

    def test_generation_returns_busy_result_when_concurrency_limit_is_reached(self):
        db = self.database.SessionLocal()
        try:
            db.add(self.models.Employee(employee_no="64017", name="限流测试", status="active"))
            db.add(self.models.User(
                employee_no="64017",
                password_hash=self.models.hash_password("123456"),
                is_admin=False,
            ))
            db.commit()
        finally:
            db.close()

        self.client.post("/api/auth/login", json={"employee_no": "64017", "password": "123456"})
        create_resp = self.client.post("/api/apps")
        self.assertEqual(201, create_resp.status_code)
        app_id = create_resp.json()["id"]

        import asyncio
        from unittest.mock import patch
        from config import Settings
        from services import app_service

        db_gen = self.database.SessionLocal()
        try:
            app = db_gen.query(self.models.App).filter(self.models.App.id == app_id).first()
            settings = Settings(GENERATION_MAX_CONCURRENT=0)
            with patch.object(app_service.code_service, "generate_static_frontend_with_opencode", side_effect=AssertionError("OpenCode should not run")):
                events = []
                async def _run():
                    async for event in app_service.handle_chat(app, "生成限流页", db_gen, settings):
                        events.append(event)
                asyncio.run(_run())
        finally:
            db_gen.close()

        self.assertTrue(any("当前生成任务较多" in event for event in events))
        self.assertTrue(any('"status": "busy"' in event for event in events))

        db = self.database.SessionLocal()
        try:
            app = db.query(self.models.App).filter(self.models.App.id == app_id).first()
            self.assertEqual("failed", app.status)
            self.assertIsNone(app.progress)
            self.assertEqual(0, app.version)
            self.assertEqual(0, db.query(self.models.UsageRecord).filter(self.models.UsageRecord.app_id == app_id).count())
        finally:
            db.close()

    def test_invalid_generation_output_records_failed_usage(self):
        db = self.database.SessionLocal()
        try:
            db.add(self.models.Employee(employee_no="64016", name="解析失败", status="active"))
            db.add(self.models.User(
                employee_no="64016",
                password_hash=self.models.hash_password("123456"),
                is_admin=False,
            ))
            db.commit()
        finally:
            db.close()

        self.client.post("/api/auth/login", json={"employee_no": "64016", "password": "123456"})
        create_resp = self.client.post("/api/apps")
        self.assertEqual(201, create_resp.status_code)
        app_id = create_resp.json()["id"]

        import asyncio
        from unittest.mock import patch
        from config import Settings
        from services import ai_service, app_service

        db_gen = self.database.SessionLocal()
        try:
            app = db_gen.query(self.models.App).filter(self.models.App.id == app_id).first()
            with patch.object(
                app_service.code_service,
                "generate_static_frontend_with_opencode",
                side_effect=app_service.code_service.ProjectValidationError("OpenCode 没有生成可保存的 React 前端源码。"),
            ):
                with patch.object(ai_service, "non_streaming_chat_with_usage", return_value=ai_service.ChatResult(content="坏输出")):
                    async def _run():
                        async for _ in app_service.handle_chat(app, "生成坏输出", db_gen, Settings()):
                            pass
                    asyncio.run(_run())
        finally:
            db_gen.close()

        db = self.database.SessionLocal()
        try:
            usage = db.query(self.models.UsageRecord).filter(
                self.models.UsageRecord.app_id == app_id,
                self.models.UsageRecord.action == "generate",
            ).first()
            self.assertIsNotNone(usage)
            self.assertEqual("failed", usage.status)
            self.assertGreater(usage.total_tokens, 0)
            self.assertTrue(usage.is_estimated)
        finally:
            db.close()

    def test_failed_background_generation_records_failed_usage(self):
        db = self.database.SessionLocal()
        try:
            db.add(self.models.Employee(employee_no="64015", name="失败测试", status="active"))
            db.add(self.models.User(
                employee_no="64015",
                password_hash=self.models.hash_password("123456"),
                is_admin=False,
            ))
            db.commit()
        finally:
            db.close()

        self.client.post("/api/auth/login", json={"employee_no": "64015", "password": "123456"})
        create_resp = self.client.post("/api/apps")
        self.assertEqual(201, create_resp.status_code)
        app_id = create_resp.json()["id"]

        import asyncio
        from unittest.mock import patch
        from config import Settings
        from services import ai_service, app_service

        db_gen = self.database.SessionLocal()
        try:
            app = db_gen.query(self.models.App).filter(self.models.App.id == app_id).first()
            with patch.object(app_service.code_service, "generate_static_frontend_with_opencode", side_effect=RuntimeError("provider failed")):
                with patch.object(ai_service, "non_streaming_chat_with_usage", return_value=ai_service.ChatResult(content="失败页")):
                    async def _run():
                        async for _ in app_service.handle_chat(app, "生成失败页", db_gen, Settings()):
                            pass
                    asyncio.run(_run())
        finally:
            db_gen.close()

        db = self.database.SessionLocal()
        try:
            usage = db.query(self.models.UsageRecord).filter(
                self.models.UsageRecord.app_id == app_id,
                self.models.UsageRecord.action == "generate",
            ).first()
            self.assertIsNotNone(usage)
            self.assertEqual("failed", usage.status)
            self.assertGreater(usage.total_tokens, 0)
        finally:
            db.close()

    def test_background_generation_rejects_single_html_output_after_disconnect(self):
        db = self.database.SessionLocal()
        try:
            db.add(self.models.Employee(employee_no="64013", name="后台测试", status="active"))
            db.add(self.models.User(
                employee_no="64013",
                password_hash=self.models.hash_password("123456"),
                is_admin=False,
            ))
            db.commit()
        finally:
            db.close()

        self.client.post("/api/auth/login", json={"employee_no": "64013", "password": "123456"})
        create_resp = self.client.post("/api/apps")
        self.assertEqual(201, create_resp.status_code)
        app_id = create_resp.json()["id"]

        import asyncio
        import threading
        from unittest.mock import patch

        generation_done = threading.Event()

        def run_generation():
            async def _run():
                from database import SessionLocal as SL
                from models import App as AppModel
                from config import Settings
                from services import ai_service, app_service
                db_gen = SL()
                try:
                    app = db_gen.query(AppModel).filter(AppModel.id == app_id).first()
                    with patch.object(
                        app_service.code_service,
                        "generate_static_frontend_with_opencode",
                        return_value=[{"path": "index.html", "content": "<!doctype html><html><body>Hello</body></html>"}],
                    ):
                        with patch.object(ai_service, "non_streaming_chat_with_usage", return_value=ai_service.ChatResult(content="测试")):
                            async for _ in app_service.handle_chat(app, "生成测试页", db_gen, Settings()):
                                pass
                finally:
                    db_gen.close()
                    generation_done.set()

            loop = asyncio.new_event_loop()
            loop.run_until_complete(_run())
            loop.close()

        t = threading.Thread(target=run_generation, daemon=True)
        t.start()
        generation_done.wait(timeout=10)
        t.join(timeout=5)

        db = self.database.SessionLocal()
        try:
            app = db.query(self.models.App).filter(self.models.App.id == app_id).first()
            self.assertEqual("failed", app.status)
            self.assertIsNone(app.progress)
            self.assertEqual(0, app.version)
            self.assertEqual("project", app.project_type)
            self.assertFalse((Path(self.tmp.name) / "data" / "apps" / app_id / "index.html").exists())

            usage = db.query(self.models.UsageRecord).filter(
                self.models.UsageRecord.app_id == app_id,
                self.models.UsageRecord.action == "generate",
            ).first()
            self.assertIsNotNone(usage)
            self.assertEqual("failed", usage.status)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
