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
| `GET /ajustes` | Sirve la página Ajustes | HTML |
| `POST /api/summarize` (multipart `file`, y opcionales `model`, `api_key`, `max_tokens`) | extractor → summarizer → summaries | `200` `{"id", "original_filename", "summary_text", "created_at", "truncated"}` |
| `GET /api/settings/defaults` | `/parameters` de summarizer | `{"model", "max_tokens", "max_tokens_limit"}` |
| `GET /api/summaries?limit=100` | summaries | `{"summaries": [...], "total": n}` |
| `GET /api/summaries/{id}` | summaries | el resumen |
| `DELETE /api/summaries/{id}` | summaries | `204` |
| `GET /api/summaries/{id}/export` | summaries → exporter | el `.docx`, con el nombre que decide el exportador |
| `GET /api/health` | `/health` de los cuatro servicios | `{"status": "healthy" \| "degraded", "services": {...}}` |
| `GET /health` | Nada: solo indica que el proceso vive (lo usa Docker) | `{"status": "healthy", "service": "web"}` |

Es el mismo contrato que tenía el monolito, más el `DELETE` y los ajustes del usuario.

- `model`, `api_key` y `max_tokens` son los **ajustes del usuario** (página Ajustes).
  Solo se reenvían a summarizer si llegan; un campo vacío cuenta como no enviado. Valen
  para esa petición: no se guardan en summaries.
- `truncated: true` significa que el modelo se quedó sin tokens y el resumen está
  incompleto. Solo viaja al generarlo; `GET /api/summaries/{id}` no lo trae.
- `/api/settings/defaults` es de solo lectura: muestra lo que usa summarizer cuando el
  usuario no elige nada (Consul o su `.env`).

### Errores

La traducción es común a toda la API (`app/presentation/errors.py`):

| Situación | Respuesta |
|---|---|
| Un servicio rechaza la petición con un motivo (PDF dañado, sin texto, demasiado grande, falta la API key, API key del usuario inválida, modelo inexistente, tope de tokens, 429, 404…) | El **mismo código y mensaje** que dio el servicio. El `429` conserva `Retry-After` |
| Un servicio no responde o falla sin explicar por qué | `502`, indicando qué servicio |
| Un servicio tarda demasiado | `504`, indicando qué servicio |
| El id no es un UUID, o `max_tokens` no es un entero mayor que 0 | `422`. Nunca devuelve lo recibido, para no reflejar la API key |

Si un paso del resumen falla, los siguientes no se ejecutan: un PDF sin texto no
llega a la IA, y si la IA falla no se guarda nada.

## Interfaz

`app/presentation/templates/index.html` y `ajustes.html`, con Tailwind compilado a
`static/css/output.css`.

- El Markdown del resumen se renderiza con `marked` y se sanea con `DOMPurify` antes
  de insertarlo. Las dos librerías van con **versión fija** (`marked@12.0.2`,
  `dompurify@3.1.6`).
- El historial se construye clonando un `<template>` y con `textContent`: el nombre de
  un archivo nunca se interpreta como HTML.
- El borrado llama a la API. Si falla, el elemento se queda en la lista y se muestra
  el error.
- Si el resumen llega con `truncated: true`, se muestra un aviso encima con un enlace a
  Ajustes.

### Página Ajustes (#13, épica pdf-extractext#72)

Se abre con el botón ⚙️ del panel del resumen. Permite elegir el modelo, **añadir
modelos propios** (nombre, modelo de OpenRouter y API key), cambiar el **máximo de
tokens** y **restablecer** los valores del servidor.

- Todo se guarda en el `localStorage` del navegador, bajo `pdf_extractext_settings`, y
  viaja con cada resumen. **Nada se guarda en el servidor**: la app no tiene usuarios,
  y así cada persona solo ve sus claves.
- Ajustes nunca escribe en Consul: los valores del servidor solo se muestran.
- El máximo de tokens se valida contra `max_tokens_limit` antes de guardar.
- Restablecer quita el modelo y los tokens elegidos; los modelos añadidos se conservan
  hasta borrarlos uno a uno.
- Los nombres de los modelos los escribe el usuario: se pintan con `textContent`,
  nunca con `innerHTML`. La página no usa `innerHTML` en ningún sitio.
- Al volver a la portada se reabre el resumen que se estaba viendo (`sessionStorage`).

La API key en `localStorage` la puede leer cualquier script de la página: por eso es
importante que todo el HTML que se inserta siga saneado (#2).

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
| `app/presentation` | Routers, manejadores de errores, schemas y las plantillas (portada y Ajustes) |
| `app/dependencies.py` | Cableado desde `Settings`; lo importan los routers y `main` |

## Flujo de trabajo

`main` y `develop` son las ramas principales. Los cambios entran por pull request a
`develop`, con los tests en verde en la CI. Los commits citan el issue (`#1`).
