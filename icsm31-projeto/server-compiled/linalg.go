// Package main — Algebra linear em Go puro, sem gonum.
//
// Todos os "calculos" da reconstrucao (produto matriz-vetor, produto da
// transposta por vetor, produto interno e norma) sao implementados aqui
// manualmente. Nenhuma biblioteca de calculo numerico e utilizada — apenas o
// pacote padrao `math` para a raiz quadrada. A matriz e guardada de forma
// densa num unico slice em ordem row-major:
//
//	H[i][j] == Data[i*Cols + j]
package main

import "math"

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

// Norm calcula a norma-2 (euclidiana) de a.
func Norm(a []float64) float64 {
	return math.Sqrt(Dot(a, a))
}
