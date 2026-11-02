import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.data_path = Path(cls.temp.name) / "snapshot.json"
        cls.process = subprocess.Popen(
            [sys.executable, "-u", str(ROOT / "server.py"), "--data", str(cls.data_path),
             "--port", "0"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        line = cls.process.stdout.readline().strip()
        if not line.startswith("Wallboard: "):
            cls.process.terminate()
            raise RuntimeError("Server did not start")
        cls.base = line.removeprefix("Wallboard: ").removesuffix("/pad")
        for _ in range(50):
            try:
                with urlopen(cls.base + "/healthz", timeout=2):
                    break
            except URLError:
                time.sleep(.02)
        else:
            cls.process.terminate()
            raise RuntimeError("Server did not become ready")

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.communicate(timeout=5)
        cls.temp.cleanup()

    def setUp(self):
        self.demo = json.loads((ROOT / "demo/demo.json").read_text(encoding="utf-8"))
        self.data_path.write_text(json.dumps(self.demo), encoding="utf-8")

    def get(self, route):
        with urlopen(self.base + route, timeout=3) as response:
            return response.status, response.headers, response.read()

    def assert_data_error(self):
        status, headers, body = self.get("/pad.json")
        error = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(error["error"], "data_unavailable")
        self.assertRegex(error["at"], r"^\d{2}:\d{2}$")
        self.assertNotIn("decisions", error)
        self.assertEqual(json.loads(self.get("/healthz")[2]), {"ok": True})
        self.assertEqual(self.get("/pad")[0], 200)
        self.assertIsNone(self.process.poll())

    def test_pad_and_health(self):
        for route in ("/", "/pad", "/pad/", "/pad?lang=ko"):
            with self.subTest(route=route):
                status, headers, body = self.get(route)
                self.assertEqual(status, 200)
                self.assertIn("text/html", headers["Content-Type"])
                self.assertEqual(body, (ROOT / "pad.html").read_bytes())
        self.assertEqual(json.loads(self.get("/healthz")[2]), {"ok": True})

    def test_json_matches_demo_and_reads_changes(self):
        status, headers, body = self.get("/pad.json")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(json.loads(body), self.demo)
        self.demo["money"] = "Synthetic tally updated"
        self.data_path.write_text(json.dumps(self.demo), encoding="utf-8")
        self.assertEqual(json.loads(self.get("/pad.json?refresh=1")[2]), self.demo)

    def test_corrupt_data_and_recovery(self):
        overflowing = json.dumps({**self.demo, "extra_value": float("inf")}).replace(
            'Infinity', '1e400').encode()
        unpaired_surrogate = json.dumps({**self.demo, "money": "\ud800"}).encode()
        for content in (b'{broken', b'\xff', b'{"now": NaN}',
                        overflowing, unpaired_surrogate):
            with self.subTest(content=content):
                self.data_path.write_bytes(content)
                self.assert_data_error()
        self.data_path.write_text(json.dumps(self.demo), encoding="utf-8")
        self.assertEqual(json.loads(self.get("/pad.json")[2]), self.demo)

    def test_missing_data_and_recovery(self):
        self.data_path.unlink()
        self.assert_data_error()
        self.data_path.write_text(json.dumps(self.demo), encoding="utf-8")
        self.assertEqual(json.loads(self.get("/pad.json")[2]), self.demo)

    def test_incomplete_snapshot_is_not_an_empty_board(self):
        for invalid in ([], {}, {**self.demo, "hands": [None]},
                        {**self.demo, "now": float("inf")},
                        {**self.demo, "requests": [{"id": "missing-fields"}]}):
            with self.subTest(invalid=invalid):
                self.data_path.write_text(json.dumps(invalid), encoding="utf-8")
                self.assert_data_error()

    def test_private_files_are_not_served(self):
        for route in ("/server.py", "/demo/demo.json", "/../LICENSE", "/unknown"):
            with self.subTest(route=route), self.assertRaises(HTTPError) as caught:
                urlopen(self.base + route, timeout=3)
            self.assertEqual(caught.exception.code, 404)
            caught.exception.close()

    def test_both_demos_have_schema_fields(self):
        required = {"at": str, "now": int, "head": dict, "decisions": list,
                    "hands": list, "notices": list, "schedule": list,
                    "requests": list, "teams": list, "money": str}
        row_fields = {"decisions": {"id": str, "what": str},
                      "hands": {"id": str, "title": str, "when": str},
                      "notices": {"id": str, "title": str},
                      "schedule": {"id": str, "time": str, "title": str},
                      "requests": {"id": str, "fromId": str, "toId": str,
                                   "title": str, "stage": str, "t": int},
                      "teams": {"name": str, "task": str, "worker": str}}
        for name in ("demo.json", "demo.ko.json"):
            with self.subTest(name=name):
                data = json.loads((ROOT / "demo" / name).read_text(encoding="utf-8"))
                for key, kind in required.items():
                    self.assertIsInstance(data[key], kind)
                for key in ("members", "working"):
                    self.assertIsInstance(data["head"][key], int)
                for section, fields in row_fields.items():
                    for item in data[section]:
                        for key, kind in fields.items():
                            self.assertIsInstance(item[key], kind)
                self.assertEqual([len(data[k]) for k in row_fields], [2, 3, 3, 5, 4, 6])
                self.assertTrue(any((data["now"] - r["t"]) / 60 > 70
                                    for r in data["requests"]))
                self.data_path.write_text(json.dumps(data), encoding="utf-8")
                self.assertEqual(json.loads(self.get("/pad.json")[2]), data)


if __name__ == "__main__":
    unittest.main()
