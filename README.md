# pdf-extractext-web

Interfaz web y orquestador (BFF) de
[pdf-extractext](https://github.com/PDF-extract-organization/pdf-extractext), dividido
en microservicios (épica: pdf-extractext#64).

El navegador solo habla con este servicio. Él sirve la interfaz y coordina por HTTP a
los demás, así el JavaScript no conoce la topología.

```
Navegador ──► web ──► extractor   (PDF → texto)
                  ├─► summarizer  (texto → resumen con IA)
                  ├─► summaries   (historial en MongoDB)
                  └─► exporter    (resumen → .docx)
```

## Contrato HTTP

Escucha en el puerto `8000`. En el stack completo, Traefik le envía `/` y `/api` sin
quitar prefijo: `http://pdf.localhost/`.

| Método y ruta | Qué hace por dentro | Respuesta |
|---|---|---|
| `GET /` | Sirve la interfaz | HTML |
| `POST /api/summarize` (multipart `file`) | extractor → summarizer → summaries | `200` `{"id", "original_filename", "summary_text", "created_at"}` |
| `GET /api/summaries?limit=100` | summaries | `{"summaries": [...], "total": n}` |
| `GET /api/summaries/{id}` | summaries | el resumen |
| `DELETE /api/summaries/{id}` | summaries | `204` |
| `GET /api/summaries/{id}/export` | summaries → exporter | el `.docx`, con el nombre que decide el exportador |
| `GET /api/health` | `/health` de los cuatro servicios | `{"status": "healthy" \| "degraded", "services": {...}}` |
| `GET /health` | Nada: solo indica que el proceso vive (lo usa Docker) | `{"status": "healthy", "service": "web"}` |

Es el mismo contrato que tenía el monolito, más el `DELETE`.

### Errores

La traducción es común a toda la API (`app/presentation/errors.py`):

| Situación | Respuesta |
|---|---|
| Un servicio rechaza la petición con un motivo (PDF dañado, sin texto, demasiado grande, falta la API key, 429, 404…) | El **mismo código y mensaje** que dio el servicio. El `429` conserva `Retry-After` |
| Un servicio no responde o falla sin explicar por qué | `502`, indicando qué servicio |
| Un servicio tarda demasiado | `504`, indicando qué servicio |
| El id no es un UUID | `422` |

Si un paso del resumen falla, los siguientes no se ejecutan: un PDF sin texto no
llega a la IA, y si la IA falla no se guarda nada.

## Interfaz

`app/presentation/templates/index.html`, con Tailwind compilado a
`static/css/output.css`.

- El Markdown del resumen se renderiza con `marked` y se sanea con `DOMPurify` antes
  de insertarlo. Las dos librerías van con **versión fija** (`marked@12.0.2`,
  `dompurify@3.1.6`).
- El historial se construye clonando un `<template>` y con `textContent`: el nombre de
  un archivo nunca se interpreta como HTML.
- El borrado llama a la API. Si falla, el elemento se queda en la lista y se muestra
  el error.

## Configuración

| Variable | Por defecto | Uso |
|---|---|---|
| `EXTRACTOR_URL` | `http://extractor:8000` | Servicio de extracción |
| `SUMMARIZER_URL` | `http://summarizer:8000` | Servicio de resúmenes |
| `SUMMARIES_URL` | `http://summaries:8000` | Servicio de historial |
| `EXPORTER_URL` | `http://exporter:8000` | Servicio de exportación |
| `SERVICE_TIMEOUT_SECONDS` | `10` | Espera a extractor, summaries y exporter |
| `SUMMARIZER_TIMEOUT_SECONDS` | `90` | Espera al resumen: más que el timeout del summarizer hacia la IA (60 s) |

Los valores por defecto son los nombres de los servicios en la red de Docker del
[repositorio de orquestación](https://github.com/PDF-extract-organization/pdf-extractext-orchestration).
Ver `.env.example`.

## Desarrollo

```bash
uv sync --group dev
uv run pytest                     # con dobles de los cuatro servicios: sin red

npm install
npm run build:css                 # o watch:css mientras se edita la plantilla
uv run uvicorn app.main:app --reload
```

`output.css` no se commitea: lo genera el `Dockerfile`. En local hay que ejecutar
`npm run build:css` al menos una vez.

## Docker

```bash
docker build -t pdf-extractext-web .
```

El `Dockerfile` tiene dos etapas: una con Node que compila Tailwind a partir de la
plantilla, y la de Python, que copia el CSS ya compilado. La imagen corre con un
usuario sin privilegios y declara un `HEALTHCHECK` sobre `/health`.

Para levantarlo junto a los demás servicios, usa el `docker-compose` del repositorio de
orquestación. Al integrar en `main`, la CI publica la imagen en
`ghcr.io/pdf-extract-organization/pdf-extractext-web`.

## Arquitectura

| Capa | Contiene |
|---|---|
| `app/application/interfaces` | Puertos de los cuatro servicios |
| `app/application/errors.py` | Errores de los servicios, sin nada de HTTP |
| `app/application/services` | `Orchestrator`: el flujo de cada operación |
| `app/infrastructure` | Clientes `httpx` de los cuatro servicios, con la traducción de errores en un solo sitio |
| `app/presentation` | Routers, manejadores de errores, schemas y la plantilla |
| `app/dependencies.py` | Cableado desde `Settings`; lo importan los routers y `main` |

## Flujo de trabajo

`main` y `develop` son las ramas principales. Los cambios entran por pull request a
`develop`, con los tests en verde en la CI. Los commits citan el issue (`#1`).
