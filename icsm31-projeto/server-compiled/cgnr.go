// Package main — CGNR (Conjugate Gradient Normal Residual) em Go puro.
//
// Toda a algebra linear e feita no proprio codigo (ver linalg.go), sem gonum.
//
// Algoritmo:
//
//	f0 = 0
//	r0 = g - H * f0
//	z0 = H^T * r0
//	p0 = z0
//	loop:
//	    w_i   = H * p_i
//	    alpha = ||z_i||^2 / ||w_i||^2
//	    f     = f + alpha * p_i
//	    r     = r - alpha * w_i
//	    z_i+1 = H^T * r
//	    beta  = ||z_i+1||^2 / ||z_i||^2
//	    p_i+1 = z_i+1 + beta * p_i
package main

import (
	"math"
	"time"
)

// CGNR resolve H * f = g por gradiente conjugado no residual normal.
//
// Parametros:
//   - H: matriz de modelo (S x M)
//   - g: vetor de sinal (tamanho S)
//   - maxIter: numero maximo de iteracoes
//   - tol: tolerancia para |epsilon|
//
// Retorna:
//   - f: vetor reconstruido (tamanho M)
//   - nIter: numero de iteracoes executadas
//   - tempo: duracao da reconstrucao
func CGNR(H *Matrix, g []float64, maxIter int, tol float64) ([]float64, int, time.Duration) {
	t0 := time.Now()

	m := H.Cols

	f := make([]float64, m)

	// r0 = g - H*f0 = g (pois f0 = 0)
	r := append([]float64(nil), g...)
	z := H.TMatVec(r)
	p := append([]float64(nil), z...)

	zNormSq := Dot(z, z)
	// epsilon = ||r_i+1||_2 - ||r_i||_2 (diferenca de normas, conforme enunciado)
	prevRNorm := math.Sqrt(Dot(r, r))

	nIter := 0
	for i := 0; i < maxIter; i++ {
		nIter = i + 1

		w := H.MatVec(p)
		wNormSq := Dot(w, w)
		if wNormSq == 0 {
			break
		}

		alpha := zNormSq / wNormSq

		for k := range f {
			f[k] += alpha * p[k]
		}
		for k := range r {
			r[k] -= alpha * w[k]
		}

		newRNorm := math.Sqrt(Dot(r, r))
		if math.Abs(newRNorm-prevRNorm) < tol {
			break
		}
		prevRNorm = newRNorm

		zNext := H.TMatVec(r)
		zNextNormSq := Dot(zNext, zNext)

		if zNormSq == 0 {
			break
		}
		beta := zNextNormSq / zNormSq

		// p = zNext + beta * p
		for k := range p {
			p[k] = zNext[k] + beta*p[k]
		}
		zNormSq = zNextNormSq
	}

	return f, nIter, time.Since(t0)
}
