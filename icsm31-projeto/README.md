# ICSM31 — Reconstrução de Imagens (CGNR / CGNE)

Desenvolvimento Integrado de Sistemas — UTFPR.

O projeto reconstrói imagens a partir de sinais `g` usando os algoritmos
iterativos **CGNR** e **CGNE**, comparando **duas implementações de servidor**:
uma interpretada e não fortemente tipada (**Python**) e outra compilada e
fortemente tipada (**Go**). Um cliente único envia a **mesma** sequência de
sinais para os dois servidores e gera os relatórios finais.

Toda a álgebra linear (produto matriz-vetor, normas, iteração de potência,
`sqrt`/`abs`) é implementada no próprio código, sem numpy/scipy nem bibliotecas
numéricas externas, nos dois servidores. **Ambos os servidores usam apenas a
biblioteca padrão da sua linguagem** — inclusive o servidor HTTP e a geração do
PNG (o Python usa `http.server` + `zlib`; o Go usa `net/http` + `image/png`).
As únicas dependências de terceiros do projeto estão no cliente e servem só para
o relatório e o transporte HTTP (`reportlab`, `requests`).

## Estrutura

| Pasta | Papel |
|-------|-------|
| [client/](client/) | Cliente: envia os sinais e gera os relatórios PDF |
| [server-interpreted/](server-interpreted/) | Servidor **interpretado / fracamente tipado** (Python, só biblioteca padrão), porta 5001 |
| [server-compiled/](server-compiled/) | Servidor **compilado / fortemente tipado** (Go), porta 5002 |
| [data/](data/) | Matrizes `H` e sinais `g` de teste (padrões do professor) |
| `reports/` | Saída dos relatórios PDF (gerada em tempo de execução) |

---

## Onde está cada requisito

### Requisitos não funcionais e restrições — metadados obrigatórios em cada imagem

Os metadados são gravados como *chunks* `tEXt` dentro do PNG **e** devolvidos no
JSON da resposta. Ambos os servidores produzem o mesmo conjunto de campos.

