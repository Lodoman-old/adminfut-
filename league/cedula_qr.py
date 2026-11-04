import re


def leer_partido_de_qr(archivo):
    """Lee el QR de una foto de cédula y devuelve el partido_id (o None).

    El QR contiene la URL corta /c/<partido_id>/.
    """
    try:
        import zxingcpp
        from PIL import Image

        archivo.seek(0)
        img = Image.open(archivo)
        img.load()
        resultados = zxingcpp.read_barcodes(img)
        for r in resultados:
            texto = getattr(r, "text", "") or ""
            m = re.search(r"/c/(\d+)", texto)
            if m:
                return int(m.group(1))
    except Exception:
        pass
    finally:
        try:
            archivo.seek(0)
        except Exception:
            pass
    return None
