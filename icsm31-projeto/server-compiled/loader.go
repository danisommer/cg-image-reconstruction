// Package main — Carregamento da matriz H a partir de arquivo CSV, em Go puro.
//
// O servidor Go le a matriz H em formato CSV (linhas = sensores,
// colunas = pixels) e a guarda numa Matrix densa (ver linalg.go), sem gonum.
package main

import (
	"bufio"
	"fmt"
	"log"
	"os"
	"strconv"
	"strings"
	"sync"
)

var (
	hCache   = make(map[string]*Matrix)
	hCacheMu sync.RWMutex
)

// LoadH carrega a matriz H de um arquivo CSV (com cache em memoria).
func LoadH(path string) (*Matrix, error) {
	hCacheMu.RLock()
	if H, ok := hCache[path]; ok {
		hCacheMu.RUnlock()
		return H, nil
	}
	hCacheMu.RUnlock()

	f, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("abrir %s: %w", path, err)
	}
	defer f.Close()

	scanner := bufio.NewScanner(f)
	// matrizes grandes — buffer generoso
	buf := make([]byte, 0, 1024*1024)
	scanner.Buffer(buf, 64*1024*1024)

	var flat []float64
	cols := -1
	rowCount := 0
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}
		fields := strings.FieldsFunc(line, func(r rune) bool {
			return r == ',' || r == ' ' || r == '\t' || r == ';'
		})
		if cols == -1 {
			cols = len(fields)
		} else if len(fields) != cols {
			return nil, fmt.Errorf("colunas inconsistentes na linha %d: %d != %d",
				rowCount+1, len(fields), cols)
		}
		for _, s := range fields {
			v, err := strconv.ParseFloat(s, 64)
			if err != nil {
				return nil, fmt.Errorf("parse '%s' linha %d: %w", s, rowCount+1, err)
			}
			flat = append(flat, v)
		}
		rowCount++
	}
	if err := scanner.Err(); err != nil {
		return nil, fmt.Errorf("leitura: %w", err)
	}
	if rowCount == 0 {
		return nil, fmt.Errorf("arquivo vazio: %s", path)
	}

	H := NewMatrix(rowCount, cols, flat)

	hCacheMu.Lock()
	hCache[path] = H
	hCacheMu.Unlock()

	log.Printf("Matriz H carregada de %s, shape=(%d, %d)", path, H.Rows, H.Cols)
	return H, nil
}
