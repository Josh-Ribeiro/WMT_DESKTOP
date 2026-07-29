"""WMT documents components."""

from __future__ import annotations

import datetime
import concurrent.futures
import copy
import difflib
import hashlib
import io
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import zipfile
from html import escape, unescape
from pathlib import Path
from typing import Literal
from xml.etree import ElementTree as ET
from uuid import uuid4
from fastapi import Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from .cache import (
    text_value,
)
from ..core.config import (
    TERMS_RESPONSIBILITY_TEMPLATE_PATH,
    TERM_TYPES,
    WORD_XML_NS,
)
from .inventory import (
    collect_machine_info,
)
from .powershell import (
    powershell_executable,
)
from ..schemas import (
    MachineReplacementReportRequest,
)
from ..core.validators import (
    validate_backup_host,
)

def terms_template_path(term_type: str) -> Path:
    entry = TERM_TYPES.get(term_type)
    if not entry:
        raise HTTPException(status_code=400, detail="Unsupported term type")

    path = Path(entry["template"]())
    if term_type == "return" and (not str(path).strip() or str(path) == "."):
        responsibility_path = TERMS_RESPONSIBILITY_TEMPLATE_PATH
        try:
            for candidate in responsibility_path.parent.glob("*.docx"):
                if "DEVOL" in candidate.name.upper():
                    return candidate
        except OSError:
            pass

    if not str(path).strip() or str(path) == ".":
        config_name = "TERMS_RETURN_TEMPLATE_PATH" if term_type == "return" else "TERMS_RESPONSIBILITY_TEMPLATE_PATH"
        raise HTTPException(
            status_code=500,
            detail=f"Template path is not configured. Configure {config_name}.",
        )

    return path


def build_terms_payload(wk: str, employee_name: str = "") -> dict:
    host = validate_backup_host(wk)
    lookup = collect_machine_info(host)

    hostname = lookup.get("hostname") or host
    serial = lookup.get("serial_number") or ""
    model = lookup.get("model") or ""
    manufacturer = lookup.get("manufacturer") or ""
    if not serial or not model or not manufacturer:
        fallback = query_terms_inventory_powershell(host)
        hostname = fallback.get("hostname") or hostname
        serial = serial or fallback.get("serial_number", "")
        model = model or fallback.get("model", "")
        manufacturer = manufacturer or fallback.get("manufacturer", "")

    if lookup.get("error") and not serial:
        raise HTTPException(status_code=502, detail=lookup.get("error") or "Unable to query workstation")

    return {
        "Hostname": hostname,
        "WKS": hostname,
        "SerialNumber": serial,
        "Serial": serial,
        "Modelo": model,
        "Model": model,
        "Marca": manufacturer,
        "Fabricante": manufacturer,
        "EmployeeName": (employee_name or "").strip(),
        "BP": "na",
        "GeneratedAt": datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
    }


