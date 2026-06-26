import json
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from services import code_service


def next_files(page_content: str = "export default function Page() { return <main>ok</main> }"):
    return [
        {
            "path": "package.json",
            "content": json.dumps({
                "scripts": {"dev": "next dev", "build": "next build", "start": "next start"},
                "dependencies": {"next": "latest", "react": "latest", "react-dom": "latest"},
                "devDependencies": {
                    "typescript": "latest",
                    "@types/node": "latest",
                    "@types/react": "latest",
                    "@types/react-dom": "latest",
                },
            }),
        },
        {
            "path": "next.config.ts",
            "content": "import type { NextConfig } from 'next'\n\nconst nextConfig: NextConfig = { output: 'export', assetPrefix: './', images: { unoptimized: true } }\nexport default nextConfig\n",
        },
        {"path": "tsconfig.json", "content": json.dumps({"compilerOptions": {"strict": True}})},
        {"path": "next-env.d.ts", "content": "/// <reference types=\"next\" />\n/// <reference types=\"next/image-types/global\" />\n"},
        {"path": "app/layout.tsx", "content": "import './globals.css'\nexport default function RootLayout({ children }: { children: React.ReactNode }) { return <html lang=\"zh-CN\"><body>{children}</body></html> }\n"},
        {"path": "app/page.tsx", "content": page_content},
        {"path": "app/globals.css", "content": "body { margin: 0; } @media (min-width: 768px) { body { padding: 24px; } }"},
    ]


def react_files():
    return [
        {
            "path": "package.json",
            "content": json.dumps({
                "scripts": {"dev": "vite", "build": "vite build", "preview": "vite preview"},
                "dependencies": {
                    "react": "latest",
                    "react-dom": "latest",
                    "vite": "latest",
                    "typescript": "latest",
                    "@vitejs/plugin-react": "latest",
                    "appwrite": "latest",
                },
            }),
        },
        {"path": "index.html", "content": "<div id=\"root\"></div><script type=\"module\" src=\"/src/main.tsx\"></script>"},
        {"path": "src/main.tsx", "content": "import React from 'react'; import { createRoot } from 'react-dom/client'; import App from './App'; createRoot(document.getElementById('root')!).render(<App />);"},
        {"path": "src/App.tsx", "content": "export default function App() { return <main>ok</main>; }"},
        {"path": "src/lib/appwrite.ts", "content": "import { Client } from 'appwrite'; export const client = new Client().setEndpoint(import.meta.env.VITE_APPWRITE_ENDPOINT).setProject(import.meta.env.VITE_APPWRITE_PROJECT_ID);"},
        {"path": ".env.example", "content": "VITE_APPWRITE_ENDPOINT=\nVITE_APPWRITE_PROJECT_ID=\n"},
    ]


class BuildPatch:
    def __enter__(self):
        self.original = code_service.build_static_export

        def fake_build(source_dir: Path) -> Path:
            out_dir = source_dir / "out"
            chunks_dir = out_dir / "_next" / "static" / "chunks"
            css_dir = out_dir / "_next" / "static" / "css"
            chunks_dir.mkdir(parents=True, exist_ok=True)
            css_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "index.html").write_text("<html><link rel='stylesheet' href=\"/_next/static/css/app.css\"><script src='/_next/static/chunks/app.js'></script></html>", encoding="utf-8")
            (chunks_dir / "app.js").write_text("console.log('built')", encoding="utf-8")
            (css_dir / "app.css").write_text("body{margin:0}", encoding="utf-8")
            return out_dir

        code_service.build_static_export = fake_build
        return self

    def __exit__(self, exc_type, exc, tb):
        code_service.build_static_export = self.original


