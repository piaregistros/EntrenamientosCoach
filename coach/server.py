#!/usr/bin/env python3
"""EntrenamientosCoach - zero-dependency production-friendly Qwen coach backend."""
from __future__ import annotations
import base64, hashlib, hmac, json, os, secrets, sqlite3, time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
DATA = ROOT / "data"
DB_PATH = Path(os.getenv("COACH_DB", DATA / "coach.sqlite3"))
PORT = int(os.getenv("COACH_PORT", "8080"))
HOST = os.getenv("COACH_HOST", "127.0.0.1")
COOKIE = "coach_session"
SESSION_TTL = int(os.getenv("COACH_SESSION_TTL", "604800"))
MAX_BODY = 256_000
MAX_MESSAGE = 12_000
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1").rstrip("/")
QWEN_API_KEY = os.getenv("QWEN_API_KEY", "") or os.getenv("DASHSCOPE_API_KEY", "")
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen3.8-max")
COACH_PASSWORD = os.getenv("COACH_PASSWORD", "")
SESSION_SECRET = os.getenv("COACH_SESSION_SECRET", "")

if not SESSION_SECRET:
    # Ephemeral secret is safe for local use; production should always set COACH_SESSION_SECRET.
    SESSION_SECRET = secrets.token_urlsafe(32)

SYSTEM_PROMPT = """Eres EntrenamientosCoach, un entrenador personal digital claro, práctico y motivador.\n\nObjetivos:\n- Ayudar a planificar entrenamientos, progresión, recuperación, hábitos y nutrición general.\n- Personalizar usando el contexto y las memorias disponibles, sin inventar datos.\n- Priorizar adherencia, técnica, progresión gradual y descanso.\n- Dar respuestas accionables: pasos, series/repeticiones/tiempo cuando proceda y una pregunta final solo si falta información importante.\n\nSeguridad:\n- No diagnostiques enfermedades ni sustituyas a un profesional sanitario.\n- Ante dolor intenso, síntomas neurológicos, dolor torácico, dificultad respiratoria, desmayo u otra señal de alarma, recomienda atención médica urgente.\n- No presentes estimaciones como hechos.\n\nEstilo:\n- Español por defecto.\n- Natural, directo y sin relleno.\n- Si el usuario pide un plan, entrégalo estructurado y listo para usar."""


