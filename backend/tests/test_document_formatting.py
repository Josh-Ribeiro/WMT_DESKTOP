from __future__ import annotations

import unittest
import re
from html import unescape

from backend.app.services.documents import (
    replace_docx_paragraph_tokens,
    term_replacements,
)


class DocumentFormattingTests(unittest.TestCase):
    def test_term_replacements_preserve_the_original_word_runs(self) -> None:
        paragraph = (
            "<w:p>"
            "<w:r><w:rPr><w:b/></w:rPr><w:t>Nome: </w:t></w:r>"
            "<w:r><w:rPr><w:i/></w:rPr><w:t>{{NOME_COMPLETO}}</w:t></w:r>"
            "<w:r><w:t> | WKS: </w:t></w:r>"
            "<w:r><w:t>{{WKS}}</w:t></w:r>"
            "</w:p>"
        )

        replaced, matches = replace_docx_paragraph_tokens(
            paragraph,
            {
                "{{NOME_COMPLETO}}": "Maria Silva",
                "{{WKS}}": "WKS001",
            },
        )

        self.assertIn("<w:b/>", replaced)
        self.assertIn("<w:i/>", replaced)
        self.assertIn("<w:t>Maria Silva</w:t>", replaced)
        self.assertIn("<w:t>WKS001</w:t>", replaced)
        self.assertIn("{{NOME_COMPLETO}}", matches)
        self.assertIn("{{WKS}}", matches)

    def test_responsibility_equipment_rows_keep_the_template_columns(self) -> None:
        document = (
            "<w:p><w:r><w:t>WKS: </w:t></w:r>"
            "<w:r><w:t>C. Custo:</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>Marca:</w:t></w:r>"
            "<w:r><w:t>                      </w:t></w:r>"
            "<w:r><w:t>Modelo: </w:t></w:r></w:p>"
            "<w:p><w:r><w:t>Nº Série:</w:t></w:r>"
            "<w:r><w:t>BP: na</w:t></w:r></w:p>"
        )
        replacements = term_replacements(
            {
                "WKS": "WKS048-51BR",
                "SerialNumber": "JYPKPZ3",
                "Modelo": "Latitude 5430",
                "Marca": "Dell Inc.",
                "BP": "na",
            }
        )

        generated, _matches = replace_docx_paragraph_tokens(
            document,
            replacements,
        )
        paragraphs = [
            "".join(
                unescape(text)
                for text in re.findall(
                    r"<w:t(?:\s+[^>]*)?>([\s\S]*?)</w:t>",
                    paragraph,
                )
            )
            for paragraph in re.findall(r"<w:p[\s\S]*?</w:p>", generated)
        ]

        self.assertEqual("WKS: WKS048-51BR C. Custo:", paragraphs[0])
        self.assertEqual(
            "Marca:                      Dell Inc. Modelo: Latitude 5430 ",
            paragraphs[1],
        )
        self.assertEqual("Nº Série: JYPKPZ3 BP: na", paragraphs[2])


if __name__ == "__main__":
    unittest.main()
