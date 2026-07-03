// Package main — Ganho de sinal aplicado ao vetor g, sem gonum.
// Enunciado: "Calculo do ganho de sinal (gamma)".
package main

// ApplySignalGain aplica gamma_l = 100 + (1/20)*l*sqrt(l) a cada amostra l
// do sinal, in-place. Espera-se g organizado em ordem column-major: para cada
// sensor c em [0,N), as S amostras consecutivas correspondem a l = 1..S.
// sqrt e implementado no proprio projeto (ver linalg.go), sem o pacote math.
func ApplySignalGain(g []float64, S, N int) {
	n := len(g)
	if n != S*N {
		// sinal 1D de tamanho S (ou menor): aplica gamma amostra a amostra
		for l := 0; l < n && l < S; l++ {
			ll := float64(l + 1)
			gamma := 100.0 + (1.0/20.0)*ll*Sqrt(ll)
			g[l] *= gamma
		}
		return
	}

	for c := 0; c < N; c++ {
		base := c * S
		for l := 0; l < S; l++ {
			ll := float64(l + 1)
			gamma := 100.0 + (1.0/20.0)*ll*Sqrt(ll)
			g[base+l] *= gamma
		}
	}
}
