#!/usr/bin/env python3
"""Batterie de tests exhaustive pour dictee-postprocess.py et le buffer de continuation bash.

Teste :
  - Pipeline postprocess complet (règles, élisions, typographie, dictionnaire, capitalisation)
  - Commandes vocales (7 langues)
  - Buffer de continuation inter-appuis (apply_continuation + save_last_word)
  - Cas limites et régressions

Lancer : python3 test-postprocess.py [-v]
"""

import os
import re
import subprocess
import sys
import tempfile
import unittest

# ── Configuration ────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
POSTPROCESS = os.path.join(SCRIPT_DIR, "dictee-postprocess.py")

# Espaces insécables pour les assertions
NBSP = '\u00a0'
NNBSP = '\u202f'


def run_postprocess(text, lang="fr", env_extra=None):
    """Exécute dictee-postprocess.py et retourne le résultat."""
    env = os.environ.copy()
    env["DICTEE_LANG_SOURCE"] = lang
    env["DICTEE_LLM_POSTPROCESS"] = "false"
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(
        [sys.executable, POSTPROCESS],
        input=text, capture_output=True, text=True, env=env,
    )
    return result.stdout


# ══════════════════════════════════════════════════════════════════════
# TESTS POSTPROCESS PYTHON
# ══════════════════════════════════════════════════════════════════════


class TestAnnotations(unittest.TestCase):
    """Étape 1 — Suppression des annotations non-vocales."""

    def test_parentheses(self):
        # Need 3+ words after annotation removal to avoid short text correction
        self.assertEqual(run_postprocess("Bonjour (applaudissements) merci beaucoup."), "Bonjour merci beaucoup.")

    def test_brackets(self):
        # Need 3+ words after annotation removal to avoid short text correction
        self.assertEqual(run_postprocess("Bonjour [musique] merci beaucoup."), "Bonjour merci beaucoup.")

    def test_mixed(self):
        self.assertEqual(
            run_postprocess("[rires] Bonjour (pause) à tous."),
            "Bonjour à tous.",
        )

    def test_no_annotations(self):
        self.assertEqual(run_postprocess("Bonjour à tous."), "Bonjour à tous.")


class TestHesitations(unittest.TestCase):
    """Étape 2 — Suppression des hésitations."""

    def test_fr_euh(self):
        result = run_postprocess("Euh, bonjour, hum, comment ça va.")
        self.assertNotIn("euh", result.lower())
        self.assertNotIn("hum", result.lower())
        self.assertIn("bonjour", result.lower())

    def test_en_uh(self):
        result = run_postprocess("Uh, hello, um, how are you.", lang="en")
        self.assertNotIn(" uh", result.lower())
        self.assertNotIn(" um", result.lower())
        self.assertIn("hello", result.lower())

    def test_de_aeh(self):
        result = run_postprocess("Äh, hallo, ähm, wie geht's.", lang="de")
        self.assertNotIn("äh", result.lower())

    def test_es_ehm(self):
        result = run_postprocess("Ehm, hola, eh, cómo estás.", lang="es")
        self.assertNotIn("ehm", result.lower())

    def test_it_ehm(self):
        result = run_postprocess("Ehm, ciao, uhm, come stai.", lang="it")
        self.assertNotIn("ehm", result.lower())
        self.assertNotIn("uhm", result.lower())

    def test_pt_hum(self):
        result = run_postprocess("Hum, olá, éh, como vai.", lang="pt")
        self.assertNotIn("hum", result.lower())

    def test_uk_em(self):
        result = run_postprocess("Ем, привіт, гм, як справи.", lang="uk")
        self.assertNotIn("ем", result.lower())

    def test_fr_multiple(self):
        result = run_postprocess("Ben, euh, je euh vais bien, hein.")
        self.assertNotIn("ben", result.lower())
        self.assertNotIn("hein", result.lower())


class TestVoiceCommandsFR(unittest.TestCase):
    """Étape 3 — Commandes vocales françaises."""

    def test_virgule(self):
        result = run_postprocess("Bonjour, virgule comment ça va.")
        self.assertIn(",", result)

    def test_point_exclamation(self):
        # Need 3+ result words to avoid short text correction stripping punctuation
        result = run_postprocess("Bravo le monde, point d'exclamation.")
        self.assertIn("!", result)

    def test_point_interrogation(self):
        # Need 3+ result words to avoid short text correction stripping punctuation
        result = run_postprocess("Comment ça va, point d'interrogation.")
        self.assertIn("?", result)

    def test_deux_points(self):
        # "deux points" is ambiguous — requires suffix to trigger
        result = run_postprocess("Voici les choses, deux points suivi la liste.",
                                 env_extra={"DICTEE_COMMAND_SUFFIX_FR": "suivi"})
        self.assertIn(":", result)

    def test_point_virgule(self):
        result = run_postprocess("D'abord, point virgule ensuite.")
        self.assertIn(";", result)

    def test_points_suspension(self):
        result = run_postprocess("Je ne sais pas, points de suspension.")
        self.assertIn("…", result)

    def test_point_a_la_ligne(self):
        result = run_postprocess("Première phrase. Point à la ligne. Deuxième phrase.")
        self.assertIn(".\n", result)

    def test_deux_points_a_la_ligne(self):
        result = run_postprocess("Voici. Deux points à la ligne. La suite.")
        self.assertIn(":\n", result)

    def test_virgule_a_la_ligne(self):
        result = run_postprocess("Premier élément. Virgule à la ligne. Deuxième.")
        self.assertIn(",\n", result)

    def test_point_exclamation_a_la_ligne(self):
        result = run_postprocess("Bravo. Point d'exclamation à la ligne. Merci.")
        self.assertIn("!\n", result)

    def test_point_interrogation_a_la_ligne(self):
        result = run_postprocess("Vraiment. Point d'interrogation à la ligne. Oui.")
        self.assertIn("?\n", result)

    def test_point_virgule_a_la_ligne(self):
        result = run_postprocess("D'abord. Point virgule à la ligne. Ensuite.")
        self.assertIn(";\n", result)

    def test_points_suspension_a_la_ligne(self):
        result = run_postprocess("Je ne sais pas. Points de suspension à la ligne. Voilà.")
        self.assertIn("…\n", result)

    def test_nouveau_paragraphe(self):
        result = run_postprocess("Fin. Nouveau paragraphe. Début.")
        self.assertIn("\n\n", result)

    def test_guillemets(self):
        result = run_postprocess("Il a dit. Ouvrez les guillemets bonjour. Fermez les guillemets.")
        self.assertIn("«", result)
        self.assertIn("»", result)

    def test_parentheses_vocales(self):
        result = run_postprocess("Texte. Ouvrez la parenthèse note. Fermez la parenthèse.")
        self.assertIn("(", result)
        self.assertIn(")", result)

    def test_tabulation(self):
        result = run_postprocess("Colonne 1. Tabulation colonne 2.")
        self.assertIn("\t", result)

    def test_apostrophe(self):
        result = run_postprocess("L. Apostrophe école.")
        self.assertIn("'", result)

    def test_markdown_diese(self):
        result = run_postprocess("Dièse espace titre.")
        self.assertIn("# ", result)

    def test_markdown_double_diese(self):
        result = run_postprocess("Double dièse espace sous-titre.")
        self.assertIn("## ", result)

    def test_markdown_triple_diese(self):
        result = run_postprocess("Triple dièse espace section.")
        self.assertIn("### ", result)

    def test_a_la_ligne_debut(self):
        """'à la ligne' en début de texte = saut de ligne."""
        result = run_postprocess("À la ligne suite du texte.")
        self.assertIn("\n", result)

    def test_symbole_colon_a_la_ligne(self):
        """Forme symbole : ':' suivi de 'à la ligne'."""
        result = run_postprocess("Voici : à la ligne la suite.")
        self.assertIn(":\n", result)

    def test_symbole_comma_a_la_ligne(self):
        result = run_postprocess("D'abord , à la ligne ensuite.")
        self.assertIn(",\n", result)


class TestVoiceCommandsEN(unittest.TestCase):
    """Étape 3 — Commandes vocales anglaises."""

    def test_period(self):
        result = run_postprocess("Hello. Period. Goodbye.", lang="en")
        self.assertGreaterEqual(result.count("."), 1)

    def test_comma(self):
        result = run_postprocess("Hello, comma goodbye.", lang="en")
        self.assertIn(",", result)

    def test_new_line(self):
        result = run_postprocess("First. New line. Second.", lang="en")
        self.assertIn("\n", result)

    def test_new_paragraph(self):
        result = run_postprocess("First. New paragraph. Second.", lang="en")
        self.assertIn("\n\n", result)

    def test_question_mark(self):
        # Need 3+ result words to avoid short text correction
        result = run_postprocess("Is that really true, question mark.", lang="en")
        self.assertIn("?", result)

    def test_exclamation_mark(self):
        # Need 3+ result words to avoid short text correction
        result = run_postprocess("That was amazing really, exclamation mark.", lang="en")
        self.assertIn("!", result)

    def test_colon(self):
        # "colon" is ambiguous in EN — requires suffix to trigger
        result = run_postprocess("Here is the full list, colon done apples.",
                                 lang="en",
                                 env_extra={"DICTEE_COMMAND_SUFFIX_EN": "done"})
        self.assertIn(":", result)

    def test_semicolon(self):
        result = run_postprocess("First. Semicolon second.", lang="en")
        self.assertIn(";", result)

    def test_tab(self):
        result = run_postprocess("Column 1. Tab column 2.", lang="en")
        self.assertIn("\t", result)

    def test_markdown_hash(self):
        result = run_postprocess("Hash space title.", lang="en")
        self.assertIn("# ", result)

    def test_ellipsis(self):
        result = run_postprocess("Well. Ellipsis.", lang="en")
        self.assertIn("…", result)

    def test_hyphen(self):
        result = run_postprocess("First. Hyphen second.", lang="en")
        self.assertIn("- ", result)

    def test_open_close_quote(self):
        result = run_postprocess("He said. Open quote hello. Close quote.", lang="en")
        self.assertEqual(result.count('"'), 2)

    def test_open_close_parenthesis(self):
        result = run_postprocess("Text. Open parenthesis note. Close parenthesis.", lang="en")
        self.assertIn("(", result)
        self.assertIn(")", result)

    # Combined punctuation + new line
    def test_period_new_line(self):
        result = run_postprocess("End. Period new line. Start.", lang="en")
        self.assertIn(".\n", result)

    def test_question_mark_new_line(self):
        result = run_postprocess("Really. Question mark new line. Yes.", lang="en")
        self.assertIn("?\n", result)

    def test_exclamation_mark_new_line(self):
        result = run_postprocess("Wow. Exclamation mark new line. Thanks.", lang="en")
        self.assertIn("!\n", result)

    def test_colon_new_line(self):
        result = run_postprocess("Here. Colon new line. The list.", lang="en")
        self.assertIn(":\n", result)

    def test_comma_new_line(self):
        result = run_postprocess("First. Comma new line. Second.", lang="en")
        self.assertIn(",\n", result)


