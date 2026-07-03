"""
Relatorio comparativo entre as duas versoes de servidor.
Requisito do enunciado (servidor): "criar um relatorio comparativo analisando
os resultados obtidos com as duas versoes".

Agrega os resultados do servidor interpretado (Python) e do compilado (Go) e
produz um PDF com tabelas de tempo medio, desvio padrao, iteracoes medias,
throughput e o ambiente de execucao. O throughput (rec/s) mede diretamente o
objetivo do trabalho: reconstruir o maior numero de imagens no menor tempo.
Os numeros vem das rodadas reais coletadas em tempo de execucao.
"""

from __future__ import annotations

import platform
import statistics
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Tuple

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from report_generator import ReconstructionResult

# Rotulo amigavel por servidor.
_SERVER_LABEL = {"python": "Python (interpretado)", "go": "Go (compilado)"}


def _fmt(value: float, nd: int = 2) -> str:
    return f"{value:.{nd}f}"


def _env_rows() -> List[List[str]]:
    uname = platform.uname()
    return [
        ["Item", "Valor"],
        ["Sistema operacional", f"{uname.system} {uname.release}"],
        ["Arquitetura", uname.machine],
        ["Processador", platform.processor() or uname.processor or "n/d"],
        ["Python", platform.python_version()],
    ]


def _aggregate(
    results: List[ReconstructionResult],
) -> Dict[Tuple[str, int, str], List[ReconstructionResult]]:
    """Agrupa por (algoritmo, modelo, servidor)."""
    groups: Dict[Tuple[str, int, str], List[ReconstructionResult]] = defaultdict(list)
    for r in results:
        groups[(r.algorithm.upper(), r.model, r.server.lower())].append(r)
    return groups


def _timings_rows(results: List[ReconstructionResult]) -> List[List[str]]:
    groups = _aggregate(results)
    rows = [
        [
            "Algoritmo",
            "Modelo",
            "Servidor",
            "Recons.",
            "Tempo medio (ms)",
            "Desvio (ms)",
            "Iter. medias",
        ]
    ]
    for key in sorted(groups.keys()):
        algo, model, server = key
        recs = groups[key]
        tempos_ms = [r.tempo_reconstrucao_s * 1000.0 for r in recs]
        iters = [r.n_iter for r in recs]
        media = statistics.mean(tempos_ms)
        desvio = statistics.pstdev(tempos_ms) if len(tempos_ms) > 1 else 0.0
        iter_med = statistics.mean(iters)
        label = _SERVER_LABEL.get(server, server)
        rows.append(
            [
                algo,
                str(model),
                label,
                str(len(recs)),
                _fmt(media),
                _fmt(desvio),
                _fmt(iter_med, 1),
            ]
        )
    return rows


def _throughput_rows(results: List[ReconstructionResult]) -> List[List[str]]:
    by_server: Dict[str, List[ReconstructionResult]] = defaultdict(list)
    for r in results:
        by_server[r.server.lower()].append(r)

    rows = [
        [
            "Servidor",
            "Recons.",
            "Tempo total (s)",
            "Tempo medio (ms)",
            "Throughput (rec/s)",
        ]
    ]
    for server in sorted(by_server.keys()):
        recs = by_server[server]
        total_s = sum(r.tempo_reconstrucao_s for r in recs)
        media_ms = (total_s / len(recs)) * 1000.0 if recs else 0.0
        throughput = (len(recs) / total_s) if total_s > 0 else 0.0
        label = _SERVER_LABEL.get(server, server)
        rows.append(
            [
                label,
                str(len(recs)),
                _fmt(total_s, 4),
                _fmt(media_ms),
                _fmt(throughput),
            ]
        )
    return rows


def _resource_rows(results: List[ReconstructionResult]) -> List[List[str]]:
    """Memoria e CPU por servidor.

    CPU = tempo de CPU (user+sys) medido pelo servidor durante a reconstrucao.
    Memoria pico = maior RSS observado no servidor (getrusage ru_maxrss).
    """
    by_server: Dict[str, List[ReconstructionResult]] = defaultdict(list)
    for r in results:
        by_server[r.server.lower()].append(r)

    rows = [
        [
            "Servidor",
            "Recons.",
            "CPU media (ms)",
            "CPU total (s)",
            "Memoria pico (MB)",
        ]
    ]
    for server in sorted(by_server.keys()):
        recs = by_server[server]
        cpu_total = sum(r.cpu_reconstrucao_s for r in recs)
        cpu_media_ms = (cpu_total / len(recs)) * 1000.0 if recs else 0.0
        mem_pico = max((r.memoria_pico_mb for r in recs), default=0.0)
        label = _SERVER_LABEL.get(server, server)
        rows.append(
            [
                label,
                str(len(recs)),
                _fmt(cpu_media_ms),
                _fmt(cpu_total, 4),
                _fmt(mem_pico, 1),
            ]
        )
    return rows


