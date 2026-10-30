import base64
import json
import os
import re

from django.conf import settings

# Modelo por defecto de cada proveedor. Ojo: los IDs NO son intercambiables
# (p. ej. qwen2.5-vl existe en OpenRouter pero no en Groq).
MODELOS_POR_DEFECTO = {
    'groq': 'meta-llama/llama-4-scout-17b-16e-instruct',
    'openrouter': 'qwen/qwen2.5-vl-72b-instruct',
    'gemini': 'gemini-3.5-flash',
    'ollama': 'qwen2.5vl:7b',
}


def _prompt_default():
    return """Eres un experto en leer cédulas arbitrales manuscritas/impresas de fútbol.
Tu tarea es extraer ÚNICAMENTE la información de los jugadores que aparecen en la lista que te doy.

INSTRUCCIONES:
- Solo considera jugadores que estén en las listas "local" o "visitante". NO inventes jugadores.
- Para cada jugador, identifica: participación (titular o cambio), goles, amarillas, rojas.
- En la cédula se marca T/C, se escribe un número para goles, se marcan cruces/palomas para amarillas/rojas.
- Si hay 2 amarillas, eso implica roja.
- Prioriza coincidencia por DORSAL primero, luego por APELLIDO, luego por NOMBRE.
- Si hay duda o no puedes leerlo con certeza, NO lo marques. Mejor omitir que equivocarte.
- Los corchetes vacíos [] y las celdas en blanco NO son marcas; ignóralos.
- Solo marca participación si hay una T o una C clara.
- Los goles son la CANTIDAD (puede ser 0,1,2,...). Si aparece escrito "1" o rayado, cuenta ese número.
- Respeta EXACTAMENTE los jugador_id que te doy.

LISTA DE JUGADORES:
{contexto_json}

Devuelve ÚNICAMENTE un JSON válido con este formato exacto:
{
  "local": [
    {"jugador_id": 123, "dorsal": 10, "participacion": "titular|cambio", "goles": 0, "amarillas": 1, "rojas": 0, "confianza": 0.95}
  ],
  "visitante": [...]
}

Si un jugador no aparece marcado o no se puede leer con certeza, NO lo incluyas en el array.
Usa confianza entre 0-1. Solo incluye si confianza >= 0.7.
"""


def construir_prompt(partido, jugadores_local, jugadores_visit, prompt_template=None):
    def listar(jugadores):
        items = []
        for j in jugadores:
            items.append({
                "jugador_id": j.id,
                "dorsal": getattr(j, 'dorsal', None),
                "nombre": (j.nombre or '').upper(),
                "apellido": (j.apellido or '').upper(),
                "equipo_id": getattr(j.equipo, 'id', None),
                "equipo_nombre": getattr(getattr(j, 'equipo', None), 'nombre', None),
            })
        return items

    ctx = {
        "partido": {
            "id": partido.id,
            "local": partido.equipo_local.nombre,
            "visitante": partido.equipo_visitante.nombre,
        },
        "local": listar(jugadores_local),
        "visitante": listar(jugadores_visit),
    }

    template = prompt_template or _prompt_default()
    if '{contexto_json}' in template:
        return template.replace('{contexto_json}', json.dumps(ctx, ensure_ascii=False, indent=2))
    if '{lista_jugadores}' in template:
        return template.replace('{lista_jugadores}', json.dumps(ctx, ensure_ascii=False, indent=2))
    # Si no hay placeholder, añadir al final
    return template + "\n\nLISTA DE JUGADORES:\n" + json.dumps(ctx, ensure_ascii=False, indent=2)


def _imagen_payload(archivo):
    data = archivo.read()
    archivo.seek(0)
    mime = getattr(archivo, 'content_type', None) or 'image/jpeg'
    b64 = base64.b64encode(data).decode('utf-8')
    return mime, b64