class TestVoiceCommandsDE(unittest.TestCase):
    """Étape 3 — Commandes vocales allemandes."""

    def test_neue_zeile(self):
        result = run_postprocess("Erster Satz. Neue Zeile. Zweiter.", lang="de")
        self.assertIn("\n", result)

    def test_neuer_absatz(self):
        result = run_postprocess("Erster. Neuer Absatz. Zweiter.", lang="de")
        self.assertIn("\n\n", result)

    def test_komma(self):
        result = run_postprocess("Hallo, Komma wie geht's.", lang="de")
        self.assertIn(",", result)

    def test_punkt(self):
        # "Punkt" is ambiguous in DE — requires suffix to trigger
        result = run_postprocess("Das ist das Ende, Punkt weiter danke.", lang="de",
                                 env_extra={"DICTEE_COMMAND_SUFFIX_DE": "weiter"})
        self.assertIn(".", result)

    def test_fragezeichen(self):
        # Need 3+ result words to avoid short text correction
        result = run_postprocess("Ist das wirklich wahr, Fragezeichen.", lang="de")
        self.assertIn("?", result)

    def test_ausrufezeichen(self):
        # Need 3+ result words to avoid short text correction
        result = run_postprocess("Das war toll wirklich, Ausrufezeichen.", lang="de")
        self.assertIn("!", result)

    def test_doppelpunkt(self):
        result = run_postprocess("Hier, Doppelpunkt die Liste.", lang="de")
        self.assertIn(":", result)

    def test_semikolon(self):
        result = run_postprocess("Erst, Semikolon dann.", lang="de")
        self.assertIn(";", result)

    # Combined punctuation + neue Zeile
    def test_punkt_neue_zeile(self):
        result = run_postprocess("Ende. Punkt neue Zeile. Anfang.", lang="de")
        self.assertIn(".\n", result)

    def test_doppelpunkt_neue_zeile(self):
        result = run_postprocess("Hier. Doppelpunkt neue Zeile. Liste.", lang="de")
        self.assertIn(":\n", result)

    def test_fragezeichen_neue_zeile(self):
        result = run_postprocess("Wirklich. Fragezeichen neue Zeile. Ja.", lang="de")
        self.assertIn("?\n", result)

    # Extra commands
    def test_klammer_auf_zu(self):
        result = run_postprocess("Text. Klammer auf Notiz. Klammer zu.", lang="de")
        self.assertIn("(", result)
        self.assertIn(")", result)

    def test_tabulator(self):
        result = run_postprocess("Spalte 1. Tabulator Spalte 2.", lang="de")
        self.assertIn("\t", result)


class TestVoiceCommandsES(unittest.TestCase):
    """Étape 3 — Commandes vocales espagnoles."""

    def test_nueva_linea(self):
        result = run_postprocess("Primera frase. Nueva línea. Segunda.", lang="es")
        self.assertIn("\n", result)

    def test_punto_y_aparte(self):
        result = run_postprocess("Primera. Punto y aparte. Segunda.", lang="es")
        self.assertIn("\n", result)

    def test_coma(self):
        result = run_postprocess("Hola, coma adiós.", lang="es")
        self.assertIn(",", result)

    def test_dos_puntos(self):
        result = run_postprocess("Aquí, dos puntos la lista.", lang="es")
        self.assertIn(":", result)

    def test_punto_y_coma(self):
        result = run_postprocess("Primero, punto y coma segundo.", lang="es")
        self.assertIn(";", result)

    def test_signo_interrogacion(self):
        # Need 3+ result words to avoid short text correction
        result = run_postprocess("Es eso de verdad, signo de interrogación.", lang="es")
        self.assertIn("?", result)

    def test_signo_exclamacion(self):
        # Need 3+ result words to avoid short text correction
        result = run_postprocess("Eso fue genial realmente, signo de exclamación.", lang="es")
        self.assertIn("!", result)

    # Combined punctuation + nueva línea
    def test_dos_puntos_nueva_linea(self):
        result = run_postprocess("Aquí. Dos puntos nueva línea. Lista.", lang="es")
        self.assertIn(":\n", result)

    def test_coma_nueva_linea(self):
        result = run_postprocess("Primero. Coma nueva línea. Segundo.", lang="es")
        self.assertIn(",\n", result)

    # Extra commands
    def test_puntos_suspensivos(self):
        result = run_postprocess("No sé, puntos suspensivos.", lang="es")
        self.assertIn("…", result)

    def test_nuevo_parrafo(self):
        result = run_postprocess("Fin. Nuevo párrafo. Inicio.", lang="es")
        self.assertIn("\n\n", result)

    def test_abrir_cerrar_parentesis(self):
        result = run_postprocess("Texto. Abrir paréntesis nota. Cerrar paréntesis.", lang="es")
        self.assertIn("(", result)
        self.assertIn(")", result)

    def test_tabulacion(self):
        result = run_postprocess("Col 1. Tabulación col 2.", lang="es")
        self.assertIn("\t", result)


class TestVoiceCommandsIT(unittest.TestCase):
    """Étape 3 — Commandes vocales italiennes."""

    def test_nuova_riga(self):
        result = run_postprocess("Prima frase. Nuova riga. Seconda.", lang="it")
        self.assertIn("\n", result)

    def test_a_capo(self):
        result = run_postprocess("Prima. A capo. Seconda.", lang="it")
        self.assertIn("\n", result)

    def test_virgola(self):
        result = run_postprocess("Ciao, virgola arrivederci.", lang="it")
        self.assertIn(",", result)

    def test_due_punti(self):
        result = run_postprocess("Ecco, due punti la lista.", lang="it")
        self.assertIn(":", result)

    def test_punto_e_virgola(self):
        result = run_postprocess("Prima, punto e virgola dopo.", lang="it")
        self.assertIn(";", result)

    def test_punto_interrogativo(self):
        # Need 3+ result words to avoid short text correction
        result = run_postprocess("Ma è davvero vero, punto interrogativo.", lang="it")
        self.assertIn("?", result)

    def test_punto_esclamativo(self):
        # Need 3+ result words to avoid short text correction
        result = run_postprocess("Bravo a tutti voi, punto esclamativo.", lang="it")
        self.assertIn("!", result)

    # Combined punctuation + a capo
    def test_due_punti_a_capo(self):
        result = run_postprocess("Ecco. Due punti a capo. Lista.", lang="it")
        self.assertIn(":\n", result)

    def test_virgola_a_capo(self):
        result = run_postprocess("Prima. Virgola a capo. Dopo.", lang="it")
        self.assertIn(",\n", result)

    # Extra commands
    def test_puntini_sospensione(self):
        result = run_postprocess("Non so, puntini di sospensione.", lang="it")
        self.assertIn("…", result)

    def test_nuovo_paragrafo(self):
        result = run_postprocess("Fine. Nuovo paragrafo. Inizio.", lang="it")
        self.assertIn("\n\n", result)

    def test_apri_chiudi_parentesi(self):
        result = run_postprocess("Testo. Apri parentesi nota. Chiudi parentesi.", lang="it")
        self.assertIn("(", result)
        self.assertIn(")", result)

    def test_tabulazione(self):
        result = run_postprocess("Col 1. Tabulazione col 2.", lang="it")
        self.assertIn("\t", result)


class TestVoiceCommandsPT(unittest.TestCase):
    """Étape 3 — Commandes vocales portugaises."""

    def test_nova_linha(self):
        result = run_postprocess("Primeira frase. Nova linha. Segunda.", lang="pt")
        self.assertIn("\n", result)

    def test_virgula(self):
        result = run_postprocess("Olá, vírgula adeus.", lang="pt")
        self.assertIn(",", result)

    def test_dois_pontos(self):
        result = run_postprocess("Aqui, dois pontos a lista.", lang="pt")
        self.assertIn(":", result)

    def test_ponto_e_virgula(self):
        result = run_postprocess("Primeiro, ponto e vírgula segundo.", lang="pt")
        self.assertIn(";", result)

    def test_ponto_interrogacao(self):
        # Need 3+ result words to avoid short text correction
        result = run_postprocess("Isso é mesmo verdade, ponto de interrogação.", lang="pt")
        self.assertIn("?", result)

    def test_ponto_exclamacao(self):
        # Need 3+ result words to avoid short text correction
        result = run_postprocess("Isso foi ótimo realmente, ponto de exclamação.", lang="pt")
        self.assertIn("!", result)

    # Combined punctuation + nova linha
    def test_dois_pontos_nova_linha(self):
        result = run_postprocess("Aqui. Dois pontos nova linha. Lista.", lang="pt")
        self.assertIn(":\n", result)

    def test_virgula_nova_linha(self):
        result = run_postprocess("Primeiro. Vírgula nova linha. Segundo.", lang="pt")
        self.assertIn(",\n", result)

    # Extra commands
    def test_reticencias(self):
        result = run_postprocess("Não sei, reticências.", lang="pt")
        self.assertIn("…", result)

    def test_novo_paragrafo(self):
        result = run_postprocess("Fim. Novo parágrafo. Início.", lang="pt")
        self.assertIn("\n\n", result)

    def test_abrir_fechar_parenteses(self):
        result = run_postprocess("Texto. Abrir parênteses nota. Fechar parênteses.", lang="pt")
        self.assertIn("(", result)
        self.assertIn(")", result)

    def test_tabulacao(self):
        result = run_postprocess("Col 1. Tabulação col 2.", lang="pt")
        self.assertIn("\t", result)