| Dado exigido | Versão interpretada (Python) | Versão compilada (Go) |
|--------------|------------------------------|-----------------------|
| Identificação do algoritmo | [`server.py:234`](server-interpreted/server.py#L234) (`"algorithm"`) | [`main.go:269`](server-compiled/main.go#L269) (`"algorithm"`) |
| Data/hora de **início** da reconstrução | [`server.py:214,235`](server-interpreted/server.py#L214) (`started_at`) | [`main.go:241,270`](server-compiled/main.go#L241) (`started_at`) |
| Data/hora de **término** da reconstrução | [`server.py:223,236`](server-interpreted/server.py#L223) (`finished_at`) | [`main.go:258,271`](server-compiled/main.go#L258) (`finished_at`) |
| Tamanho em pixels | [`server.py:237`](server-interpreted/server.py#L237) (`"size"`) | [`main.go:272`](server-compiled/main.go#L272) (`"size"`) |
| Número de iterações executadas | [`server.py:238`](server-interpreted/server.py#L238) (`"iterations"`) | [`main.go:273`](server-compiled/main.go#L273) (`"iterations"`) |

- Montagem do bloco de metadados: [`server.py:233-242`](server-interpreted/server.py#L233-L242) / [`main.go:268-277`](server-compiled/main.go#L268-L277)
- Gravação dos metadados no PNG (encoder próprio, sem Pillow): [`_encode_png_gray` — server.py:100-121](server-interpreted/server.py#L100-L121) / [`addPNGText` — main.go:88-126](server-compiled/main.go#L88-L126)

### Cliente

Aplicação única em [client/client.py](client/client.py).

| Requisito | Onde está |
|-----------|-----------|
| Enviar sequência de sinais `g` em **intervalos de tempo aleatórios** | Atraso sorteado uma vez por rodada em [`client.py:294`](client/client.py#L294) (`rng.uniform(0.5, 3.0)`) e aplicado em [`client.py:391-398`](client/client.py#L391-L398) (`time.sleep`) |
| **Ganho de sinal e modelo definidos aleatoriamente** | O sinal é sorteado do pool em [`_build_jobs` — client.py:256-273](client/client.py#L256-L273); cada sinal já carrega o **modelo** (1 ou 2) e o flag de **ganho** (`apply_gain`), definidos em [`_discover_all_signals` — client.py:157-167](client/client.py#L157-L167) e [`SignalFile` — client.py:42-47](client/client.py#L42-L47). Algoritmo (cgnr/cgne) também sorteado em [`client.py:270`](client/client.py#L270) |
| Gerar **relatório com todas as imagens** (imagem + iterações + tempo) | [client/report_generator.py](client/report_generator.py) — imagem em [`_image_flowable:82-88`](client/report_generator.py#L82-L88), iterações e tempo na tabela comparativa [`_compare_table:147-148`](client/report_generator.py#L147-L148). Chamado em [`client.py:490`](client/client.py#L490). **Python e Go são exibidos lado a lado por imagem** (pareados por `request_id` em [`_pair_by_round:67`](client/report_generator.py#L67), montados em [`_images_table:93`](client/report_generator.py#L93)) |
| **Mesma sequência `g` para as duas versões** | O plano de rodadas é montado **uma única vez** ([`RoundSpec` — client.py:51-66](client/client.py#L51-L66), [`_build_plan` — client.py:276-324](client/client.py#L276-L324)) e reexecutado idêntico contra cada servidor no laço [`client.py:448-470`](client/client.py#L448-L470). Mesmos sinais, mesma ordem e os mesmos atrasos para os dois |

> Restrição de execução: os servidores **nunca rodam em paralelo**. O cliente
> pausa entre as fases e pede a troca — ver [`_prompt_server_swap` — client.py:327-353](client/client.py#L327-L353).

### Servidor

| Requisito | Onde está |
|-----------|-----------|
| Versão em **linguagem interpretada e não fortemente tipada** | [server-interpreted/](server-interpreted/) — Python, só stdlib ([`server.py`](server-interpreted/server.py)) |
| Versão em **linguagem compilada e fortemente tipada** | [server-compiled/](server-compiled/) — Go, só stdlib ([`main.go`](server-compiled/main.go)) |
| **Executar o algoritmo de reconstrução** | CGNR: [`cgnr.py`](server-interpreted/cgnr.py) / [`cgnr.go`](server-compiled/cgnr.go) · CGNE: [`cgne.py`](server-interpreted/cgne.py) / [`cgne.go`](server-compiled/cgne.go). Despacho em [`server.py:216-221`](server-interpreted/server.py#L216-L221) / [`main.go:248-256`](server-compiled/main.go#L248-L256) |
| **Parar quando ε < 1e-4 ou nº de iterações = 10** | Python: `max_iter=10`, `tol=1e-4` ([`cgnr.py:41-42`](server-interpreted/cgnr.py#L41-L42), critério em [`cgnr.py:85`](server-interpreted/cgnr.py#L85); idem [`cgne.py:36-37`](server-interpreted/cgne.py#L36-L37) e [`cgne.py:81`](server-interpreted/cgne.py#L81)). Go: `CGNR(H, g, 10, 1e-4)` em [`main.go:250`](server-compiled/main.go#L250), critério em [`cgnr.go:74`](server-compiled/cgnr.go#L74) |
| **Relatório comparativo** entre as duas versões | [client/comparative_report.py](client/comparative_report.py) — tempos por algoritmo/modelo/servidor ([`_timings_rows:64`](client/comparative_report.py#L64)), speedup ([`_speedup_text:132`](client/comparative_report.py#L132)). Chamado em [`client.py:496`](client/client.py#L496) |
| Objetivo: **mais reconstruções no menor tempo** | Métrica de **throughput** (rec/s) em [`_throughput_rows` — comparative_report.py:100-129](client/comparative_report.py#L100-L129) |

Detalhes auxiliares dos servidores:

- Ganho de sinal `γ_l = 100 + (1/20)·l·√l`: [`signal_gain.py`](server-interpreted/signal_gain.py) / [`signal_gain.go`](server-compiled/signal_gain.go), aplicado em [`server.py:201-205`](server-interpreted/server.py#L201-L205) / [`main.go:222-230`](server-compiled/main.go#L222-L230).
- Parâmetros do enunciado `c = ‖HᵀH‖₂` e `λ = max(|Hᵀg|)·0,10`: [`params.py`](server-interpreted/params.py) / [`params.go`](server-compiled/params.go), calculados em [`server.py:209-210`](server-interpreted/server.py#L209-L210) / [`main.go:234-235`](server-compiled/main.go#L234-L235).
- Carregamento da matriz `H` (sem cache, recalculada a cada requisição): [`_load_H` — server.py:65-76](server-interpreted/server.py#L65-L76) / [`LoadH` — loader.go:20](server-compiled/loader.go#L20).
- Servidor HTTP e encoder PNG, ambos só com a stdlib: [`ReconstructHandler` — server.py:272-313](server-interpreted/server.py#L272-L313) / [`main.go`](server-compiled/main.go).

---

## Como executar

```bash
# 1) Servidor interpretado (porta 5001) — só stdlib, sem pip install
cd server-interpreted
python server.py

# 2) Servidor compilado (porta 5002) — SUBIR SÓ APÓS DERRUBAR O PYTHON
cd server-compiled
go build -o server-compiled .
./server-compiled

# 3) Cliente — roda o mesmo plano contra cada servidor, um de cada vez
cd client
pip install -r requirements.txt
python client.py --rounds 20
```

Por padrão o cliente sorteia o tamanho (30x30 ou 60x60) a cada rodada. Para
fixar **todas** as rodadas de uma execução em um único tamanho, use `--size`:

```bash
python client.py --size 30x30 --rounds 20   # todas as rodadas em 30x30 (modelo 2)
python client.py --size 60x60 --rounds 10   # todas as rodadas em 60x60 (modelo 1)
```

O cliente pausa entre as fases pedindo a troca de servidor (eles não rodam em
paralelo). Ao final, os PDFs são gravados em `reports/`:

- `relatorio_*.pdf` — todas as imagens reconstruídas (imagem, iterações, tempo);
- `relatorio_comparativo_*.pdf` — comparação Python × Go.
