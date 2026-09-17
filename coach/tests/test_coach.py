import json, os, sys, tempfile, threading, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DB = Path(tempfile.gettempdir()) / "entrenamientoscoach-test.sqlite3"
try: DB.unlink()
except FileNotFoundError: pass
os.environ["COACH_PASSWORD"] = "test-password"
os.environ["COACH_SESSION_SECRET"] = "test-secret-please-change"
os.environ["COACH_DB"] = str(DB)
os.environ["QWEN_API_KEY"] = "test-key"
import server

class CoachTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.init_db()
        cls.original_qwen = server.qwen
        cls.original_rate = getattr(server.rate_ok, "bucket", {})
        server.qwen = lambda messages, mode: "Respuesta de prueba del coach."
        server.rate_ok.bucket = {}
        cls.http = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True); cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.http.server_port}"
    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown(); cls.thread.join(timeout=2)
        server.qwen = cls.original_qwen
        try: DB.unlink()
        except FileNotFoundError: pass
    def request(self, path, method="GET", payload=None, cookie=None):
        from urllib.request import Request, urlopen
        headers={"Content-Type":"application/json"}
        if cookie: headers["Cookie"]=cookie
        body=json.dumps(payload).encode() if payload is not None else None
        try:
            with urlopen(Request(self.base+path,data=body,method=method,headers=headers)) as r:
                return r.status, json.loads(r.read()), r.headers.get("Set-Cookie")
        except Exception as e:
            return getattr(e,"code",500), json.loads(e.read()), None
    def test_health_public(self):
        status,data,_=self.request("/api/health"); self.assertEqual(status,200); self.assertTrue(data["ok"])
    def test_auth_and_memory(self):
        status,data,cookie=self.request("/api/login","POST",{"password":"test-password"})
        self.assertEqual(status,200); self.assertTrue(cookie)
        session=cookie.split(";",1)[0]
        status,data,_=self.request("/api/memories","POST",{"content":"Objetivo: mejorar fuerza"},session)
        self.assertEqual(status,200); mid=data["id"]
        status,data,_=self.request("/api/memories",cookie=session); self.assertEqual(status,200); self.assertEqual(len(data["memories"]),1)
        status,_,_=self.request(f"/api/memories/{mid}","DELETE",cookie=session); self.assertEqual(status,200)
    def test_chat_persists(self):
        _,_,cookie=self.request("/api/login","POST",{"password":"test-password"}); session=cookie.split(";",1)[0]
        status,data,_=self.request("/api/chat","POST",{"message":"Quiero entrenar hoy","mode":"coach"},session)
        self.assertEqual(status,200); self.assertIn("Respuesta",data["answer"]); cid=data["conversation_id"]
        status,data,_=self.request(f"/api/conversations/{cid}",cookie=session); self.assertEqual(status,200); self.assertEqual(len(data["messages"]),2)
    def test_wrong_password(self):
        status,_,_=self.request("/api/login","POST",{"password":"wrong"}); self.assertEqual(status,401)

if __name__ == "__main__": unittest.main()
