"""
Parametros definidos no enunciado (secao "Algoritmos e definicoes").

    "Calculo do fator de reducao (c)":            c = ||H^T H||_2
    "Calculo do coeficiente de regularizacao (l)": lambda = max(abs(H^T g)) * 0.10

Como ||H^T H||_2 = sigma_max(H)^2 (maior autovalor de H^T H), o fator de
reducao e obtido por iteracao de potencia sobre H^T H, evitando montar a
matriz cheia ou rodar uma SVD completa em H (50816 x 3600). Toda a algebra
e implementada no proprio projeto (modulo `linalg`), sem numpy/scipy.

Sem cache: c e recalculado do zero a cada requisicao (nenhum estado e
reaproveitado entre reconstrucoes).
"""

from __future__ import annotations

from typing import Sequence

from linalg import Matrix, fabs, norm


def reduction_factor(
    H: Matrix,
    max_iter: int = 100,
    tol: float = 1e-4,
) -> float:
    """Enunciado, "Calculo do fator de reducao (c)": c = ||H^T H||_2.

    Obtido como o maior autovalor de H^T H por iteracao de potencia. Usa um
    vetor inicial deterministico (todos 1) — identico ao do servidor Go — para
    que ambas as versoes produzam o mesmo c para a mesma matriz H.

    Args:
        H: matriz de modelo (linalg.Matrix), shape (S, M).
        max_iter: numero maximo de iteracoes de potencia (limite de seguranca).
        tol: tolerancia relativa para parada. Para as matrizes H deste projeto
             o autovalor dominante e pouco separado, entao |dnw|/nw estabiliza
             em ~1e-4 e nao desce muito abaixo disso; 1e-4 e atingido por volta
             da iteracao ~30, dando o mesmo c pratico que dezenas de iteracoes
             extras — apenas muito mais rapido. Mesmo valor no servidor Go.

    Returns:
        c: o valor da norma-2 de H^T H (>= 0).
    """
    m = H.cols
    v = [1.0] * m
    nv = norm(v)
    if nv == 0.0:
        return 0.0
    v = [x / nv for x in v]

    eigval = 0.0
    for _ in range(max_iter):
        # w = (H^T H) v, sem montar H^T H explicitamente
        w = H.rmatvec(H.matvec(v))
        nw = norm(w)
        if nw == 0.0:
            eigval = 0.0
            break
        v = [x / nw for x in w]
        if fabs(nw - eigval) <= tol * nw:
            eigval = nw
            break
        eigval = nw

    return float(eigval)


def regularization_lambda(H: Matrix, g: Sequence[float]) -> float:
    """Enunciado, "Calculo do coeficiente de regularizacao (l)":
    lambda = max(abs(H^T g)) * 0.10.
    """
    htg = H.rmatvec(g)
    max_abs = 0.0
    for value in htg:
        a = fabs(value)
        if a > max_abs:
            max_abs = a
    return max_abs * 0.10
