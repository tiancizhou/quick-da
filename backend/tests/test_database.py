import importlib
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

from alembic import command
from alembic.config import Config

BACKEND_DIR = Path(__file__).resolve().parents[1]


class DatabaseConfigurationTestCase(unittest.TestCase):
    def import_database_with_url(self, database_url: str):
        old_cwd = os.getcwd()
        tmp = tempfile.TemporaryDirectory()
        os.chdir(tmp.name)
        sys.path.insert(0, str(BACKEND_DIR))
        os.environ["LLM_API_KEY"] = "test-key"
        os.environ["LLM_BASE_URL"] = "https://example.test"
        os.environ["LLM_MODEL"] = "test-model"
        os.environ["DATABASE_URL"] = database_url
        for name in list(sys.modules):
            if name in {"database", "config"}:
                sys.modules.pop(name, None)
        try:
            return importlib.import_module("database"), tmp, old_cwd
        except Exception:
            os.chdir(old_cwd)
            tmp.cleanup()
            raise

    def cleanup_import(self, tmp, old_cwd):
        os.chdir(old_cwd)
        tmp.cleanup()
        for name in list(sys.modules):
            if name in {"database", "config"}:
                sys.modules.pop(name, None)
        os.environ.pop("DATABASE_URL", None)

    def test_sqlite_database_url_uses_sqlite_connect_args(self):
        database, tmp, old_cwd = self.import_database_with_url("sqlite:///./quickapp.db")
        try:
            self.assertEqual({"check_same_thread": False}, database.connect_args_for("sqlite:///./quickapp.db"))
        finally:
            database.engine.dispose()
            self.cleanup_import(tmp, old_cwd)

    def test_postgresql_database_url_uses_no_sqlite_connect_args(self):
        database, tmp, old_cwd = self.import_database_with_url(
            "postgresql+psycopg://quickapp:quickapp@localhost:5432/quickapp"
        )
        try:
            self.assertEqual({}, database.connect_args_for("postgresql+psycopg://quickapp:quickapp@localhost:5432/quickapp"))
        finally:
            database.engine.dispose()
            self.cleanup_import(tmp, old_cwd)

    def test_sqlite_connections_enable_foreign_keys(self):
        database, tmp, old_cwd = self.import_database_with_url("sqlite:///./quickapp.db")
        try:
            with database.engine.connect() as connection:
                enabled = connection.exec_driver_sql("PRAGMA foreign_keys").scalar()
            self.assertEqual(1, enabled)
        finally:
            database.engine.dispose()
            self.cleanup_import(tmp, old_cwd)

    def test_importing_app_does_not_create_schema_without_alembic(self):
        self.assert_import_does_not_create_schema("main")

    def test_admin_creation_script_has_been_removed(self):
        self.assertFalse((BACKEND_DIR / "create_admin.py").exists())

    def test_alembic_upgrade_seeds_default_styles(self):
        database, models, db, tmp, old_cwd = self.upgrade_temporary_database()
        try:
            styles = db.query(models.Style).order_by(models.Style.name).all()
            self.assertEqual(14, len(styles))
            self.assertEqual([
                "3D 元素",
                "Comic Book（漫画书）",
                "Ink Wash（水墨）",
                "反设计工作室",
                "工业设计",
                "平面设计系统",
                "手绘涂鸦",
                "拟物化",
                "无障碍设计",
                "滚动叙事",
                "生成艺术",
                "科幻 HUD",
                "粒子系统",
                "街机 CRT 扫描线",
            ], [style.name for style in styles])
            for style in styles:
                self.assertTrue(style.is_active)
                self.assertGreater(len(style.prompt), 20)
        finally:
            db.close()
            database.engine.dispose()
            os.chdir(old_cwd)
            tmp.cleanup()
            for name in list(sys.modules):
                if name in {"database", "models", "config"}:
                    sys.modules.pop(name, None)
            os.environ.pop("DATABASE_URL", None)

    def test_alembic_upgrade_seeds_default_admin(self):
        database, models, db, tmp, old_cwd = self.upgrade_temporary_database()
        try:
            employee = db.query(models.Employee).filter(models.Employee.employee_no == "64003").first()
            admin = db.query(models.User).filter(models.User.employee_no == "64003").first()
            self.assertIsNotNone(employee)
            self.assertEqual("管理员", employee.name)
            self.assertEqual("active", employee.status)
            self.assertIsNotNone(admin)
            self.assertTrue(admin.is_admin)
            self.assertTrue(models.verify_password("123456", admin.password_hash))
        finally:
            db.close()
            database.engine.dispose()
            os.chdir(old_cwd)
            tmp.cleanup()
            for name in list(sys.modules):
                if name in {"database", "models", "config"}:
                    sys.modules.pop(name, None)
            os.environ.pop("DATABASE_URL", None)

    def test_database_preparation_upgrades_existing_sqlite_database(self):
        old_cwd = os.getcwd()
        tmp = tempfile.TemporaryDirectory()
        db_path = Path(tmp.name) / "quickapp.db"
        os.chdir(BACKEND_DIR)
        sys.path.insert(0, str(BACKEND_DIR))
        os.environ["LLM_API_KEY"] = "test-key"
        os.environ["LLM_BASE_URL"] = "https://example.test"
        os.environ["LLM_MODEL"] = "test-model"
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
        for name in list(sys.modules):
            if name in {"config", "prepare_database", "database", "models"}:
                sys.modules.pop(name, None)
        try:
            alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
            command.upgrade(alembic_cfg, "0001_initial_schema")

            prepare_database = importlib.import_module("prepare_database")
            prepare_database.main()

            connection = sqlite3.connect(db_path)
            try:
                tables = [row[0] for row in connection.execute("select name from sqlite_master where type='table'").fetchall()]
                version = connection.execute("select version_num from alembic_version").fetchone()[0]
            finally:
                connection.close()

            self.assertIn("users", tables)
            self.assertIn("app_data_records", tables)
            self.assertIn("llm_settings", tables)
            self.assertEqual("0004_opencode_sessions", version)
            backups = list(Path(tmp.name).glob("quickapp.db.legacy-*.bak"))
            self.assertEqual([], backups)
        finally:
            os.chdir(old_cwd)
            tmp.cleanup()
            for name in list(sys.modules):
                if name in {"config", "prepare_database", "database", "models"}:
                    sys.modules.pop(name, None)
            os.environ.pop("DATABASE_URL", None)

    def test_database_preparation_initializes_missing_sqlite_database(self):
        old_cwd = os.getcwd()
        tmp = tempfile.TemporaryDirectory()
        db_path = Path(tmp.name) / "quickapp.db"
        os.chdir(BACKEND_DIR)
        sys.path.insert(0, str(BACKEND_DIR))
        os.environ["LLM_API_KEY"] = "test-key"
        os.environ["LLM_BASE_URL"] = "https://example.test"
        os.environ["LLM_MODEL"] = "test-model"
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
        for name in list(sys.modules):
            if name in {"config", "prepare_database", "database", "models"}:
                sys.modules.pop(name, None)
        try:
            prepare_database = importlib.import_module("prepare_database")
            prepare_database.main()

            connection = sqlite3.connect(db_path)
            try:
                user_columns = [row[1] for row in connection.execute("pragma table_info(users)").fetchall()]
                session_columns = [row[1] for row in connection.execute("pragma table_info(sessions)").fetchall()]
                style_count = connection.execute("select count(*) from styles").fetchone()[0]
                admin_count = connection.execute("select count(*) from users where employee_no = '64003'").fetchone()[0]
            finally:
                connection.close()

            self.assertIn("updated_at", user_columns)
            self.assertIn("ip_address", session_columns)
            self.assertEqual(14, style_count)
            self.assertEqual(1, admin_count)
        finally:
            os.chdir(old_cwd)
            tmp.cleanup()
            for name in list(sys.modules):
                if name in {"config", "prepare_database", "database", "models"}:
                    sys.modules.pop(name, None)
            os.environ.pop("DATABASE_URL", None)

    def upgrade_temporary_database(self):
        old_cwd = os.getcwd()
        tmp = tempfile.TemporaryDirectory()
        os.chdir(tmp.name)
        sys.path.insert(0, str(BACKEND_DIR))
        os.environ["LLM_API_KEY"] = "test-key"
        os.environ["LLM_BASE_URL"] = "https://example.test"
        os.environ["LLM_MODEL"] = "test-model"
        os.environ["DATABASE_URL"] = "sqlite:///./quickapp.db"
        for name in list(sys.modules):
            if name in {"database", "models", "config"}:
                sys.modules.pop(name, None)
        alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
        command.upgrade(alembic_cfg, "head")
        database = importlib.import_module("database")
        models = importlib.import_module("models")
        db = database.SessionLocal()
        return database, models, db, tmp, old_cwd

    def assert_import_does_not_create_schema(self, module_name: str, expect_error: bool = False):
        old_cwd = os.getcwd()
        tmp = tempfile.TemporaryDirectory()
        os.chdir(tmp.name)
        sys.path.insert(0, str(BACKEND_DIR))
        os.environ["LLM_API_KEY"] = "test-key"
        os.environ["LLM_BASE_URL"] = "https://example.test"
        os.environ["LLM_MODEL"] = "test-model"
        os.environ["DATABASE_URL"] = "sqlite:///./quickapp.db"
        for name in list(sys.modules):
            if name in {module_name, "main", "database", "models", "config"} or name.startswith("routers") or name.startswith("services"):
                sys.modules.pop(name, None)
        try:
            database = importlib.import_module("database")
            if expect_error:
                with self.assertRaises(Exception):
                    importlib.import_module(module_name)
            else:
                importlib.import_module(module_name)
            with database.engine.connect() as connection:
                tables = connection.exec_driver_sql(
                    "select name from sqlite_master where type='table' and name not like 'sqlite_%'"
                ).fetchall()
            self.assertEqual([], tables)
        finally:
            database.engine.dispose()
            os.chdir(old_cwd)
            tmp.cleanup()
            for name in list(sys.modules):
                if name in {module_name, "main", "database", "models", "config"} or name.startswith("routers") or name.startswith("services"):
                    sys.modules.pop(name, None)
            os.environ.pop("DATABASE_URL", None)


