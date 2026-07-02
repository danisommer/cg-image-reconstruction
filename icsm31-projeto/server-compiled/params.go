// Package main — Parametros do enunciado (Algoritmos e definicoes), em Go puro.
//
//	c      = ||H^T H||_2              // fator de reducao
//	lambda = max(abs(H^T g)) * 0.10  // coeficiente de regularizacao
//
// Como ||H^T H||_2 = sigma_max(H)^2 (maior autovalor de H^T H), c e obtido
// por iteracao de potencia sobre H^T H, sem montar H^T H nem rodar SVD na
// matriz cheia. Toda a algebra e feita no proprio codigo (ver linalg.go), sem
// gonum. O resultado e cacheado por chave (caminho de H).
package main

import (
	"math"
	"sync"
)

var (
	cCache   = make(map[string]float64)
	cCacheMu sync.RWMutex
)

// ReductionFactor calcula c = ||H^T H||_2 (maior autovalor de H^T H) por
// iteracao de potencia. cacheKey vazio desativa o cache (ex.: H inline).
func ReductionFactor(H *Matrix, cacheKey string) float64 {
	if cacheKey != "" {
		cCacheMu.RLock()
		if v, ok := cCache[cacheKey]; ok {
			cCacheMu.RUnlock()
			return v
		}
		cCacheMu.RUnlock()
	}

	const maxIter = 200
	const tol = 1e-9

	m := H.Cols
	v := make([]float64, m)
	for i := range v {
		// vetor inicial deterministico e nao-nulo
		v[i] = 1.0
	}
	nv := Norm(v)
	if nv == 0 {
		return 0
	}
	for i := range v {
		v[i] /= nv
	}

	eigval := 0.0
	for iter := 0; iter < maxIter; iter++ {
		// w = (H^T H) v
		w := H.TMatVec(H.MatVec(v))
		nw := Norm(w)
		if nw == 0 {
			eigval = 0
			break
		}
		for i := range v {
			v[i] = w[i] / nw
		}
		if math.Abs(nw-eigval) <= tol*nw {
			eigval = nw
			break
		}
		eigval = nw
	}

	if cacheKey != "" {
		cCacheMu.Lock()
		cCache[cacheKey] = eigval
		cCacheMu.Unlock()
	}
	return eigval
}

// RegularizationLambda calcula lambda = max(abs(H^T g)) * 0.10.
func RegularizationLambda(H *Matrix, g []float64) float64 {
	htg := H.TMatVec(g)

	maxAbs := 0.0
	for _, v := range htg {
		if a := math.Abs(v); a > maxAbs {
			maxAbs = a
		}
	}
	return maxAbs * 0.10
}
