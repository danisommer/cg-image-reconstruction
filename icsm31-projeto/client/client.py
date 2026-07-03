"""
Cliente Python — envia sinais g aos servidores, UM DE CADA VEZ, e coleta os
resultados.

Comportamento:
    1. Carrega matrizes H e sinais g do diretorio data/.
    2. Monta as rodadas sorteando algoritmo (cgnr/cgne) e sinal a cada rodada
       (o sinal fixa modelo e ganho aleatoriamente).
    3. Executa TODAS as rodadas contra o PRIMEIRO servidor (sequencialmente).
    4. Entra em modo de espera e pede ao usuario para DERRUBAR o primeiro
       servidor e SUBIR o segundo (os servidores NUNCA rodam em paralelo).
    5. Executa exatamente as MESMAS rodadas contra o segundo servidor
       (mesmo g em cada rodada -> comparacao justa entre implementacoes).
    6. Ao final, gera os relatorios PDF (imagens + comparativo) em reports/.

Uso:
    python client/client.py                       # 5 rodadas aleatorias
    python client/client.py --rounds 20           # 20 rodadas aleatorias
"""

from __future__ import annotations

import argparse
import base64
import logging
import os
import random
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Sequence, Tuple

import requests

from comparative_report import generate_comparative_report
from report_generator import ReconstructionResult, generate_report


@dataclass
class SignalFile:
    """Sinal de teste pronto para envio."""

    path: str
    apply_gain: bool  # True se o sinal e bruto e precisa de ganho
    model: int  # modelo (1 ou 2) ao qual o sinal pertence


@dataclass
class RoundSpec:
    """Descricao imutavel de uma rodada — reaproveitada por cada servidor."""

    round_idx: int
    request_id: str
    algorithm: str
    model: int
    signal: SignalFile
    g: List[float]
    h_path: str


LOG = logging.getLogger("client")
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
)

# Raiz do projeto (icsm31-projeto/), um nivel acima de client/.
# Usada para resolver os defaults de data/ e reports/ independentemente do cwd.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DATA_DIR = os.path.join(PROJECT_ROOT, "data")
DEFAULT_REPORT_DIR = os.path.join(PROJECT_ROOT, "reports")

SERVERS = {
    "python": "http://127.0.0.1:5001/reconstruct",
    "go": "http://127.0.0.1:5002/reconstruct",
}

_SERVER_LABEL = {
    "python": "Python (interpretado, porta 5001)",
    "go": "Go (compilado, porta 5002)",
}

# Ordem fixa: interpretado (Python) e depois compilado (Go). Os servidores
# nunca rodam em paralelo — o cliente pausa e pede a troca entre as fases.
SERVER_ORDER = ["python", "go"]

MODEL_CONFIG = {
    1: {"S": 794, "N": 64, "size": (60, 60)},
    2: {"S": 436, "N": 64, "size": (30, 30)},
}


def _load_signal(path: str) -> List[float]:
    """Carrega um vetor de sinal g de arquivo CSV/texto, em Python puro."""
    values: List[float] = []
    with open(path, "r") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            parts = line.split(",") if "," in line else line.split()
            values.extend(float(p) for p in parts)
    return values


def _discover_signals(data_dir: str, model: int) -> List[SignalFile]:
    """Descobre sinais de teste para o modelo dado.

    Convencao dos arquivos do professor:
        Modelo 1 (60x60):
            - G-*.csv          -> sinais brutos          (apply_gain=True)
            - A-60x60-*.csv    -> sinais com ganho ja aplicado (apply_gain=False)
        Modelo 2 (30x30):
            - g-30x30-*.csv    -> sinais brutos          (apply_gain=True)
            - A-30x30-*.csv    -> sinais com ganho ja aplicado (apply_gain=False)
    """
    if not os.path.isdir(data_dir):
        return []

    exts = (".csv", ".txt")
    files = sorted(os.listdir(data_dir))

    def _is_signal(fn: str) -> bool:
        return fn.lower().endswith(exts)

    found: List[SignalFile] = []

    if model == 1:
        for fn in files:
            if not _is_signal(fn):
                continue
            low = fn.lower()
            if low.startswith("g-") and not low.startswith("g-30x30"):
                found.append(SignalFile(os.path.join(data_dir, fn), apply_gain=True, model=1))
            elif low.startswith("a-60x60"):
                found.append(SignalFile(os.path.join(data_dir, fn), apply_gain=False, model=1))
    elif model == 2:
        for fn in files:
            if not _is_signal(fn):
                continue
            low = fn.lower()
            if low.startswith("g-30x30"):
                found.append(SignalFile(os.path.join(data_dir, fn), apply_gain=True, model=2))
            elif low.startswith("a-30x30"):
                found.append(SignalFile(os.path.join(data_dir, fn), apply_gain=False, model=2))
    return found


