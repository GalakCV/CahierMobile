import json
import re
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from portability.mobile import build


class MobileBuildTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_content", verbosity=0)

    def test_build_produces_offline_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            info = build(Path(tmp) / "app")
            root = Path(info["dest"])
            for name in ("index.html", "app.css", "content.json", "sw.js", "manifest.webmanifest", "js/app.js",
                         "icons/icon-192.png", "icons/icon-512.png", "icons/apple-touch-icon.png"):
                self.assertTrue((root / name).exists(), name)
            self.assertFalse((root / "sw.template.js").exists())
            sw = (root / "sw.js").read_text(encoding="utf-8")
            self.assertIn(f'cahier-{info["cache_version"]}', sw)
            precache = json.loads(re.search(r"const PRECACHE = (\[.*?\]);", sw).group(1))
            for f in precache[1:]:
                self.assertTrue((root / f).exists(), f)
            self.assertIn("content.json", precache)
            self.assertIn("js/views/practice.js", precache)
            content = json.loads((root / "content.json").read_text(encoding="utf-8"))
            self.assertEqual(content["format"], "cahier-mobile-content")
            self.assertEqual(len(content["exercises"]), info["exercises"])
            self.assertGreaterEqual(len(content["chapters"]), 4)
            json.loads((root / "manifest.webmanifest").read_text(encoding="utf-8"))
            html = (root / "index.html").read_text(encoding="utf-8")
            self.assertNotRegex(html, r'(src|href)="https?://')

    def test_cache_version_changes_with_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            v1 = build(Path(tmp) / "a")["cache_version"]
            from content.models import Exercise
            ex = Exercise.objects.first()
            ex.explanation += " (corrigida)"
            ex.save()
            v2 = build(Path(tmp) / "b")["cache_version"]
            self.assertNotEqual(v1, v2)
