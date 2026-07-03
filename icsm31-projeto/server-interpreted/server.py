"""
Servidor HTTP interpretado — porta 5001.

Usa APENAS a biblioteca padrao do Python (http.server + zlib), sem Flask e sem
Pillow. O objetivo e que as DUAS versoes comparadas (esta e a compilada em Go)
rodem so com a stdlib da linguagem + o codigo do projeto — nenhuma dependencia
de terceiros, nem para HTTP nem para gerar o PNG. Toda a algebra linear ja e
implementada a mao no modulo `linalg`.

Endpoint:
    POST /reconstruct
        Recebe JSON:
            {
                "g": [...],             # vetor de sinal (lista de floats)
                "H_path": "...",        # opcional — caminho local p/ matriz
                "algorithm": "cgnr"|"cgne",
                "model": 1 | 2,
                "apply_gain": true|false
            }
        Responde JSON:
            {
                "algorithm": ...,
                "image_base64": "<PNG em base64>",
                "width": int, "height": int,
                "n_iter": int,
                "tempo_reconstrucao_s": float,
                "started_at": "ISO8601",
                "finished_at": "ISO8601",
                "server": "python"
            }
    GET /health -> {"status": "ok", "server": "python"}
"""

from __future__ import annotations

import base64
import json
import logging
import os
import resource
import struct
import sys
import time
import zlib
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Sequence, Tuple

from cgne import cgne
from cgnr import cgnr
from linalg import Matrix, load_matrix_csv
from params import reduction_factor, regularization_lambda
from signal_gain import apply_signal_gain

LOG = logging.getLogger("server-interpreted")
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
)

MODEL_CONFIG = {
    1: {"S": 794, "N": 64, "size": (60, 60)},
    2: {"S": 436, "N": 64, "size": (30, 30)},
}


def _peak_rss_mb() -> float:
    """Pico de memoria residente (RSS) do processo, em MB, so com a stdlib.

    Usa resource.getrusage(RUSAGE_SELF).ru_maxrss. As unidades diferem por SO:
    macOS/BSD reportam em bytes; Linux, em kilobytes.
    """
    maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return maxrss / (1024.0 * 1024.0)  # bytes -> MB
    return maxrss / 1024.0                  # kB -> MB (Linux)