def _discover_all_signals(data_dir: str) -> List[SignalFile]:
    """Junta os sinais de todos os modelos em um unico pool.

    O cliente sorteia um sinal deste pool a cada rodada, de modo que o
    **modelo** (1 ou 2) e o **ganho** (aplicar ou nao, conforme o sinal e bruto
    ou ja vem com ganho) ficam definidos aleatoriamente, como pede o enunciado.
    """
    pool: List[SignalFile] = []
    for model in (1, 2):
        pool.extend(_discover_signals(data_dir, model))
    return pool


def _resolve_h_path(data_dir: str, model: int) -> Optional[str]:
    """Resolve o caminho do arquivo H (CSV) para o modelo (padroes do professor)."""
    candidates = [
        f"H-{model}.csv",
        f"H_modelo_{model}.csv",
    ]
    for name in candidates:
        p = os.path.join(data_dir, name)
        if os.path.exists(p):
            return os.path.abspath(p)
    return None


def _send_one(
    server_name: str,
    url: str,
    g: Sequence[float],
    algorithm: str,
    model: int,
    h_path: Optional[str],
    request_id: str,
    timeout_s: float,
    apply_gain: bool,
) -> Optional[ReconstructionResult]:
    """Envia uma requisicao para um servidor e devolve o resultado."""
    payload = {
        "g": list(g),
        "algorithm": algorithm,
        "model": model,
        "apply_gain": apply_gain,
    }
    if h_path:
        payload["H_path"] = h_path

    t0 = time.perf_counter()
    try:
        resp = requests.post(url, json=payload, timeout=timeout_s)
    except requests.RequestException as exc:
        LOG.error("[%s][%s] falha de rede: %s", request_id, server_name, exc)
        return None
    rtt = time.perf_counter() - t0

    if resp.status_code != 200:
        LOG.error(
            "[%s][%s] erro HTTP %d: %s",
            request_id,
            server_name,
            resp.status_code,
            resp.text[:200],
        )
        return None

    data = resp.json()
    LOG.info(
        "[%s][%s] algo=%s iter=%d tempo=%.4fs rtt=%.4fs",
        request_id,
        server_name,
        data.get("algorithm"),
        data.get("n_iter"),
        data.get("tempo_reconstrucao_s"),
        rtt,
    )

    try:
        img_bytes = base64.b64decode(data["image_base64"])
    except Exception as exc:  # noqa: BLE001
        LOG.error("[%s][%s] base64 invalido: %s", request_id, server_name, exc)
        return None

    return ReconstructionResult(
        server=str(data.get("server", server_name)),
        algorithm=str(data.get("algorithm", algorithm.upper())),
        width=int(data["width"]),
        height=int(data["height"]),
        n_iter=int(data["n_iter"]),
        tempo_reconstrucao_s=float(data["tempo_reconstrucao_s"]),
        started_at=str(data.get("started_at", "")),
        finished_at=str(data.get("finished_at", "")),
        image_png_bytes=img_bytes,
        model=model,
        request_id=request_id,
        reduction_factor=float(data.get("reduction_factor", 0.0)),
        lambda_reg=float(data.get("lambda_reg", 0.0)),
    )


