"""
Divide imágenes grandes de periódico en mosaicos (tiles) legibles.

PROBLEMA: La API de Anthropic reduce automáticamente imágenes grandes a
~1.15 megapíxeles / 1568px por lado. Una foto de página de periódico
(~3000x3175px = 9.5MP) se reduce tanto que el texto diminuto queda ilegible,
causando que Claude "invente" datos en vez de leer los reales.

SOLUCIÓN: Partir cada imagen en tiles que se mantengan bajo el límite de
Anthropic, de modo que NO se reduzcan y el texto siga legible. Se agrega
solape (overlap) entre tiles para no cortar avisos a la mitad.
"""
import base64
import io
from PIL import Image

# Anthropic reduce a ~1.15MP. Usamos tiles bajo ese límite para evitar reducción.
MAX_TILE_ANCHO = 1500   # bajo 1568 para no forzar reducción por lado largo
MAX_TILE_ALTO = 1500
OVERLAP = 0.12          # 12% de solape entre tiles para no cortar avisos


def _imagen_a_part(img: Image.Image) -> dict:
    """Convierte una imagen PIL a un content block de imagen para Claude."""
    buf = io.BytesIO()
    # Guardar como JPEG con buena calidad
    if img.mode != "RGB":
        img = img.convert("RGB")
    img.save(buf, format="JPEG", quality=90)
    b64 = base64.standard_b64encode(buf.getvalue()).decode("utf-8")
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
    }


def _calcular_cortes(dimension: int, max_tile: int) -> list[tuple[int, int]]:
    """Calcula los rangos (inicio, fin) para dividir una dimensión en tiles
    con solape."""
    if dimension <= max_tile:
        return [(0, dimension)]

    # Número de tiles necesarios
    import math
    paso = int(max_tile * (1 - OVERLAP))
    n_tiles = math.ceil((dimension - max_tile) / paso) + 1
    cortes = []
    for i in range(n_tiles):
        inicio = i * paso
        fin = min(inicio + max_tile, dimension)
        cortes.append((inicio, fin))
        if fin >= dimension:
            break
    return cortes


def generar_tiles(rutas_imagenes: list[str]) -> list[dict]:
    """
    Toma una o más imágenes (ej. mitad superior + inferior de una página),
    las apila verticalmente en UNA página continua, y la divide en tiles
    legibles.

    Devuelve una lista de content blocks de imagen listos para Claude,
    ordenados de arriba-abajo, izquierda-derecha (orden de lectura).
    """
    imagenes = [Image.open(r) for r in rutas_imagenes]

    # Apilar verticalmente (las imágenes son mitad superior + inferior de la
    # misma página larga). Se alinean por el ancho máximo.
    ancho_max = max(img.width for img in imagenes)
    alto_total = sum(img.height for img in imagenes)

    pagina = Image.new("RGB", (ancho_max, alto_total), (255, 255, 255))
    y = 0
    for img in imagenes:
        rgb = img.convert("RGB")
        pagina.paste(rgb, (0, y))
        y += img.height

    # Dividir en tiles
    cortes_x = _calcular_cortes(pagina.width, MAX_TILE_ANCHO)
    cortes_y = _calcular_cortes(pagina.height, MAX_TILE_ALTO)

    tiles = []
    for (y0, y1) in cortes_y:
        for (x0, x1) in cortes_x:
            tile = pagina.crop((x0, y0, x1, y1))
            tiles.append(_imagen_a_part(tile))

    print(f"[image_tiler] Página {pagina.width}x{pagina.height} dividida en "
          f"{len(tiles)} tiles ({len(cortes_x)} col x {len(cortes_y)} fila)")

    return tiles


def contar_tiles(rutas_imagenes: list[str]) -> int:
    """Cuenta cuántos tiles se generarían (para logging/estimación)."""
    return len(generar_tiles(rutas_imagenes))
