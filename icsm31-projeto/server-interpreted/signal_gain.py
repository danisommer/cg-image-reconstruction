"""
Ganho de sinal aplicado ao vetor g antes da reconstrucao.
Enunciado: "Calculo do ganho de sinal (gamma)".

Formula:
    for c = 1 .. N:
        for l = 1 .. S:
            gamma_l = 100 + (1/20) * l * sqrt(l)
            g[l, c] = g[l, c] * gamma_l

O vetor g chega achatado em ordem coluna-a-coluna (Fortran): o indice plano
k mapeia para a amostra l = k % S e o sensor c = k // S. Assim basta
multiplicar cada posicao pelo gamma da sua amostra l. sqrt e implementado no
proprio projeto (modulo `linalg`), sem a lib math.
"""

from __future__ import annotations

from typing import List, Sequence

from linalg import sqrt


def apply_signal_gain(g: Sequence[float], S: int, N: int) -> List[float]:
    """Aplica o ganho gamma_l a cada amostra l do sinal.

    Args:
        g: vetor de sinal achatado (tamanho S*N, ordem coluna-a-coluna) ou de
           tamanho S (um unico sensor).
        S: numero de amostras por sensor.
        N: numero de sensores.

    Returns:
        nova lista com o ganho aplicado (mesmo tamanho do input).
    """
    # gamma_l = 100 + (1/20) * l * sqrt(l), para l = 1..S
    gamma = [100.0 + (1.0 / 20.0) * l * sqrt(l) for l in range(1, S + 1)]

    n = len(g)
    if n == S * N:
        # sinal completo (S*N): posicao k pertence a amostra l = k % S
        return [g[k] * gamma[k % S] for k in range(n)]

    # sinal 1D de tamanho S (ou menor): aplica gamma amostra a amostra
    return [g[i] * gamma[i] for i in range(n)]