def _build_jobs(
    signal_pool: List[SignalFile],
    rounds: int,
    rng: random.Random,
) -> List[Tuple[str, SignalFile]]:
    """Monta a lista de jobs (algoritmo, sinal) sorteando a cada rodada.

    Cada job sorteia o algoritmo (cgnr/cgne) e o sinal (o que define modelo e
    ganho aleatoriamente). A lista e montada uma unica vez e depois reproduzida
    identicamente em cada servidor — garantindo comparacao justa.
    """
    jobs = [
        (rng.choice(["cgnr", "cgne"]), rng.choice(signal_pool)) for _ in range(rounds)
    ]
    LOG.info("%d rodada(s) aleatoria(s) por servidor", rounds)
    return jobs


def _build_plan(
    jobs: List[Tuple[str, SignalFile]],
    data_dir: str,
) -> List[RoundSpec]:
    """Converte os jobs num plano fixo (carrega g e resolve H uma unica vez)."""
    plan: List[RoundSpec] = []
    for round_idx, (algorithm, signal) in enumerate(jobs, start=1):
        request_id = uuid.uuid4().hex[:8]
        model = signal.model

        try:
            g = _load_signal(signal.path)
        except Exception as exc:  # noqa: BLE001
            LOG.error("[%s] erro lendo %s: %s", request_id, signal.path, exc)
            continue

        h_path = _resolve_h_path(data_dir, model)
        if h_path is None:
            LOG.warning(
                "[%s] matriz H nao encontrada para modelo %d em %s — pulando",
                request_id,
                model,
                data_dir,
            )
            continue

        plan.append(
            RoundSpec(
                round_idx=round_idx,
                request_id=request_id,
                algorithm=algorithm,
                model=model,
                signal=signal,
                g=g,
                h_path=h_path,
            )
        )
    return plan


def _prompt_server_swap(server_name: str, phase_idx: int, order: List[str]) -> None:
    """Entra em modo de espera ate o usuario confirmar qual servidor esta no ar.

    Antes da primeira fase, pede para subir o primeiro servidor. Entre fases,
    pede explicitamente para DERRUBAR o servidor anterior e SUBIR o proximo —
    os servidores nunca devem rodar simultaneamente.
    """
    label = _SERVER_LABEL.get(server_name, server_name)
    if phase_idx == 0:
        msg = (
            f"\n>>> Suba APENAS o servidor {label}.\n"
            f">>> Lembre-se: os servidores NAO rodam em paralelo — um de cada vez.\n"
            f">>> Pressione ENTER quando ele estiver no ar para iniciar os envios... "
        )
    else:
        prev = order[phase_idx - 1]
        prev_label = _SERVER_LABEL.get(prev, prev)
        msg = (
            f"\n>>> Fase do servidor {prev_label} concluida.\n"
            f">>> Agora DERRUBE o servidor {prev_label} e SUBA o servidor {label}.\n"
            f">>> Pressione ENTER quando a troca estiver feita para continuar... "
        )
    try:
        input(msg)
    except EOFError:
        LOG.warning("Entrada nao interativa (EOF); prosseguindo sem confirmacao.")


def _run_server_phase(
    server_name: str,
    url: str,
    plan: List[RoundSpec],
    timeout_s: float,
    rng: random.Random,
) -> List[ReconstructionResult]:
    """Executa todas as rodadas do plano contra UM servidor, sequencialmente."""
    results: List[ReconstructionResult] = []
    total = len(plan)
    for i, spec in enumerate(plan, start=1):
        LOG.info(
            "[%s][%s] rodada %d/%d modelo=%d algo=%s sinal=%s ganho=%s",
            spec.request_id,
            server_name,
            i,
            total,
            spec.model,
            spec.algorithm,
            os.path.basename(spec.signal.path),
            "sim" if spec.signal.apply_gain else "ja_aplicado",
        )

        rec = _send_one(
            server_name,
            url,
            spec.g,
            spec.algorithm,
            spec.model,
            spec.h_path,
            spec.request_id,
            timeout_s,
            spec.signal.apply_gain,
        )
        if rec is not None:
            results.append(rec)

        # intervalo aleatorio entre rodadas
        if i < total:
            delay = rng.uniform(0.5, 3.0)
            LOG.info("[%s] aguardando %.2fs ate proxima rodada", spec.request_id, delay)
            time.sleep(delay)

    return results


