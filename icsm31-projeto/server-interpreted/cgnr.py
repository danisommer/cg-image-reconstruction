"""
CGNR — Conjugate Gradient Normal Residual (Python puro, sem numpy).

Implementacao do algoritmo iterativo para resolver sistemas H * f = g
no sentido de minimos quadrados, em problemas mal condicionados de
reconstrucao de imagens. Toda a algebra linear (produtos matriz-vetor,
produtos internos, normas e combinacoes lineares) e feita no proprio
codigo, via o modulo `linalg`.

Algoritmo:
    f0 = 0
    r0 = g - H * f0
    z0 = H^T * r0
    p0 = z0
    while not convergiu:
        w_i   = H * p_i
        alpha = ||z_i||^2 / ||w_i||^2
        f     = f + alpha * p_i
        r     = r - alpha * w_i
        z_i+1 = H^T * r
        beta  = ||z_i+1||^2 / ||z_i||^2
        p_i+1 = z_i+1 + beta * p_i
"""

from __future__ import annotations

import time
from typing import List, Sequence, Tuple

from linalg import Matrix, axpy, dot


def cgnr(
    H: Matrix,
    g: Sequence[float],
    max_iter: int = 10,
    tol: float = 1e-4,
) -> Tuple[List[float], int, float]:
    """Reconstrucao por Conjugate Gradient Normal Residual.

    Args:
        H: matriz de modelo (linalg.Matrix), shape (S, M).
        g: vetor de sinal, tamanho S.
        max_iter: numero maximo de iteracoes (default 10).
        tol: tolerancia para o criterio de parada |epsilon| (default 1e-4).

    Returns:
        f: vetor da imagem reconstruida, tamanho M.
        n_iter: numero de iteracoes efetivamente executadas.
        tempo_total: duracao da reconstrucao em segundos.
    """
    t0 = time.perf_counter()

    m = H.cols

    f = [0.0] * m
    # r0 = g - H*f0 = g (pois f0 = 0)
    r = list(g)
    z = H.rmatvec(r)
    p = list(z)

    z_norm_sq = dot(z, z)
    # epsilon = ||r_i+1||_2 - ||r_i||_2 (diferenca de normas, conforme enunciado)
    prev_r_norm = dot(r, r) ** 0.5

    n_iter = 0
    for i in range(max_iter):
        n_iter = i + 1

        w = H.matvec(p)
        w_norm_sq = dot(w, w)
        if w_norm_sq == 0.0:
            break

        alpha = z_norm_sq / w_norm_sq

        f = axpy(alpha, p, f)
        r = axpy(-alpha, w, r)

        new_r_norm = dot(r, r) ** 0.5
        epsilon = new_r_norm - prev_r_norm
        if abs(epsilon) < tol:
            break
        prev_r_norm = new_r_norm

        z_next = H.rmatvec(r)
        z_next_norm_sq = dot(z_next, z_next)

        if z_norm_sq == 0.0:
            break

        beta = z_next_norm_sq / z_norm_sq

        p = axpy(beta, p, z_next)  # p = z_next + beta * p
        z = z_next
        z_norm_sq = z_next_norm_sq

    tempo_total = time.perf_counter() - t0
    return f, n_iter, tempo_total
