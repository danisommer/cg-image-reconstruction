// Package main — Ganho de sinal aplicado ao vetor g, em Go puro (sem gonum).
package main

import "math"

// ApplySignalGain aplica gamma_l = 100 + (1/20)*sqrt(l*l) a cada amostra l
// do sinal, in-place. Espera-se g organizado em ordem column-major: para cada
// sensor c em [0,N), as S amostras consecutivas correspondem a l = 1..S.
func ApplySignalGain(g []float64, S, N int) {
	n := len(g)
	if n != S*N {
		// fallback: aplica apenas onde houver l valido
		for l := 0; l < n && l < S; l++ {
			ll := float64(l + 1)
			gamma := 100.0 + (1.0/20.0)*math.Sqrt(ll*ll)
			g[l] *= gamma
		}
		return
	}

	for c := 0; c < N; c++ {
		base := c * S
		for l := 0; l < S; l++ {
			ll := float64(l + 1)
			gamma := 100.0 + (1.0/20.0)*math.Sqrt(ll*ll)
			g[base+l] *= gamma
		}
	}
}
