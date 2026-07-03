// Package main — Algebra linear em Go puro, sem gonum.
//
// Todos os "calculos" da reconstrucao (produto matriz-vetor, produto da
// transposta por vetor, produto interno, norma, raiz quadrada e valor absoluto)
// sao implementados aqui manualmente. NENHUMA biblioteca e utilizada — nem
// mesmo o pacote `math`. A matriz e guardada de forma densa num unico slice em
// ordem row-major:
//
//	H[i][j] == Data[i*Cols + j]
package main

// Matrix e uma matriz densa de float64 (row-major).
type Matrix struct {
	Data []float64
	Rows int
	Cols int
}

// NewMatrix cria uma matriz a partir de um slice plano row-major.
func NewMatrix(rows, cols int, data []float64) *Matrix {
	return &Matrix{Data: data, Rows: rows, Cols: cols}
}

// Dims devolve (linhas, colunas).
func (m *Matrix) Dims() (int, int) { return m.Rows, m.Cols }

// MatVec calcula H * x (vetor de tamanho Rows).
func (m *Matrix) MatVec(x []float64) []float64 {
	out := make([]float64, m.Rows)
	data := m.Data
	cols := m.Cols
	base := 0
	for i := 0; i < m.Rows; i++ {
		var s float64
		for j := 0; j < cols; j++ {
			s += data[base+j] * x[j]
		}
		out[i] = s
		base += cols
	}
	return out
}

// TMatVec calcula H^T * y (vetor de tamanho Cols).
func (m *Matrix) TMatVec(y []float64) []float64 {
	out := make([]float64, m.Cols)
	data := m.Data
	cols := m.Cols
	base := 0
	for i := 0; i < m.Rows; i++ {
		yi := y[i]
		if yi != 0 {
			for j := 0; j < cols; j++ {
				out[j] += data[base+j] * yi
			}
		}
		base += cols
	}
	return out
}

// Dot calcula o produto interno a . b.
func Dot(a, b []float64) float64 {
	var s float64
	for i := range a {
		s += a[i] * b[i]
	}
	return s
}

// Abs devolve o valor absoluto de x — implementado no proprio codigo (sem math).
func Abs(x float64) float64 {
	if x < 0 {
		return -x
	}
	return x
}

// Sqrt calcula a raiz quadrada por Newton-Raphson, no proprio codigo (sem math).
//
// Resolve x^2 = a iterando x <- (x + a/x) / 2 ate estabilizar. Para a <= 0
// retorna 0 (os usos deste projeto — normas e sqrt(l) do ganho — sao >= 0).
func Sqrt(a float64) float64 {
	if a <= 0 {
		return 0
	}
	x := a
	for i := 0; i < 100; i++ {
		nx := 0.5 * (x + a/x)
		if Abs(nx-x) <= 1e-15*nx {
			return nx
		}
		x = nx
	}
	return x
}

// Norm calcula a norma-2 (euclidiana) de a, usando o Sqrt implementado acima.
func Norm(a []float64) float64 {
	return Sqrt(Dot(a, a))
}