def _modelo_para(prov, modelo):
    modelo = (modelo or '').strip()
    default = MODELOS_POR_DEFECTO.get(prov, '')
    if not modelo:
        return default
    # Evita un 404 cuando se arrastra el modelo de otro proveedor.
    if prov == 'groq' and (modelo.startswith('qwen/') or modelo.startswith('google/')):
        return default
    if prov == 'gemini' and not modelo.startswith('gemini'):
        return default
    return modelo


def _extraer_json(texto):
    """Saca el primer objeto JSON del texto, aunque venga con ``` o explicaciones."""
    if not texto:
        return None
    limpio = texto.strip()
    limpio = re.sub(r'^```[a-zA-Z0-9_-]*\s*', '', limpio)
    limpio = re.sub(r'\s*```$', '', limpio)
    inicio = limpio.find('{')
    fin = limpio.rfind('}')
    if inicio < 0 or fin <= inicio:
        return None
    return json.loads(limpio[inicio:fin + 1])


def _entero(valor, default=0):
    try:
        return max(0, int(valor))
    except (TypeError, ValueError):
        return default


def _limpiar_resultado(resultado, valid_local, valid_visit):
    """Normaliza y descarta jugadores que no pertenecen a las listas dadas."""
    if not isinstance(resultado, dict):
        return None
    for clave, validos in (('local', valid_local), ('visitante', valid_visit)):
        items = resultado.get(clave)
        if not isinstance(items, list):
            resultado[clave] = []
            continue
        limpios = []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                jugador_id = int(item.get('jugador_id'))
            except (TypeError, ValueError):
                continue
            if jugador_id not in validos:
                continue
            participacion = (item.get('participacion') or '').strip().lower()
            if participacion not in ('titular', 'cambio'):
                participacion = ''
            try:
                confianza = float(item.get('confianza') or 0)
            except (TypeError, ValueError):
                confianza = 0
            limpios.append({
                'jugador_id': jugador_id,
                'participacion': participacion,
                'goles': _entero(item.get('goles')),
                'amarillas': _entero(item.get('amarillas')),
                'rojas': _entero(item.get('rojas')),
                'confianza': confianza,
            })
        resultado[clave] = limpios
    return resultado


def _error_http(resp):
    if resp.status_code == 429:
        return ("Se alcanzó el límite de solicitudes del proveedor (429). "
                "Espera un momento o revisa el plan de tu cuenta.")
    if resp.status_code in (500, 502, 503, 504):
        return ("El modelo de IA está saturado en este momento. "
                "Intenta de nuevo en unos segundos.")
    try:
        detalle = (resp.text or '')[:300].strip()
    except Exception:
        detalle = ''
    base = f"El proveedor respondió {resp.status_code}."
    return f"{base} {detalle}".strip()


def _post_con_reintentos(url, headers, payload, timeout, intentos=3):
    """POST con reintentos cortos para 429/5xx (saturación temporal)."""
    import time

    import requests

    resp = None
    for intento in range(intentos):
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if resp.status_code not in (429, 500, 502, 503, 504):
            return resp
        if intento < intentos - 1:
            time.sleep(1.5 * (intento + 1))
    return resp


def _post_chat_compatible(url, api_key, modelo, prompt, img_b64, mime='image/jpeg', timeout=120, extra_headers=None):
    """Proveedores compatibles con OpenAI: Groq, OpenRouter y Ollama."""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if extra_headers:
        headers.update(extra_headers)
    payload = {
        "model": modelo,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img_b64}"}},
            ],
        }],
        "temperature": 0.1,
        "max_tokens": 4096,
    }
    resp = _post_con_reintentos(url, headers, payload, timeout)
    if resp.status_code >= 400:
        return {"error": _error_http(resp)}
    data = resp.json()
    choices = data.get('choices') or []
    contenido = ''
    if choices:
        contenido = (choices[0].get('message') or {}).get('content') or ''
    if not isinstance(contenido, str):
        contenido = json.dumps(contenido)
    return {'contenido': contenido}