def run_rounds(
    data_dir: str,
    report_dir: str,
    timeout_s: float,
    seed: Optional[int],
    rounds: int,
) -> None:
    rng = random.Random(seed)
    order = SERVER_ORDER

    os.makedirs(report_dir, exist_ok=True)

    # Pool global de sinais: cobre os dois modelos (1 e 2) e os dois tipos de
    # ganho (aplicar ou nao). A cada rodada sorteia-se um sinal deste pool.
    signal_pool = _discover_all_signals(data_dir)
    if not signal_pool:
        LOG.error("Nenhum sinal encontrado em %s — nada a fazer.", data_dir)
        return

    jobs = _build_jobs(signal_pool, rounds, rng)
    plan = _build_plan(jobs, data_dir)
    if not plan:
        LOG.error("Nenhuma rodada valida montada — nada a fazer.")
        return

    all_results: List[ReconstructionResult] = []

    # Executa o mesmo plano contra cada servidor, UM DE CADA VEZ. Entre fases,
    # o cliente espera o usuario derrubar um servidor e subir o proximo.
    for phase_idx, server_name in enumerate(order):
        url = SERVERS.get(server_name)
        if url is None:
            LOG.error("Servidor desconhecido: %s — pulando.", server_name)
            continue

        _prompt_server_swap(server_name, phase_idx, order)

        LOG.info(
            "=== Fase %d/%d — %d rodadas contra o servidor '%s' ===",
            phase_idx + 1,
            len(order),
            len(plan),
            server_name,
        )
        results = _run_server_phase(server_name, url, plan, timeout_s, rng)
        all_results.extend(results)
        LOG.info(
            "Fase do servidor '%s' concluida: %d/%d reconstrucoes coletadas.",
            server_name,
            len(results),
            len(plan),
        )

    if not all_results:
        LOG.warning("Nenhum resultado coletado; relatorio nao sera gerado.")
        return

    # Nome do PDF prioriza a configuracao da execucao; o timestamp vai como
    # sufixo apenas para nao sobrescrever execucoes com a mesma configuracao.
    config_slug = (
        f"aleatorio-{len(plan)}rodada{'s' if len(plan) != 1 else ''}"
        "_1servidor-por-vez"
    )

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(report_dir, f"relatorio_{config_slug}_{ts}.pdf")
    generate_report(all_results, out_path)
    LOG.info("Relatorio gerado em %s (%d reconstrucoes)", out_path, len(all_results))

    comp_path = os.path.join(
        report_dir, f"relatorio_comparativo_{config_slug}_{ts}.pdf"
    )
    generate_comparative_report(all_results, comp_path)
    LOG.info("Relatorio comparativo gerado em %s", comp_path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cliente ICSM31 — reconstrucao de imagens (um servidor por vez)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemplos:\n"
            "  client.py                      # 5 rodadas aleatorias\n"
            "  client.py --rounds 20          # 20 rodadas aleatorias\n"
            "\nO mesmo plano de rodadas e executado contra cada servidor, UM DE\n"
            "CADA VEZ. Entre servidores o cliente pausa e pede a troca — eles\n"
            "nunca rodam em paralelo."
        ),
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=5,
        help="numero de rodadas aleatorias (default 5)",
    )
    parser.add_argument(
        "--data-dir",
        default=DEFAULT_DATA_DIR,
        help="diretorio dos dados (default: <raiz do projeto>/data)",
    )
    parser.add_argument(
        "--report-dir",
        default=DEFAULT_REPORT_DIR,
        help="diretorio de saida (default: <raiz do projeto>/reports)",
    )
    parser.add_argument("--timeout", type=float, default=300.0, help="timeout HTTP em segundos")
    parser.add_argument("--seed", type=int, default=None, help="seed do RNG (opcional)")
    args = parser.parse_args()

    if not os.path.isdir(args.data_dir):
        LOG.error("Diretorio de dados nao existe: %s", args.data_dir)
        return 1
    if args.rounds < 1:
        LOG.error("--rounds deve ser >= 1")
        return 1

    run_rounds(
        data_dir=args.data_dir,
        report_dir=args.report_dir,
        timeout_s=args.timeout,
        seed=args.seed,
        rounds=args.rounds,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