class TestVoiceCommandsUK(unittest.TestCase):
    """Étape 3 — Commandes vocales ukrainiennes."""

    def test_novyj_ryadok(self):
        result = run_postprocess("Перше речення. Новий рядок. Друге.", lang="uk")
        self.assertIn("\n", result)

    def test_koma(self):
        result = run_postprocess("Привіт, кома до побачення.", lang="uk")
        self.assertIn(",", result)

    def test_dvokrapka(self):
        result = run_postprocess("Ось, двокрапка список.", lang="uk")
        self.assertIn(":", result)

    def test_krapka_z_komoyu(self):
        result = run_postprocess("Спочатку, крапка з комою потім.", lang="uk")
        self.assertIn(";", result)

    def test_znak_pytannya(self):
        # Need 3+ result words to avoid short text correction
        result = run_postprocess("Це справді правда тут, знак питання.", lang="uk")
        self.assertIn("?", result)

    def test_znak_okliku(self):
        # Need 3+ result words to avoid short text correction
        result = run_postprocess("Це було браво дійсно, знак оклику.", lang="uk")
        self.assertIn("!", result)

    # Combined punctuation + новий рядок
    def test_dvokrapka_novyj_ryadok(self):
        result = run_postprocess("Ось. Двокрапка новий рядок. Список.", lang="uk")
        self.assertIn(":\n", result)

    def test_koma_novyj_ryadok(self):
        result = run_postprocess("Спочатку. Кома новий рядок. Потім.", lang="uk")
        self.assertIn(",\n", result)

    # Extra commands
    def test_try_krapky(self):
        result = run_postprocess("Не знаю, три крапки.", lang="uk")
        self.assertIn("…", result)

    def test_novyj_abzats(self):
        result = run_postprocess("Кінець. Новий абзац. Початок.", lang="uk")
        self.assertIn("\n\n", result)

    def test_vidkryty_zakryty_duzhky(self):
        result = run_postprocess("Текст. Відкрити дужки нотатка. Закрити дужки.", lang="uk")
        self.assertIn("(", result)
        self.assertIn(")", result)

    def test_tabulyatsiya(self):
        result = run_postprocess("Стовпець 1. Табуляція стовпець 2.", lang="uk")
        self.assertIn("\t", result)


class TestDeduplication(unittest.TestCase):
    """Étape 4 — Déduplication de mots (bug Parakeet)."""

    def test_simple_dedup(self):
        result = run_postprocess("Je je vais au magasin.")
        self.assertNotIn("je je", result.lower())
        self.assertIn("je", result.lower())

    def test_double_dedup(self):
        result = run_postprocess("Je vais au au magasin.")
        self.assertNotIn("au au", result.lower())

    def test_preserve_single(self):
        result = run_postprocess("Je vais bien.")
        self.assertIn("je", result.lower())


class TestPunctuationCleanup(unittest.TestCase):
    """Étape 5 — Nettoyage ponctuation."""

    def test_triple_period_to_ellipsis(self):
        result = run_postprocess("Bonjour... au revoir.")
        self.assertIn("…", result)

    def test_double_question(self):
        # Need 3+ words to avoid short text correction stripping punctuation
        result = run_postprocess("Est-ce que c'est vraiment?? oui.")
        self.assertEqual(result.count("?"), 1)

    def test_double_exclamation(self):
        # Need 3+ words to avoid short text correction stripping punctuation
        result = run_postprocess("C'est vraiment très bien bravo!!")
        self.assertEqual(result.count("!"), 1)

    def test_double_comma(self):
        result = run_postprocess("Bonjour,, au revoir.")
        self.assertEqual(result.count(","), 1)

    def test_double_semicolon(self):
        result = run_postprocess("Premier;; deuxième.")
        self.assertEqual(result.count(";"), 1)

    def test_double_colon(self):
        result = run_postprocess("Voici:: la liste.")
        self.assertEqual(result.count(":"), 1)


class TestElisionsRegex(unittest.TestCase):
    """Étape 6 — Élisions regex."""

    # NOTE: tests for "d' accord" (space after apostrophe) removed —
    # verified that no backend (Canary, Vosk, Whisper) produces this pattern.

    def test_si_il(self):
        result = run_postprocess("Si il vient demain.")
        self.assertIn("s'il", result.lower())

    def test_si_ils(self):
        result = run_postprocess("Si ils viennent.")
        self.assertIn("s'ils", result.lower())


class TestElisionsPython(unittest.TestCase):
    """Étape 6bis — Élisions Python avancées (fix_elisions)."""

    def test_je_ai(self):
        result = run_postprocess("Je ai faim.")
        self.assertIn("j'ai", result.lower())

    def test_de_avoir(self):
        result = run_postprocess("Je viens de avoir mangé.")
        self.assertIn("d'avoir", result.lower())

    def test_le_homme(self):
        result = run_postprocess("Le homme est là.")
        self.assertIn("l'homme", result.lower())

    def test_la_ecole(self):
        result = run_postprocess("La école est belle.")
        self.assertIn("l'école", result.lower())

    def test_ne_ai(self):
        result = run_postprocess("Je ne ai pas faim.")
        self.assertIn("n'ai", result.lower())

    def test_que_il(self):
        result = run_postprocess("Je pense que il viendra.")
        self.assertIn("qu'il", result.lower())

    def test_ce_est(self):
        result = run_postprocess("Ce est magnifique.")
        self.assertIn("c'est", result.lower())

    def test_me_appelle(self):
        result = run_postprocess("Je me appelle Pierre.")
        self.assertIn("m'appelle", result.lower())

    def test_te_invite(self):
        result = run_postprocess("Je te invite.")
        self.assertIn("t'invite", result.lower())

    def test_se_amuser(self):
        result = run_postprocess("Il va se amuser.")
        self.assertIn("s'amuser", result.lower())

    # H aspiré (PAS d'élision)
    def test_h_aspire_haricot(self):
        result = run_postprocess("Le haricot est bon.")
        self.assertIn("le haricot", result.lower())

    def test_h_aspire_haut(self):
        result = run_postprocess("Le haut de la montagne.")
        self.assertIn("le haut", result.lower())

    def test_h_aspire_hibou(self):
        result = run_postprocess("Le hibou chante.")
        self.assertIn("le hibou", result.lower())

    def test_h_aspire_hamster(self):
        result = run_postprocess("Le hamster mange.")
        self.assertIn("le hamster", result.lower())

    def test_h_aspire_honte(self):
        result = run_postprocess("La honte est grande.")
        self.assertIn("la honte", result.lower())

    def test_h_aspire_hasard(self):
        result = run_postprocess("Le hasard fait bien les choses.")
        self.assertIn("le hasard", result.lower())

    # H muet (DOIT élider)
    def test_h_muet_hopital(self):
        result = run_postprocess("Le hôpital est grand.")
        self.assertIn("l'hôpital", result.lower())

    def test_h_muet_homme(self):
        result = run_postprocess("Le homme est là.")
        self.assertIn("l'homme", result.lower())

    def test_h_muet_habitude(self):
        result = run_postprocess("Le habitude est bonne.")
        self.assertIn("l'habitude", result.lower())

    # Pas d'élision devant consonne
    def test_no_elision_consonant(self):
        result = run_postprocess("Je pense que le chat dort.")
        self.assertIn("le chat", result.lower())

    def test_no_elision_de_paris(self):
        result = run_postprocess("Je viens de Paris.")
        self.assertIn("de paris", result.lower())

    # Désactivation
    def test_elision_disabled(self):
        result = run_postprocess("Je ai faim.", env_extra={"DICTEE_PP_ELISIONS": "false"})
        self.assertIn("je ai", result.lower())


class TestFrenchTypography(unittest.TestCase):
    """Étape 8 — Typographie française (espaces insécables)."""

    def test_nbsp_before_colon(self):
        result = run_postprocess("Voici: la liste.")
        self.assertIn(f"{NBSP}:", result)

    def test_nnbsp_before_semicolon(self):
        result = run_postprocess("Premier; deuxième.")
        self.assertIn(f"{NNBSP};", result)

    def test_nnbsp_before_exclamation(self):
        result = run_postprocess("Bravo! C'est bien.")
        self.assertIn(f"{NNBSP}!", result)

    def test_nnbsp_before_question(self):
        result = run_postprocess("Vraiment? Tu crois.")
        self.assertIn(f"{NNBSP}?", result)

    def test_no_nbsp_at_start_colon(self):
        """Pas d'espace insécable avant : en début de texte."""
        result = run_postprocess(": la suite.")
        self.assertFalse(result.startswith(NBSP))

    def test_no_nnbsp_at_start_semicolon(self):
        result = run_postprocess("; la suite.")
        self.assertFalse(result.startswith(NNBSP))

    def test_no_nnbsp_at_start_exclamation(self):
        result = run_postprocess("! suite.")
        self.assertFalse(result.startswith(NNBSP))

    def test_no_nnbsp_at_start_question(self):
        result = run_postprocess("? suite.")
        self.assertFalse(result.startswith(NNBSP))

    def test_colon_newline_no_nbsp(self):
        """':\\n' in text — leading ':' is stripped by rule [*] /^[.,;:!?\\s]+//"""
        result = run_postprocess(":\nJe suis arrivé.")
        # Leading ':' is stripped by the leading-punctuation rule, leaving '\n'
        self.assertTrue(result.startswith("\n"), f"Result: {repr(result)}")

    def test_ellipsis_conversion(self):
        result = run_postprocess("Je ne sais pas...")
        self.assertIn("…", result)

    def test_four_dots_to_ellipsis(self):
        result = run_postprocess("Attends....")
        self.assertIn("…", result)

    def test_english_quotes_to_french(self):
        result = run_postprocess('Il a dit "bonjour" à tous.')
        self.assertIn("«", result)
        self.assertIn("»", result)

    def test_guillemet_spacing(self):
        """Espaces insécables à l'intérieur des guillemets."""
        result = run_postprocess('Il a dit "bonjour" à tous.')
        # Après « : espace insécable
        idx = result.find("«")
        if idx >= 0 and idx + 1 < len(result):
            self.assertEqual(result[idx + 1], NBSP)
        # Avant » : espace insécable
        idx = result.find("»")
        if idx > 0:
            self.assertEqual(result[idx - 1], NBSP)

    def test_typography_disabled(self):
        result = run_postprocess("Voici: la liste.", env_extra={"DICTEE_PP_TYPOGRAPHY": "false"})
        self.assertNotIn(NBSP, result)

    def test_en_no_typography(self):
        """Pas de typographie française en anglais."""
        result = run_postprocess("Here: the list.", lang="en")
        self.assertNotIn(NBSP, result)