def query_terms_inventory_powershell(host: str) -> dict:
    executable = powershell_executable()
    if executable is None:
        return {}
    script = (
        "$ErrorActionPreference='Stop'; "
        f"$ComputerName={json.dumps(host)}; "
        "$bios=Get-CimInstance -ClassName Win32_BIOS -ComputerName $ComputerName; "
        "$cs=Get-CimInstance -ClassName Win32_ComputerSystem -ComputerName $ComputerName; "
        "[pscustomobject]@{ "
        "hostname=if($cs.DNSHostName){$cs.DNSHostName}else{$ComputerName}; "
        "serial_number=[string]$bios.SerialNumber; "
        "model=[string]$cs.Model; "
        "manufacturer=[string]$cs.Manufacturer "
        "} | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            [executable, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        if result.returncode != 0:
            return {}
        payload = json.loads((result.stdout or "{}").strip() or "{}")
        return {
            "hostname": text_value(payload.get("hostname")),
            "serial_number": text_value(payload.get("serial_number")),
            "model": text_value(payload.get("model")),
            "manufacturer": text_value(payload.get("manufacturer")),
        }
    except Exception:
        return {}


def _terms_aliases(key: str) -> set[str]:
    compact = re.sub(r"[^A-Za-z0-9]+", "", key)
    aliases = {key, key.upper(), key.lower(), compact, compact.upper(), compact.lower()}
    if compact:
        aliases.add(compact[0].lower() + compact[1:])
        aliases.add(compact[0].upper() + compact[1:])
    return {item for item in aliases if item}


def term_replacements(data: dict) -> dict[str, str]:
    values = {
        "WKS": data.get("WKS", ""),
        "HOSTNAME": data.get("Hostname", ""),
        "SERIAL": data.get("SerialNumber", ""),
        "SERIALNUMBER": data.get("SerialNumber", ""),
        "SERIAL_NUMBER": data.get("SerialNumber", ""),
        "SERIAL NUMBER": data.get("SerialNumber", ""),
        "serialNumber": data.get("SerialNumber", ""),
        "serial_number": data.get("SerialNumber", ""),
        "MODELO": data.get("Modelo", ""),
        "MODEL": data.get("Model", ""),
        "MARCA": data.get("Marca", ""),
        "FABRICANTE": data.get("Fabricante", ""),
        "NOME_COMPLETO": data.get("EmployeeName", ""),
        "NOME": data.get("EmployeeName", ""),
        "BP": data.get("BP", "na"),
        "DATA_GERACAO": data.get("GeneratedAt", ""),
    }

    replacements: dict[str, str] = {}
    for key, value in values.items():
        text = str(value or "")
        for alias in _terms_aliases(key):
            replacements[f"{{{{{alias}}}}}"] = text
            replacements[f"[[{alias}]]"] = text
            replacements[f"<<{alias}>>"] = text
            replacements[f"${{{alias}}}"] = text

    replacements.update(
        {
            "NOME COMPLETO": str(data.get("EmployeeName") or ""),
            "SERIAL NUMBER": str(data.get("SerialNumber") or ""),
            "SERIALNUMBER": str(data.get("SerialNumber") or ""),
            "SERIAL": str(data.get("SerialNumber") or ""),
            "MODELO": str(data.get("Modelo") or ""),
            "MARCA": str(data.get("Marca") or ""),
            "FABRICANTE": str(data.get("Fabricante") or ""),
        }
    )
    return replacements


def apply_terms_text_replacements(text: str, replacements: dict[str, str]) -> tuple[str, set[str]]:
    matched: set[str] = set()
    replaced = text

    for token, value in replacements.items():
        if token in replaced:
            replaced = replaced.replace(token, str(value or ""))
            matched.add(token)

    degree = r"[°ºÂ]"
    serie = r"S(?:[ée]|Ã©)rie"
    next_label = rf"(?:Cart(?:[ãa]|Ã£)o\s+Ponto:|Departamento:|WKS:|C\.\s*Custo:|Centro\s+de\s+Custo:|Marca:|Modelo:|N\.?\s*{degree}\.?\s*(?:de\s*)?{serie}:|Serial\s*Number:|BP:|Componentes:|$)"
    label_rules = [
        (rf"(Nome:\s*)(?={next_label})", replacements.get("{{NOME_COMPLETO}}", ""), "NOME_COMPLETO"),
        (rf"(WKS:\s*)(?={next_label})", replacements.get("{{WKS}}", ""), "WKS"),
        (rf"(Marca:\s*)(?={next_label})", replacements.get("{{MARCA}}", ""), "MARCA"),
        (rf"(Modelo:\s*)(?={next_label})", replacements.get("{{MODELO}}", ""), "MODELO"),
        (rf"(N\.?\s*{degree}\.?\s*(?:de\s*)?{serie}:\s*)(?={next_label})", replacements.get("{{SERIAL}}", ""), "SERIAL"),
        (rf"(Serial\s*Number:\s*)(?={next_label})", replacements.get("{{SERIAL}}", ""), "SERIAL"),
        (rf"(BP:\s*)(?={next_label})", replacements.get("{{BP}}", "na"), "BP"),
    ]

    for pattern, value, key in label_rules:
        if not value:
            continue

        def fill_label(match: re.Match[str]) -> str:
            matched.add(key)
            prefix = match.group(1)
            if not prefix.endswith(" "):
                prefix = f"{prefix} "
            return f"{prefix}{value} "

        replaced = re.sub(pattern, fill_label, replaced, flags=re.IGNORECASE)

    return replaced, matched


def _redistribute_replaced_text(
    original_parts: list[str],
    replaced: str,
) -> list[str]:
    """Keep unchanged text in its original Word run and style replacements locally."""
    original = "".join(original_parts)
    if original == replaced:
        return original_parts

    boundaries: list[tuple[int, int]] = []
    offset = 0
    for part in original_parts:
        boundaries.append((offset, offset + len(part)))
        offset += len(part)
    output = ["" for _part in original_parts]

    def run_at(position: int) -> int:
        if not boundaries:
            return 0
        for index, (start, end) in enumerate(boundaries):
            if start <= position < end:
                return index
        return len(boundaries) - 1

    def append_original_slice(start: int, end: int) -> None:
        for index, (run_start, run_end) in enumerate(boundaries):
            overlap_start = max(start, run_start)
            overlap_end = min(end, run_end)
            if overlap_start < overlap_end:
                output[index] += original[overlap_start:overlap_end]

    matcher = difflib.SequenceMatcher(a=original, b=replaced, autojunk=False)
    for operation, source_start, source_end, target_start, target_end in matcher.get_opcodes():
        if operation == "equal":
            append_original_slice(source_start, source_end)
        elif operation in {"replace", "insert"}:
            anchor = source_start if source_start < len(original) else source_start - 1
            output[run_at(max(0, anchor))] += replaced[target_start:target_end]
        # A delete intentionally contributes no text.
    return output


def replace_docx_paragraph_tokens(xml: str, replacements: dict[str, str]) -> tuple[str, set[str]]:
    matched: set[str] = set()

    def replace_paragraph(match: re.Match[str]) -> str:
        paragraph = match.group(0)
        text_matches = list(re.finditer(r"(<w:t(?:\s+[^>]*)?>)([\s\S]*?)(</w:t>)", paragraph))
        if not text_matches:
            return paragraph

        combined = "".join(unescape(item.group(2)) for item in text_matches)
        replaced, replacement_matches = apply_terms_text_replacements(combined, replacements)
        matched.update(replacement_matches)

        if replaced == combined:
            return paragraph

        redistributed = _redistribute_replaced_text(
            [unescape(item.group(2)) for item in text_matches],
            replaced,
        )
        output_parts = []
        cursor = 0
        for index, item in enumerate(text_matches):
            output_parts.append(paragraph[cursor:item.start()])
            value = redistributed[index]
            start_tag = item.group(1)
            if value != value.strip() and "xml:space=" not in start_tag:
                start_tag = start_tag[:-1] + ' xml:space="preserve">'
            output_parts.append(
                f"{start_tag}{escape(value, quote=False)}{item.group(3)}"
            )
            cursor = item.end()
        output_parts.append(paragraph[cursor:])
        return "".join(output_parts)

    return re.sub(r"<w:p[\s\S]*?</w:p>", replace_paragraph, xml), matched


def replace_docx_xml_tokens(content: bytes, replacements: dict[str, str]) -> tuple[bytes, set[str]]:
    matched: set[str] = set()
    root = ET.fromstring(content)
    paragraph_tag = f"{{{WORD_XML_NS}}}p"
    text_tag = f"{{{WORD_XML_NS}}}t"

    for paragraph in root.iter(paragraph_tag):
        text_nodes = list(paragraph.iter(text_tag))
        if not text_nodes:
            continue

        combined = "".join(node.text or "" for node in text_nodes)
        replaced, text_matches = apply_terms_text_replacements(combined, replacements)
        if replaced == combined:
            continue

        matched.update(text_matches)
        redistributed = _redistribute_replaced_text(
            [node.text or "" for node in text_nodes],
            replaced,
        )
        for index, node in enumerate(text_nodes):
            node.text = redistributed[index]

    return ET.tostring(root, encoding="utf-8", xml_declaration=True), matched


def validate_docx_xml(docx_bytes: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as archive:
            archive.testzip()
            for name in archive.namelist():
                if not name.endswith(".xml"):
                    continue
                ET.fromstring(archive.read(name))
    except ET.ParseError as exc:
        raise HTTPException(status_code=500, detail=f"Generated DOCX has invalid XML: {exc}")
    except zipfile.BadZipFile:
        raise HTTPException(status_code=500, detail="Generated DOCX is not a valid zip package")


def convert_docx_to_pdf(docx_bytes: bytes, filename_stem: str) -> bytes:
    with tempfile.TemporaryDirectory(prefix="wmt_terms_") as temp_dir:
        temp_path = Path(temp_dir)
        docx_path = temp_path / f"{filename_stem}.docx"
        pdf_path = temp_path / f"{filename_stem}.pdf"
        docx_path.write_bytes(docx_bytes)

        script = (
            "$ErrorActionPreference = 'Stop'; "
            f"$docx = {json.dumps(str(docx_path))}; "
            f"$pdf = {json.dumps(str(pdf_path))}; "
            "$word = $null; $doc = $null; "
            "try { "
            "$word = New-Object -ComObject Word.Application; "
            "$word.Visible = $false; "
            "$word.DisplayAlerts = 0; "
            "$doc = $word.Documents.Open($docx, $false, $true); "
            "$doc.ExportAsFixedFormat($pdf, 17); "
            "} finally { "
            "if ($doc -ne $null) { $doc.Close($false) | Out-Null }; "
            "if ($word -ne $null) { $word.Quit() | Out-Null }; "
            "[GC]::Collect(); [GC]::WaitForPendingFinalizers(); "
            "} "
        )
        executable = powershell_executable()
        if executable is None:
            raise HTTPException(status_code=500, detail="PowerShell not found. Cannot convert DOCX to PDF.")

        result = subprocess.run(
            [executable, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
        )
        if result.returncode != 0 or not pdf_path.exists():
            detail = (result.stderr or result.stdout or "").strip()
            raise HTTPException(
                status_code=500,
                detail=detail or "Microsoft Word could not convert the term to PDF.",
            )

        return pdf_path.read_bytes()


def convert_html_to_pdf(html: str, filename_stem: str) -> bytes:
    with tempfile.TemporaryDirectory(prefix="wmt_report_") as temp_dir:
        temp_path = Path(temp_dir)
        html_path = temp_path / f"{filename_stem}.html"
        pdf_path = temp_path / f"{filename_stem}.pdf"
        html_path.write_text(html, encoding="utf-8")
        script = (
            "$ErrorActionPreference = 'Stop'; "
            f"$source = {json.dumps(str(html_path))}; "
            f"$pdf = {json.dumps(str(pdf_path))}; "
            "$word = $null; $doc = $null; "
            "try { "
            "$word = New-Object -ComObject Word.Application; "
            "$word.Visible = $false; $word.DisplayAlerts = 0; "
            "$doc = $word.Documents.Open($source, $false, $true); "
            "$doc.ExportAsFixedFormat($pdf, 17); "
            "} finally { "
            "if ($doc -ne $null) { $doc.Close($false) | Out-Null }; "
            "if ($word -ne $null) { $word.Quit() | Out-Null }; "
            "[GC]::Collect(); [GC]::WaitForPendingFinalizers(); "
            "} "
        )
        executable = powershell_executable()
        if executable is None:
            raise HTTPException(status_code=500, detail="PowerShell not found. Cannot generate PDF report.")
        result = subprocess.run(
            [executable, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
        )
        if result.returncode != 0 or not pdf_path.exists():
            detail = (result.stderr or result.stdout or "").strip()
            raise HTTPException(status_code=500, detail=detail or "Microsoft Word could not generate the PDF report.")
        return pdf_path.read_bytes()


def simple_text_pdf(title: str, sections: list[tuple[str, list[str]]]) -> bytes:
    lines: list[tuple[str, int]] = [(title, 18)]
    for heading, values in sections:
        lines.append(("", 10))
        lines.append((heading, 13))
        for value in values:
            wrapped = textwrap.wrap(str(value or ""), width=92, break_long_words=False, break_on_hyphens=False) or [""]
            lines.extend((item, 9) for item in wrapped)

    pages: list[list[tuple[str, int]]] = []
    current: list[tuple[str, int]] = []
    used_height = 0
    for line, size in lines:
        line_height = max(13, size + 4)
        if current and used_height + line_height > 720:
            pages.append(current)
            current = []
            used_height = 0
        current.append((line, size))
        used_height += line_height
    if current:
        pages.append(current)

    def pdf_text(value: str) -> bytes:
        encoded = value.encode("cp1252", errors="replace")
        return encoded.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")

    objects: dict[int, bytes] = {}
    page_ids: list[int] = []
    objects[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    for index, page_lines in enumerate(pages):
        page_id = 4 + index * 2
        content_id = page_id + 1
        page_ids.append(page_id)
        stream = bytearray(b"BT\n")
        y = 800
        for line, size in page_lines:
            y -= max(13, size + 4)
            stream.extend(f"/F1 {size} Tf 50 {y} Td (".encode("ascii"))
            stream.extend(pdf_text(line))
            stream.extend(b") Tj\n")
            stream.extend(f"-50 {-y} Td\n".encode("ascii"))
        stream.extend(b"ET")
        objects[content_id] = b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + bytes(stream) + b"\nendstream"
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode("ascii")
    objects[2] = f"<< /Type /Pages /Kids [{' '.join(f'{item} 0 R' for item in page_ids)}] /Count {len(page_ids)} >>".encode("ascii")
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id in range(1, max(objects) + 1):
        offsets.append(len(output))
        output.extend(f"{object_id} 0 obj\n".encode("ascii"))
        output.extend(objects[object_id])
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode("ascii"))
    return bytes(output)


def fallback_term_pdf(payload: dict, employee_name: str) -> bytes:
    return simple_text_pdf(
        "TERMO DE RESPONSABILIDADE DE EQUIPAMENTO",
        [
            ("COLABORADOR", [employee_name or payload.get("Employee Name") or "Nao informado"]),
            (
                "EQUIPAMENTO",
                [
                    f"Hostname: {payload.get('WKS') or payload.get('Hostname') or 'Nao informado'}",
                    f"Fabricante: {payload.get('Brand') or 'Nao informado'}",
                    f"Modelo: {payload.get('Model') or 'Nao informado'}",
                    f"Numero de serie: {payload.get('SerialNumber') or 'Nao informado'}",
                ],
            ),
            (
                "RESPONSABILIDADE",
                [
                    "Declaro o recebimento do equipamento descrito acima em condicoes de uso.",
                    "Comprometo-me a utilizar o equipamento exclusivamente para atividades profissionais, zelar por sua conservacao e comunicar imediatamente qualquer perda, dano ou incidente.",
                    "A devolucao devera ocorrer quando solicitada pela empresa ou no encerramento da relacao de trabalho.",
                ],
            ),
            ("ASSINATURAS", ["Colaborador: ______________________________________", "Data: ____/____/________", "Responsavel TI: ___________________________________"]),
        ],
    )


def machine_replacement_report_html(request: MachineReplacementReportRequest) -> str:
    applications = request.applications[:1000]
    app_rows = "".join(
        "<tr>"
        f"<td>{escape(str(item.get('name') or ''))}</td>"
        f"<td>{escape(str(item.get('source_version') or 'Nao instalado'))}</td>"
        f"<td>{escape(str(item.get('destination_version') or 'Nao instalado'))}</td>"
        f"<td>{escape(str(item.get('action') or 'Verificar'))}</td>"
        "</tr>"
        for item in applications
    )
    if not app_rows:
        app_rows = '<tr><td colspan="4">Nenhuma diferenca de software identificada.</td></tr>'
    profiles = ", ".join(escape(item) for item in request.profiles) or "Nenhum perfil informado"
    generated_at = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 18mm; }}
body {{ font-family: Arial, sans-serif; color: #20242a; font-size: 10pt; }}
h1 {{ color: #1d4ed8; font-size: 23pt; margin: 0 0 4px; }}
h2 {{ color: #1f2937; font-size: 13pt; margin: 22px 0 8px; border-bottom: 2px solid #dbeafe; padding-bottom: 5px; }}
.subtitle {{ color: #6b7280; margin-bottom: 20px; }}
.grid {{ width: 100%; border-collapse: separate; border-spacing: 8px; margin-left: -8px; }}
.grid td {{ width: 50%; background: #f5f7fa; border: 1px solid #dfe3e8; padding: 10px; }}
.label {{ color: #6b7280; font-size: 8pt; text-transform: uppercase; }}
.value {{ font-weight: bold; margin-top: 3px; }}
table.apps {{ width: 100%; border-collapse: collapse; font-size: 8.5pt; }}
.apps th {{ background: #1d4ed8; color: white; text-align: left; padding: 7px; }}
.apps td {{ border: 1px solid #dfe3e8; padding: 7px; vertical-align: top; }}
.status {{ display: inline-block; padding: 4px 9px; border: 1px solid #86efac; background: #f0fdf4; color: #166534; font-weight: bold; }}
.footer {{ margin-top: 28px; color: #6b7280; font-size: 8pt; }}
</style></head><body>
<h1>Relatorio de troca de maquina</h1>
<div class="subtitle">WMT - Gerado em {generated_at}</div>
<table class="grid"><tr>
<td><div class="label">Colaborador</div><div class="value">{escape(request.employee_name or "Nao informado")}</div></td>
<td><div class="label">Tecnico responsavel</div><div class="value">{escape(request.technician or "Nao informado")}</div></td>
</tr><tr>
<td><div class="label">Equipamento de origem</div><div class="value">{escape(request.source)}</div></td>
<td><div class="label">Equipamento de destino</div><div class="value">{escape(request.destination)}</div></td>
</tr></table>
<h2>Migracao de dados</h2>
<p><b>Perfis selecionados:</b> {profiles}</p>
<p><b>Pre-check:</b> {escape(request.precheck_status or "Nao executado")} - {escape(request.precheck_message)}</p>
<p><b>Job:</b> {escape(request.backup_job_id or "Nao informado")} <span class="status">{escape(request.backup_status or "Sem status")}</span></p>
<p><b>Resultado:</b> {escape(request.backup_summary or "Sem resumo retornado")}</p>
<p><b>Validacao final:</b> {escape(request.validation_status or "Pendente")}</p>
<p><b>Termo:</b> {"Gerado" if request.term_generated else "Nao gerado"}</p>
<h2>Aplicativos que exigem atencao no destino</h2>
<table class="apps"><thead><tr><th>Aplicativo</th><th>Origem</th><th>Destino</th><th>Acao</th></tr></thead><tbody>{app_rows}</tbody></table>
<div class="footer">Relatorio produzido automaticamente pelo WMT com base nas informacoes coletadas durante a migracao.</div>
</body></html>"""


def fill_docx_template(template_path: Path, replacements: dict[str, str]) -> tuple[bytes, list[str]]:
    if not template_path.exists():
        raise HTTPException(status_code=500, detail=f"Template not found or inaccessible: {template_path}")

    matched_tokens: set[str] = set()
    expected_tokens: set[str] = set()
    output = io.BytesIO()

    try:
        with zipfile.ZipFile(template_path, "r") as source, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
            for item in source.infolist():
                content = source.read(item.filename)
                should_replace = (
                    item.filename.startswith("word/") and item.filename.endswith(".xml")
                ) or item.filename.startswith("docProps/")

                if should_replace:
                    xml = content.decode("utf-8", errors="ignore")
                    expected_tokens.update(token for token in replacements if token in xml)
                    xml, matches = replace_docx_paragraph_tokens(xml, replacements)
                    matched_tokens.update(matches)
                    content = xml.encode("utf-8")

                target.writestr(item, content)
    except zipfile.BadZipFile:
        raise HTTPException(status_code=500, detail="Template is not a valid .docx file")

    missing_keys = sorted(token.strip("{}[]<>") for token in expected_tokens if token not in matched_tokens)
    docx_bytes = output.getvalue()
    validate_docx_xml(docx_bytes)
    return docx_bytes, missing_keys
