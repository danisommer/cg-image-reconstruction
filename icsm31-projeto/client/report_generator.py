"""
Gerador de relatorio PDF com as imagens reconstruidas.

As reconstrucoes sao PAREADAS por rodada (request_id) e exibidas LADO A LADO:
a coluna da esquerda mostra a versao interpretada (Python) e a da direita a
versao compilada (Go) para a MESMA imagem (mesmo g, mesmo algoritmo, mesmo
modelo). Como o cliente executa o mesmo plano contra os dois servidores, cada
rodada gera um resultado Python e um resultado Go com o mesmo request_id.

Cada bloco de rodada mostra:
    - Imagem reconstruida (Python | Go)
    - Algoritmo (CGNR ou CGNE), modelo e tamanho em pixels (cabecalho)
    - Numero de iteracoes (Python | Go)
    - Tempo de reconstrucao (Python | Go)
    - Timestamps de inicio e fim (Python | Go)
"""

from __future__ import annotations

import io
from collections import OrderedDict
from dataclasses import dataclass
from typing import Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image as RLImage,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


@dataclass
class ReconstructionResult:
    """Resultado de uma reconstrucao executada por um dos servidores."""

    server: str
    algorithm: str
    width: int
    height: int
    n_iter: int
    tempo_reconstrucao_s: float
    started_at: str
    finished_at: str
    image_png_bytes: bytes
    model: int
    request_id: str
    reduction_factor: float = 0.0
    lambda_reg: float = 0.0


# Largura util em A4 com margens de 2 cm de cada lado (~17 cm). Cada coluna
# (Python | Go) ocupa metade.
_COL_W = 8.0 * cm
_IMG_W = 6.0 * cm


def _pair_by_round(
    results: List[ReconstructionResult],
) -> "OrderedDict[str, Dict[str, ReconstructionResult]]":
    """Agrupa os resultados por rodada (request_id), preservando a ordem.

    Retorna um dict ordenado request_id -> {"python": rec, "go": rec}. A ordem
    das rodadas segue a primeira aparicao no relatorio (o cliente roda a fase
    Python antes da fase Go, entao a ordem acompanha o plano de rodadas).
    """
    rounds: "OrderedDict[str, Dict[str, ReconstructionResult]]" = OrderedDict()
    for r in results:
        rounds.setdefault(r.request_id, {})[r.server.lower()] = r
    return rounds


def _image_flowable(rec: Optional[ReconstructionResult], styles):
    """Devolve a imagem (ou um aviso) como flowable para a celula da coluna."""
    if rec is None:
        return Paragraph("<i>sem resultado</i>", styles["Italic"])
    try:
        img_buf = io.BytesIO(rec.image_png_bytes)
        return RLImage(img_buf, width=_IMG_W, height=_IMG_W, kind="proportional")
    except Exception as exc:  # noqa: BLE001
        return Paragraph(f"<i>Falha ao renderizar: {exc}</i>", styles["Italic"])


def _images_table(
    py: Optional[ReconstructionResult],
    go: Optional[ReconstructionResult],
    styles,
) -> Table:
    """Monta a linha com as duas imagens lado a lado e seus rotulos."""
    header = [
        Paragraph("<b>Python (interpretado)</b>", styles["Normal"]),
        Paragraph("<b>Go (compilado)</b>", styles["Normal"]),
    ]
    imgs = [_image_flowable(py, styles), _image_flowable(go, styles)]
    table = Table([header, imgs], colWidths=[_COL_W, _COL_W])
    table.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOX", (0, 0), (-1, -1), 0.25, colors.grey),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _fmt_time(rec: Optional[ReconstructionResult]) -> str:
    if rec is None:
        return "n/d"
    return f"{rec.tempo_reconstrucao_s:.4f}"


def _fmt_iter(rec: Optional[ReconstructionResult]) -> str:
    return "n/d" if rec is None else str(rec.n_iter)


