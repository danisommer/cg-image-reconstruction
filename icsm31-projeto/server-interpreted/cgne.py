"""
CGNE — Conjugate Gradient Normal Error.
Enunciado: "Algoritmo 1: CGNE".

Toda a algebra linear e implementada no proprio projeto (modulo `linalg`), sem
numpy/scipy.

Siglas do enunciado: g = vetor de sinal, H = matriz de modelo, f = imagem.

Passos (cada linha do laco abaixo esta rotulada com o passo correspondente):
    f0 = 0
    r0 = g - H f0
    p0 = H^T r0
    para i = 0, 1, ... ate convergir:
        alpha_i = (r_i^T r_i) / (p_i^T p_i)
        f_i+1   = f_i + alpha_i p_i
        r_i+1   = r_i - alpha_i H p_i
        beta_i  = (r_i+1^T r_i+1) / (r_i^T r_i)
        p_i+1   = H^T r_i+1 + beta_i p_i

Criterio de parada (enunciado): |epsilon| < 1e-4 OU 10 iteracoes, o que ocorrer
primeiro, com epsilon = ||r_i+1||_2 - ||r_i||_2 ("Calculo do erro").
"""

from __future__ import annotations

import time
from typing import List, Sequence, Tuple

from linalg import Matrix, axpy, dot, fabs, sqrt


def cgne(
    H: Matrix,
    g: Sequence[float],
    max_iter: int = 10,   # enunciado: no maximo 10 iteracoes
    tol: float = 1e-4,     # enunciado: parar quando |epsilon| < 1e-4
) -> Tuple[List[float], int, float]:
    """Reconstrucao por Conjugate Gradient Normal Error.

    Args:
        H: matriz de modelo (linalg.Matrix), shape (S, M).
        g: vetor de sinal, tamanho S.
        max_iter: numero maximo de iteracoes (default 10, conforme enunciado).
        tol: tolerancia do criterio de parada |epsilon| (default 1e-4).

    Returns:
        f: vetor da imagem reconstruida, tamanho M.
        n_iter: numero de iteracoes efetivamente executadas.
        tempo_total: duracao da reconstrucao em segundos.
    """
    t0 = time.perf_counter()

    m = H.cols

    f = [0.0] * m           # f0 = 0
    r = list(g)             # r0 = g - H f0 = g  (pois f0 = 0)
    p = H.rmatvec(r)        # p0 = H^T r0

    r_norm_sq = dot(r, r)             # ||r0||^2
    prev_r_norm = sqrt(r_norm_sq)     # ||r0||_2, base do erro epsilon

    n_iter = 0
    for i in range(max_iter):
        n_iter = i + 1

        p_norm_sq = dot(p, p)
        if p_norm_sq == 0.0:
            break

        alpha = r_norm_sq / p_norm_sq         # alpha_i = (r_i^T r_i) / (p_i^T p_i)

        f = axpy(alpha, p, f)                 # f_i+1 = f_i + alpha_i p_i
        Hp = H.matvec(p)                      # H p_i
        r = axpy(-alpha, Hp, r)               # r_i+1 = r_i - alpha_i H p_i

        new_r_norm_sq = dot(r, r)
        new_r_norm = sqrt(new_r_norm_sq)      # ||r_i+1||_2

        epsilon = new_r_norm - prev_r_norm    # epsilon = ||r_i+1|| - ||r_i||
        if fabs(epsilon) < tol:               # parada: |epsilon| < 1e-4
            break
        prev_r_norm = new_r_norm

        if r_norm_sq == 0.0:
            break
        beta = new_r_norm_sq / r_norm_sq      # beta_i = (r_i+1^T r_i+1) / (r_i^T r_i)

        p = axpy(beta, p, H.rmatvec(r))       # p_i+1 = H^T r_i+1 + beta_i p_i
        r_norm_sq = new_r_norm_sq

    tempo_total = time.perf_counter() - t0
    return f, n_iter, tempo_total
