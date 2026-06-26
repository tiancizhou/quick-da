import asyncio
import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[1]


def load_app(tmpdir: str):
    old_cwd = os.getcwd()
    os.chdir(tmpdir)
    sys.path.insert(0, str(BACKEND_DIR))
    os.environ["LLM_API_KEY"] = "env-secret-key"
    os.environ["LLM_BASE_URL"] = "https://env.example.test/v1"
    os.environ["LLM_MODEL"] = "env-model"
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


class LLMSettingsTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        app, database, models = load_app(self.tmp.name)
        self.client = TestClient(app)
        self.database = database
        self.models = models

    def tearDown(self):
        self.database.engine.dispose()
        self.tmp.cleanup()

    def login_admin(self):
        response = self.client.post("/api/auth/login", json={"employee_no": "64003", "password": "123456"})
        self.assertEqual(200, response.status_code)

    def test_llm_settings_requires_admin(self):
        response = self.client.get("/api/admin/llm-settings")
        self.assertEqual(401, response.status_code)

        db = self.database.SessionLocal()
        try:
            db.add(self.models.Employee(employee_no="64031", name="普通用户", status="active"))
            db.add(self.models.User(
                employee_no="64031",
                password_hash=self.models.hash_password("123456"),
                is_admin=False,
            ))
            db.commit()
        finally:
            db.close()

        self.client.post("/api/auth/login", json={"employee_no": "64031", "password": "123456"})
        response = self.client.get("/api/admin/llm-settings")
        self.assertEqual(403, response.status_code)

    def test_llm_settings_fallback_masks_env_key(self):
        self.login_admin()
        response = self.client.get("/api/admin/llm-settings")
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual("https://env.example.test/v1", data["base_url"])
        self.assertEqual("env-model", data["model"])
        self.assertTrue(data["api_key_configured"])
        self.assertEqual("env-******-key", data["api_key_masked"])
        self.assertEqual("env", data["source"])
        self.assertNotIn("env-secret-key", json.dumps(data))

    def test_save_and_read_llm_settings_masks_api_key(self):
        self.login_admin()
        response = self.client.put(
            "/api/admin/llm-settings",
            json={"base_url": " https://db.example.test/v1 ", "model": " db-model ", "api_key": "db-secret-key"},
        )
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual("https://db.example.test/v1", data["base_url"])
        self.assertEqual("db-model", data["model"])
        self.assertEqual("db-s*****-key", data["api_key_masked"])
        self.assertEqual("database", data["source"])
        self.assertNotIn("db-secret-key", json.dumps(data))

        response = self.client.get("/api/admin/llm-settings")
        self.assertEqual(200, response.status_code)
        self.assertNotIn("db-secret-key", json.dumps(response.json()))

        db = self.database.SessionLocal()
        try:
            saved = db.query(self.models.LLMSetting).filter(self.models.LLMSetting.id == "global").first()
            self.assertIsNotNone(saved)
            self.assertEqual("db-secret-key", saved.api_key)
        finally:
            db.close()

    def test_empty_api_key_update_preserves_existing_key(self):
        self.login_admin()
        response = self.client.put(
            "/api/admin/llm-settings",
            json={"base_url": "https://db.example.test/v1", "model": "db-model", "api_key": "first-secret"},
        )
        self.assertEqual(200, response.status_code)

        response = self.client.put(
            "/api/admin/llm-settings",
            json={"base_url": "https://new.example.test/v1", "model": "new-model", "api_key": ""},
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual("https://new.example.test/v1", response.json()["base_url"])

        db = self.database.SessionLocal()
        try:
            saved = db.query(self.models.LLMSetting).filter(self.models.LLMSetting.id == "global").first()
            self.assertEqual("first-secret", saved.api_key)
        finally:
            db.close()

    def test_first_empty_api_key_save_uses_env_fallback_key(self):
        self.login_admin()
        response = self.client.put(
            "/api/admin/llm-settings",
            json={"base_url": "https://first.example.test/v1", "model": "first-model", "api_key": ""},
        )
        self.assertEqual(200, response.status_code)
        self.assertNotIn("env-secret-key", json.dumps(response.json()))

        db = self.database.SessionLocal()
        try:
            saved = db.query(self.models.LLMSetting).filter(self.models.LLMSetting.id == "global").first()
            self.assertEqual("env-secret-key", saved.api_key)
        finally:
            db.close()

    def test_empty_api_key_save_without_existing_or_env_key_returns_chinese_error(self):
        self.login_admin()
        from config import settings

        with patch.object(settings, "LLM_API_KEY", ""):
            response = self.client.put(
                "/api/admin/llm-settings",
                json={"base_url": "https://first.example.test/v1", "model": "first-model", "api_key": ""},
            )

        self.assertEqual(400, response.status_code)
        self.assertEqual("请填写 API Key 后再保存模型配置", response.json()["detail"])

    def test_generation_uses_database_llm_settings(self):
        db = self.database.SessionLocal()
        try:
            db.add(self.models.Employee(employee_no="64032", name="模型测试", status="active"))
            db.add(self.models.User(
                employee_no="64032",
                password_hash=self.models.hash_password("123456"),
                is_admin=False,
            ))
            db.add(self.models.LLMSetting(
                id="global",
                base_url="https://db-provider.test/v1",
                model="db-generation-model",
                api_key="db-generation-key",
            ))
            db.commit()
        finally:
            db.close()

        self.client.post("/api/auth/login", json={"employee_no": "64032", "password": "123456"})
        create_resp = self.client.post("/api/apps")
        self.assertEqual(201, create_resp.status_code)
        app_id = create_resp.json()["id"]

        from config import Settings
        from services import ai_service, app_service

        observed = {"name": None, "generate": None}
        next_files = [
            {"path": "package.json", "content": '{"scripts":{"build":"next build"},"dependencies":{"next":"latest","react":"latest","react-dom":"latest"},"devDependencies":{"typescript":"latest","@types/node":"latest","@types/react":"latest","@types/react-dom":"latest"}}'},
            {"path": "next.config.ts", "content": "const nextConfig = { output: 'export', assetPrefix: './', images: { unoptimized: true } }; export default nextConfig;"},
            {"path": "tsconfig.json", "content": "{}"},
            {"path": "next-env.d.ts", "content": "/// <reference types=\"next\" />"},
            {"path": "app/layout.tsx", "content": "import './globals.css'; export default function RootLayout({ children }) { return <html><body>{children}</body></html>; }"},
            {"path": "app/page.tsx", "content": "export default function Page() { return <main>db</main>; }"},
            {"path": "app/globals.css", "content": "body { color: blue; }"},
        ]
        project_reply = json.dumps({"files": next_files})

        async def fake_name(messages, settings):
            observed["name"] = (settings.LLM_BASE_URL, settings.LLM_MODEL, settings.LLM_API_KEY)
            return ai_service.ChatResult(content="模型页", usage=ai_service.TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2))

        async def fake_stream(messages, settings):
            observed["generate"] = (settings.LLM_BASE_URL, settings.LLM_MODEL, settings.LLM_API_KEY)
            yield ai_service.StreamChatEvent(content=project_reply)
            yield ai_service.StreamChatEvent(usage=ai_service.TokenUsage(prompt_tokens=2, completion_tokens=3, total_tokens=5))

        def fake_build(source_dir):
            out_dir = source_dir / "out"
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "index.html").write_text("<html>db</html>", encoding="utf-8")
            return out_dir

        db_gen = self.database.SessionLocal()
        try:
            app = db_gen.query(self.models.App).filter(self.models.App.id == app_id).first()
            with patch.object(ai_service, "non_streaming_chat_with_usage", fake_name):
                with patch.object(ai_service, "stream_chat_events", fake_stream):
                    with patch.object(app_service.code_service, "build_static_export", fake_build):
                        async def _run():
                            async for _ in app_service.handle_chat(app, "生成模型测试页", db_gen, Settings()):
                                pass
                        asyncio.run(_run())
        finally:
            db_gen.close()

        expected = ("https://db-provider.test/v1", "db-generation-model", "db-generation-key")
        self.assertEqual(expected, observed["name"])
        self.assertEqual(expected, observed["generate"])

        db = self.database.SessionLocal()
        try:
            usage = db.query(self.models.UsageRecord).filter(self.models.UsageRecord.app_id == app_id).all()
            self.assertEqual({"db-generation-model"}, {record.model for record in usage})
        finally:
            db.close()

    def test_generation_returns_actionable_error_when_llm_api_key_is_missing(self):
        db = self.database.SessionLocal()
        try:
            db.add(self.models.Employee(employee_no="64033", name="缺少密钥", status="active"))
            db.add(self.models.User(
                employee_no="64033",
                password_hash=self.models.hash_password("123456"),
                is_admin=False,
            ))
            db.commit()
        finally:
            db.close()

        self.client.post("/api/auth/login", json={"employee_no": "64033", "password": "123456"})
        create_resp = self.client.post("/api/apps")
        self.assertEqual(201, create_resp.status_code)
        app_id = create_resp.json()["id"]

        from config import Settings
        from services import ai_service, app_service

        async def stream_should_not_run(messages, settings):
            raise AssertionError("LLM should not be called when API Key is missing")
            yield ai_service.StreamChatEvent(content="")

        db_gen = self.database.SessionLocal()
        try:
            app = db_gen.query(self.models.App).filter(self.models.App.id == app_id).first()
            settings = Settings(
                LLM_API_KEY="",
                LLM_BASE_URL="https://env.example.test/v1",
                LLM_MODEL="env-model",
                DATA_DIR=str(Path(self.tmp.name) / "data"),
            )
            with patch.object(ai_service, "stream_chat_events", stream_should_not_run):
                events = []

                async def _run():
                    async for event in app_service.handle_chat(app, "生成缺少密钥测试页", db_gen, settings):
                        events.append(event)

                asyncio.run(_run())
        finally:
            db_gen.close()

        self.assertTrue(any("模型配置未完成" in event for event in events))
        self.assertTrue(any("API Key" in event for event in events))

        db = self.database.SessionLocal()
        try:
            app = db.query(self.models.App).filter(self.models.App.id == app_id).first()
            self.assertEqual("failed", app.status)
            self.assertIsNone(app.progress)
            self.assertEqual(0, db.query(self.models.UsageRecord).filter(self.models.UsageRecord.app_id == app_id).count())
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