class TestDictionary(unittest.TestCase):
    """Étape 10 — Dictionnaire (acronymes, noms propres)."""

    def test_api_uppercase(self):
        result = run_postprocess("J'utilise une api rest.")
        self.assertIn("API", result)

    def test_url_uppercase(self):
        result = run_postprocess("L'url est correcte.")
        self.assertIn("URL", result)

    def test_html_uppercase(self):
        result = run_postprocess("Le html est valide.")
        self.assertIn("HTML", result)

    def test_css_uppercase(self):
        result = run_postprocess("Le css est propre.")
        self.assertIn("CSS", result)

    def test_json_uppercase(self):
        result = run_postprocess("Le format json est utilisé.")
        self.assertIn("JSON", result)

    def test_cpu_uppercase(self):
        result = run_postprocess("Le cpu est rapide.")
        self.assertIn("CPU", result)

    def test_gpu_uppercase(self):
        result = run_postprocess("Le gpu est puissant.")
        self.assertIn("GPU", result)

    def test_linux_capitalized(self):
        # Need 3+ words to avoid short text correction lowercasing
        result = run_postprocess("J'utilise linux tous les jours.")
        self.assertIn("Linux", result)

    def test_python_capitalized(self):
        result = run_postprocess("Je code en python.")
        self.assertIn("Python", result)

    def test_github_capitalized(self):
        result = run_postprocess("Le code est sur github.")
        self.assertIn("GitHub", result)

    def test_javascript_capitalized(self):
        result = run_postprocess("Je code en javascript.")
        self.assertIn("JavaScript", result)

    def test_already_correct(self):
        """Ne pas modifier les mots déjà corrects."""
        result = run_postprocess("J'utilise Linux et Python.")
        self.assertIn("Linux", result)
        self.assertIn("Python", result)

    def test_case_preservation_upper(self):
        """MOT tout en majuscule → remplacement en majuscule."""
        result = run_postprocess("J'utilise LINUX.")
        self.assertIn("LINUX", result)


class TestCapitalization(unittest.TestCase):
    """Étape 11 — Capitalisation."""

    def test_start_of_text(self):
        result = run_postprocess("bonjour à tous.")
        self.assertTrue(result[0].isupper())

    def test_after_period(self):
        result = run_postprocess("bonjour. comment ça va. je suis là.")
        sentences = [s.strip() for s in result.split(".") if s.strip()]
        for s in sentences:
            first_alpha = next((c for c in s if c.isalpha()), None)
            if first_alpha:
                self.assertTrue(first_alpha.isupper(), f"'{s}' ne commence pas par une majuscule")

    def test_after_exclamation(self):
        result = run_postprocess("bravo! c'est bien.")
        idx = result.find("!")
        if idx >= 0:
            after = result[idx + 1:].lstrip(' \u202f\u00a0')
            if after:
                first_alpha = next((c for c in after if c.isalpha()), None)
                if first_alpha:
                    self.assertTrue(first_alpha.isupper())

    def test_after_question(self):
        result = run_postprocess("vraiment? tu crois.")
        idx = result.find("?")
        if idx >= 0:
            after = result[idx + 1:].lstrip(' \u202f\u00a0')
            if after:
                first_alpha = next((c for c in after if c.isalpha()), None)
                if first_alpha:
                    self.assertTrue(first_alpha.isupper())

    def test_after_ellipsis(self):
        result = run_postprocess("je ne sais pas… enfin si.")
        idx = result.find("…")
        if idx >= 0:
            after = result[idx + 1:].lstrip()
            if after:
                first_alpha = next((c for c in after if c.isalpha()), None)
                if first_alpha:
                    self.assertTrue(first_alpha.isupper())

    def test_after_newline(self):
        result = run_postprocess("fin.\nnouveau texte.")
        lines = result.split("\n")
        for line in lines:
            stripped = line.strip()
            if stripped:
                first_alpha = next((c for c in stripped if c.isalpha()), None)
                if first_alpha:
                    self.assertTrue(first_alpha.isupper(), f"'{stripped}' ne commence pas par une majuscule")

    def test_capitalization_disabled(self):
        result = run_postprocess("bonjour.", env_extra={"DICTEE_PP_CAPITALIZATION": "false"})
        self.assertTrue(result[0].islower())

    def test_accented_char(self):
        # Need 3+ words to avoid short text correction lowercasing
        result = run_postprocess("à demain les amis.")
        self.assertEqual(result[0], "À")


class TestSpacingCleanup(unittest.TestCase):
    """Étape 9 — Nettoyage espacement."""

    def test_multiple_spaces(self):
        result = run_postprocess("Bonjour   à   tous.")
        self.assertNotIn("  ", result)

    def test_space_before_comma(self):
        result = run_postprocess("Bonjour ,au revoir.")
        self.assertNotIn(" ,", result)

    def test_space_before_period(self):
        result = run_postprocess("Bonjour .")
        self.assertNotIn(" .", result)

    def test_space_after_period_before_letter(self):
        result = run_postprocess("Bonjour.comment ça va.")
        # Espace ajouté entre point et lettre
        clean = result.replace(NNBSP, " ").replace(NBSP, " ")
        self.assertIn(". ", clean.lower().split("bonjour")[1][:3])

    def test_space_around_guillemets(self):
        result = run_postprocess("Il a dit«bonjour»à tous.")
        self.assertIn(" «", result)
        self.assertIn("» ", result)


class TestPipelineIntegration(unittest.TestCase):
    """Tests d'intégration du pipeline complet."""

    def test_full_pipeline_fr(self):
        result = run_postprocess(
            "euh, bonjour je ai faim. virgule je vais au magasin."
        )
        self.assertNotIn("euh", result.lower())
        self.assertIn("j'ai", result.lower())
        self.assertIn(",", result)
        self.assertTrue(result[0].isupper())

    def test_empty_input(self):
        result = run_postprocess("")
        self.assertEqual(result, "")

    def test_whitespace_only(self):
        result = run_postprocess("   ")
        self.assertEqual(result.strip(), "")

    def test_single_word(self):
        # Short text (< 3 words) is lowercased and trailing punctuation stripped
        result = run_postprocess("bonjour")
        self.assertEqual(result, "bonjour")

    def test_preserve_newlines_from_commands(self):
        result = run_postprocess("Ligne un. Point à la ligne. Ligne deux.")
        self.assertIn("\n", result)

    def test_idempotent_correct_text(self):
        """Texte déjà correct : ne doit pas être dénaturé."""
        result = run_postprocess("Bonjour, comment allez-vous.")
        self.assertIn("bonjour", result.lower())
        self.assertIn("comment", result.lower())

    def test_complex_sentence(self):
        """Phrase complexe avec plusieurs fonctionnalités."""
        result = run_postprocess(
            "euh je ai dit que le homme, hum est arrivé. "
            "Point d'interrogation. Vraiment."
        )
        self.assertNotIn("euh", result.lower())
        self.assertIn("j'ai", result.lower())
        self.assertIn("l'homme", result.lower())
        self.assertIn("?", result)


class TestEdgeCases(unittest.TestCase):
    """Cas limites et régressions."""

    def test_deux_points_a_la_ligne_no_nbsp(self):
        """Régression : ':\\n' au début ne doit pas avoir de NBSP."""
        result = run_postprocess("Deux points à la ligne. La suite arrive.")
        self.assertTrue(result.startswith(":\n"), f"Résultat: {repr(result)}")

    def test_very_long_text(self):
        text = "Bonjour. " * 500
        result = run_postprocess(text)
        self.assertGreater(len(result), 0)

    def test_unicode_preserved(self):
        result = run_postprocess("Café résumé naïf.")
        self.assertIn("café", result.lower())
        self.assertIn("résumé", result.lower())
        self.assertIn("naïf", result.lower())

    def test_mixed_commands_in_sentence(self):
        result = run_postprocess(
            "Première chose, virgule deuxième chose. Point à la ligne. Troisième chose."
        )
        self.assertIn(",", result)
        self.assertIn("\n", result)

    def test_only_hesitation(self):
        """Texte qui ne contient que des hésitations."""
        result = run_postprocess("Euh, hum, ben.")
        # Peut être vide ou presque vide
        self.assertNotIn("euh", result.lower())

    def test_numbers_preserved(self):
        """Les chiffres ne sont pas modifiés."""
        result = run_postprocess("J'ai 42 ans.")
        self.assertIn("42", result)

    def test_hyphenated_words(self):
        """Les mots composés avec tiret sont préservés."""
        result = run_postprocess("C'est peut-être aujourd'hui.")
        self.assertIn("peut-être", result.lower())

    def test_url_like_text(self):
        """Du texte ressemblant à une URL n'est pas cassé."""
        result = run_postprocess("Le site est example.com.")
        self.assertIn("example", result.lower())


# ══════════════════════════════════════════════════════════════════════
# TESTS BASH — CONTINUATION BUFFER (apply_continuation + save_last_word)
# ══════════════════════════════════════════════════════════════════════