def _fmt_ts(rec: Optional[ReconstructionResult], attr: str) -> str:
    return "n/d" if rec is None else str(getattr(rec, attr))


def _compare_table(
    py: Optional[ReconstructionResult],
    go: Optional[ReconstructionResult],
) -> Table:
    """Tabela comparativa das metricas por servidor (Metrica | Python | Go)."""
    rows = [
        ["Metrica", "Python (interpretado)", "Go (compilado)"],
        ["Iteracoes", _fmt_iter(py), _fmt_iter(go)],
        ["Tempo (s)", _fmt_time(py), _fmt_time(go)],
        ["Inicio", _fmt_ts(py, "started_at"), _fmt_ts(go, "started_at")],
        ["Termino", _fmt_ts(py, "finished_at"), _fmt_ts(go, "finished_at")],
    ]
    table = Table(rows, colWidths=[3 * cm, 6.5 * cm, 6.5 * cm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#34495e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
                ("BACKGROUND", (0, 1), (0, -1), colors.lightgrey),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _speedup_paragraph(
    py: Optional[ReconstructionResult],
    go: Optional[ReconstructionResult],
    styles,
) -> Optional[Paragraph]:
    """Nota curta indicando qual versao foi mais rapida nesta rodada."""
    if py is None or go is None:
        return None
    pt, gt = py.tempo_reconstrucao_s, go.tempo_reconstrucao_s
    if pt <= 0 or gt <= 0:
        return None
    if gt <= pt:
        factor = pt / gt
        txt = (
            f"Go foi <b>{factor:.2f}x</b> mais rapido nesta imagem "
            f"({gt * 1000:.1f} ms vs {pt * 1000:.1f} ms)."
        )
    else:
        factor = gt / pt
        txt = (
            f"Python foi <b>{factor:.2f}x</b> mais rapido nesta imagem "
            f"({pt * 1000:.1f} ms vs {gt * 1000:.1f} ms)."
        )
    return Paragraph(txt, styles["Italic"])


def generate_report(
    results: List[ReconstructionResult], output_path: str
) -> None:
    """Gera um PDF em 'output_path' com Python e Go LADO A LADO por imagem."""
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title="Relatorio de Reconstrucoes — ICSM31",
    )
    styles = getSampleStyleSheet()
    story = []

    rounds = _pair_by_round(results)

    story.append(
        Paragraph("Relatorio de Reconstrucoes — CGNR / CGNE", styles["Title"])
    )
    story.append(Spacer(1, 0.3 * cm))
    story.append(
        Paragraph(
            f"Imagens (rodadas): <b>{len(rounds)}</b> &nbsp;|&nbsp; "
            f"Reconstrucoes totais: <b>{len(results)}</b> &nbsp;|&nbsp; "
            "Comparacao lado a lado: <b>Python (interpretado)</b> x "
            "<b>Go (compilado)</b>",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 0.6 * cm))

    for i, (request_id, by_server) in enumerate(rounds.items(), start=1):
        py = by_server.get("python")
        go = by_server.get("go")
        rep = py or go  # representante para os campos compartilhados da rodada
        if rep is None:
            continue

        size = f"{rep.width} x {rep.height}"
        block = [
            Paragraph(
                f"<b>#{i}</b> — {rep.algorithm} — Modelo {rep.model} "
                f"({size} px) — req {request_id}",
                styles["Heading3"],
            ),
            Spacer(1, 0.2 * cm),
            _images_table(py, go, styles),
            Spacer(1, 0.3 * cm),
            _compare_table(py, go),
        ]
        speedup = _speedup_paragraph(py, go, styles)
        if speedup is not None:
            block.append(Spacer(1, 0.15 * cm))
            block.append(speedup)

        # KeepTogether evita que uma rodada seja quebrada entre paginas.
        story.append(KeepTogether(block))
        story.append(Spacer(1, 0.8 * cm))

    doc.build(story)
