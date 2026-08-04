import unittest

from backend.app.v2.description.builder import (
    build_descripcion_completa,
    build_descripcion_portada,
    limpiar_texto_aviso,
    _split_sentences,
)


class TestDescripcionCompleta(unittest.TestCase):
    def test_empty_text(self):
        self.assertEqual(build_descripcion_completa(""), "")

    def test_keeps_all_distinct_lines(self):
        text = "AVISO DE REMATE\nEXPEDIENTE N\u00b0 12345\nAVAL\u00daO COMERCIAL: $1,000.00"
        result = build_descripcion_completa(text)
        for line in ["AVISO DE REMATE", "EXPEDIENTE N\u00b0 12345", "AVAL\u00daO COMERCIAL: $1,000.00"]:
            self.assertIn(line, result)

    def test_does_not_lose_text_length_order(self):
        text = "LINEA UNO\nLINEA DOS\nLINEA TRES"
        result = build_descripcion_completa(text)
        self.assertEqual(result, "LINEA UNO\nLINEA DOS\nLINEA TRES")

    def test_removes_duplicate_paragraphs(self):
        # Un párrafo repetido exactamente (típico de re-segmentación con
        # solape) no debe duplicarse en la salida.
        text = "AVISO DE REMATE\nEXPEDIENTE N\u00b0 12345\nEXPEDIENTE N\u00b0 12345\nFINCA 500"
        result = build_descripcion_completa(text)
        self.assertEqual(result.count("EXPEDIENTE N\u00b0 12345"), 1)
        self.assertIn("FINCA 500", result)

    def test_duplicate_detection_ignores_case_and_spacing(self):
        text = "Expediente 12345\nEXPEDIENTE   12345\nFinca 500"
        result = build_descripcion_completa(text)
        self.assertEqual(len(result.split("\n")), 2)

    def test_does_not_split_words(self):
        # No debe reintroducir cortes: si ya llega "JUDICIAL" unida (por el
        # fix de ocr/mapper.py), debe seguir así.
        text = "PROCESO JUDICIAL EN CURSO"
        result = build_descripcion_completa(text)
        self.assertIn("JUDICIAL", result)
        self.assertNotIn("JUDI-", result)


class TestSplitSentences(unittest.TestCase):
    def test_simple_two_sentences(self):
        sentences = _split_sentences("Primera oracion completa. Segunda oracion completa.")
        self.assertEqual(len(sentences), 2)
        self.assertEqual(sentences[0], "Primera oracion completa.")

    def test_does_not_split_on_sa_abbreviation(self):
        sentences = _split_sentences(
            "DEMANDANTE: Financiera Familiar, S.A. DEMANDADO: Ismael Bonilla."
        )
        self.assertEqual(len(sentences), 1)
        self.assertIn("Financiera Familiar, S.A.", sentences[0])
        self.assertIn("DEMANDADO", sentences[0])

    def test_does_not_split_on_single_letter_initial(self):
        sentences = _split_sentences("El Sr. J. Rodriguez compareci\u00f3. Se orden\u00f3 el remate.")
        # No debe cortar en "Sr." ni en "J." -- ambas son abreviatura/inicial
        # de 1-2 letras o 1 letra antes del punto.
        self.assertEqual(sentences[0], "El Sr. J. Rodriguez compareci\u00f3.")

    def test_empty_text(self):
        self.assertEqual(_split_sentences(""), [])


class TestDescripcionPortada(unittest.TestCase):
    def test_empty_text(self):
        self.assertEqual(build_descripcion_portada(""), "")

    def test_ends_in_complete_sentence(self):
        text = ("Se rematar\u00e1 vivienda ubicada en el sector norte. "
                "Consta de dos plantas y jard\u00edn amplio. "
                "El remate se realizar\u00e1 en el juzgado correspondiente.")
        result = build_descripcion_portada(text, max_chars=60)
        self.assertTrue(result.endswith("."))
        self.assertTrue(result.startswith("Se rematar\u00e1 vivienda"))
        # No debe cortar a mitad de palabra ni de oraci\u00f3n.
        self.assertNotIn("..", result)

    def test_never_cuts_mid_sentence_even_if_over_budget(self):
        # Si ni la primera oraci\u00f3n completa entra en el presupuesto, se
        # devuelve completa igual (mejor larga que incompleta).
        text = "Esta es una oracion bastante mas larga que el presupuesto dado."
        result = build_descripcion_portada(text, max_chars=10)
        self.assertEqual(result, text)

    def test_takes_multiple_sentences_within_budget(self):
        text = "Idea uno breve. Idea dos breve. Idea tres que ya no entra en el presupuesto dado aqui."
        result = build_descripcion_portada(text, max_chars=35)
        self.assertIn("Idea uno breve.", result)
        self.assertIn("Idea dos breve.", result)
        self.assertNotIn("Idea tres", result)

    def test_does_not_just_take_first_lines_but_first_ideas(self):
        # El texto de un aviso suele empezar con encabezados/etiquetas, no
        # con la idea principal; el resumen debe tomar oraciones completas
        # con contenido, no las primeras l\u00edneas literales sin sentido de
        # oraci\u00f3n.
        text = "AVISO DE REMATE\nEXPEDIENTE N\u00b0 12345\nSe rematar\u00e1 finca urbana ubicada en Panam\u00e1."
        result = build_descripcion_portada(text, max_chars=200)
        self.assertIn("Se rematar\u00e1 finca urbana", result)


class TestLimpiarTextoAviso(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(limpiar_texto_aviso(""), "")
        self.assertEqual(limpiar_texto_aviso(None), "")

    def test_quita_cabecera_edicto_nnn(self):
        texto = "Edicto 810\nEDICTO 810\nAVISO DE REMATE\nFINCA 12345"
        result = limpiar_texto_aviso(texto)
        self.assertNotIn("810", result)
        self.assertIn("AVISO DE REMATE", result)
        self.assertIn("FINCA 12345", result)

    def test_quita_banner_publicitario(self):
        texto = (
            "AVISO DE REMATE IC Publica tus judiciales llamando al 204-0000 "
            "204-0045 correo : judiciales@laestrella.com.pa 10 estrellaonline "
            "laestrellaonline\nEDICTO EMPLAZATORIO No. 853-26"
        )
        result = limpiar_texto_aviso(texto)
        self.assertNotIn("204-0000", result)
        self.assertNotIn("judiciales@laestrella.com.pa", result)
        self.assertNotIn("estrellaonline", result)
        self.assertIn("EDICTO EMPLAZATORIO No. 853-26", result)

    def test_conserva_texto_real_del_aviso(self):
        texto = (
            "Publica tus judiciales llamando al 204-0000 204-0045\n"
            "EDICTO EMPLAZATORIO No. 853-26\n"
            "GRAVAMENES DERECHOS REALES Y OTROS VIGENTES\n"
            "HIPOTECA DE BIEN INMUEBLE"
        )
        result = limpiar_texto_aviso(texto)
        self.assertIn("GRAVAMENES DERECHOS REALES Y OTROS VIGENTES", result)
        self.assertIn("HIPOTECA DE BIEN INMUEBLE", result)

    def test_no_toca_expediente_con_digitos(self):
        texto = "EDICTO EMPLAZATORIO No. 853-26\nN74459-26\nB / 104,355.34"
        result = limpiar_texto_aviso(texto)
        self.assertIn("N74459-26", result)
        self.assertIn("104,355.34", result)


if __name__ == "__main__":
    unittest.main()
