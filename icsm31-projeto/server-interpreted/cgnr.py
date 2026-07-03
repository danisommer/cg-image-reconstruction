"""
CGNR — Conjugate Gradient Normal Residual.
Enunciado: "Algoritmo 1: CGNR" (Saad 2003, p. 266).

Metodo iterativo que resolve H f = g no sentido de minimos quadrados, adequado
ao problema mal condicionado de reconstrucao de imagem. Toda a algebra linear
(produtos matriz-vetor, produtos internos, normas e combinacoes lineares) e
implementada no proprio projeto (modulo `linalg`), sem numpy/scipy.

Siglas do enunciado: g = vetor de sinal, H = matriz de modelo, f = imagem.

Passos (cada linha do laco abaixo esta rotulada com o passo correspondente):
    f0 = 0
    r0 = g - H f0
    z0 = H^T r0
    p0 = z0
    para i = 0, 1, ... ate convergir:
        w_i     = H p_i
        alpha_i = ||z_i||^2 / ||w_i||^2
        f_i+1   = f_i + alpha_i p_i
        r_i+1   = r_i - alpha_i w_i
        z_i+1   = H^T r_i+1
        beta_i  = ||z_i+1||^2 / ||z_i||^2
        p_i+1   = z_i+1 + beta_i p_i

Criterio de parada (enunciado): |epsilon| < 1e-4 OU 10 iteracoes, o que ocorrer
primeiro, com epsilon = ||r_i+1||_2 - ||r_i||_2 ("Calculo do erro").
"""

from __future__ import annotations

import time
from typing import List, Sequence, Tuple

from linalg import Matrix, axpy, dot, fabs, sqrt


def cgnr(
    H: Matrix,
    g: Sequence[float],
    max_iter: int = 10,   # enunciado: no maximo 10 iteracoes
    tol: float = 1e-4,     # enunciado: parar quando |epsilon| < 1e-4
) -> Tuple[List[float], int, float]:
    """Reconstrucao por Conjugate Gradient Normal Residual.

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
    z = H.rmatvec(r)        # z0 = H^T r0
    p = list(z)             # p0 = z0

    z_norm_sq = dot(z, z)             # ||z0||^2
    prev_r_norm = sqrt(dot(r, r))     # ||r0||_2, base do erro epsilon

    n_iter = 0
    for i in range(max_iter):
        n_iter = i + 1

        w = H.matvec(p)               # w_i = H p_i
        w_norm_sq = dot(w, w)
        if w_norm_sq == 0.0:
            break

        alpha = z_norm_sq / w_norm_sq         # alpha_i = ||z_i||^2 / ||w_i||^2

        f = axpy(alpha, p, f)                 # f_i+1 = f_i + alpha_i p_i
        r = axpy(-alpha, w, r)                # r_i+1 = r_i - alpha_i w_i

        new_r_norm = sqrt(dot(r, r))          # ||r_i+1||_2
        epsilon = new_r_norm - prev_r_norm    # epsilon = ||r_i+1|| - ||r_i||
        if fabs(epsilon) < tol:               # parada: |epsilon| < 1e-4
            break
        prev_r_norm = new_r_norm

        z_next = H.rmatvec(r)                 # z_i+1 = H^T r_i+1
        z_next_norm_sq = dot(z_next, z_next)
        if z_norm_sq == 0.0:
            break
        beta = z_next_norm_sq / z_norm_sq     # beta_i = ||z_i+1||^2 / ||z_i||^2

        p = axpy(beta, p, z_next)             # p_i+1 = z_i+1 + beta_i p_i
        z = z_next
        z_norm_sq = z_next_norm_sq

    tempo_total = time.perf_counter() - t0
    return f, n_iter, tempo_total
