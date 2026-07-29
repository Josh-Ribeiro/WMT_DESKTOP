from __future__ import annotations

import datetime
import io
import re
from fastapi import Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi import APIRouter

from ..core.config import TERM_TYPES
from ..core.validators import validate_backup_host
from ..repositories.state import audit
from ..schemas import (
    MachineReplacementReportRequest,
    TermsGenerateRequest,
)
from ..services.auth import require_role
from ..services.documents import (
    build_terms_payload,
    convert_docx_to_pdf,
    fallback_term_pdf,
    fill_docx_template,
    simple_text_pdf,
    term_replacements,
    terms_template_path,
)

router = APIRouter()


@router.get("/api/terms/config")
def terms_config(user: dict = Depends(require_role("admin", "operator"))):
    return {
        "types": [
            {
                "value": key,
                "label": entry["label"],
                "template_path": str(terms_template_path(key)),
                "template_accessible": terms_template_path(key).exists(),
            }
            for key, entry in TERM_TYPES.items()
        ],
        "placeholders": ["WKS", "Hostname", "SerialNumber", "serialNumber", "Serial Number", "Model", "Brand", "Employee Name"],
    }


@router.post("/api/terms/generate")
def terms_generate(request: TermsGenerateRequest, user: dict = Depends(require_role("admin", "operator"))):
    term_entry = TERM_TYPES.get(request.term_type)
    if not term_entry:
        raise HTTPException(status_code=400, detail="Unsupported term type")

    payload = build_terms_payload(request.wk, request.employee_name)
    template_path = terms_template_path(request.term_type)
    docx_bytes, missing_placeholders = fill_docx_template(template_path, term_replacements(payload))

    filename_wk = re.sub(r"[^A-Z0-9_-]+", "_", str(payload.get("WKS") or "WKS").upper())
    filename = f"{filename_wk}-{term_entry['filename_suffix']}.docx"
    audit(
        "terms.generate",
        user["username"],
        {
            "wk": payload.get("WKS", request.wk),
            "term_type": request.term_type,
            "employee_name": request.employee_name,
            "filename": filename,
        },
    )
    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Missing-Placeholders": ",".join(missing_placeholders),
        },
    )


@router.post("/api/terms/print")
def terms_print(
    request: TermsGenerateRequest,
    portable: bool = Query(default=False),
    user: dict = Depends(require_role("admin", "operator")),
):
    term_entry = TERM_TYPES.get(request.term_type)
    if not term_entry:
        raise HTTPException(status_code=400, detail="Unsupported term type")

    payload = build_terms_payload(request.wk, request.employee_name)
    filename_wk = re.sub(r"[^A-Z0-9_-]+", "_", str(payload.get("WKS") or "WKS").upper())
    filename = f"{filename_wk}-{term_entry['filename_suffix']}.pdf"
    if portable:
        pdf_bytes = fallback_term_pdf(payload, request.employee_name)
    else:
        template_path = terms_template_path(request.term_type)
        docx_bytes, _missing_placeholders = fill_docx_template(template_path, term_replacements(payload))
        try:
            pdf_bytes = convert_docx_to_pdf(docx_bytes, filename_wk)
        except HTTPException:
            pdf_bytes = fallback_term_pdf(payload, request.employee_name)
    audit(
        "terms.print",
        user["username"],
        {
            "wk": payload.get("WKS", request.wk),
            "term_type": request.term_type,
            "employee_name": request.employee_name,
            "filename": filename,
        },
    )
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.post("/api/machine-replacement/report")
def machine_replacement_report(
    request: MachineReplacementReportRequest,
    user: dict = Depends(require_role("admin", "operator")),
):
    source = validate_backup_host(request.source)
    destination = validate_backup_host(request.destination)
    filename = f"troca-{source}-{destination}.pdf"
    application_sections = [
        (
            f"{index}. {item.get('name') or 'Aplicativo'}",
            [
                f"Versao na origem: {item.get('source_version') or 'Nao instalado'}",
                f"Versao no destino: {item.get('destination_version') or 'Nao instalado'}",
                f"Acao recomendada: {item.get('action') or 'Verificar'}",
                "-" * 72,
            ],
        )
        for index, item in enumerate(request.applications[:1000], start=1)
    ]
    if not application_sections:
        application_sections = [("APLICATIVOS", ["Nenhum aplicativo exige instalacao ou atualizacao."])]
    pdf_bytes = simple_text_pdf(
        "RELATORIO DE TROCA DE MAQUINA",
        [
            (
                "IDENTIFICACAO",
                [
                    f"Colaborador: {request.employee_name or 'Nao informado'}",
                    f"Tecnico: {request.technician or user['username']}",
                    f"Origem: {source}",
                    f"Destino: {destination}",
                    f"Gerado em: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}",
                ],
            ),
            ("DADOS MIGRADOS", [f"Perfis: {', '.join(request.profiles) or 'Nenhum perfil informado'}"]),
            (
                "VALIDACOES E BACKUP",
                [
                    f"Pre-check: {request.precheck_status or 'Nao executado'} - {request.precheck_message}",
                    f"Job: {request.backup_job_id or 'Nao informado'}",
                    f"Status: {request.backup_status or 'Nao informado'}",
                    f"Resumo: {request.backup_summary or 'Sem resumo retornado'}",
                    f"Validacao final: {request.validation_status or 'Pendente'}",
                    f"Termo: {'Gerado' if request.term_generated else 'Nao gerado'}",
                ],
            ),
            ("APLICATIVOS PARA INSTALAR OU ATUALIZAR", [f"Total identificado: {len(request.applications)}"]),
            *application_sections,
        ],
    )
    audit(
        "machine_replacement.report",
        user["username"],
        {
            "source": source,
            "destination": destination,
            "backup_job_id": request.backup_job_id,
            "applications": len(request.applications),
        },
    )
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