def _post_gemini(url, api_key, modelo, prompt, mime, img_b64, timeout=120):
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
    gen = {"temperature": 0.1, "maxOutputTokens": 4096}
    if modelo.startswith("gemini-2.5-flash"):
        # Leer una cédula no requiere razonamiento; evita tokens de "thinking".
        gen["thinkingConfig"] = {"thinkingBudget": 0}
    elif modelo.startswith("gemini-3"):
        # En Gemini 3 el nivel de razonamiento se controla con thinkingLevel.
        gen["thinkingConfig"] = {"thinkingLevel": "low"}
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime, "data": img_b64}},
            ],
        }],
        "generationConfig": gen,
    }
    resp = _post_con_reintentos(url, headers, payload, timeout)
    if resp.status_code >= 400:
        return {"error": _error_http(resp)}
    data = resp.json()
    candidatos = data.get('candidates') or []
    texto = ''
    if candidatos:
        partes = (candidatos[0].get('content') or {}).get('parts') or []
        texto = ''.join(p.get('text', '') for p in partes if isinstance(p, dict))
    return {'contenido': texto}


def escanear_cedula_con_vision(imagen_file, partido, jugadores_local, jugadores_visit, proveedor=None):
    from league.models import ConfiguracionLiga

    cfg = ConfiguracionLiga.obtener()
    prov = (proveedor or cfg.cedula_vision_proveedor or 'groq').lower()
    api_key = (cfg.cedula_vision_api_key or '').strip() or getattr(settings, 'GROQ_API_KEY', None) or os.environ.get('GROQ_API_KEY') or ''
    modelo = _modelo_para(prov, cfg.cedula_vision_modelo)
    endpoint = (cfg.cedula_vision_endpoint or '').strip()
    prompt_tpl = (cfg.cedula_vision_prompt or '').strip() or None

    prompt = construir_prompt(partido, jugadores_local, jugadores_visit, prompt_tpl)
    mime, img_b64 = _imagen_payload(imagen_file)

    if prov != 'ollama' and not api_key:
        return {"error": "Falta la API Key del proveedor de visión. Configúrala en Configuración > Publicidad."}

    try:
        if prov == 'gemini':
            url = endpoint or f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
            salida = _post_gemini(url, api_key, modelo, prompt, mime, img_b64)
        elif prov == 'groq':
            url = endpoint or "https://api.groq.com/openai/v1/chat/completions"
            salida = _post_chat_compatible(url, api_key, modelo, prompt, img_b64, mime=mime)
        elif prov == 'openrouter':
            url = endpoint or "https://openrouter.ai/api/v1/chat/completions"
            extra = {
                "HTTP-Referer": getattr(settings, 'SITE_URL', ''),
                "X-Title": "AdminFut",
            }
            salida = _post_chat_compatible(url, api_key, modelo, prompt, img_b64, mime=mime, extra_headers=extra)
        elif prov == 'ollama':
            url = endpoint or "http://localhost:11434/v1/chat/completions"
            salida = _post_chat_compatible(url, api_key, modelo, prompt, img_b64, mime=mime)
        else:
            return {"error": f"Proveedor de visión no soportado: {prov}"}
    except Exception as e:
        return {"error": f"No se pudo conectar con el proveedor de visión: {e}"}

    if salida.get('error'):
        mensaje = salida['error']
        if prov == 'groq' and '404' in mensaje:
            mensaje += (" Groq no ofrece modelos de visión en esta cuenta; "
                        "usa Google Gemini u OpenRouter.")
        return {"error": mensaje}

    try:
        resultado = _extraer_json(salida.get('contenido'))
    except Exception:
        return {"error": "La IA devolvió un JSON inválido. Intenta con una foto más clara o revisa el prompt."}
    if resultado is None:
        return {"error": "La IA no devolvió datos reconocibles. Intenta con una foto más clara y completa de la cédula."}

    valid_local = {j.id for j in jugadores_local}
    valid_visit = {j.id for j in jugadores_visit}
    limpio = _limpiar_resultado(resultado, valid_local, valid_visit)
    if limpio is None:
        return {"error": "La IA devolvió un formato inesperado. Intenta de nuevo."}
    return limpio