class ModelMetadataTestCase(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(BACKEND_DIR))
        os.environ["LLM_API_KEY"] = "test-key"
        os.environ["LLM_BASE_URL"] = "https://example.test"
        os.environ["LLM_MODEL"] = "test-model"
        for name in list(sys.modules):
            if name in {"database", "models", "config"}:
                sys.modules.pop(name, None)
        self.models = importlib.import_module("models")

    def tearDown(self):
        for name in list(sys.modules):
            if name in {"database", "models", "config"}:
                sys.modules.pop(name, None)
        os.environ.pop("DATABASE_URL", None)

    def test_apps_have_project_metadata_columns(self):
        columns = self.models.App.__table__.columns
        self.assertIn("entry_path", columns)
        self.assertIn("project_type", columns)
        self.assertIn("visibility", columns)
        self.assertIn("preview_token", columns)
        self.assertIn("opencode_session_id", columns)
        self.assertIn("opencode_workspace", columns)

    def test_opencode_events_have_session_replay_columns(self):
        columns = self.models.OpenCodeEvent.__table__.columns
        self.assertIn("app_id", columns)
        self.assertIn("sequence", columns)
        self.assertIn("event_type", columns)
        self.assertIn("payload", columns)
        index_names = {index.name for index in self.models.OpenCodeEvent.__table__.indexes}
        self.assertIn("ix_opencode_events_app_sequence", index_names)

    def test_sessions_have_audit_columns(self):
        columns = self.models.SessionToken.__table__.columns
        self.assertIn("ip_address", columns)
        self.assertIn("user_agent", columns)

    def test_usage_records_have_commercial_tracking_columns(self):
        columns = self.models.UsageRecord.__table__.columns
        self.assertIn("provider", columns)
        self.assertIn("cost", columns)
        self.assertEqual(12, columns["cost"].type.precision)
        self.assertEqual(6, columns["cost"].type.scale)

    def test_core_check_constraints_exist(self):
        constraint_names = {
            constraint.name
            for table in self.models.Base.metadata.tables.values()
            for constraint in table.constraints
            if constraint.name
        }
        self.assertIn("ck_employees_status", constraint_names)
        self.assertIn("ck_apps_status", constraint_names)
        self.assertIn("ck_apps_project_type", constraint_names)
        self.assertIn("ck_apps_visibility", constraint_names)
        self.assertIn("ck_conversations_role", constraint_names)
        self.assertIn("ck_usage_records_action", constraint_names)
        self.assertIn("ck_usage_records_status", constraint_names)

    def test_app_foreign_keys_define_database_delete_behavior(self):
        app_id_fk = next(iter(self.models.Conversation.__table__.columns["app_id"].foreign_keys))
        usage_app_fk = next(iter(self.models.UsageRecord.__table__.columns["app_id"].foreign_keys))
        app_data_fk = next(iter(self.models.AppDataRecord.__table__.columns["app_id"].foreign_keys))
        style_fk = next(iter(self.models.App.__table__.columns["style_id"].foreign_keys))
        self.assertEqual("CASCADE", app_id_fk.ondelete)
        self.assertEqual("SET NULL", usage_app_fk.ondelete)
        self.assertEqual("CASCADE", app_data_fk.ondelete)
        self.assertEqual("SET NULL", style_fk.ondelete)

    def test_preview_token_uses_unique_constraint_without_duplicate_index(self):
        index_names = {index.name for index in self.models.App.__table__.indexes}
        self.assertNotIn("ix_apps_preview_token", index_names)


if __name__ == "__main__":
    unittest.main()
