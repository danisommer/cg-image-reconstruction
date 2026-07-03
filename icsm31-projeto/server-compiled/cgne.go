// Package main — CGNE (Conjugate Gradient Normal Error).
// Enunciado: "Algoritmo 1: CGNE".
//
// Toda a algebra linear e implementada no proprio projeto (ver linalg.go), sem
// gonum. Siglas: g = vetor de sinal, H = matriz de modelo, f = imagem.
//
// Passos (cada linha do laco esta rotulada com o passo correspondente):
//
//	f0 = 0
//	r0 = g - H f0
//	p0 = H^T r0
//	para i = 0, 1, ... ate convergir:
//	    alpha_i = (r_i^T r_i) / (p_i^T p_i)
//	    f_i+1   = f_i + alpha_i p_i
//	    r_i+1   = r_i - alpha_i H p_i
//	    beta_i  = (r_i+1^T r_i+1) / (r_i^T r_i)
//	    p_i+1   = H^T r_i+1 + beta_i p_i
//
// Criterio de parada (enunciado): |epsilon| < 1e-4 OU maxIter iteracoes, com
// epsilon = ||r_i+1||_2 - ||r_i||_2 ("Calculo do erro").
package main

import "time"

// CGNE resolve H f = g por gradiente conjugado no erro normal. Mesma assinatura
// e mesmos criterios de parada do CGNR (maxIter=10, tol=1e-4 no enunciado).
func CGNE(H *Matrix, g []float64, maxIter int, tol float64) ([]float64, int, time.Duration) {
	t0 := time.Now()

	m := H.Cols

	f := make([]float64, m)           // f0 = 0
	r := append([]float64(nil), g...) // r0 = g - H f0 = g  (f0 = 0)
	p := H.TMatVec(r)                 // p0 = H^T r0

	rNormSq := Dot(r, r)       // ||r0||^2
	prevRNorm := Sqrt(rNormSq) // ||r0||_2, base do erro epsilon

	nIter := 0
	for i := 0; i < maxIter; i++ {
		nIter = i + 1

		pNormSq := Dot(p, p)
		if pNormSq == 0 {
			break
		}
		alpha := rNormSq / pNormSq // alpha_i = (r_i^T r_i) / (p_i^T p_i)

		for k := range f {
			f[k] += alpha * p[k] // f_i+1 = f_i + alpha_i p_i
		}

		Hp := H.MatVec(p) // H p_i
		for k := range r {
			r[k] -= alpha * Hp[k] // r_i+1 = r_i - alpha_i H p_i
		}

		newRNormSq := Dot(r, r)
		newRNorm := Sqrt(newRNormSq) // ||r_i+1||_2

		if Abs(newRNorm-prevRNorm) < tol { // parada: |epsilon| < 1e-4
			break
		}
		prevRNorm = newRNorm

		if rNormSq == 0 {
			break
		}
		beta := newRNormSq / rNormSq // beta_i = (r_i+1^T r_i+1) / (r_i^T r_i)

		HtR := H.TMatVec(r) // H^T r_i+1
		for k := range p {
			p[k] = HtR[k] + beta*p[k] // p_i+1 = H^T r_i+1 + beta_i p_i
		}

		rNormSq = newRNormSq
	}

	return f, nIter, time.Since(t0)
}