def _load_H(path: str) -> Matrix:
    """Carrega a matriz H de arquivo CSV/texto em Python puro.

    Sem cache: cada requisicao le a matriz do zero, para que toda reconstrucao
    seja independente (nenhum estado reaproveitado entre requisicoes).
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Matriz H nao encontrada: {path}")

    H = load_matrix_csv(path)
    LOG.info("Matriz H carregada de %s, shape=%s", path, H.shape)
    return H


# ---------------------------------------------------------------------------
# Encoder PNG em Python puro (stdlib) — substitui o Pillow.
#
# Escreve um PNG 8-bit em tons de cinza (color type 0), gravando os metadados
# como chunks tEXt (antes do IDAT, igual ao servidor Go). Formato de cada chunk:
#   length(4, big-endian) | tipo(4) | dados | CRC(4) de (tipo+dados).
# A compressao do IDAT usa zlib (stdlib); o stream deflate/zlib e exatamente o
# que o PNG espera.
# ---------------------------------------------------------------------------
_PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + chunk_type
        + data
        + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
    )


def _encode_png_gray(
    pixels: bytes, width: int, height: int, metadata: Dict[str, Any]
) -> bytes:
    """Serializa um buffer row-major de 8 bits (L) em PNG, com chunks tEXt."""
    # IHDR: largura, altura, profundidade=8, color type=0 (cinza), demais=0
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    out = [_PNG_SIG, _png_chunk(b"IHDR", ihdr)]

    # tEXt: keyword\0texto, em Latin-1 conforme a especificacao do PNG.
    for key, value in metadata.items():
        text = (
            str(key).encode("latin-1", "replace")
            + b"\x00"
            + str(value).encode("latin-1", "replace")
        )
        out.append(_png_chunk(b"tEXt", text))

    # IDAT: cada scanline recebe um byte de filtro (0 = None) + os pixels da linha.
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        raw.extend(pixels[y * width : (y + 1) * width])
    out.append(_png_chunk(b"IDAT", zlib.compress(bytes(raw), 9)))

    out.append(_png_chunk(b"IEND", b""))
    return b"".join(out)


def _vector_to_png(
    f: Sequence[float], width: int, height: int, metadata: Dict[str, Any]
) -> bytes:
    """Converte um vetor reconstruido em PNG (com metadados tEXt), sem Pillow.

    A normalizacao (min-max para 0..255) e feita em Python puro; o PNG e montado
    a mao por `_encode_png_gray`.
    """
    # O vetor f esta em ordem coluna-a-coluna para a imagem (height, width):
    #   pixel(x, y) = f[y + x * height]
    fmin = min(f)
    span = max(f) - fmin
    scale = 255.0 / span if span > 0 else 0.0

    pixels = bytearray(width * height)
    for y in range(height):
        row_off = y * width
        for x in range(width):
            val = (f[y + x * height] - fmin) * scale
            if val < 0.0:
                val = 0.0
            elif val > 255.0:
                val = 255.0
            pixels[row_off + x] = int(val)

    return _encode_png_gray(bytes(pixels), width, height, metadata)


def _resolve_H(payload: Dict[str, Any], model: int) -> Matrix:
    """Resolve e carrega a matriz H (do payload ou dos padroes em ./data)."""
    if payload.get("H_path"):
        return _load_H(payload["H_path"])

    default_path = os.environ.get(f"H_MODEL_{model}_PATH")
    if not default_path:
        for cand in (
            os.path.join("data", f"H-{model}.csv"),
            os.path.join("data", f"H_modelo_{model}.csv"),
        ):
            if os.path.exists(cand):
                default_path = cand
                break
    if not default_path:
        raise FileNotFoundError(
            f"matriz H do modelo {model} nao encontrada em ./data"
        )
    return _load_H(default_path)


def handle_reconstruct(payload: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    """Executa a reconstrucao e devolve (status_http, corpo_json)."""
    algorithm: str = str(payload.get("algorithm", "cgnr")).lower()
    model: int = int(payload.get("model", 1))
    apply_gain: bool = bool(payload.get("apply_gain", True))

    if model not in MODEL_CONFIG:
        return 400, {"error": f"modelo invalido: {model}"}
    cfg = MODEL_CONFIG[model]
    S, N = cfg["S"], cfg["N"]
    width, height = cfg["size"]

    g_raw = payload.get("g")
    if g_raw is None:
        return 400, {"error": "campo 'g' ausente"}
    g: List[float] = [float(x) for x in g_raw]

    try:
        H = _resolve_H(payload, model)
    except FileNotFoundError as exc:
        return 500, {"error": str(exc)}

    # Ganho de sinal do enunciado (signal_gain.py). Aplicado so quando o sinal
    # chega bruto; sinais que ja vem com ganho passam apply_gain=False.
    if apply_gain:
        try:
            g = apply_signal_gain(g, S=S, N=N)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("Falha no ganho de sinal: %s", exc)

    # Parametros do enunciado (params.py), recalculados do zero a cada requisicao:
    #   c = ||H^T H||_2  e  lambda = max(abs(H^T g)) * 0.10
    c_reduction = reduction_factor(H)
    lambda_reg = regularization_lambda(H, g)

    # started_at / finished_at cercam APENAS a reconstrucao (2 dos metadados
    # obrigatorios). Despacho para o algoritmo escolhido (enunciado, "Algoritmo 1").
    # cpu0: tempo de CPU (user+sys) do processo, para medir a CPU consumida.
    started_at = datetime.now(timezone.utc)
    cpu0 = time.process_time()

    if algorithm == "cgnr":
        f, n_iter, tempo = cgnr(H, g)
    elif algorithm == "cgne":
        f, n_iter, tempo = cgne(H, g)
    else:
        return 400, {"error": f"algoritmo invalido: {algorithm}"}

    cpu_reconstrucao = time.process_time() - cpu0  # CPU gasta na reconstrucao (s)
    finished_at = datetime.now(timezone.utc)
    mem_pico_mb = _peak_rss_mb()  # pico de RSS do processo ate aqui (MB)

    # Metadados obrigatorios do enunciado ("Requisitos nao funcionais"), gravados
    # no PNG (chunks tEXt) e tambem devolvidos no JSON:
    #   algorithm  -> identificacao do algoritmo
    #   started_at -> data/hora de inicio da reconstrucao
    #   finished_at-> data/hora de termino da reconstrucao
    #   size       -> tamanho em pixels
    #   iterations -> numero de iteracoes executadas
    # (reduction_factor e lambda_reg sao extras uteis para o relatorio.)
    metadata = {
        "algorithm": algorithm.upper(),
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "size": f"{width}x{height}",
        "iterations": n_iter,
        "reduction_factor": f"{c_reduction:.6g}",
        "lambda_reg": f"{lambda_reg:.6g}",
        "server": "python",
    }

    png_bytes = _vector_to_png(f, width, height, metadata)
    image_b64 = base64.b64encode(png_bytes).decode("ascii")

    LOG.info(
        "reconstruct ok algo=%s model=%d iter=%d tempo=%.4fs cpu=%.4fs mem=%.1fMB",
        algorithm,
        model,
        n_iter,
        tempo,
        cpu_reconstrucao,
        mem_pico_mb,
    )

    return 200, {
        "algorithm": algorithm.upper(),
        "image_base64": image_b64,
        "width": width,
        "height": height,
        "n_iter": n_iter,
        "tempo_reconstrucao_s": tempo,
        "cpu_reconstrucao_s": cpu_reconstrucao,
        "memoria_pico_mb": mem_pico_mb,
        "reduction_factor": c_reduction,
        "lambda_reg": lambda_reg,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "server": "python",
    }


class ReconstructHandler(BaseHTTPRequestHandler):
    """Handler HTTP baseado apenas na stdlib (http.server)."""

    def _send_json(self, status: int, obj: Dict[str, Any]) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (nome exigido pela stdlib)
        if self.path == "/health":
            self._send_json(200, {"status": "ok", "server": "python"})
        else:
            self._send_json(404, {"error": "nao encontrado"})

    def do_POST(self) -> None:  # noqa: N802 (nome exigido pela stdlib)
        if self.path != "/reconstruct":
            self._send_json(404, {"error": "nao encontrado"})
            return

        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError as exc:
            self._send_json(400, {"error": f"json invalido: {exc}"})
            return

        try:
            status, body = handle_reconstruct(payload)
        except Exception as exc:  # noqa: BLE001
            LOG.exception("erro inesperado na reconstrucao")
            self._send_json(500, {"error": f"erro interno: {exc}"})
            return
        self._send_json(status, body)

    def log_message(self, *args: Any) -> None:
        # Silencia o log de acesso padrao do http.server; usamos o logging acima.
        pass


def main() -> int:
    port = int(os.environ.get("PORT", 5001))
    LOG.info("Servidor interpretado iniciando na porta %d", port)
    httpd = ThreadingHTTPServer(("0.0.0.0", port), ReconstructHandler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        LOG.info("Servidor encerrado pelo usuario.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