def _speedup_text(results: List[ReconstructionResult]) -> str:
    by_server: Dict[str, List[float]] = defaultdict(list)
    for r in results:
        by_server[r.server.lower()].append(r.tempo_reconstrucao_s)

    if "python" in by_server and "go" in by_server:
        py = statistics.mean(by_server["python"])
        go = statistics.mean(by_server["go"])
        if go > 0:
            ratio = py / go
            faster = "Go (compilado)" if ratio >= 1 else "Python (interpretado)"
            factor = ratio if ratio >= 1 else (1.0 / ratio)
            return (
                f"Em media, <b>{faster}</b> foi <b>{_fmt(factor)}x</b> mais rapido "
                f"por reconstrucao (Python: {_fmt(py * 1000)} ms, "
                f"Go: {_fmt(go * 1000)} ms)."
            )
    return (
        "<i>Dados insuficientes para comparar os dois servidores "
        "(rode com ambos ativos).</i>"
    )


def _styled_table(rows: List[List[str]], col_widths=None) -> Table:
    table = Table(rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#34495e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f4f6")]),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def generate_comparative_report(
    results: List[ReconstructionResult], output_path: str
) -> None:
    """Gera o relatorio comparativo (PDF) com numeros reais."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    n_iter_total = sum(r.n_iter for r in results)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title="Relatorio Comparativo — ICSM31",
    )
    styles = getSampleStyleSheet()
    story = []

    story.append(
        Paragraph("Relatorio Comparativo — CGNR/CGNE: Python vs Go", styles["Title"])
    )
    story.append(Spacer(1, 0.3 * cm))
    story.append(
        Paragraph(
            "ICSM31 — Desenvolvimento Integrado de Sistemas — UTFPR", styles["Normal"]
        )
    )
    story.append(
        Paragraph(
            f"Gerado em: <b>{now}</b> &nbsp;|&nbsp; "
            f"Reconstrucoes: <b>{len(results)}</b> &nbsp;|&nbsp; "
            f"Iteracoes totais: <b>{n_iter_total}</b>",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 0.6 * cm))

    story.append(Paragraph("1. Ambiente de execucao", styles["Heading2"]))
    story.append(Spacer(1, 0.2 * cm))
    story.append(_styled_table(_env_rows(), col_widths=[5 * cm, 10 * cm]))
    story.append(Spacer(1, 0.6 * cm))

    story.append(
        Paragraph("2. Tempos por (algoritmo x modelo x servidor)", styles["Heading2"])
    )
    story.append(Spacer(1, 0.2 * cm))
    story.append(_styled_table(_timings_rows(results)))
    story.append(Spacer(1, 0.2 * cm))
    story.append(
        Paragraph(
            "Tempo de reconstrucao = campo <font face='Courier'>tempo_reconstrucao_s</font> "
            "retornado pelo servidor (nao inclui latencia de rede). "
            "Desvio = desvio padrao populacional.",
            styles["Italic"],
        )
    )
    story.append(Spacer(1, 0.6 * cm))

    story.append(Paragraph("3. Throughput por servidor", styles["Heading2"]))
    story.append(Spacer(1, 0.2 * cm))
    story.append(_styled_table(_throughput_rows(results)))
    story.append(Spacer(1, 0.2 * cm))
    story.append(
        Paragraph(
            "Throughput = numero de reconstrucoes / soma dos tempos de reconstrucao "
            "do servidor. O objetivo do trabalho e maximizar reconstrucoes por "
            "unidade de tempo.",
            styles["Italic"],
        )
    )
    story.append(Spacer(1, 0.6 * cm))

    story.append(Paragraph("4. Memoria e CPU por servidor", styles["Heading2"]))
    story.append(Spacer(1, 0.2 * cm))
    story.append(_styled_table(_resource_rows(results)))
    story.append(Spacer(1, 0.2 * cm))
    story.append(
        Paragraph(
            "CPU = tempo de CPU (user+sys) gasto na reconstrucao, medido pelo "
            "servidor (getrusage). Memoria pico = maior RSS do processo servidor "
            "(getrusage ru_maxrss); reflete o custo de carregar a matriz H "
            "(a versao Python ainda cacheia a transposta H^T).",
            styles["Italic"],
        )
    )
    story.append(Spacer(1, 0.6 * cm))

    story.append(Paragraph("5. Sintese", styles["Heading2"]))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(_speedup_text(results), styles["Normal"]))
    story.append(Spacer(1, 0.2 * cm))
    for bullet in (
        "Ambos os servidores executam o mesmo g em cada rodada, garantindo "
        "comparacao justa entre as implementacoes.",
        "O numero de iteracoes tende a ser identico entre Python e Go para o "
        "mesmo par (algoritmo, sinal), pois implementam o mesmo metodo iterativo; "
        "pequenas diferencas vem de arredondamento de ponto flutuante.",
        "O criterio de parada e |epsilon| < 1e-4 ou 10 iteracoes (o que ocorrer primeiro).",
    ):
        story.append(Paragraph(f"• {bullet}", styles["Normal"]))
        story.append(Spacer(1, 0.1 * cm))

    story.append(Spacer(1, 0.5 * cm))
    story.append(
        Paragraph(
            "<i>Relatorio gerado automaticamente por "
            "client/comparative_report.py a partir das rodadas coletadas.</i>",
            styles["Italic"],
        )
    )

    doc.build(story)