def db():
    DATA.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT 'Nueva conversación',
            mode TEXT NOT NULL DEFAULT 'coach',
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK(role IN ('user','assistant','system')),
            content TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, id);
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id, updated_at DESC);
        """)


def now(): return int(time.time())


def sign(value: str) -> str:
    mac = hmac.new(SESSION_SECRET.encode(), value.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode().rstrip("=")


def make_session(user_id="owner"):
    payload = f"{user_id}:{now()+SESSION_TTL}"
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=") + "." + sign(payload)


def read_session(handler):
    raw = handler.headers.get("Cookie", "")
    cookies = {}
    for part in raw.split(";"):
        if "=" in part:
            k, v = part.strip().split("=", 1); cookies[k] = v
    token = cookies.get(COOKIE, "")
    if "." not in token: return None
    encoded, sig = token.rsplit(".", 1)
    try: payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
    except Exception: return None
    if not hmac.compare_digest(sign(payload), sig): return None
    try: user, exp = payload.rsplit(":", 1); exp = int(exp)
    except Exception: return None
    return user if exp >= now() else None


def json_bytes(obj): return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def extract_text(response):
    choices = response.get("choices") or []
    if not choices: return "No se recibió respuesta del modelo."
    msg = choices[0].get("message") or {}
    content = msg.get("content", "")
    if isinstance(content, list):
        return "".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in content)
    return str(content)


def qwen(messages, mode):
    if not QWEN_API_KEY:
        raise RuntimeError("QWEN_API_KEY no está configurada")
    mode_hint = {
        "coach": "Actúa como entrenador general.",
        "plan": "Prioriza planes de entrenamiento estructurados y progresión.",
        "nutrition": "Prioriza nutrición general y hábitos; no hagas dietas médicas.",
        "recovery": "Prioriza recuperación, sueño, fatiga y gestión de carga.",
    }.get(mode, "Actúa como entrenador general.")
    payload = {"model": QWEN_MODEL, "messages": [{"role":"system","content":SYSTEM_PROMPT+"\n\nModo actual: "+mode_hint}] + messages, "temperature":0.4, "max_tokens":1200}
    req = Request(QWEN_BASE_URL + "/chat/completions", data=json_bytes(payload), method="POST", headers={"Authorization":"Bearer "+QWEN_API_KEY,"Content-Type":"application/json"})
    try:
        with urlopen(req, timeout=60) as r: return extract_text(json.loads(r.read().decode("utf-8")))
    except HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"Qwen HTTP {e.code}: {detail}")
    except URLError as e:
        raise RuntimeError(f"No se pudo conectar con Qwen: {e.reason}")


def memory_context(con, user_id, text):
    rows = con.execute("SELECT id,content FROM memories WHERE user_id=? ORDER BY updated_at DESC LIMIT 30", (user_id,)).fetchall()
    if not rows: return []
    words = set(text.lower().split())
    ranked = []
    for r in rows:
        score = sum(1 for w in set(r["content"].lower().split()) if len(w) > 3 and w in words)
        ranked.append((score, r["content"]))
    ranked.sort(key=lambda x: x[0], reverse=True)
    return [x[1] for x in ranked[:8]]


def rate_ok(ip):
    bucket = getattr(rate_ok, "bucket", {})
    ts = now(); items = bucket.get(ip, [])
    items = [x for x in items if x > ts-60]
    if len(items) >= 30: bucket[ip] = items; rate_ok.bucket = bucket; return False
    items.append(ts); bucket[ip] = items; rate_ok.bucket = bucket; return True


class Handler(BaseHTTPRequestHandler):
    server_version = "EntrenamientosCoach/1.0"
    def log_message(self, fmt, *args): print(f"[{self.log_date_time_string()}] {self.address_string()} {fmt%args}")
    def send_json(self, obj, status=200, extra=None):
        data=json_bytes(obj); self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Content-Length",str(len(data)))
        for k,v in (extra or {}).items(): self.send_header(k,v)
        self.end_headers(); self.wfile.write(data)
    def body(self):
        n=int(self.headers.get("Content-Length","0"))
        if n>MAX_BODY: raise ValueError("body demasiado grande")
        raw=self.rfile.read(n); return json.loads(raw or b"{}")
    def auth(self):
        return read_session(self)
    def do_GET(self):
        path=urlparse(self.path).path
        if path == "/api/health": return self.send_json({"ok":True,"qwen_configured":bool(QWEN_API_KEY),"model":QWEN_MODEL})
        user=self.auth()
        if path == "/api/me": return self.send_json({"authenticated":bool(user),"user_id":user})
        if not user:
            if path.startswith("/api/"): return self.send_json({"error":"Autenticación requerida"},401)
            return self.static(path)
        if path == "/api/conversations":
            with db() as con: rows=con.execute("SELECT id,title,mode,created_at,updated_at FROM conversations WHERE user_id=? ORDER BY updated_at DESC",(user,)).fetchall()
            return self.send_json({"conversations":[dict(r) for r in rows]})
        if path.startswith("/api/conversations/"):
            try: cid=int(path.rsplit("/",1)[1])
            except: return self.send_json({"error":"ID inválido"},400)
            with db() as con:
                c=con.execute("SELECT * FROM conversations WHERE id=? AND user_id=?",(cid,user)).fetchone()
                if not c: return self.send_json({"error":"Conversación no encontrada"},404)
                ms=con.execute("SELECT id,role,content,created_at FROM messages WHERE conversation_id=? ORDER BY id",(cid,)).fetchall()
            return self.send_json({"conversation":dict(c),"messages":[dict(m) for m in ms]})
        if path == "/api/memories":
            with db() as con: rows=con.execute("SELECT id,content,created_at,updated_at FROM memories WHERE user_id=? ORDER BY updated_at DESC",(user,)).fetchall()
            return self.send_json({"memories":[dict(r) for r in rows]})
        if path == "/api/config": return self.send_json({"model":QWEN_MODEL,"qwen_configured":bool(QWEN_API_KEY)})
        if path.startswith("/api/"): return self.send_json({"error":"Ruta no encontrada"},404)
        return self.static(path)
    def static(self,path):
        if path=="/": path="/index.html"
        rel=path.lstrip("/")
        if ".." in Path(rel).parts: return self.send_json({"error":"Ruta inválida"},400)
        p=PUBLIC/rel
        if not p.is_file(): p=PUBLIC/"index.html"
        types={".html":"text/html",".js":"text/javascript",".css":"text/css",".json":"application/json",".svg":"image/svg+xml"}
        data=p.read_bytes(); self.send_response(200); self.send_header("Content-Type",types.get(p.suffix,"application/octet-stream")); self.send_header("Content-Length",str(len(data))); self.send_header("Cache-Control","no-store"); self.security_headers(); self.end_headers(); self.wfile.write(data)
    def security_headers(self):
        self.send_header("X-Content-Type-Options","nosniff"); self.send_header("X-Frame-Options","DENY"); self.send_header("Referrer-Policy","same-origin"); self.send_header("Permissions-Policy","camera=(), microphone=(), geolocation=()")
    def do_POST(self):
        if not rate_ok(self.client_address[0]): return self.send_json({"error":"Demasiadas peticiones. Espera un minuto."},429)
        path=urlparse(self.path).path
        try: data=self.body()
        except Exception: return self.send_json({"error":"JSON inválido"},400)
        if path=="/api/login":
            if not COACH_PASSWORD: return self.send_json({"error":"COACH_PASSWORD no configurada en el servidor"},503)
            if not hmac.compare_digest(str(data.get("password","")),COACH_PASSWORD): return self.send_json({"error":"Contraseña incorrecta"},401)
            token=make_session(); return self.send_json({"ok":True},extra={"Set-Cookie":f"{COOKIE}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_TTL}"})
        if path=="/api/logout": return self.send_json({"ok":True},extra={"Set-Cookie":f"{COOKIE}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"})
        user=self.auth()
        if not user: return self.send_json({"error":"Autenticación requerida"},401)
        if path=="/api/conversations":
            title=str(data.get("title") or "Nueva conversación")[:120]; mode=str(data.get("mode") or "coach")
            if mode not in {"coach","plan","nutrition","recovery"}: mode="coach"
            t=now()
            with db() as con:
                cur=con.execute("INSERT INTO conversations(user_id,title,mode,created_at,updated_at) VALUES(?,?,?,?,?)",(user,title,mode,t,t)); cid=cur.lastrowid
            return self.send_json({"id":cid,"title":title,"mode":mode})
        if path=="/api/chat":
            text=str(data.get("message","")).strip(); cid=data.get("conversation_id"); mode=str(data.get("mode") or "coach")
            if not text or len(text)>MAX_MESSAGE: return self.send_json({"error":f"El mensaje debe tener entre 1 y {MAX_MESSAGE} caracteres"},400)
            if mode not in {"coach","plan","nutrition","recovery"}: mode="coach"
            with db() as con:
                if cid:
                    c=con.execute("SELECT * FROM conversations WHERE id=? AND user_id=?",(int(cid),user)).fetchone()
                    if not c: return self.send_json({"error":"Conversación no encontrada"},404)
                else:
                    t=now(); cur=con.execute("INSERT INTO conversations(user_id,title,mode,created_at,updated_at) VALUES(?,?,?,?,?)",(user,text[:60],mode,t,t)); cid=cur.lastrowid
                mems=memory_context(con,user,text)
                prior=con.execute("SELECT role,content FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT 16",(cid,)).fetchall()
                prior=list(reversed(prior))
                context=[]
                if mems: context.append({"role":"system","content":"Memorias relevantes del usuario:\n- " + "\n- ".join(mems)})
                context += [{"role":r["role"],"content":r["content"]} for r in prior if r["role"] in {"user","assistant"}]
                context.append({"role":"user","content":text})
                con.execute("INSERT INTO messages(conversation_id,role,content,created_at) VALUES(?,?,?,?)",(cid,"user",text,now()))
            try: answer=qwen(context,mode)
            except Exception as e:
                with db() as con: con.execute("DELETE FROM messages WHERE conversation_id=? AND id=(SELECT max(id) FROM messages WHERE conversation_id=? AND role='user')",(cid,cid))
                return self.send_json({"error":str(e)},502)
            with db() as con:
                con.execute("INSERT INTO messages(conversation_id,role,content,created_at) VALUES(?,?,?,?)",(cid,"assistant",answer,now())); con.execute("UPDATE conversations SET updated_at=?,mode=? WHERE id=?",(now(),mode,cid))
            return self.send_json({"conversation_id":cid,"answer":answer})
        if path=="/api/memories":
            text=str(data.get("content","")).strip()
            if not text or len(text)>1000: return self.send_json({"error":"Memoria inválida"},400)
            t=now()
            with db() as con: cur=con.execute("INSERT INTO memories(user_id,content,created_at,updated_at) VALUES(?,?,?,?)",(user,text,t,t))
            return self.send_json({"id":cur.lastrowid,"content":text})
        return self.send_json({"error":"Ruta no encontrada"},404)
    def do_DELETE(self):
        if not rate_ok(self.client_address[0]): return self.send_json({"error":"Demasiadas peticiones"},429)
        user=self.auth()
        if not user: return self.send_json({"error":"Autenticación requerida"},401)
        path=urlparse(self.path).path
        if path.startswith("/api/memories/"):
            try: mid=int(path.rsplit("/",1)[1])
            except: return self.send_json({"error":"ID inválido"},400)
            with db() as con: con.execute("DELETE FROM memories WHERE id=? AND user_id=?",(mid,user))
            return self.send_json({"ok":True})
        return self.send_json({"error":"Ruta no encontrada"},404)

if __name__ == "__main__":
    init_db()
    if not COACH_PASSWORD: print("WARNING: define COACH_PASSWORD antes de exponer el servicio")
    print(f"EntrenamientosCoach escuchando en http://{HOST}:{PORT} | model={QWEN_MODEL}")
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
