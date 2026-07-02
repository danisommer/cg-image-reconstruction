"""
Parametros definidos no enunciado (Algoritmos e definicoes) — Python puro.

    c = ||H^T * H||_2              # Fator de reducao
    lambda = max(abs(H^T * g)) * 0.10  # Coeficiente de regularizacao

Como ||H^T H||_2 = sigma_max(H)^2 (maior autovalor de H^T H), o fator de
reducao e obtido por iteracao de potencia sobre H^T H, evitando montar a
matriz cheia ou rodar uma SVD completa em H (50816 x 3600). Toda a algebra
e feita no proprio codigo (modulo `linalg`), sem numpy/scipy. O resultado e
cacheado por caminho de H, pois depende apenas da matriz de modelo.
"""

from __future__ import annotations

from typing import Optional, Sequence

from linalg import Matrix, norm

# Cache do fator de reducao por chave (caminho de H). c depende so de H.
_C_CACHE: dict[str, float] = {}


def reduction_factor(
    H: Matrix,
    cache_key: Optional[str] = None,
    max_iter: int = 200,
    tol: float = 1e-9,
) -> float:
    """Calcula c = ||H^T H||_2 (maior autovalor de H^T H) por iteracao de potencia.

    Usa um vetor inicial deterministico (todos 1) — identico ao do servidor Go —
    para que ambas as versoes produzam o mesmo c para a mesma matriz H.

    Args:
        H: matriz de modelo (linalg.Matrix), shape (S, M).
        cache_key: chave de cache (ex.: caminho do arquivo de H). Se None, nao cacheia.
        max_iter: numero maximo de iteracoes de potencia.
        tol: tolerancia relativa para parada antecipada.

    Returns:
        c: o valor da norma-2 de H^T H (>= 0).
    """
    if cache_key is not None and cache_key in _C_CACHE:
        return _C_CACHE[cache_key]

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
        if abs(nw - eigval) <= tol * nw:
            eigval = nw
            break
        eigval = nw

    c = float(eigval)
    if cache_key is not None:
        _C_CACHE[cache_key] = c
    return c


def regularization_lambda(H: Matrix, g: Sequence[float]) -> float:
    """Calcula lambda = max(abs(H^T * g)) * 0.10."""
    htg = H.rmatvec(g)
    max_abs = 0.0
    for value in htg:
        a = value if value >= 0.0 else -value
        if a > max_abs:
            max_abs = a
    return max_abs * 0.10
