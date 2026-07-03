## Onde está cada requisito

### Requisitos não funcionais e restrições — metadados obrigatórios em cada imagem

Os metadados são gravados como *chunks* `tEXt` dentro do PNG **e** devolvidos no
JSON da resposta. Ambos os servidores produzem o mesmo conjunto de campos.

| Dado exigido | Versão interpretada (Python) | Versão compilada (Go) |
|--------------|------------------------------|-----------------------|
| Identificação do algoritmo | [`server.py:252`](server-interpreted/server.py#L252) (`"algorithm"`) | [`main.go:306`](server-compiled/main.go#L306) (`"algorithm"`) |
| Data/hora de **início** da reconstrução | [`server.py:229,253`](server-interpreted/server.py#L229) (`started_at`) | [`main.go:275,307`](server-compiled/main.go#L275) (`started_at`) |
| Data/hora de **término** da reconstrução | [`server.py:240,254`](server-interpreted/server.py#L240) (`finished_at`) | [`main.go:294,308`](server-compiled/main.go#L294) (`finished_at`) |
| Tamanho em pixels | [`server.py:255`](server-interpreted/server.py#L255) (`"size"`) | [`main.go:309`](server-compiled/main.go#L309) (`"size"`) |
| Número de iterações executadas | [`server.py:256`](server-interpreted/server.py#L256) (`"iterations"`) | [`main.go:310`](server-compiled/main.go#L310) (`"iterations"`) |

- Montagem do bloco de metadados: [`server.py:251-260`](server-interpreted/server.py#L251-L260) / [`main.go:305-314`](server-compiled/main.go#L305-L314)
- Gravação dos metadados no PNG (encoder próprio, sem Pillow): [`_encode_png_gray` — server.py:114-135](server-interpreted/server.py#L114-L135) / [`addPNGText` — main.go:122-160](server-compiled/main.go#L122-L160)

### Cliente

Aplicação única em [client/client.py](client/client.py).

| Requisito | Onde está |
|-----------|-----------|
| Enviar sequência de sinais `g` em **intervalos de tempo aleatórios** | Atraso sorteado uma vez por rodada em [`client.py:298`](client/client.py#L298) (`rng.uniform(0.5, 3.0)`) e aplicado em [`client.py:395-402`](client/client.py#L395-L402) (`time.sleep`) |
| **Ganho de sinal e modelo definidos aleatoriamente** | O sinal é sorteado do pool em [`_build_jobs` — client.py:260-277](client/client.py#L260-L277); cada sinal já carrega o **modelo** (1 ou 2) e o flag de **ganho** (`apply_gain`), definidos em [`_discover_all_signals` — client.py:157-167](client/client.py#L157-L167) e [`SignalFile` — client.py:42-47](client/client.py#L42-L47). Algoritmo (cgnr/cgne) também sorteado em [`client.py:274`](client/client.py#L274) |
| Gerar **relatório com todas as imagens** (imagem + iterações + tempo) | [client/report_generator.py](client/report_generator.py) — imagem em [`_image_flowable:84-90`](client/report_generator.py#L84-L90), iterações e tempo na tabela comparativa [`_compare_table:149-150`](client/report_generator.py#L149-L150). Chamado em [`client.py:490`](client/client.py#L490). **Python e Go são exibidos lado a lado por imagem** (pareados por `request_id` em [`_pair_by_round:69`](client/report_generator.py#L69), montados em [`_images_table:95`](client/report_generator.py#L95)) |
| **Mesma sequência `g` para as duas versões** | O plano de rodadas é montado **uma única vez** ([`RoundSpec` — client.py:51-66](client/client.py#L51-L66), [`_build_plan` — client.py:280-328](client/client.py#L280-L328)) e reexecutado idêntico contra cada servidor no laço [`client.py:452-474`](client/client.py#L452-L474). Mesmos sinais, mesma ordem e os mesmos atrasos para os dois |

> Restrição de execução: os servidores **nunca rodam em paralelo**. O cliente
> pausa entre as fases e pede a troca — ver [`_prompt_server_swap` — client.py:331-357](client/client.py#L331-L357).

### Servidor

| Requisito | Onde está |
|-----------|-----------|
| Versão em **linguagem interpretada e não fortemente tipada** | [server-interpreted/](server-interpreted/) — Python, só stdlib ([`server.py`](server-interpreted/server.py)) |
| Versão em **linguagem compilada e fortemente tipada** | [server-compiled/](server-compiled/) — Go, só stdlib ([`main.go`](server-compiled/main.go)) |
| **Executar o algoritmo de reconstrução** | CGNR: [`cgnr.py`](server-interpreted/cgnr.py) / [`cgnr.go`](server-compiled/cgnr.go) · CGNE: [`cgne.py`](server-interpreted/cgne.py) / [`cgne.go`](server-compiled/cgne.go). Despacho em [`server.py:232-237`](server-interpreted/server.py#L232-L237) / [`main.go:283-291`](server-compiled/main.go#L283-L291) |
| **Parar quando ε < 1e-4 ou nº de iterações = 10** | Python: `max_iter=10`, `tol=1e-4` ([`cgnr.py:41-42`](server-interpreted/cgnr.py#L41-L42), critério em [`cgnr.py:85`](server-interpreted/cgnr.py#L85); idem [`cgne.py:36-37`](server-interpreted/cgne.py#L36-L37) e [`cgne.py:81`](server-interpreted/cgne.py#L81)). Go: `CGNR(H, g, 10, 1e-4)` em [`main.go:285`](server-compiled/main.go#L285), critério em [`cgnr.go:74`](server-compiled/cgnr.go#L74) |
| **Relatório comparativo** entre as duas versões | [client/comparative_report.py](client/comparative_report.py) — tempos por algoritmo/modelo/servidor ([`_timings_rows:64`](client/comparative_report.py#L64)), speedup ([`_speedup_text:169`](client/comparative_report.py#L169)). Chamado em [`client.py:496`](client/client.py#L496) |
| Objetivo: **mais reconstruções no menor tempo** | Métrica de **throughput** (rec/s) em [`_throughput_rows` — comparative_report.py:100-129](client/comparative_report.py#L100-L129) |

Detalhes auxiliares dos servidores:

- Ganho de sinal `γ_l = 100 + (1/20)·l·√l`: [`signal_gain.py`](server-interpreted/signal_gain.py) / [`signal_gain.go`](server-compiled/signal_gain.go), aplicado em [`server.py:215-219`](server-interpreted/server.py#L215-L219) / [`main.go:256-264`](server-compiled/main.go#L256-L264).
- Parâmetros do enunciado `c = ‖HᵀH‖₂` e `λ = max(|Hᵀg|)·0,10`: [`params.py`](server-interpreted/params.py) / [`params.go`](server-compiled/params.go), calculados em [`server.py:223-224`](server-interpreted/server.py#L223-L224) / [`main.go:268-269`](server-compiled/main.go#L268-L269).
- **Memória e CPU usados** (medidos com a stdlib via `getrusage`): CPU consumida na reconstrução e pico de RSS do processo. Python: [`_peak_rss_mb` — server.py:67](server-interpreted/server.py#L67) e medição em [`server.py:230,241`](server-interpreted/server.py#L230). Go: [`peakRSSMB`/`cpuTimeSeconds` — main.go:64-84](server-compiled/main.go#L64-L84) e medição em [`main.go:276,295`](server-compiled/main.go#L276). Exibidos por imagem em [`report_generator.py:151-152`](client/report_generator.py#L151-L152) e agregados por servidor em [`_resource_rows` — comparative_report.py:132](client/comparative_report.py#L132) (seção "4. Memória e CPU").
- Carregamento da matriz `H` (sem cache, recalculada a cada requisição): [`_load_H` — server.py:79-90](server-interpreted/server.py#L79-L90) / [`LoadH` — loader.go:20](server-compiled/loader.go#L20).
- Servidor HTTP e encoder PNG, ambos só com a stdlib: [`ReconstructHandler` — server.py:292-333](server-interpreted/server.py#L292-L333) / [`main.go`](server-compiled/main.go).