class ProjectCodeServiceTestCase(unittest.TestCase):
    def test_parse_project_json_accepts_fenced_next_json(self):
        payload = {"files": next_files()}

        files = code_service.parse_project_json(f"```json\n{json.dumps(payload)}\n```")

        self.assertEqual(payload["files"], files)

    def test_parse_project_json_accepts_raw_next_json(self):
        payload = {"files": next_files()}

        files = code_service.parse_project_json(json.dumps(payload))

        self.assertEqual(payload["files"], files)

    def test_parse_project_json_rejects_legacy_html_project(self):
        payload = {
            "files": [
                {"path": "index.html", "content": "<html></html>"},
                {"path": "css/style.css", "content": "body { margin: 0; }"},
                {"path": "js/app.js", "content": "console.log('ok')"},
            ]
        }

        self.assertIsNone(code_service.parse_project_json(json.dumps(payload)))
        with self.assertRaisesRegex(code_service.ProjectValidationError, "缺少必要文件"):
            code_service.parse_project_json_or_raise(json.dumps(payload))

    def test_parse_project_json_rejects_missing_required_next_file(self):
        files = [file for file in next_files() if file["path"] != "app/page.tsx"]
        payload = {"files": files}

        self.assertIsNone(code_service.parse_project_json(json.dumps(payload)))
        with self.assertRaisesRegex(code_service.ProjectValidationError, "app/page.tsx"):
            code_service.parse_project_json_or_raise(json.dumps(payload))

    def test_parse_project_json_rejects_invalid_json_with_detail(self):
        with self.assertRaisesRegex(code_service.ProjectValidationError, "不是有效 JSON"):
            code_service.parse_project_json_or_raise("not json")

    def test_parse_project_json_rejects_unsafe_and_runtime_paths(self):
        unsafe_paths = [
            "../secret.txt",
            "..\\secret.txt",
            "/tmp/index.html",
            "C:\\tmp\\index.html",
            "backend.py",
            "app/api/users/route.ts",
            "pages/api/user.ts",
            "middleware.ts",
            "app/dashboard/route.tsx",
        ]
        for path in unsafe_paths:
            with self.subTest(path=path):
                payload = {"files": [*next_files(), {"path": path, "content": "bad"}]}
                self.assertIsNone(code_service.parse_project_json(json.dumps(payload)))

    def test_parse_project_json_rejects_bad_next_config_and_package(self):
        bad_config = next_files()
        bad_config[1] = {"path": "next.config.ts", "content": "const nextConfig = {}\nexport default nextConfig\n"}
        with self.assertRaisesRegex(code_service.ProjectValidationError, "output"):
            code_service.parse_project_json_or_raise(json.dumps({"files": bad_config}))

        bad_asset_prefix = next_files()
        bad_asset_prefix[1] = {
            "path": "next.config.ts",
            "content": "const nextConfig = { output: 'export', images: { unoptimized: true } }\nexport default nextConfig\n",
        }
        with self.assertRaisesRegex(code_service.ProjectValidationError, "assetPrefix"):
            code_service.parse_project_json_or_raise(json.dumps({"files": bad_asset_prefix}))

        bad_package = next_files()
        bad_package[0] = {
            "path": "package.json",
            "content": json.dumps({
                "scripts": {"build": "next build", "postinstall": "node bad.js"},
                "dependencies": {"next": "latest", "react": "latest", "react-dom": "latest", "lodash": "latest"},
            }),
        }
        with self.assertRaisesRegex(code_service.ProjectValidationError, "不支持的脚本"):
            code_service.parse_project_json_or_raise(json.dumps({"files": bad_package}))

    def test_parse_project_json_rejects_unsafe_package_versions(self):
        bad_package = next_files()
        bad_package[0] = {
            "path": "package.json",
            "content": json.dumps({
                "scripts": {"build": "next build"},
                "dependencies": {"next": "file:../next", "react": "latest", "react-dom": "latest"},
            }),
        }

        with self.assertRaisesRegex(code_service.ProjectValidationError, "依赖版本不安全"):
            code_service.parse_project_json_or_raise(json.dumps({"files": bad_package}))

    def test_parse_project_json_rejects_limits(self):
        too_many = {"files": [*next_files(), *[{"path": f"app/components/{i}.tsx", "content": "export default function X() { return null }"} for i in range(code_service.MAX_PROJECT_FILES)]]}
        oversized = {"files": [*next_files(), {"path": "app/large.tsx", "content": "x" * (code_service.MAX_FILE_BYTES + 1)}]}

        self.assertIsNone(code_service.parse_project_json(json.dumps(too_many)))
        self.assertIsNone(code_service.parse_project_json(json.dumps(oversized)))

    def test_parse_changes_json_accepts_next_source_changes_without_required_files(self):
        payload = {"changes": [{"path": "app/globals.css", "content": "body { color: red; }"}]}

        changes = code_service.parse_changes_json(json.dumps(payload))

        self.assertEqual(payload["changes"], changes)

    def test_save_project_stores_source_and_publishes_static_export(self):
        with tempfile.TemporaryDirectory() as tmpdir, BuildPatch():
            files = next_files()

            project_dir = code_service.save_project("app-1", files, tmpdir)

            self.assertEqual(Path(tmpdir) / "apps" / "app-1" / "project", project_dir)
            source_dir = Path(tmpdir) / "apps" / "app-1" / "source"
            self.assertTrue((source_dir / "app" / "page.tsx").is_file())
            self.assertTrue((project_dir / "index.html").is_file())
            self.assertTrue((project_dir / "_next" / "static" / "chunks" / "app.js").is_file())
            self.assertNotIn("/_next/static", (project_dir / "index.html").read_text(encoding="utf-8"))
            self.assertIn("_next/static/chunks/app.js", (project_dir / "index.html").read_text(encoding="utf-8"))
            self.assertFalse((project_dir / "app" / "page.tsx").exists())
            self.assertEqual(sorted(files, key=lambda item: item["path"]), code_service.read_project_files("app-1", tmpdir))

    def test_save_static_frontend_publishes_files_without_build(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            files = [
                {"path": "index.html", "content": "<!doctype html><html><body><script src=\"app.js\"></script></body></html>"},
                {"path": "app.js", "content": "document.body.dataset.ready = 'true'"},
                {"path": "styles.css", "content": "body { margin: 0; }"},
            ]

            project_dir = code_service.save_static_frontend("app-1", files, tmpdir)

            self.assertEqual(Path(tmpdir) / "apps" / "app-1" / "project", project_dir)
            self.assertEqual(files[0]["content"], (project_dir / "index.html").read_text(encoding="utf-8"))
            self.assertEqual(files[1]["content"], (project_dir / "app.js").read_text(encoding="utf-8"))
            self.assertFalse((Path(tmpdir) / "apps" / "app-1" / "source").exists())

    def test_save_static_frontend_requires_index_html(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(code_service.ProjectValidationError, "index.html"):
                code_service.save_static_frontend("app-1", [{"path": "app.js", "content": "console.log('x')"}], tmpdir)

    def test_save_frontend_source_accepts_react_project_without_build(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = code_service.save_frontend_source("app-1", react_files(), tmpdir)

            self.assertEqual(Path(tmpdir) / "apps" / "app-1" / "source", source_dir)
            self.assertTrue((source_dir / "src" / "App.tsx").is_file())
            self.assertTrue((source_dir / "src" / "lib" / "appwrite.ts").is_file())
            self.assertFalse((Path(tmpdir) / "apps" / "app-1" / "project").exists())

    def test_save_frontend_source_rejects_single_html_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(code_service.ProjectValidationError, "React 前端源码"):
                code_service.save_frontend_source("app-1", [{"path": "index.html", "content": "<html></html>"}], tmpdir)

    def test_save_changes_updates_source_and_rebuilds_preview(self):
        with tempfile.TemporaryDirectory() as tmpdir, BuildPatch():
            project_dir = code_service.save_project("app-1", next_files("export default function Page() { return <main>old</main> }"), tmpdir)

            code_service.save_changes("app-1", [{"path": "app/page.tsx", "content": "export default function Page() { return <main>new</main> }"}], tmpdir)

            source_dir = Path(tmpdir) / "apps" / "app-1" / "source"
            self.assertIn("new", (source_dir / "app" / "page.tsx").read_text(encoding="utf-8"))
            self.assertTrue((project_dir / "index.html").is_file())
            self.assertTrue((project_dir / "_next" / "static" / "chunks" / "app.js").is_file())

    def test_save_changes_build_failure_preserves_existing_source_and_preview(self):
        with tempfile.TemporaryDirectory() as tmpdir, BuildPatch():
            project_dir = code_service.save_project("app-1", next_files("export default function Page() { return <main>old</main> }"), tmpdir)
            (project_dir / "index.html").write_text("old preview", encoding="utf-8")

            original_build = code_service.build_static_export
            try:
                def fail_build(source_dir: Path) -> Path:
                    raise code_service.ProjectValidationError("Next.js 项目构建失败。")

                code_service.build_static_export = fail_build
                with self.assertRaisesRegex(code_service.ProjectValidationError, "构建失败"):
                    code_service.save_changes("app-1", [{"path": "app/page.tsx", "content": "export default function Page() { return <main>bad</main> }"}], tmpdir)
            finally:
                code_service.build_static_export = original_build

            self.assertEqual("old preview", (project_dir / "index.html").read_text(encoding="utf-8"))
            source_dir = Path(tmpdir) / "apps" / "app-1" / "source"
            self.assertIn("old", (source_dir / "app" / "page.tsx").read_text(encoding="utf-8"))

    def test_save_project_build_failure_preserves_existing_source_and_preview(self):
        with tempfile.TemporaryDirectory() as tmpdir, BuildPatch():
            project_dir = code_service.save_project("app-1", next_files("export default function Page() { return <main>old</main> }"), tmpdir)
            source_dir = Path(tmpdir) / "apps" / "app-1" / "source"
            (project_dir / "index.html").write_text("old preview", encoding="utf-8")

            original_build = code_service.build_static_export
            try:
                def fail_build(source_dir: Path) -> Path:
                    raise code_service.ProjectValidationError("Next.js 项目构建失败。")

                code_service.build_static_export = fail_build
                with self.assertRaisesRegex(code_service.ProjectValidationError, "构建失败"):
                    code_service.save_project("app-1", next_files("export default function Page() { return <main>new</main> }"), tmpdir)
            finally:
                code_service.build_static_export = original_build

            self.assertEqual("old preview", (project_dir / "index.html").read_text(encoding="utf-8"))
            self.assertIn("old", (source_dir / "app" / "page.tsx").read_text(encoding="utf-8"))

    def test_save_project_rejects_invalid_entries_without_removing_existing_project(self):
        with tempfile.TemporaryDirectory() as tmpdir, BuildPatch():
            project_dir = code_service.save_project("app-1", next_files(), tmpdir)
            (project_dir / "index.html").write_text("old preview", encoding="utf-8")

            with self.assertRaises(code_service.ProjectValidationError):
                code_service.save_project("app-1", [{"path": "../bad.txt", "content": "bad"}], tmpdir)

            self.assertEqual("old preview", (project_dir / "index.html").read_text(encoding="utf-8"))

    def test_save_changes_rejects_invalid_entries_without_partial_write(self):
        with tempfile.TemporaryDirectory() as tmpdir, BuildPatch():
            code_service.save_project("app-1", next_files("export default function Page() { return <main>old</main> }"), tmpdir)
            source_dir = Path(tmpdir) / "apps" / "app-1" / "source"

            with self.assertRaises(code_service.ProjectValidationError):
                code_service.save_changes("app-1", [
                    {"path": "app/page.tsx", "content": "export default function Page() { return <main>new</main> }"},
                    {"path": "../bad.txt", "content": "bad"},
                ], tmpdir)

            self.assertIn("old", (source_dir / "app" / "page.tsx").read_text(encoding="utf-8"))

    def test_save_changes_rejects_final_source_file_count_over_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir, BuildPatch():
            original_files = [
                *next_files(),
                *[
                    {"path": f"app/existing/{i}.tsx", "content": "export default function X() { return null }"}
                    for i in range(30)
                ],
            ]
            code_service.save_project("app-1", original_files, tmpdir)
            changes = [
                {"path": f"app/pages/{i}.tsx", "content": "export default function X() { return null }"}
                for i in range(code_service.MAX_CHANGE_FILES)
            ]

            with self.assertRaisesRegex(code_service.ProjectValidationError, "文件数量超过上限"):
                code_service.save_changes("app-1", changes, tmpdir)

            source_dir = Path(tmpdir) / "apps" / "app-1" / "source"
            self.assertFalse((source_dir / "app" / "pages" / "0.tsx").exists())

    def test_static_export_rewrite_makes_root_next_assets_relative(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            (project_dir / "nested").mkdir(parents=True)
            (project_dir / "index.html").write_text("<script src=\"/_next/static/chunks/app.js\"></script><link href='/_next/static/css/app.css'>", encoding="utf-8")
            (project_dir / "nested" / "style.css").write_text("body { background: url(/_next/static/media/bg.png); }", encoding="utf-8")
            (project_dir / "_next" / "static" / "chunks").mkdir(parents=True)
            (project_dir / "_next" / "static" / "chunks" / "app.js").write_text("self.__next_f.push('/_next/static/css/app.css')", encoding="utf-8")

            code_service._rewrite_static_export_asset_paths(project_dir)

            self.assertEqual("<script src=\"_next/static/chunks/app.js\"></script><link href='_next/static/css/app.css'>", (project_dir / "index.html").read_text(encoding="utf-8"))
            self.assertEqual("body { background: url(../_next/static/media/bg.png); }", (project_dir / "nested" / "style.css").read_text(encoding="utf-8"))
            self.assertEqual("self.__next_f.push('_next/static/css/app.css')", (project_dir / "_next" / "static" / "chunks" / "app.js").read_text(encoding="utf-8"))

    def test_resolve_project_file_allows_next_static_export_assets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            target = code_service.resolve_project_file(project_dir, "_next/static/chunks/app.js")

            self.assertEqual(project_dir.resolve() / "_next" / "static" / "chunks" / "app.js", target)


if __name__ == "__main__":
    unittest.main()
