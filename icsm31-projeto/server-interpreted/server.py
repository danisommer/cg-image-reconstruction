"""
Servidor HTTP interpretado (Flask) — porta 5001.

Endpoint:
    POST /reconstruct
        Recebe JSON:
            {
                "g": [...],             # vetor de sinal (lista de floats)
                "H_path": "...",        # opcional — caminho local p/ matriz cacheada
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
"""

from __future__ import annotations

import base64
import io
import logging
import os
import sys
from datetime import datetime, timezone
from typing import List, Optional, Sequence

from flask import Flask, jsonify, request
from PIL import Image, PngImagePlugin

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

app = Flask(__name__)

MODEL_CONFIG = {
    1: {"S": 794, "N": 64, "size": (60, 60)},
    2: {"S": 436, "N": 64, "size": (30, 30)},
}

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


def _vector_to_png(
    f: Sequence[float], width: int, height: int, metadata: dict
) -> bytes:
    """Converte um vetor reconstruido em um PNG (com metadados tEXt).

    A normalizacao (min-max para 0..255) e feita em Python puro; o Pillow e
    usado apenas para serializar o PNG e gravar os metadados tEXt.
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

    img = Image.frombytes("L", (width, height), bytes(pixels))

    info = PngImagePlugin.PngInfo()
    for k, v in metadata.items():
        info.add_text(str(k), str(v))

    buf = io.BytesIO()
    img.save(buf, format="PNG", pnginfo=info)
    return buf.getvalue()


@app.get("/health")
def health() -> tuple:
    return jsonify({"status": "ok", "server": "python"}), 200


@app.post("/reconstruct")
def reconstruct() -> tuple:
    payload = request.get_json(force=True, silent=False)

    algorithm: str = str(payload.get("algorithm", "cgnr")).lower()
    model: int = int(payload.get("model", 1))
    apply_gain: bool = bool(payload.get("apply_gain", True))

    if model not in MODEL_CONFIG:
        return jsonify({"error": f"modelo invalido: {model}"}), 400
    cfg = MODEL_CONFIG[model]
    S, N = cfg["S"], cfg["N"]
    width, height = cfg["size"]

    g_raw = payload.get("g")
    if g_raw is None:
        return jsonify({"error": "campo 'g' ausente"}), 400
    g: List[float] = [float(x) for x in g_raw]

    H: Optional[Matrix] = None
    if "H_path" in payload and payload["H_path"]:
        H = _load_H(payload["H_path"])
    else:
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
            return (
                jsonify({"error": f"matriz H do modelo {model} nao encontrada em ./data"}),
                500,
            )
        H = _load_H(default_path)

    if apply_gain:
        try:
            g = apply_signal_gain(g, S=S, N=N)
        except Exception as exc:
            LOG.warning("Falha no ganho de sinal: %s", exc)

    # Parametros do enunciado (recalculados do zero a cada requisicao):
    #   c = ||H^T H||_2  e  lambda = max(abs(H^T g)) * 0.10
    c_reduction = reduction_factor(H)
    lambda_reg = regularization_lambda(H, g)

    started_at = datetime.now(timezone.utc)

    if algorithm == "cgnr":
        f, n_iter, tempo = cgnr(H, g)
    elif algorithm == "cgne":
        f, n_iter, tempo = cgne(H, g)
    else:
        return jsonify({"error": f"algoritmo invalido: {algorithm}"}), 400

    finished_at = datetime.now(timezone.utc)

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
        "reconstruct ok algo=%s model=%d iter=%d tempo=%.4fs c=%.4g lambda=%.4g",
        algorithm,
        model,
        n_iter,
        tempo,
        c_reduction,
        lambda_reg,
    )

    return (
        jsonify(
            {
                "algorithm": algorithm.upper(),
                "image_base64": image_b64,
                "width": width,
                "height": height,
                "n_iter": n_iter,
                "tempo_reconstrucao_s": tempo,
                "reduction_factor": c_reduction,
                "lambda_reg": lambda_reg,
                "started_at": started_at.isoformat(),
                "finished_at": finished_at.isoformat(),
                "server": "python",
            }
        ),
        200,
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    LOG.info("Servidor interpretado iniciando na porta %d", port)
    try:
        app.run(host="0.0.0.0", port=port, threaded=True)
    except KeyboardInterrupt:
        LOG.info("Servidor encerrado pelo usuario.")
        sys.exit(0)
