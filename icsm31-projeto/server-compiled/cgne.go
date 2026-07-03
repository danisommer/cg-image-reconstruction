// Package main — CGNE (Conjugate Gradient Normal Error) em Go puro.
//
// Toda a algebra linear e feita no proprio codigo (ver linalg.go), sem gonum.
//
// Algoritmo:
//
//	f0 = 0
//	r0 = g - H * f0
//	p0 = H^T * r0
//	loop:
//	    alpha = (r^T r) / (p^T p)
//	    f     = f + alpha * p
//	    r     = r - alpha * H * p
//	    beta  = (r_new^T r_new) / (r^T r)
//	    p     = H^T * r_new + beta * p
package main

import "time"

// CGNE resolve H * f = g por gradiente conjugado no erro normal.
func CGNE(H *Matrix, g []float64, maxIter int, tol float64) ([]float64, int, time.Duration) {
	t0 := time.Now()

	m := H.Cols

	f := make([]float64, m)

	// r0 = g - H*f0 = g (pois f0 = 0)
	r := append([]float64(nil), g...)
	p := H.TMatVec(r)

	rNormSq := Dot(r, r)
	prevRNorm := Sqrt(rNormSq)

	nIter := 0
	for i := 0; i < maxIter; i++ {
		nIter = i + 1

		pNormSq := Dot(p, p)
		if pNormSq == 0 {
			break
		}
		alpha := rNormSq / pNormSq

		for k := range f {
			f[k] += alpha * p[k]
		}

		Hp := H.MatVec(p)
		for k := range r {
			r[k] -= alpha * Hp[k]
		}

		newRNormSq := Dot(r, r)
		newRNorm := Sqrt(newRNormSq)

		if Abs(newRNorm-prevRNorm) < tol {
			break
		}
		prevRNorm = newRNorm

		if rNormSq == 0 {
			break
		}
		beta := newRNormSq / rNormSq

		HtR := H.TMatVec(r)
		// p = H^T r + beta * p
		for k := range p {
			p[k] = HtR[k] + beta*p[k]
		}

		rNormSq = newRNormSq
	}

	return f, nIter, time.Since(t0)
}
