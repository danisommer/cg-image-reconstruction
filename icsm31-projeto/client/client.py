"""
Cliente Python — envia sinais g aos dois servidores e coleta resultados.

Comportamento:
    1. Carrega matrizes H e sinais g do diretorio data/.
    2. Monta os jobs conforme o modo:
         - aleatorio (padrao): sorteia algoritmo (cgnr/cgne) e sinal a cada rodada;
         - percorrer todas (--all): cada algoritmo x cada sinal, repetido --passes vezes.
    3. Envia cada job aos dois servidores (Python:5001 e Go:5002):
         - paralelo (padrao): os dois ao mesmo tempo;
         - serie (--serie): Python, espera, depois Go.
    4. Espera um intervalo aleatorio (0.5 s a 3 s) entre jobs.
    5. Ao final, gera os relatorios PDF (imagens + comparativo) em reports/.

Uso:
    python client/client.py                   # padrao: 10 rodadas aleatorias, paralelo
    python client/client.py --rounds 20       # 20 rodadas aleatorias
    python client/client.py --all             # percorre todas as combinacoes 1 vez
    python client/client.py --all --passes 3  # percorre todas as combinacoes 3 vezes
    python client/client.py --serie           # envia aos servidores em serie
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures as futures
import logging
import os
import random
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import numpy as np
import requests

from comparative_report import generate_comparative_report
from report_generator import ReconstructionResult, generate_report


@dataclass
class SignalFile:
    """Sinal de teste pronto para envio."""

    path: str
    apply_gain: bool  # True se o sinal e bruto e precisa de ganho
    model: int  # modelo (1 ou 2) ao qual o sinal pertence

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

MODEL_CONFIG = {
    1: {"S": 794, "N": 64, "size": (60, 60)},
    2: {"S": 436, "N": 64, "size": (30, 30)},
}


def _load_signal(path: str) -> np.ndarray:
    """Carrega um vetor de sinal g de .npy ou texto."""
    if path.endswith(".npy"):
        return np.load(path).astype(np.float64).ravel()
    return np.loadtxt(path, dtype=np.float64).ravel()


def _discover_signals(data_dir: str, model: int) -> List[SignalFile]:
    """Descobre sinais de teste para o modelo dado.

    Convencao dos arquivos do professor:
        Modelo 1 (60x60):
            - G-*.csv          -> sinais brutos          (apply_gain=True)
            - A-60x60-*.csv    -> sinais com ganho ja aplicado (apply_gain=False)
        Modelo 2 (30x30):
            - g-30x30-*.csv    -> sinais brutos          (apply_gain=True)
            - A-30x30-*.csv    -> sinais com ganho ja aplicado (apply_gain=False)

    Tambem aceita .npy nas mesmas nomenclaturas para quem pre-converter.
    """
    if not os.path.isdir(data_dir):
        return []

    exts = (".csv", ".npy", ".txt")
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
    """Resolve o caminho do arquivo H para o modelo (padroes do professor).

    Procura, em ordem: H-<model>.npy (mais rapido), H-<model>.csv,
    e os nomes alternativos H_modelo_<model>.npy/.csv.
    """
    candidates = [
        f"H-{model}.npy",
        f"H-{model}.csv",
        f"H_modelo_{model}.npy",
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
    g: np.ndarray,
    algorithm: str,
    model: int,
    h_path: Optional[str],
    request_id: str,
    timeout_s: float,
    apply_gain: bool,
) -> Optional[ReconstructionResult]:
    """Envia uma requisicao para um servidor e devolve o resultado."""
    payload = {
        "g": g.tolist(),
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
    sweep_all: bool,
    rounds: int,
    passes: int,
    rng: random.Random,
) -> List[tuple]:
    """Monta a lista de jobs (algoritmo, sinal) conforme o modo escolhido.

    - Modo aleatorio: `rounds` jobs, cada um sorteando algoritmo e sinal.
    - Modo "percorrer todas": todas as combinacoes (cgnr/cgne x cada sinal),
      repetidas `passes` vezes.

    Em ambos os modos, cada job e enviado aos DOIS servidores (Python e Go),
    entao o numero de imagens geradas e o dobro do numero de jobs.
    """
    if sweep_all:
        jobs: List[tuple] = []
        for _ in range(passes):
            for algorithm in ("cgnr", "cgne"):
                for signal in signal_pool:
                    jobs.append((algorithm, signal))
        LOG.info(
            "Modo: PERCORRER TODAS — %d sinais x 2 algoritmos x %d passada(s) = "
            "%d jobs (%d imagens nos 2 servidores)",
            len(signal_pool),
            passes,
            len(jobs),
            len(jobs) * 2,
        )
        return jobs

    jobs = [
        (rng.choice(["cgnr", "cgne"]), rng.choice(signal_pool)) for _ in range(rounds)
    ]
    LOG.info(
        "Modo: ALEATORIO — %d rodada(s) (%d imagens nos 2 servidores)",
        rounds,
        rounds * 2,
    )
    return jobs


def run_rounds(
    data_dir: str,
    report_dir: str,
    timeout_s: float,
    seed: Optional[int],
    sweep_all: bool,
    rounds: int,
    passes: int,
    parallel: bool,
) -> None:
    rng = random.Random(seed)

    os.makedirs(report_dir, exist_ok=True)

    all_results: List[ReconstructionResult] = []

    # Pool global de sinais: cobre os dois modelos (1 e 2) e os dois tipos de
    # ganho (aplicar ou nao). No modo aleatorio sorteia-se daqui; no modo
    # "percorrer todas" usam-se todos.
    signal_pool = _discover_all_signals(data_dir)
    if not signal_pool:
        LOG.error("Nenhum sinal encontrado em %s — nada a fazer.", data_dir)
        return

    jobs = _build_jobs(signal_pool, sweep_all, rounds, passes, rng)
    total = len(jobs)

    LOG.info(
        "Envio aos servidores: %s",
        "PARALELO (Python e Go ao mesmo tempo)"
        if parallel
        else "SERIE (Python, espera, depois Go)",
    )

    # No modo paralelo cada job dispara os 2 servidores ao mesmo tempo (pool de
    # 2 threads). No modo serie nao ha pool: chama-se um servidor de cada vez.
    pool = futures.ThreadPoolExecutor(max_workers=2) if parallel else None
    try:
        for job_idx, (algorithm, signal) in enumerate(jobs, start=1):
            request_id = uuid.uuid4().hex[:8]

            # modelo e ganho vem do sinal do job
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

            LOG.info(
                "[%s] job %d/%d modelo=%d algo=%s sinal=%s ganho=%s",
                request_id,
                job_idx,
                total,
                model,
                algorithm,
                os.path.basename(signal.path),
                "sim" if signal.apply_gain else "ja_aplicado",
            )

            if parallel:
                futs = {
                    pool.submit(
                        _send_one,
                        name,
                        url,
                        g,
                        algorithm,
                        model,
                        h_path,
                        request_id,
                        timeout_s,
                        signal.apply_gain,
                    ): name
                    for name, url in SERVERS.items()
                }
                for fut in futures.as_completed(futs):
                    rec = fut.result()
                    if rec is not None:
                        all_results.append(rec)
            else:
                # serie: um servidor por vez, na ordem (Python depois Go)
                for name, url in SERVERS.items():
                    rec = _send_one(
                        name,
                        url,
                        g,
                        algorithm,
                        model,
                        h_path,
                        request_id,
                        timeout_s,
                        signal.apply_gain,
                    )
                    if rec is not None:
                        all_results.append(rec)

            # intervalo aleatorio entre jobs
            if job_idx < total:
                delay = rng.uniform(0.5, 3.0)
                LOG.info("[%s] aguardando %.2fs ate o proximo job", request_id, delay)
                time.sleep(delay)
    finally:
        if pool is not None:
            pool.shutdown()

    if not all_results:
        LOG.warning("Nenhum resultado coletado; relatorio nao sera gerado.")
        return

    # Nome do PDF prioriza as configuracoes da execucao; o timestamp vai como
    # sufixo apenas para nao sobrescrever execucoes com a mesma configuracao.
    if sweep_all:
        mode_part = f"todas-{passes}passada{'s' if passes != 1 else ''}"
    else:
        mode_part = f"aleatorio-{rounds}rodada{'s' if rounds != 1 else ''}"
    disp_part = "paralelo" if parallel else "serie"
    config_slug = f"{mode_part}_{disp_part}"

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
        description="Cliente ICSM31 — reconstrucao de imagens",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemplos:\n"
            "  client.py                      # padrao: 10 rodadas aleatorias, paralelo\n"
            "  client.py --rounds 20          # 20 rodadas aleatorias\n"
            "  client.py --all                # percorre TODAS as combinacoes 1 vez\n"
            "  client.py --all --passes 3     # percorre TODAS as combinacoes 3 vezes\n"
            "  client.py --serie              # envia aos 2 servidores em serie\n"
            "\nEm qualquer modo cada job vai para os 2 servidores, entao o numero\n"
            "de imagens geradas e o dobro do numero de jobs."
        ),
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=5,
        help="modo aleatorio: numero de rodadas (default 10)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="percorre TODAS as combinacoes (algoritmo x sinal) em vez de sortear",
    )
    parser.add_argument(
        "--passes",
        type=int,
        default=1,
        help="com --all: quantas vezes percorrer todas as combinacoes (default 1)",
    )
    parser.add_argument(
        "--serie",
        action="store_true",
        help="envia a cada servidor em serie (Python, espera, depois Go); "
        "sem a flag, envia aos 2 em paralelo (padrao)",
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
    if args.passes < 1:
        LOG.error("--passes deve ser >= 1")
        return 1

    run_rounds(
        data_dir=args.data_dir,
        report_dir=args.report_dir,
        timeout_s=args.timeout,
        seed=args.seed,
        sweep_all=args.all,
        rounds=args.rounds,
        passes=args.passes,
        parallel=not args.serie,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
