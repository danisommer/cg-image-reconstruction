"""
Algebra linear em Python puro — sem numpy/scipy.

Todos os "calculos" da reconstrucao (produto matriz-vetor, produto da
transposta por vetor, produto interno, norma e combinacoes lineares) sao
implementados aqui manualmente. Nenhuma biblioteca de calculo numerico e
utilizada: usa-se apenas o modulo `array` da biblioteca padrao como
contêiner denso de doubles (8 bytes por elemento), o que mantem o uso de
memoria viavel mesmo para a matriz H grande (ex.: 50816 x 3600).

A matriz e guardada em ordem row-major num unico `array('d')`:
    H[i][j] == data[i * cols + j]

Desempenho (ainda 100% Python puro, sem libs de calculo):
  - Os produtos internos usam `sum(map(mul, ...))`, que empurra o laco para
    o C do interpretador (map/sum), em vez de um `for` byte a byte.
  - `rmatvec` (H^T @ y) e feito como um matvec sobre a transposta H^T, que e
    construida uma unica vez e cacheada (`_HT`). Assim tanto H @ x quanto
    H^T @ y percorrem linhas contiguas — o caso rapido do padrao acima.
    Custo: uma copia extra da matriz em memoria (aceitavel, e paga so quando
    rmatvec e usado, e os servidores rodam um de cada vez).
"""

from __future__ import annotations

from array import array
from operator import mul
from typing import List, Optional, Sequence, Tuple


class Matrix:
    """Matriz densa de doubles armazenada num array plano (row-major)."""

    __slots__ = ("data", "rows", "cols", "_HT")

    def __init__(self, data: "array", rows: int, cols: int) -> None:
        self.data = data
        self.rows = rows
        self.cols = cols
        # Transposta (row-major) construida sob demanda em _ensure_transpose().
        self._HT: Optional["array"] = None

    @property
    def shape(self) -> Tuple[int, int]:
        return (self.rows, self.cols)

    def matvec(self, x: Sequence[float]) -> List[float]:
        """Retorna H @ x (vetor de tamanho `rows`)."""
        data = self.data
        cols = self.cols
        out = [0.0] * self.rows
        base = 0
        for i in range(self.rows):
            out[i] = sum(map(mul, data[base:base + cols], x))
            base += cols
        return out

    def _ensure_transpose(self) -> "array":
        """Constroi (uma vez) e cacheia H^T em ordem row-major.

        HT[j * rows + i] == H[i][j] == data[i * cols + j]
        """
        if self._HT is not None:
            return self._HT
        data = self.data
        rows = self.rows
        cols = self.cols
        HT = array("d", bytes(8 * rows * cols))
        base = 0
        for i in range(rows):
            # espalha a linha i de H na coluna i de H^T (passo `rows`)
            k = i
            for v in data[base:base + cols]:
                HT[k] = v
                k += rows
            base += cols
        self._HT = HT
        return HT

    def rmatvec(self, y: Sequence[float]) -> List[float]:
        """Retorna H^T @ y (vetor de tamanho `cols`).

        Implementado como um matvec sobre a transposta cacheada H^T.
        """
        HT = self._ensure_transpose()
        rows = self.rows
        out = [0.0] * self.cols
        base = 0
        for j in range(self.cols):
            out[j] = sum(map(mul, HT[base:base + rows], y))
            base += rows
        return out


def dot(a: Sequence[float], b: Sequence[float]) -> float:
    """Produto interno a . b (via map/sum, ainda Python puro)."""
    return sum(map(mul, a, b))


def norm(a: Sequence[float]) -> float:
    """Norma-2 (euclidiana) de a — sqrt via expoente 0.5, sem bibliotecas."""
    return sum(map(mul, a, a)) ** 0.5


def axpy(alpha: float, x: Sequence[float], y: Sequence[float]) -> List[float]:
    """Retorna alpha * x + y (novo vetor)."""
    return [alpha * xi + yi for xi, yi in zip(x, y)]


def sub(a: Sequence[float], b: Sequence[float]) -> List[float]:
    """Retorna a - b (novo vetor)."""
    return [ai - bi for ai, bi in zip(a, b)]


def load_matrix_csv(path: str) -> Matrix:
    """Carrega uma matriz densa de um arquivo CSV/texto, em Python puro.

    Cada linha do arquivo vira uma linha da matriz; os valores podem estar
    separados por virgula (padrao dos dados do professor) ou por espaco.
    """
    data = array("d")
    rows = 0
    cols = 0
    with open(path, "r") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            parts = line.split(",") if "," in line else line.split()
            values = [float(p) for p in parts]
            if cols == 0:
                cols = len(values)
            elif len(values) != cols:
                raise ValueError(
                    f"linha {rows + 1} de {path} tem {len(values)} colunas, "
                    f"esperado {cols}"
                )
            data.extend(values)
            rows += 1
    return Matrix(data, rows, cols)


def load_vector_csv(path: str) -> List[float]:
    """Carrega um vetor (um valor por linha, ou linha unica separada) em Python puro."""
    values: List[float] = []
    with open(path, "r") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            parts = line.split(",") if "," in line else line.split()
            values.extend(float(p) for p in parts)
    return values
