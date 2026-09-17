# EntrenamientosCoach — Coach con Qwen

Rama de trabajo: `feature/qwen-coach`.

Esta implementación es **aislada**: no toca `main`. El repositorio de origen actual contiene únicamente el README, por lo que el Coach se ha construido como un módulo autocontenido y desplegable sin dependencias Python externas. Cuando la aplicación principal se importe al repositorio, este módulo puede integrarse detrás de su navegación sin cambiar el contrato de la app existente.

## Incluye

- UI responsive de Coach.
- Login con cookie HttpOnly y sesión firmada.
- Conversaciones persistentes en SQLite.
- Memoria explícita del usuario, con alta y borrado.
- Recuperación de contexto relevante + últimas conversaciones.
- Integración Qwen mediante API OpenAI-compatible, sin exponer la API key al navegador.
- Modos Coach / Plan / Nutrición / Recuperación.
- Límites de entrada y rate limit básico.
- Cabeceras de seguridad y same-origin.
- Health check para CT105.
- Tests unitarios sin llamadas reales a Qwen.
- CI de GitHub Actions.

Qwen Model Studio ofrece una interfaz OpenAI-compatible para Chat Completions; el endpoint y el modelo se configuran por variables de entorno.

## Configuración

```bash
export COACH_PASSWORD='una-clave-larga-y-unica'
export COACH_SESSION_SECRET='un-secreto-largo-y-aleatorio'
export QWEN_API_KEY='sk-...'
export QWEN_BASE_URL='https://dashscope-intl.aliyuncs.com/compatible-mode/v1'
export QWEN_MODEL='qwen3.8-max'
```

Para producción, usar secretos del sistema/CI; **no** guardar claves en Git.

## Arranque

```bash
python3 coach/server.py
```

Por defecto escucha en `127.0.0.1:8080`. Para CT105 detrás de un reverse proxy:

```bash
export COACH_HOST=127.0.0.1
export COACH_PORT=8080
```

La base de datos se crea en `coach/data/coach.sqlite3` y usa WAL.

## Tests

```bash
python3 -m unittest discover -s coach/tests -v
python3 -m py_compile coach/server.py
```

## Despliegue en CT105

El archivo `deploy/EntrenamientosCoach.service` deja el proceso bajo systemd. Copiar `.env` al directorio de despliegue y no versionarlo.

```bash
sudo cp deploy/EntrenamientosCoach.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now EntrenamientosCoach
sudo systemctl status EntrenamientosCoach
curl http://127.0.0.1:8080/api/health
```

## Seguridad antes de vender

1. Mantener `COACH_HOST=127.0.0.1` y publicar mediante HTTPS/reverse proxy.
2. Definir `COACH_PASSWORD` y `COACH_SESSION_SECRET` con secretos reales.
3. No subir `.env` ni la SQLite a Git.
4. Hacer copia de seguridad de `coach/data/`.
5. Configurar límites del reverse proxy y HTTPS.
6. Probar Qwen desde CT105 antes de abrir acceso público.

### Arquitectura

```text
Browser
  │ HTTPS
  ▼
Reverse proxy
  │ localhost:8080
  ▼
coach/server.py
  ├── Auth/session
  ├── SQLite memory + chats
  └── Qwen OpenAI-compatible API
```