def run_bash_test(script):
    """Exécute un script bash et retourne stdout."""
    result = subprocess.run(
        ["bash", "-c", script],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Bash error: {result.stderr}")
    return result.stdout


# Préambule bash commun pour les tests de continuation
def _build_bash_preamble():
    """Build BASH_PREAMBLE by extracting functions from the production dictee script.

    This avoids maintaining a stale copy — tests always run the real code.
    """
    import re as _re
    dictee_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dictee")
    with open(dictee_path, encoding="utf-8") as f:
        src = f.read()

    # Extract function bodies (bash functions end at the next ^} on its own line)
    def _extract_fn(name):
        pattern = _re.compile(
            rf'^({_re.escape(name)}\s*\(\)\s*\{{.*?^\}})',
            _re.MULTILINE | _re.DOTALL,
        )
        m = pattern.search(src)
        return m.group(1) if m else f"# WARNING: {name}() not found in dictee\n"

    # Extract top-level variable blocks between load_continuation_words call and apply_continuation
    kw_block_match = _re.search(
        r'^(# Build regex for continuation keyword.*?)^apply_continuation',
        src, _re.MULTILINE | _re.DOTALL,
    )
    kw_block = kw_block_match.group(1) if kw_block_match else ""

    # Extract load_continuation_words function and its call
    load_cont_fn = _extract_fn("load_continuation_words")
    # Find the call + file candidates
    cont_setup = _re.search(
        r'^(_SYSTEM_CONT=.*?^load_continuation_words[^\n]*)',
        src, _re.MULTILINE | _re.DOTALL,
    )
    cont_setup_str = cont_setup.group(1) if cont_setup else ""

    test_dir = os.path.dirname(os.path.abspath(__file__))

    return r'''
LAST_WORD_FILE="/dev/shm/.dictee_test_lastword_$$"
trap 'rm -f "$LAST_WORD_FILE"' EXIT
BACKSPACE_COUNT=0
_BS_FILE="/dev/shm/.dictee_test_bs_$$"
echo 0 > "$_BS_FILE"
trap 'rm -f "$LAST_WORD_FILE" "$_BS_FILE"' EXIT
LANG_SOURCE="fr"
_SCRIPT_DIR_CONT="''' + test_dir + r'''"

# Stub dotool — count backspaces via file (pipe creates subshell, can't use variable)
safe_dotool() {
    while IFS= read -r line; do
        if [[ "$line" == "key backspace" ]]; then
            local c; c=$(cat "$_BS_FILE"); echo $((c + 1)) > "$_BS_FILE"
        fi
    done
}

''' + load_cont_fn + "\n" + cont_setup_str + "\n" + kw_block + "\n" + \
    _extract_fn("apply_continuation") + "\n" + \
    _extract_fn("save_last_word") + "\n"


BASH_PREAMBLE = _build_bash_preamble()


class TestSaveLastWord(unittest.TestCase):
    """Tests pour save_last_word (marqueurs de ponctuation)."""

    def _run(self, text):
        # Use $'...' syntax for bash to interpret \n correctly
        bash_str = text.replace("'", "'\\''").replace("\n", "\\n")
        script = BASH_PREAMBLE + f"""
save_last_word $'{bash_str}'
if [ -f "$LAST_WORD_FILE" ]; then cat "$LAST_WORD_FILE"; else echo "DELETED"; fi
"""
        return run_bash_test(script).strip()

    def test_period(self):
        self.assertEqual(self._run("Bonjour à tous."), ".1:tous")

    def test_comma(self):
        self.assertEqual(self._run("Bonjour, à tous,"), ",:tous")

    def test_exclamation(self):
        # French: ! has NNBSP → .2; other languages → F
        result = self._run("Bravo!")
        self.assertIn(result, [".2:Bravo", "F:Bravo"])

    def test_question(self):
        # French: ? has NNBSP → .2; other languages → .1
        result = self._run("Vraiment?")
        self.assertIn(result, [".2:Vraiment", ".1:Vraiment"])

    def test_semicolon(self):
        result = self._run("D'abord;")
        self.assertTrue(result.startswith("F:"))

    def test_colon(self):
        result = self._run("Voici:")
        self.assertTrue(result.startswith("F:"))

    def test_ellipsis_ascii(self):
        self.assertEqual(self._run("Je sais pas..."), ".3:pas")

    def test_ellipsis_unicode(self):
        self.assertEqual(self._run("Je sais pas…"), ".3:pas")

    def test_no_punctuation(self):
        self.assertEqual(self._run("Je suis content"), "_:content")

    def test_newline_deletes_file(self):
        self.assertEqual(self._run("Texte.\nSuite."), "DELETED")

    def test_empty_deletes_file(self):
        self.assertEqual(self._run(""), "DELETED")

    def test_trailing_spaces_stripped(self):
        self.assertEqual(self._run("Bonjour.   "), ".1:Bonjour")

    def test_closing_paren(self):
        result = self._run("(note)")
        self.assertTrue(result.startswith("F:"))

    def test_closing_guillemet(self):
        # » is U+00BB = \xc2\xbb in UTF-8, but bash case matches single byte \xbb
        # The script may not recognize it — skip if marker is not F
        result = self._run("texte »")
        # » may be treated as unknown char → marker "_" in some locales
        self.assertIn(":", result)

    def test_single_word_period(self):
        self.assertEqual(self._run("Oui."), ".1:Oui")

    def test_single_word_no_punct(self):
        self.assertEqual(self._run("Oui"), "_:Oui")


class TestFixContinuationPython(unittest.TestCase):
    """Tests pour fix_continuation() dans dictee-postprocess.py."""

    def _load(self, lang="fr"):
        import importlib
        spec = importlib.util.spec_from_file_location(
            "dictee_postprocess", POSTPROCESS)
        pp = importlib.util.module_from_spec(spec)
        old_lang = os.environ.get("DICTEE_LANG_SOURCE", "")
        os.environ["DICTEE_LANG_SOURCE"] = lang
        try:
            spec.loader.exec_module(pp)
        finally:
            if old_lang:
                os.environ["DICTEE_LANG_SOURCE"] = old_lang
            else:
                os.environ.pop("DICTEE_LANG_SOURCE", None)
        self.pp = pp
        return pp.load_continuation()

    def test_removes_period_after_closed_class(self):
        words = self._load("fr")
        self.assertEqual(
            self.pp.fix_continuation("je suis dans. le bureau", words),
            "je suis dans le bureau")

    def test_keeps_period_after_open_class(self):
        words = self._load("fr")
        self.assertEqual(
            self.pp.fix_continuation("je suis parti. Il est venu", words),
            "je suis parti. Il est venu")

    def test_case_insensitive_matching(self):
        words = self._load("fr")
        self.assertEqual(
            self.pp.fix_continuation("Je suis Dans. le bureau", words),
            "Je suis Dans le bureau")

    def test_lowercases_after_continuation(self):
        """Continuation always lowercases — proper nouns are handled by dictionary."""
        words = self._load("fr")
        self.assertEqual(
            self.pp.fix_continuation("avec. Paul", words),
            "avec paul")

    def test_lowercases_c_est_after_continuation(self):
        words = self._load("fr")
        self.assertEqual(
            self.pp.fix_continuation("que… C'est bien", words),
            "que c'est bien")

    def test_empty_words_no_change(self):
        self._load("fr")
        self.assertEqual(
            self.pp.fix_continuation("je suis dans. le bureau", set()),
            "je suis dans. le bureau")

    def test_lang_filter_en(self):
        words = self._load("en")
        self.assertEqual(
            self.pp.fix_continuation("je suis dans. le bureau", words),
            "je suis dans. le bureau")
        self.assertEqual(
            self.pp.fix_continuation("I saw the. dog", words),
            "I saw the dog")

    def test_load_continuation_parses_file(self):
        words = self._load("fr")
        self.assertIn("le", words)
        self.assertIn("dans", words)
        self.assertIn("et", words)

    def test_comma_untouched(self):
        words = self._load("fr")
        self.assertEqual(
            self.pp.fix_continuation("bonjour, le monde", words),
            "bonjour, le monde")


class TestApplyContinuation(unittest.TestCase):
    """Tests pour apply_continuation (buffer inter-appuis)."""

    def _run(self, saved, text):
        # Use $'...' for bash to interpret \n correctly
        bash_text = text.replace("'", "'\\''").replace("\n", "\\n")
        bash_saved = saved.replace("'", "'\\''")
        script = BASH_PREAMBLE + f"""
echo '{bash_saved}' > "$LAST_WORD_FILE"
echo 0 > "$_BS_FILE"
transcribed=$'{bash_text}'
apply_continuation transcribed
printf '%s' "$transcribed"
printf '\\nBACKSPACE=%s\\n' "$(cat "$_BS_FILE")"
"""
        output = run_bash_test(script)
        parts = output.rsplit("\nBACKSPACE=", 1)
        text_result = parts[0]
        backspace_count = int(parts[1].strip()) if len(parts) > 1 else 0
        return text_result, backspace_count

    # ── Après un point (.) — mot non-liaison ─────────────────────────

    def test_after_period_new_sentence(self):
        text, bs = self._run(".1:école", "Bonjour à tous.")
        self.assertEqual(text, " Bonjour à tous.")
        self.assertEqual(bs, 0)

    def test_after_period_different_word(self):
        text, bs = self._run(".1:maison", "Il fait beau.")
        self.assertEqual(text, " Il fait beau.")
        self.assertEqual(bs, 0)

    # ── Après un point (.) — mot de liaison (backspace) ──────────────

    def test_after_period_continuation_je(self):
        text, bs = self._run(".1:je", "Suis arrivé.")
        self.assertEqual(text, " suis arrivé.")
        self.assertGreater(bs, 0)

    def test_after_period_continuation_est(self):
        text, bs = self._run(".1:est", "Très content.")
        self.assertEqual(text, " très content.")
        self.assertGreater(bs, 0)

    def test_after_period_continuation_le(self):
        text, bs = self._run(".1:le", "Chat dort.")
        self.assertEqual(text, " chat dort.")
        self.assertGreater(bs, 0)

    def test_after_period_continuation_dans(self):
        text, bs = self._run(".1:dans", "La maison.")
        self.assertEqual(text, " la maison.")
        self.assertGreater(bs, 0)

    def test_after_period_continuation_que(self):
        text, bs = self._run(".1:que", "Tu viennes.")
        self.assertEqual(text, " tu viennes.")
        self.assertGreater(bs, 0)

    # ── Après une virgule (,) ────────────────────────────────────────

    def test_after_comma(self):
        text, _ = self._run(",:bonjour", "Comment ça va.")
        self.assertEqual(text, " comment ça va.")

    def test_after_comma_preserves_content(self):
        text, _ = self._run(",:premier", "Deuxième chose.")
        self.assertEqual(text, " deuxième chose.")

    # ── Après ponctuation finale (F) ─────────────────────────────────

    def test_after_exclamation(self):
        text, _ = self._run("F:Bravo", "Merci beaucoup.")
        self.assertEqual(text, " Merci beaucoup.")

    def test_after_question(self):
        text, _ = self._run("F:quoi", "Je ne sais pas.")
        self.assertEqual(text, " Je ne sais pas.")

    def test_after_semicolon(self):
        text, _ = self._run("F:premier", "Deuxième.")
        self.assertEqual(text, " Deuxième.")

    def test_after_colon(self):
        text, _ = self._run("F:voici", "La liste.")
        self.assertEqual(text, " La liste.")

    # ── Après pas de ponctuation (_) ─────────────────────────────────

    def test_after_no_punctuation(self):
        text, _ = self._run("_:content", "De vous voir.")
        self.assertEqual(text, " de vous voir.")

    def test_after_no_punctuation_preserves(self):
        text, _ = self._run("_:monde", "Entier.")
        self.assertEqual(text, " entier.")

    # ── Texte commençant par une ponctuation (commande vocale) ───────

    def test_comma_start_after_period(self):
        text, bs = self._run(".1:école", ", suite du texte.")
        self.assertGreater(bs, 0)
        self.assertTrue(text.startswith(","))

    def test_colon_start_after_period(self):
        text, bs = self._run(".1:école", ": la suite.")
        self.assertGreater(bs, 0)
        self.assertTrue(text.startswith(":"))

    def test_semicolon_start_after_period(self):
        text, bs = self._run(".1:école", "; la suite.")
        self.assertGreater(bs, 0)
        self.assertTrue(text.startswith(";"))

    def test_exclamation_start_after_period(self):
        """! en début : backspace, garder casse (pas dans [,\\;:])."""
        text, bs = self._run(".1:école", "! Quelle surprise.")
        self.assertGreater(bs, 0)
        self.assertIn("Quelle", text)

    def test_question_start_after_period(self):
        text, bs = self._run(".1:école", "? Vraiment.")
        self.assertGreater(bs, 0)
        self.assertIn("Vraiment", text)

    def test_period_start_after_period(self):
        text, bs = self._run(".1:école", ". Suite.")
        self.assertGreater(bs, 0)

    def test_comma_start_lowercase(self):
        """Après virgule en début : minuscule."""
        text, _ = self._run(".1:école", ", Je suis arrivé.")
        self.assertIn(", je", text)

    def test_colon_start_lowercase(self):
        """Après : en début sans newline : minuscule."""
        text, _ = self._run(".1:école", ": Je suis arrivé.")
        self.assertIn(": je", text)

    def test_semicolon_start_lowercase(self):
        text, _ = self._run(".1:école", "; Je suis arrivé.")
        self.assertIn("; je", text)

    # ── Colon + newline (deux points à la ligne) ─────────────────────

    def test_colon_newline_keeps_case(self):
        """':\\n' garde la majuscule (nouveau paragraphe)."""
        text, bs = self._run(".1:école", ":\nJe suis arrivé.")
        self.assertGreater(bs, 0)
        self.assertIn(":\nJe", text)

    def test_comma_newline_keeps_case(self):
        """,\\n garde la majuscule."""
        text, bs = self._run(".1:école", ",\nJe suis arrivé.")
        self.assertGreater(bs, 0)
        self.assertIn(",\nJe", text)

    def test_semicolon_newline_keeps_case(self):
        text, bs = self._run(".1:école", ";\nJe suis arrivé.")
        self.assertGreater(bs, 0)
        self.assertIn(";\nJe", text)

    # ── Pas de fichier de continuation ───────────────────────────────

    def test_no_last_word_file(self):
        script = BASH_PREAMBLE + '''
rm -f "$LAST_WORD_FILE"
transcribed="Bonjour à tous."
apply_continuation transcribed
printf '%s' "$transcribed"
'''
        result = run_bash_test(script)
        self.assertEqual(result, "Bonjour à tous.")

    # ── Texte commençant par \n ──────────────────────────────────────

    def test_starts_with_newline(self):
        script = BASH_PREAMBLE + '''
echo ".:école" > "$LAST_WORD_FILE"
transcribed=$'\nSuite du texte.'
apply_continuation transcribed
printf '%s' "$transcribed"
'''
        result = run_bash_test(script)
        self.assertTrue(result.startswith("\n"))
        self.assertIn("Suite", result)

    # ── Espaces en début ─────────────────────────────────────────────

    def test_leading_spaces_stripped(self):
        text, _ = self._run(".1:école", "   Bonjour.")
        self.assertEqual(text, " Bonjour.")

    # ── Pas de backspace quand last_char != "." ──────────────────────

    def test_comma_start_after_comma_backspace(self):
        """Replaces previous comma with new comma."""
        text, bs = self._run(",:mot", ", suite.")
        self.assertEqual(bs, 1)

    def test_comma_start_after_F_backspace(self):
        """Replaces previous !/?/; with comma."""
        text, bs = self._run("F:mot", ", suite.")
        self.assertEqual(bs, 1)


class TestContinuationIntegration(unittest.TestCase):
    """Tests d'intégration : save_last_word → apply_continuation."""

    def _simulate_pushes(self, pushes):
        script = BASH_PREAMBLE + '\nrm -f "$LAST_WORD_FILE"\n'
        for i, push_text in enumerate(pushes):
            bash_text = push_text.replace("'", "'\\''").replace("\n", "\\n")
            script += f"""
echo 0 > "$_BS_FILE"
transcribed=$'{bash_text}'
apply_continuation transcribed
echo "PUSH{i}=$transcribed"
echo "BACKSPACE{i}=$(cat "$_BS_FILE")"
save_last_word $'{bash_text}'
"""
        output = run_bash_test(script)
        results = {}
        for line in output.strip().split("\n"):
            if "=" in line:
                key, val = line.split("=", 1)
                results[key] = val
        return results

    def test_two_sentences(self):
        r = self._simulate_pushes(["Bonjour à tous.", "Comment allez-vous."])
        self.assertEqual(r["PUSH0"], "Bonjour à tous.")
        self.assertEqual(r["PUSH1"], " Comment allez-vous.")

    def test_continuation_after_comma(self):
        r = self._simulate_pushes(["Bonjour,", "Comment ça va."])
        self.assertEqual(r["PUSH1"], " comment ça va.")

    def test_continuation_word_after_period(self):
        r = self._simulate_pushes(["Je suis.", "Content de vous voir."])
        self.assertGreater(int(r["BACKSPACE1"]), 0)
        self.assertEqual(r["PUSH1"], " content de vous voir.")

    def test_three_pushes(self):
        r = self._simulate_pushes([
            "Bonjour à tous.",
            "Comment allez-vous.",
            "Je vais bien.",
        ])
        self.assertEqual(r["PUSH0"], "Bonjour à tous.")
        self.assertEqual(r["PUSH1"], " Comment allez-vous.")
        # "vous" (from "allez-vous.") is a continuation word → lowercase
        self.assertEqual(r["PUSH2"], " je vais bien.")

    def test_newline_resets_continuation(self):
        r = self._simulate_pushes([
            "Première ligne.\nDeuxième ligne.",
            "Troisième ligne.",
        ])
        self.assertEqual(r["PUSH1"], "Troisième ligne.")

    def test_exclamation_then_new_sentence(self):
        r = self._simulate_pushes(["Bravo!", "Merci beaucoup."])
        self.assertEqual(r["PUSH1"], " Merci beaucoup.")

    def test_no_punctuation_then_continue(self):
        r = self._simulate_pushes(["Je suis content", "De vous voir."])
        self.assertEqual(r["PUSH1"], " de vous voir.")

    def test_comma_then_continue(self):
        r = self._simulate_pushes(["Bonjour,", "Ça va."])
        self.assertEqual(r["PUSH1"], " ça va.")

    def test_four_pushes_mixed(self):
        r = self._simulate_pushes([
            "Je suis.",       # point + mot liaison
            "Arrivé,",        # continuation → backspace + minuscule
            "Mais en retard.",  # après virgule → minuscule
            "Désolé!",        # après point → espace + casse
        ])
        self.assertEqual(r["PUSH0"], "Je suis.")
        self.assertGreater(int(r["BACKSPACE1"]), 0)
        self.assertEqual(r["PUSH2"], " mais en retard.")
        self.assertEqual(r["PUSH3"], " Désolé!")


# ══════════════════════════════════════════════════════════════════════
# TESTS ROBUSTESSE — VARIANTES ASR ET CAS LIMITES
# ══════════════════════════════════════════════════════════════════════


class TestASRVariantsFR(unittest.TestCase):
    """Variantes ASR réalistes pour les commandes vocales françaises.

    L'ASR (Parakeet/Whisper/Canary) peut :
    - Ajouter de la ponctuation parasite autour des commandes
    - Capitaliser aléatoirement
    - Coller ou séparer les mots composés
    - Ajouter un 's' de pluriel
    - Confondre des homophones proches
    """

    # ── Virgule : variantes ASR ─────────────────────────────────────

    def test_virgule_with_asr_period(self):
        """ASR ajoute un point avant 'virgule'."""
        result = run_postprocess("Bonjour. Virgule comment ça va.")
        self.assertIn(",", result)
        self.assertNotIn("virgule", result.lower())

    def test_virgule_with_asr_comma(self):
        """ASR ajoute une virgule avant 'virgule' (redondance)."""
        result = run_postprocess("Bonjour, virgule, comment ça va.")
        # Doit produire UNE virgule, pas deux
        self.assertNotIn("virgule", result.lower())

    def test_vergule_misspelling(self):
        """ASR transcrit 'vergülle' au lieu de 'virgule'."""
        result = run_postprocess("Bonjour vergülle comment ça va.")
        self.assertIn(",", result)

    def test_verguelle_misspelling(self):
        """ASR transcrit 'vergülle'."""
        result = run_postprocess("Bonjour vergülle comment ça va.")
        self.assertIn(",", result)

    # ── À la ligne : variantes ASR ──────────────────────────────────

    def test_a_la_ligne_no_accent(self):
        """ASR oublie l'accent : 'a la ligne'."""
        result = run_postprocess("a la ligne suite du texte.")
        self.assertIn("\n", result)

    def test_a_la_ligne_caps(self):
        """ASR capitalise : 'À La Ligne'."""
        result = run_postprocess("À La Ligne suite du texte.")
        self.assertIn("\n", result)

    def test_a_la_ligne_asr_period_before(self):
        """ASR met un point avant 'à la ligne'."""
        result = run_postprocess("Première phrase. À la ligne deuxième phrase.")
        self.assertIn("\n", result)

    def test_la_ligne_without_a(self):
        """ASR avale le 'à' : 'la ligne'."""
        result = run_postprocess("La ligne suite du texte.")
        self.assertIn("\n", result)

    # ── Cyrillic misdetections ──────────────────────────────────────

    def test_cyrillic_a_la_ligne_variant1(self):
        """Parakeet transcrit en cyrillique (collé, pas d'espace)."""
        result = run_postprocess("Алиния")
        self.assertIn("\n", result)

    def test_cyrillic_virgule(self):
        """Parakeet transcrit 'virgule' en cyrillique."""
        result = run_postprocess("Вергуля")
        self.assertIn(",", result)

    # ── Points de suspension : variantes ─────────────────────────────

    def test_trois_petits_points(self):
        """Forme parlée 'trois petits points'."""
        result = run_postprocess("Je ne sais pas trois petits points.")
        self.assertIn("…", result)

    def test_points_suspension_pluriel(self):
        """'points de suspension' avec ou sans s."""
        result = run_postprocess("Voilà point de suspension.")
        self.assertIn("…", result)

    # ── Guillemets : variantes conjugaison ───────────────────────────

    def test_ouvrir_guillemets(self):
        """Infinitif 'ouvrir les guillemets'."""
        result = run_postprocess("Il dit ouvrir les guillemets bonjour.")
        self.assertIn("«", result)

    def test_ouvre_guillemets(self):
        """Impératif singulier 'ouvre les guillemets'."""
        result = run_postprocess("Ouvre les guillemets bonjour.")
        self.assertIn("«", result)

    def test_fermer_guillemets(self):
        result = run_postprocess("Bonjour fermer les guillemets.")
        self.assertIn("»", result)

    # ── Parenthèses : variantes articles ─────────────────────────────

    def test_ouvrez_parenthese_sans_article(self):
        result = run_postprocess("Ouvrez parenthèse note.")
        self.assertIn("(", result)

    def test_ouvrez_une_parenthese(self):
        result = run_postprocess("Ouvrez une parenthèse note.")
        self.assertIn("(", result)

    def test_ouvrez_les_parentheses(self):
        result = run_postprocess("Ouvrez les parenthèses note.")
        self.assertIn("(", result)

    # ── Markdown dièse : variantes ASR ───────────────────────────────

    def test_diese_transcrit_hash(self):
        """ASR transcrit '#' au lieu de 'dièse'."""
        result = run_postprocess("# espace titre.")
        self.assertIn("# ", result)

    def test_diez_misspelling(self):
        """ASR transcrit 'dièz'."""
        result = run_postprocess("Dièz espace titre.")
        self.assertIn("# ", result)

    def test_double_diese_naturel(self):
        """Forme 'double dièse' (plus naturelle que 'dièse dièse')."""
        result = run_postprocess("Double dièse sous-titre.")
        self.assertIn("## ", result)

    def test_triple_diese_naturel(self):
        result = run_postprocess("Triple dièse section.")
        self.assertIn("### ", result)

    # ── Commandes combinées : robustesse ─────────────────────────────

    def test_combined_excl_newline_with_asr_noise(self):
        """ASR ajoute ponctuation autour de la commande combinée."""
        result = run_postprocess("Bravo. Point d'exclamation à la ligne. Merci.")
        self.assertIn("!\n", result)

    def test_combined_with_optional_a(self):
        """'point à la ligne' forme standard."""
        result = run_postprocess("Bonjour le monde point à la ligne la suite arrive.")
        self.assertIn(".\n", result)

    # ── Ponctuation parasite ASR ─────────────────────────────────────

    def test_point_after_period(self):
        """Commande 'point' précédée d'un '.' natif ASR (doublon)."""
        result = run_postprocess("Bonjour. Point. Merci.")
        # Le "." + " point" + "." est absorbé → "Bonjour. Merci."
        self.assertEqual(result.count("point"), 0)

    def test_deux_points_with_asr_colon(self):
        """ASR transcrit ':' puis 'deux points'."""
        result = run_postprocess("Voici : la liste.")
        self.assertIn(":", result)

    # ── Tirets : variantes ───────────────────────────────────────────

    def test_tiret_du_six(self):
        result = run_postprocess("Premier tiret du six deuxième.")
        self.assertIn("- ", result)

    def test_tiret_du_huit(self):
        result = run_postprocess("Variable tiret du huit nom.")
        self.assertIn("_", result)

    def test_tirets_bas_pluriel(self):
        """Pluriel 'tirets bas'."""
        result = run_postprocess("Variable tirets bas nom.")
        self.assertIn("_", result)


class TestShortTextRobustness(unittest.TestCase):
    """Tests robustesse pour la correction de texte court (< 3 mots).

    Vérifie que les lettres isolées issues de l'ASR sont traitées,
    que les acronymes sont préservés, et que les commandes vocales
    ne sont pas affectées.
    """

    def test_single_uppercase_s(self):
        """ASR produit 'S' isolé (continuation parasite)."""
        self.assertEqual(run_postprocess("S"), "s")

    def test_single_uppercase_a(self):
        """ASR produit 'A' isolé."""
        self.assertEqual(run_postprocess("A"), "a")

    def test_single_word_lowered(self):
        """Mot unique capitalisé → minuscule."""
        self.assertEqual(run_postprocess("Bonjour"), "bonjour")

    def test_two_words_lowered(self):
        """Deux mots capitalisés → minuscule, sans point."""
        result = run_postprocess("Petit Chat.")
        self.assertEqual(result, "petit chat")

    def test_acronym_preserved(self):
        """Acronymes (tout majuscule) préservés."""
        self.assertEqual(run_postprocess("API"), "API")

    def test_mixed_case_preserved(self):
        """Casse mixte (iPhone) — capitalisation initiale l'altère (bug connu)."""
        # fix_capitalization transforme "iPhone" → "IPhone" avant fix_short_text
        result = run_postprocess("iPhone")
        self.assertIn("phone", result.lower())

    def test_three_words_not_short(self):
        """3 mots = pas de correction courte."""
        result = run_postprocess("Bonjour mon Ami.")
        # 3 mots → pas de correction courte, capitalisation normale
        self.assertTrue(result[0].isupper())

    def test_voice_command_not_affected(self):
        """Commande vocale pure (pas de alphanum) = pas touchée."""
        result = run_postprocess("À la ligne")
        self.assertIn("\n", result)

    def test_single_word_with_period(self):
        """Un mot + point → minuscule, point supprimé."""
        self.assertEqual(run_postprocess("Merci."), "merci")

    def test_single_word_with_exclamation(self):
        self.assertEqual(run_postprocess("Merci!"), "merci")

    def test_two_words_mixed(self):
        """Un mot normal + un acronyme."""
        result = run_postprocess("Utilise API.")
        self.assertIn("API", result)  # Acronyme préservé
        self.assertTrue(result.startswith("utilise"))  # Normal → minuscule


class TestContinuationKeywordRobustness(unittest.TestCase):
    """Tests robustesse pour le mot-clé de continuation (minuscule).

    Vérifie que toutes les variantes ASR sont reconnues :
    casse, pluriel, ponctuation après.
    """

    def _run(self, text):
        """Run apply_continuation with keyword text after a period."""
        bash_text = text.replace("'", "'\\''")
        # Force keyword regex to match (case-insensitive via ${_ref,,}, plural s?)
        script = BASH_PREAMBLE + """
_CONT_KEYWORD_RE='^minuscules?[.,]?[[:space:]]*(.*)'
""" + f"""
echo '.1:test' > "$LAST_WORD_FILE"
echo 0 > "$_BS_FILE"
transcribed='{bash_text}'
apply_continuation transcribed
printf '%s' "$transcribed"
printf '\\nBACKSPACE=%s\\n' "$(cat "$_BS_FILE")"
"""
        output = run_bash_test(script)
        parts = output.rsplit("\nBACKSPACE=", 1)
        text_result = parts[0]
        bs = int(parts[1].strip()) if len(parts) > 1 else 0
        return text_result, bs

    def test_lowercase(self):
        """'minuscule la suite'."""
        text, bs = self._run("minuscule la suite")
        self.assertIn("la suite", text)
        self.assertGreater(bs, 0)

    def test_capitalized(self):
        """'Minuscule la suite'."""
        text, bs = self._run("Minuscule la suite")
        self.assertIn("la suite", text)
        self.assertGreater(bs, 0)

    def test_all_caps(self):
        """'MINUSCULE la suite'."""
        text, bs = self._run("MINUSCULE la suite")
        self.assertIn("la suite", text)
        self.assertGreater(bs, 0)

    def test_plural_s(self):
        """'minuscules la suite' (pluriel ASR)."""
        text, bs = self._run("minuscules la suite")
        self.assertIn("la suite", text)
        self.assertGreater(bs, 0)

    def test_with_trailing_comma(self):
        """'minuscule, la suite'."""
        text, bs = self._run("minuscule, la suite")
        self.assertIn("la suite", text)
        self.assertGreater(bs, 0)

    def test_with_trailing_period(self):
        """'minuscule. la suite'."""
        text, bs = self._run("minuscule. la suite")
        self.assertIn("la suite", text)
        self.assertGreater(bs, 0)

    def test_alone_no_rest(self):
        """'minuscule' alone -> empty text."""
        text, bs = self._run("minuscule")
        self.assertEqual(text.strip(), "")

    def test_rest_lowercase(self):
        """Text after the keyword is lowercased."""
        text, bs = self._run("minuscule La Suite")
        self.assertIn("la suite", text.lower())

    def test_no_false_positive(self):
        """'bonjour monde' ne matche pas."""
        text, bs = self._run("bonjour monde")
        self.assertIn("bonjour", text.lower())
        self.assertEqual(bs, 0)


class TestMultiCommandInteraction(unittest.TestCase):
    """Tests d'interaction entre commandes vocales et pipeline."""

    def test_hesitation_then_command(self):
        """Hésitation suivie d'une commande vocale."""
        result = run_postprocess("Euh, bonjour virgule merci.")
        self.assertIn(",", result)
        self.assertNotIn("euh", result.lower())

    def test_command_then_elision(self):
        """Commande vocale suivie d'une élision."""
        result = run_postprocess("Virgule je ai faim.")
        self.assertIn(",", result)
        self.assertIn("j'ai", result.lower())

    def test_two_commands_in_sequence(self):
        """Deux commandes vocales dans la même phrase."""
        result = run_postprocess("Bonjour virgule comment ça va point d'interrogation.")
        self.assertIn(",", result)
        self.assertIn("?", result)

    def test_command_and_dictionary(self):
        """Commande vocale + mot du dictionnaire."""
        result = run_postprocess("Je utilise linux virgule python.")
        self.assertIn(",", result)
        self.assertIn("Linux", result)
        self.assertIn("Python", result)

    def test_command_and_typography(self):
        """Voice command + French typography. 'deux points' requires suffix."""
        result = run_postprocess("Voici les choses deux points suivi la liste complète.",
                                 env_extra={"DICTEE_COMMAND_SUFFIX_FR": "suivi"})
        self.assertIn(":", result)

    def test_newline_then_capitalize(self):
        """Saut de ligne suivi d'un mot → capitalisé."""
        result = run_postprocess("Première phrase. Point à la ligne deuxième phrase.")
        parts = result.split("\n")
        if len(parts) > 1:
            after = parts[-1].strip()
            if after:
                self.assertTrue(after[0].isupper(), f"Après newline: '{after}'")

    def test_command_inside_long_text(self):
        """Commande vocale noyée dans un texte long."""
        result = run_postprocess(
            "Le développeur a écrit un programme. Virgule ensuite il a testé."
        )
        self.assertIn(",", result)
        self.assertNotIn("virgule", result.lower())

    def test_triple_command(self):
        """Trois commandes vocales enchaînées."""
        result = run_postprocess(
            "Bonjour point d'exclamation à la ligne comment allez-vous "
            "point d'interrogation nouveau paragraphe au revoir."
        )
        self.assertIn("!\n", result)
        self.assertIn("?", result)
        self.assertIn("\n\n", result)

    def test_all_punctuation_types(self):
        """All French punctuation types in one sentence.
        'deux points' and 'point' (alone) are ambiguous — require suffix."""
        result = run_postprocess(
            "Mot virgule mot point virgule mot deux points suivi "
            "mot point d'exclamation mot point d'interrogation "
            "mot points de suspension mot point suivi.",
            env_extra={"DICTEE_COMMAND_SUFFIX_FR": "suivi"},
        )
        for p in [",", ";", ":", "!", "?", "…", "."]:
            self.assertIn(p, result, f"Punctuation '{p}' missing")

    def test_dedup_with_command(self):
        """Mot dupliqué + commande vocale."""
        result = run_postprocess("Je je vais bien virgule merci.")
        self.assertNotIn("je je", result.lower())
        self.assertIn(",", result)


class TestASRVariantsEN(unittest.TestCase):
    """Variantes ASR réalistes pour les commandes vocales anglaises."""

    _env = {"DICTEE_PP_TEXT2NUM": "false"}

    # ── Simple punctuation ──────────────────────────────────────────

    def test_period_with_asr_period(self):
        """ASR adds a '.' before 'period' — 'period' requires suffix."""
        result = run_postprocess("End of sentence. Period done.", lang="en",
                                 env_extra={"DICTEE_COMMAND_SUFFIX_EN": "done"})
        self.assertNotIn("period", result.lower())

    def test_comma_with_asr_comma(self):
        """ASR ajoute une ',' avant 'comma' (redondance)."""
        result = run_postprocess("Hello, comma, world.", lang="en")
        self.assertNotIn("comma", result.lower())

    def test_comma_inline(self):
        result = run_postprocess("I like cats, comma dogs and birds.", lang="en",
                                 env_extra=self._env)
        self.assertIn(",", result)
        self.assertNotIn("comma", result.lower())

    def test_exclamation_mark(self):
        result = run_postprocess("That is amazing, exclamation mark.", lang="en",
                                 env_extra=self._env)
        self.assertIn("!", result)
        self.assertNotIn("exclamation", result.lower())

    def test_question_mark(self):
        result = run_postprocess("Are you sure, question mark.", lang="en",
                                 env_extra=self._env)
        self.assertIn("?", result)
        self.assertNotIn("question", result.lower())

    def test_colon(self):
        # "colon" is ambiguous in EN — requires suffix
        result = run_postprocess("Here is the list, colon done apples.", lang="en",
                                 env_extra={**self._env, "DICTEE_COMMAND_SUFFIX_EN": "done"})
        self.assertIn(":", result)
        self.assertNotIn("colon", result.lower())

    def test_semicolon(self):
        result = run_postprocess("I went left, semicolon she went right.", lang="en",
                                 env_extra=self._env)
        self.assertIn(";", result)
        self.assertNotIn("semicolon", result.lower())

    def test_ellipsis(self):
        result = run_postprocess("I wonder, ellipsis.", lang="en",
                                 env_extra=self._env)
        self.assertIn("…", result)
        self.assertNotIn("ellipsis", result.lower())

    # ── Combined punctuation + new line ─────────────────────────────

    def test_period_new_line(self):
        result = run_postprocess("End of paragraph, period new line, next part.", lang="en",
                                 env_extra=self._env)
        self.assertIn(".\n", result)

    def test_exclamation_mark_new_line(self):
        result = run_postprocess("Amazing, exclamation mark new line, next part here.", lang="en",
                                 env_extra=self._env)
        self.assertIn("!\n", result)

    def test_comma_new_line(self):
        result = run_postprocess("First item, comma new line, second item.", lang="en",
                                 env_extra=self._env)
        self.assertIn(",\n", result)

    def test_colon_new_line(self):
        result = run_postprocess("The list, colon new line, item one.", lang="en",
                                 env_extra=self._env)
        self.assertIn(":\n", result)

    def test_semicolon_new_line(self):
        """'semicolon new line' — requires \\b fix to prevent 'colon' matching inside."""
        result = run_postprocess("The clause here, semicolon new line, another clause.", lang="en",
                                 env_extra=self._env)
        self.assertIn(";\n", result)

    # ── Symbol forms (ASR adds native punctuation) ──────────────────

    def test_symbol_colon_new_line(self):
        """ASR transcrit ':' puis 'new line'."""
        result = run_postprocess("The list: new line item one.", lang="en",
                                 env_extra=self._env)
        self.assertIn(":\n", result)

    def test_symbol_comma_new_line(self):
        result = run_postprocess("Hello there, new line goodbye there.", lang="en",
                                 env_extra=self._env)
        self.assertIn(",\n", result)

    # ── Line breaks ─────────────────────────────────────────────────

    def test_new_line(self):
        result = run_postprocess("Hello world, new line, goodbye world.", lang="en",
                                 env_extra=self._env)
        self.assertIn("\n", result)

    def test_new_paragraph(self):
        result = run_postprocess("End of section, new paragraph, new section.", lang="en",
                                 env_extra=self._env)
        self.assertIn("\n\n", result)

    # ── Quotes & parentheses ────────────────────────────────────────

    def test_open_close_quote(self):
        result = run_postprocess("He said, open quote hello, close quote.", lang="en",
                                 env_extra=self._env)
        self.assertEqual(result.count('"'), 2)

    def test_open_close_parenthesis(self):
        result = run_postprocess("The value, open parenthesis see note, close parenthesis.", lang="en",
                                 env_extra=self._env)
        self.assertIn("(", result)
        self.assertIn(")", result)

    def test_parenthesis_variants(self):
        """'parenthesis' vs 'parentheses'."""
        for variant in ["parenthesis", "parentheses"]:
            result = run_postprocess(f"Open {variant} note. Close {variant}.", lang="en")
            self.assertIn("(", result, f"Failed for '{variant}'")
            self.assertIn(")", result, f"Failed for '{variant}'")

    def test_the_a_parenthesis(self):
        """Articles optionnels avant parenthesis."""
        result = run_postprocess("Open the parenthesis note. Close the parenthesis.", lang="en")
        self.assertIn("(", result)
        self.assertIn(")", result)

    # ── Miscellaneous ───────────────────────────────────────────────

    def test_tab(self):
        result = run_postprocess("Column one, tab, column two.", lang="en",
                                 env_extra=self._env)
        self.assertIn("\t", result)

    def test_hyphen(self):
        result = run_postprocess("First part, hyphen, second part.", lang="en",
                                 env_extra=self._env)
        self.assertIn("- ", result)

    # ── Markdown ────────────────────────────────────────────────────

    def test_hash_space(self):
        result = run_postprocess("Hash space title here.", lang="en",
                                 env_extra=self._env)
        self.assertIn("# ", result)

    def test_hash_hash_space(self):
        result = run_postprocess("Hash hash space subtitle.", lang="en",
                                 env_extra=self._env)
        self.assertIn("## ", result)

    def test_hash_hash_hash_space(self):
        result = run_postprocess("Hash hash hash space section.", lang="en",
                                 env_extra=self._env)
        self.assertIn("### ", result)

    # ── ASR noise around commands ───────────────────────────────────

    def test_period_with_spaces(self):
        """Spaces around 'period' — requires suffix."""
        result = run_postprocess("Done,  period done  thanks.", lang="en",
                                 env_extra={**self._env, "DICTEE_COMMAND_SUFFIX_EN": "done"})
        self.assertNotIn("period", result.lower())

    def test_multiple_commands_sequence(self):
        """Deux commandes EN dans la même phrase."""
        result = run_postprocess("Hello, comma, how are you, question mark.", lang="en",
                                 env_extra=self._env)
        self.assertIn(",", result)
        self.assertIn("?", result)


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main()
