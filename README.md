# EntrenamientosCoach — Coach con Qwen

Rama de trabajo: `feature/qwen-coach`.

Esta implementación es aislada y no modifica `main`. El repositorio disponible contenía únicamente el README original, por lo que el Coach se ha construido como módulo autocontenido y desplegable. Antes de integrarlo en la aplicación principal, hay que sincronizar el código actual de la app en este repositorio.

## Incluye
- UI responsive de Coach.
- Login con cookie HttpOnly y sesión firmada.
- Conversaciones persistentes en SQLite.
- Memoria explícita del usuario.
- Recuperación de memoria relevante y contexto reciente.
- Integración Qwen OpenAI-compatible sin exponer la API key.
- Modos Coach / Plan / Nutrición / Recuperación.
- Límites de entrada y rate limit básico.
- Cabeceras de seguridad.
- Health check para CT105.
- Tests unitarios con Qwen simulado.
- CI de GitHub Actions.
- Unidad systemd para CT105.

## Configuración

```bash
export COACH_PASSWORD='una-clave-larga-y-unica'
export COACH_SESSION_SECRET='un-secreto-largo-y-aleatorio'
export QWEN_API_KEY='sk-...'
export QWEN_BASE_URL='https://dashscope-intl.aliyuncs.com/compatible-mode/v1'
export QWEN_MODEL='qwen3.8-max'
```

No guardar secretos en Git.

## Arranque

```bash
python3 coach/server.py
```

Por defecto escucha en `127.0.0.1:8080`.

## Tests

```bash
python3 -m unittest discover -s coach/tests -v
python3 -m py_compile coach/server.py
```

## CT105

`deploy/EntrenamientosCoach.service` proporciona el servicio systemd. Publicarlo mediante HTTPS/reverse proxy y mantener el backend escuchando en localhost.

## Integración segura

`main` debe permanecer intacto hasta que la aplicación actual esté sincronizada con el repositorio. Después se integra Coach detrás de la navegación existente y se ejecuta el build/test completo de la aplicación.
