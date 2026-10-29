import json
import base64
import os
from django.conf import settings


def _imagen_a_base64(archivo):
    data = archivo.read()
    archivo.seek(0)
    mime = getattr(archivo, 'content_type', None) or 'image/jpeg'
    b64 = base64.b64encode(data).decode('utf-8')
    return f"data:{mime};base64,{b64}"


def construir_prompt(partido, jugadores_local, jugadores_visit):
    def listar(jugadores):
        items = []
        for j in jugadores:
            items.append({
                "jugador_id": j.id,
                "dorsal": getattr(j, 'dorsal', None),
                "nombre": (j.nombre or '').upper(),
                "apellido": (j.apellido or '').upper(),
                "equipo_id": getattr(j.equipo, 'id', None),
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
    
    prompt = f"""Eres un experto en leer cédulas arbitrales manuscritas/impresas de fútbol.
Tu tarea es extraer ÚNICAMENTE la información de los jugadores que aparecen en la lista que te doy.

INSTRUCCIONES:
- Solo considera jugadores que estén en las listas "local" o "visitante". NO inventes jugadores.
- Para cada jugador, identifica: participación (titular o cambio), goles, amarillas, rojas.
- En la cédula se marca T/C, se escribe un número para goles, se marcan cruces/palomas para amarillas/rojas.
- Si hay 2 amarillas, eso implica roja.
- Prioriza coincidencia por DORSAL primero, luego por APELLIDO, luego por NOMBRE.
- Si hay duda o no puedes leerlo con certeza, NO lo marques. Mejor omitir que equivocarte.
- Solo marca participación si hay una T o una C clara.
- Los goles son la CANTIDAD (puede ser 0,1,2,...). Si aparece escrito "1" o rayado, cuenta ese número.
- Respeta EXACTAMENTE los jugador_id que te doy.

LISTA DE JUGADORES:
{json.dumps(ctx, ensure_ascii=False, indent=2)}

Devuelve ÚNICAMENTE un JSON válido con este formato exacto:
{{
  "local": [
    {{"jugador_id": 123, "dorsal": 10, "participacion": "titular|cambio", "goles": 0, "amarillas": 1, "rojas": 0, "confianza": 0.95}}
  ],
  "visitante": [...]
}}

Si un jugador no aparece marcado o no se puede leer con certeza, NO lo incluyas en el array.
Usa confianza entre 0-1. Solo incluye si confianza >= 0.7.
"""
    return prompt


def escanear_cedula_con_vision(imagen_file, partido, jugadores_local, jugadores_visit, proveedor="groq"):
    """
    Escanea la cédula usando un modelo de visión.
    Por ahora soporta Groq/OpenRouter/Gemini vía configuración en settings.
    """
    import requests
    
    prompt = construir_prompt(partido, jugadores_local, jugadores_visit)
    img_b64 = _imagen_a_base64(imagen_file)
    
    # Intentar Groq primero
    api_key = getattr(settings, 'GROQ_API_KEY', None) or os.environ.get('GROQ_API_KEY')
    if proveedor == 'groq' and api_key:
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": "meta-llama/llama-4-scout-17b-16e-instruct",  # o qwen2.5-vl si disponible
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": img_b64}},
                        ]
                    }
                ],
                "temperature": 0.1,
                "max_tokens": 2000,
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            content = data['choices'][0]['message']['content']
            # Extraer JSON
            start = content.find('{')
            end = content.rfind('}') + 1
            if start >= 0 and end > start:
                return json.loads(content[start:end])
        except Exception as e:
            return {"error": str(e)}
    
    # Fallback genérico
    return {"error": "No hay proveedor de visión configurado. Configura GROQ_API_KEY en settings/env."}
