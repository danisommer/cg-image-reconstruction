// Package main — CGNR (Conjugate Gradient Normal Residual).
// Enunciado: "Algoritmo 1: CGNR" (Saad 2003, p. 266).
//
// Metodo iterativo que resolve H f = g no sentido de minimos quadrados. Toda a
// algebra linear e implementada no proprio projeto (ver linalg.go), sem gonum.
// Siglas: g = vetor de sinal, H = matriz de modelo, f = imagem.
//
// Passos (cada linha do laco esta rotulada com o passo correspondente):
//
//	f0 = 0
//	r0 = g - H f0
//	z0 = H^T r0
//	p0 = z0
//	para i = 0, 1, ... ate convergir:
//	    w_i     = H p_i
//	    alpha_i = ||z_i||^2 / ||w_i||^2
//	    f_i+1   = f_i + alpha_i p_i
//	    r_i+1   = r_i - alpha_i w_i
//	    z_i+1   = H^T r_i+1
//	    beta_i  = ||z_i+1||^2 / ||z_i||^2
//	    p_i+1   = z_i+1 + beta_i p_i
package main

import "time"

// CGNR resolve H f = g por gradiente conjugado no residual normal.
//
// Parametros:
//   - H: matriz de modelo (S x M)
//   - g: vetor de sinal (tamanho S)
//   - maxIter: numero maximo de iteracoes (10, conforme enunciado)
//   - tol: tolerancia do criterio de parada |epsilon| (1e-4)
//
// Retorna:
//   - f: vetor reconstruido (tamanho M)
//   - nIter: numero de iteracoes executadas
//   - tempo: duracao da reconstrucao
//
// Criterio de parada (enunciado): |epsilon| < 1e-4 OU maxIter iteracoes, com
// epsilon = ||r_i+1||_2 - ||r_i||_2 ("Calculo do erro").
func CGNR(H *Matrix, g []float64, maxIter int, tol float64) ([]float64, int, time.Duration) {
	t0 := time.Now()

	m := H.Cols

	f := make([]float64, m)           // f0 = 0
	r := append([]float64(nil), g...) // r0 = g - H f0 = g  (f0 = 0)
	z := H.TMatVec(r)                 // z0 = H^T r0
	p := append([]float64(nil), z...) // p0 = z0

	zNormSq := Dot(z, z)         // ||z0||^2
	prevRNorm := Sqrt(Dot(r, r)) // ||r0||_2, base do erro epsilon

	nIter := 0
	for i := 0; i < maxIter; i++ {
		nIter = i + 1

		w := H.MatVec(p) // w_i = H p_i
		wNormSq := Dot(w, w)
		if wNormSq == 0 {
			break
		}

		alpha := zNormSq / wNormSq // alpha_i = ||z_i||^2 / ||w_i||^2

		for k := range f {
			f[k] += alpha * p[k] // f_i+1 = f_i + alpha_i p_i
		}
		for k := range r {
			r[k] -= alpha * w[k] // r_i+1 = r_i - alpha_i w_i
		}

		newRNorm := Sqrt(Dot(r, r))        // ||r_i+1||_2
		if Abs(newRNorm-prevRNorm) < tol { // parada: |epsilon| < 1e-4
			break
		}
		prevRNorm = newRNorm

		zNext := H.TMatVec(r) // z_i+1 = H^T r_i+1
		zNextNormSq := Dot(zNext, zNext)
		if zNormSq == 0 {
			break
		}
		beta := zNextNormSq / zNormSq // beta_i = ||z_i+1||^2 / ||z_i||^2

		for k := range p {
			p[k] = zNext[k] + beta*p[k] // p_i+1 = z_i+1 + beta_i p_i
		}
		zNormSq = zNextNormSq
	}

	return f, nIter, time.Since(t0)
}
