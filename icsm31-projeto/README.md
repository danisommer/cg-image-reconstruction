# ICSM31 — Reconstrução de Imagens (CGNR / CGNE)

Desenvolvimento Integrado de Sistemas — UTFPR.

O projeto reconstrói imagens a partir de sinais `g` usando os algoritmos
iterativos **CGNR** e **CGNE**, comparando **duas implementações de servidor**:
uma interpretada e não fortemente tipada (**Python/Flask**) e outra compilada e
fortemente tipada (**Go**). Um cliente único envia a **mesma** sequência de
sinais para os dois servidores e gera os relatórios finais.

Toda a álgebra linear (produto matriz-vetor, normas, iteração de potência,
`sqrt`/`abs`) é implementada no próprio código, sem numpy/scipy nem bibliotecas
numéricas externas, nos dois servidores.

## Estrutura

| Pasta | Papel |
|-------|-------|
| [client/](client/) | Cliente: envia os sinais e gera os relatórios PDF |
| [server-interpreted/](server-interpreted/) | Servidor **interpretado / fracamente tipado** (Python + Flask), porta 5001 |
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
| Identificação do algoritmo | [`server.py:176`](server-interpreted/server.py#L176) (`"algorithm"`) | [`main.go:256`](server-compiled/main.go#L256) (`"algorithm"`) |
| Data/hora de **início** da reconstrução | [`server.py:164,177`](server-interpreted/server.py#L164) (`started_at`) | [`main.go:236,257`](server-compiled/main.go#L236) (`started_at`) |
| Data/hora de **término** da reconstrução | [`server.py:173,178`](server-interpreted/server.py#L173) (`finished_at`) | [`main.go:253,258`](server-compiled/main.go#L253) (`finished_at`) |
| Tamanho em pixels | [`server.py:179`](server-interpreted/server.py#L179) (`"size"`) | [`main.go:259`](server-compiled/main.go#L259) (`"size"`) |
| Número de iterações executadas | [`server.py:180`](server-interpreted/server.py#L180) (`"iterations"`) | [`main.go:260`](server-compiled/main.go#L260) (`"iterations"`) |

- Montagem do bloco de metadados: [`server.py:175-184`](server-interpreted/server.py#L175-L184) / [`main.go:255-264`](server-compiled/main.go#L255-L264)
- Gravação dos metadados no PNG: [`_vector_to_png` — server.py:100-106](server-interpreted/server.py#L100-L106) / [`addPNGText` — main.go:88-126](server-compiled/main.go#L88-L126)

### Cliente

Aplicação única em [client/client.py](client/client.py).

| Requisito | Onde está |
|-----------|-----------|
| Enviar sequência de sinais `g` em **intervalos de tempo aleatórios** | Atraso sorteado uma vez por rodada em [`client.py:289`](client/client.py#L289) (`rng.uniform(0.5, 3.0)`) e aplicado em [`client.py:387-393`](client/client.py#L387-L393) (`time.sleep`) |
| **Ganho de sinal e modelo definidos aleatoriamente** | O sinal é sorteado do pool em [`_build_jobs` — client.py:256-271](client/client.py#L256-L271); cada sinal já carrega o **modelo** (1 ou 2) e o flag de **ganho** (`apply_gain`), definidos em [`_discover_all_signals` — client.py:157-167](client/client.py#L157-L167) e [`SignalFile` — client.py:41-47](client/client.py#L41-L47). Algoritmo (cgnr/cgne) também sorteado em [`client.py:267-268`](client/client.py#L267-L268) |
| Gerar **relatório com todas as imagens** (imagem + iterações + tempo) | [client/report_generator.py](client/report_generator.py) — imagem em [`_image_flowable:80-88`](client/report_generator.py#L80-L88), iterações e tempo na tabela comparativa [`_compare_table:141-142`](client/report_generator.py#L141-L142). Chamado em [`client.py:462-465`](client/client.py#L462-L465). **Python e Go são exibidos lado a lado por imagem** (pareados por `request_id` em [`_pair_by_round:65`](client/report_generator.py#L65), montados em [`_images_table:91`](client/report_generator.py#L91)) |
| **Mesma sequência `g` para as duas versões** | O plano de rodadas é montado **uma única vez** ([`RoundSpec` — client.py:50-66](client/client.py#L50-L66), [`_build_plan` — client.py:274-319](client/client.py#L274-L319)) e reexecutado idêntico contra cada servidor no laço [`client.py:427-449`](client/client.py#L427-L449). Mesmos sinais, mesma ordem e os mesmos atrasos para os dois |

> Restrição de execução: os servidores **nunca rodam em paralelo**. O cliente
> pausa entre as fases e pede a troca — ver [`_prompt_server_swap` — client.py:322-347](client/client.py#L322-L347).

### Servidor

| Requisito | Onde está |
|-----------|-----------|
| Versão em **linguagem interpretada e não fortemente tipada** | [server-interpreted/](server-interpreted/) — Python + Flask ([`server.py`](server-interpreted/server.py)) |
| Versão em **linguagem compilada e fortemente tipada** | [server-compiled/](server-compiled/) — Go ([`main.go`](server-compiled/main.go)) |
| **Executar o algoritmo de reconstrução** | CGNR: [`cgnr.py`](server-interpreted/cgnr.py) / [`cgnr.go`](server-compiled/cgnr.go) · CGNE: [`cgne.py`](server-interpreted/cgne.py) / [`cgne.go`](server-compiled/cgne.go). Despacho em [`server.py:166-171`](server-interpreted/server.py#L166-L171) / [`main.go:243-251`](server-compiled/main.go#L243-L251) |
| **Parar quando ε < 1e-4 ou nº de iterações = 10** | Python: `max_iter=10`, `tol=1e-4` ([`cgnr.py:37-38`](server-interpreted/cgnr.py#L37-L38), critério em [`cgnr.py:82`](server-interpreted/cgnr.py#L82); idem [`cgne.py:74-77`](server-interpreted/cgne.py#L74-L77)). Go: `CGNR(H, g, 10, 1e-4)` em [`main.go:245-247`](server-compiled/main.go#L245-L247), critério em [`cgnr.go:71`](server-compiled/cgnr.go#L71) |
| **Relatório comparativo** entre as duas versões | [client/comparative_report.py](client/comparative_report.py) — tempos por algoritmo/modelo/servidor ([`_timings_rows:63`](client/comparative_report.py#L63)), speedup ([`_speedup_text:131`](client/comparative_report.py#L131)). Chamado em [`client.py:467-471`](client/client.py#L467-L471) |
| Objetivo: **mais reconstruções no menor tempo** | Métrica de **throughput** (rec/s) em [`_throughput_rows` — comparative_report.py:99-128](client/comparative_report.py#L99-L128) |

Detalhes auxiliares dos servidores:

- Ganho de sinal `γ_l = 100 + (1/20)·l·√l`: [`signal_gain.py`](server-interpreted/signal_gain.py) / [`signal_gain.go`](server-compiled/signal_gain.go), aplicado em [`server.py:153-157`](server-interpreted/server.py#L153-L157) / [`main.go:222-228`](server-compiled/main.go#L222-L228).
- Parâmetros do enunciado `c = ‖HᵀH‖₂` e `λ = max(|Hᵀg|)·0,10`: [`params.py`](server-interpreted/params.py) / [`params.go`](server-compiled/params.go), calculados em [`server.py:161-162`](server-interpreted/server.py#L161-L162) / [`main.go:232-233`](server-compiled/main.go#L232-L233).
- Carregamento da matriz `H` (sem cache, recalculada a cada requisição): [`_load_H` — server.py:59-70](server-interpreted/server.py#L59-L70) / [`LoadH` — loader.go:20](server-compiled/loader.go#L20).

---

## Como executar

```bash
# 1) Servidor interpretado (porta 5001)
cd server-interpreted
pip install -r requirements.txt
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
