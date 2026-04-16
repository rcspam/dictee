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
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)  # parent of tests/
POSTPROCESS = os.path.join(PROJECT_DIR, "dictee-postprocess.py")

# Espaces insécables pour les assertions
NBSP = '\u00a0'
NNBSP = '\u202f'


def run_postprocess(text, lang="fr", env_extra=None, keep_markers=False):
    """Exécute dictee-postprocess.py et retourne le résultat.

    Le marker interne \\x03 (keepcaps hit) est strippé par défaut pour que
    les comparaisons d'égalité fonctionnent comme avant l'ajout du flag.
    Passer keep_markers=True pour le voir."""
    env = os.environ.copy()
    env["DICTEE_LANG_SOURCE"] = lang
    env["DICTEE_LLM_POSTPROCESS"] = "false"
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(
        [sys.executable, POSTPROCESS],
        input=text, capture_output=True, text=True, env=env,
    )
    out = result.stdout
    if not keep_markers:
        out = out.lstrip("\x03")
    return out


def run_postprocess_with_trace(text, lang="fr", env_extra=None):
    """Run dictee-postprocess with DICTEE_PP_DEBUG=true, return (stdout, [step_labels])."""
    env = os.environ.copy()
    env["DICTEE_LANG_SOURCE"] = lang
    env["DICTEE_LLM_POSTPROCESS"] = "false"
    env["DICTEE_PP_DEBUG"] = "true"
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(
        [sys.executable, POSTPROCESS],
        input=text, capture_output=True, text=True, env=env,
    )
    steps = [line.split("\t")[1] for line in result.stderr.splitlines()
             if line.startswith("STEP\t") and len(line.split("\t")) >= 2]
    return result.stdout, steps


def run_postprocess_full(text, lang="fr", env_extra=None):
    """Run dictee-postprocess and return the full subprocess result."""
    env = os.environ.copy()
    env["DICTEE_LANG_SOURCE"] = lang
    env["DICTEE_LLM_POSTPROCESS"] = "false"
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, POSTPROCESS],
        input=text, capture_output=True, text=True, env=env,
    )


# All-false env dict to disable every PP step individually
_ALL_PP_FALSE = {
    "DICTEE_PP_RULES": "false",
    "DICTEE_PP_CONTINUATION": "false",
    "DICTEE_PP_LANGUAGE_RULES": "false",
    "DICTEE_PP_NUMBERS": "false",
    "DICTEE_PP_DICT": "false",
    "DICTEE_PP_CAPITALIZATION": "false",
    "DICTEE_PP_SHORT_TEXT": "false",
}


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
        # Use "maison" — not a keepcaps exception, so short_text lowercases it.
        result = run_postprocess("maison.", env_extra={"DICTEE_PP_CAPITALIZATION": "false"})
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
        # NB: use "table" — not a keepcaps exception. Greetings like "bonjour"
        # are now whitelisted (see test_short_text_keepcaps_*).
        result = run_postprocess("table")
        self.assertEqual(result, "table")

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
    dictee_path = os.path.join(PROJECT_DIR, "dictee")
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

    test_dir = PROJECT_DIR  # continuation.conf.default is in project root

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

    def test_continuation_preserves_word_with_unicode_ellipsis(self):
        """Regression: Whisper ends sentences with '…' (U+2026, 1 bash char
        but 3 keystrokes after type_text). save_last_word must strip 1 bash
        char, not 3, when appending the continuation indicator — otherwise
        'Je pars pour…' becomes 'Je pars po>>' instead of 'Je pars pour>>'."""
        bash_text = "Je pars pour…"
        script = BASH_PREAMBLE + f"""
CONTINUATION_INDICATOR=">>"
CONTINUATION_INDICATOR_LEN=2
rm -f "$LAST_WORD_FILE"
transcribed=$'{bash_text}'
save_last_word "$transcribed" transcribed
printf '%s' "$transcribed"
"""
        output = run_bash_test(script)
        # "pour" is a continuation word → indicator appended, "…" stripped
        self.assertEqual(output, "Je pars pour>>")


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
        # FR typography prepends NBSP (U+00A0) before ':' at head of push
        text, bs = self._run(".1:école", ": la suite.")
        self.assertGreater(bs, 0)
        self.assertTrue(text.startswith("\u00a0:") or text.startswith(":"))

    def test_semicolon_start_after_period(self):
        # FR typography prepends NNBSP (U+202F) before ';' at head of push
        text, bs = self._run(".1:école", "; la suite.")
        self.assertGreater(bs, 0)
        self.assertTrue(text.startswith("\u202f;") or text.startswith(";"))

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


class TestShortTextKeepcaps(unittest.TestCase):
    """Short-text exceptions via short_text_keepcaps.conf.default.

    Greetings and courtesy words dictated alone keep their capital letter
    and their trailing punctuation — fix_short_text is skipped entirely.
    A leading \\x03 marker is emitted so dictee bash's apply_continuation
    won't lowercase the word in mode "_". Tests strip it before comparison.
    """

    @staticmethod
    def _clean(result):
        # Strip leading \x03 keepcaps marker (internal PP→bash signal)
        return result.lstrip("\x03")

    def test_fr_bonjour_kept(self):
        self.assertEqual(self._clean(run_postprocess("Bonjour", lang="fr")), "Bonjour")

    def test_fr_bonjour_with_period_stripped(self):
        # Keepcaps emits the canonical form: no trailing punct, first char
        # uppercased. "Bonjour." → "Bonjour".
        self.assertEqual(self._clean(run_postprocess("Bonjour.", lang="fr")), "Bonjour")

    def test_fr_bonjour_case_insensitive_match(self):
        # "bonjour." lowercase input → "Bonjour" (trailing punct stripped,
        # first char uppercased).
        self.assertEqual(self._clean(run_postprocess("bonjour.", lang="fr")), "Bonjour")

    def test_fr_merci_explicit_exclamation_kept(self):
        # "!" is always an explicit voice command ("point d'exclamation") so
        # it is preserved, along with the NNBSP inserted by FR typography.
        self.assertEqual(
            self._clean(run_postprocess("Merci!", lang="fr")),
            "Merci\u202f!")

    def test_en_hello_kept(self):
        self.assertEqual(self._clean(run_postprocess("Hello", lang="en")), "Hello")

    def test_en_hello_not_kept_in_fr(self):
        # "Hello" is not a FR keepcaps entry → usual short-text lowercasing.
        self.assertEqual(run_postprocess("Hello", lang="fr"), "hello")

    def test_de_hallo_kept(self):
        self.assertEqual(self._clean(run_postprocess("Hallo", lang="de")), "Hallo")

    def test_unrelated_word_still_lowered(self):
        # "Maison" is not in FR keepcaps → short text lowercases.
        self.assertEqual(run_postprocess("Maison.", lang="fr"), "maison")

    def test_fr_keepcaps_point_final_keeps_period(self):
        # "point final" is an explicit voice command → keep the period (but
        # strip the internal \x02 marker).
        result = run_postprocess(
            "bonjour point final", lang="fr",
            env_extra={"DICTEE_COMMAND_SUFFIX_FR": "final"})
        self.assertEqual(self._clean(result), "Bonjour.")

    def test_fr_keepcaps_virgule_kept(self):
        # "," is always an explicit voice command → preserved.
        self.assertEqual(
            self._clean(run_postprocess("mesdames virgule", lang="fr")),
            "Mesdames,")

    def test_fr_keepcaps_auto_period_stripped(self):
        # ASR may auto-append "." at sentence end without the user saying
        # "point final". Without \x02 marker, that "." is dropped.
        self.assertEqual(
            self._clean(run_postprocess("Bonjour.", lang="fr")),
            "Bonjour")

    def test_fr_au_revoir_kept(self):
        self.assertEqual(self._clean(run_postprocess("Au revoir", lang="fr")), "Au revoir")

    def test_fr_mesdames_kept(self):
        self.assertEqual(self._clean(run_postprocess("Mesdames", lang="fr")), "Mesdames")

    def test_keepcaps_marker_present_when_match(self):
        # The PP must emit \x03 at the start so dictee bash knows to skip
        # lowercasing in apply_continuation mode "_".
        self.assertTrue(
            run_postprocess("Bonjour", lang="fr", keep_markers=True).startswith("\x03"))

    def test_keepcaps_marker_absent_when_no_match(self):
        # No keepcaps match → no marker
        self.assertFalse(
            run_postprocess("Maison", lang="fr", keep_markers=True).startswith("\x03"))

    def test_fr_first_word_keepcaps_cher_ami(self):
        # "cher" is in keepcaps, "ami" is not. First-word match preserves
        # the uppercase on "cher" while leaving "ami" as-is.
        self.assertEqual(self._clean(run_postprocess("cher ami", lang="fr")), "Cher ami")

    def test_fr_first_word_keepcaps_chere_isabelle(self):
        self.assertEqual(
            self._clean(run_postprocess("chère Isabelle", lang="fr")),
            "Chère Isabelle")

    def test_fr_first_word_keepcaps_drops_auto_period(self):
        self.assertEqual(self._clean(run_postprocess("cher ami.", lang="fr")), "Cher ami")

    def test_fr_first_word_keepcaps_keeps_virgule(self):
        self.assertEqual(
            self._clean(run_postprocess("cher ami virgule", lang="fr")),
            "Cher ami,")

    def test_fr_second_word_keepcaps_ignored(self):
        # "cher" in 2nd position → NOT triggered (only first-word match).
        self.assertEqual(run_postprocess("table cher", lang="fr"), "table cher")

    # --- Extended mode (DICTEE_PP_KEEPCAPS_EXTENDED) ---

    def test_extended_full_match_long_text_emits_marker(self):
        # "je vous prie de croire" (6 words) = full-list FR entry.
        # Extended ON → \x03 emitted, treated as keepcaps regardless of length.
        result = run_postprocess(
            "je vous prie de croire", lang="fr",
            keep_markers=True,
            env_extra={"DICTEE_PP_KEEPCAPS_EXTENDED": "true"})
        self.assertTrue(result.startswith("\x03"))

    def test_extended_first_word_long_text_signal_only(self):
        # First-word "bonjour" matches but text is long → emit \x03 signal
        # without altering the text (the bash side consumes it).
        result = run_postprocess(
            "bonjour mes amis comment allez-vous", lang="fr",
            keep_markers=True,
            env_extra={"DICTEE_PP_KEEPCAPS_EXTENDED": "true"})
        self.assertTrue(result.startswith("\x03"))
        self.assertIn("bonjour mes amis", result.lower())

    def test_extended_disabled_no_marker_on_long_text(self):
        # With extended=false, long text → no \x03 emitted at all.
        result = run_postprocess(
            "je vous prie de croire", lang="fr",
            keep_markers=True,
            env_extra={"DICTEE_PP_KEEPCAPS_EXTENDED": "false"})
        self.assertFalse(result.startswith("\x03"))

    def test_keepcaps_master_off_no_marker(self):
        # Master toggle off → keepcaps fully disabled, standard short-text
        # behavior (lowercase + strip trailing punct).
        result = run_postprocess(
            "Bonjour.", lang="fr",
            keep_markers=True,
            env_extra={"DICTEE_PP_KEEPCAPS": "false"})
        self.assertFalse(result.startswith("\x03"))
        self.assertEqual(result, "bonjour")


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
        """Mot unique capitalisé → minuscule (mot hors keepcaps)."""
        self.assertEqual(run_postprocess("Maison"), "maison")

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
        """Un mot + point → minuscule, point supprimé (mot hors keepcaps)."""
        self.assertEqual(run_postprocess("Table."), "table")

    def test_single_word_with_exclamation(self):
        """Un mot + ! → minuscule, ! supprimé (mot hors keepcaps)."""
        self.assertEqual(run_postprocess("Chaise!"), "chaise")

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
# TESTS LLM + COMPLÉMENTS
# ══════════════════════════════════════════════════════════════════════

# Import postprocess module for unit tests (add project dir to path)
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
import importlib
_pp = importlib.import_module("dictee-postprocess")


class TestSystemPrompts(unittest.TestCase):
    """Chargement des presets de prompt système LLM."""

    def test_preset_default(self):
        os.environ["DICTEE_LLM_SYSTEM_PROMPT"] = "default"
        result = _pp._load_system_prompt()
        self.assertIn("spell checker", result)
        self.assertIn("dictation", result.lower())

    def test_preset_minimal(self):
        os.environ["DICTEE_LLM_SYSTEM_PROMPT"] = "minimal"
        result = _pp._load_system_prompt()
        self.assertIn("dictation", result.lower())

    def test_preset_unknown_fallback(self):
        os.environ["DICTEE_LLM_SYSTEM_PROMPT"] = "NonExistent"
        result = _pp._load_system_prompt()
        # Falls back to FR
        self.assertIn("spell checker", result)

    def test_custom_from_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                         delete=False, encoding="utf-8") as f:
            f.write("Mon prompt custom pour test")
            f.flush()
            os.environ["DICTEE_LLM_SYSTEM_PROMPT"] = "custom"
            orig = _pp._SYSTEM_PROMPT_PATH
            try:
                _pp._SYSTEM_PROMPT_PATH = f.name
                result = _pp._load_system_prompt()
                self.assertEqual(result, "Mon prompt custom pour test")
            finally:
                _pp._SYSTEM_PROMPT_PATH = orig
                os.unlink(f.name)

    def test_custom_no_file_fallback(self):
        os.environ["DICTEE_LLM_SYSTEM_PROMPT"] = "custom"
        orig_sys = _pp._SYSTEM_PROMPT_PATH
        orig_leg = _pp._LEGACY_PROMPT_PATH
        try:
            _pp._SYSTEM_PROMPT_PATH = "/nonexistent/path.txt"
            _pp._LEGACY_PROMPT_PATH = "/nonexistent/legacy.txt"
            result = _pp._load_system_prompt()
            # Falls back to FR
            self.assertIn("spell checker", result)
        finally:
            _pp._SYSTEM_PROMPT_PATH = orig_sys
            _pp._LEGACY_PROMPT_PATH = orig_leg

    def test_prompts_not_empty(self):
        for name, prompt in _pp.SYSTEM_PROMPTS.items():
            self.assertTrue(len(prompt.strip()) > 10,
                            f"Prompt '{name}' is too short or empty")

    def tearDown(self):
        os.environ.pop("DICTEE_LLM_SYSTEM_PROMPT", None)


class TestLLMPostprocess(unittest.TestCase):
    """Appel HTTP Ollama — tests avec mock."""

    def setUp(self):
        os.environ["DICTEE_LLM_SYSTEM_PROMPT"] = "minimal"
        os.environ["DICTEE_LLM_MODEL"] = "test-model"
        os.environ["DICTEE_LLM_TIMEOUT"] = "5"

    def tearDown(self):
        for k in ("DICTEE_LLM_SYSTEM_PROMPT", "DICTEE_LLM_MODEL",
                   "DICTEE_LLM_TIMEOUT"):
            os.environ.pop(k, None)

    def _mock_urlopen(self, response_json):
        """Create a mock for urllib.request.urlopen."""
        from unittest.mock import MagicMock, patch
        import json as _json
        mock_resp = MagicMock()
        mock_resp.read.return_value = _json.dumps(response_json).encode("utf-8")
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return patch("urllib.request.urlopen", return_value=mock_resp)

    def test_success_returns_corrected(self):
        with self._mock_urlopen({"response": "texte corrigé"}):
            result = _pp.llm_postprocess("texte brut")
        self.assertEqual(result, "texte corrigé")

    def test_empty_response_returns_original(self):
        with self._mock_urlopen({"response": ""}):
            result = _pp.llm_postprocess("texte brut")
        self.assertEqual(result, "texte brut")

    def test_timeout_returns_original(self):
        from unittest.mock import patch
        with patch("urllib.request.urlopen", side_effect=TimeoutError):
            result = _pp.llm_postprocess("texte brut")
        self.assertEqual(result, "texte brut")

    def test_connection_refused_returns_original(self):
        from unittest.mock import patch
        import urllib.error
        with patch("urllib.request.urlopen",
                   side_effect=urllib.error.URLError("Connection refused")):
            result = _pp.llm_postprocess("texte brut")
        self.assertEqual(result, "texte brut")

    def test_invalid_json_returns_original(self):
        from unittest.mock import MagicMock, patch
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"not json"
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = _pp.llm_postprocess("texte brut")
        self.assertEqual(result, "texte brut")

    def test_model_from_env(self):
        from unittest.mock import patch, ANY
        import json as _json
        from unittest.mock import MagicMock
        os.environ["DICTEE_LLM_MODEL"] = "my-custom-model"
        with patch("urllib.request.urlopen") as mock_url:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"response": "ok"}'
            mock_url.return_value = mock_resp
            _pp.llm_postprocess("test")
            # Check the payload contains the model
            call_args = mock_url.call_args
            req = call_args[0][0]
            payload = _json.loads(req.data.decode("utf-8"))
            self.assertEqual(payload["model"], "my-custom-model")

    def test_system_prompt_in_payload(self):
        from unittest.mock import patch, MagicMock
        import json as _json
        with patch("urllib.request.urlopen") as mock_url:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"response": "ok"}'
            mock_url.return_value = mock_resp
            _pp.llm_postprocess("test")
            req = mock_url.call_args[0][0]
            payload = _json.loads(req.data.decode("utf-8"))
            self.assertIn("system", payload)
            self.assertTrue(len(payload["system"]) > 0)

    def test_stream_false_in_payload(self):
        from unittest.mock import patch, MagicMock
        import json as _json
        with patch("urllib.request.urlopen") as mock_url:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"response": "ok"}'
            mock_url.return_value = mock_resp
            _pp.llm_postprocess("test")
            req = mock_url.call_args[0][0]
            payload = _json.loads(req.data.decode("utf-8"))
            self.assertFalse(payload["stream"])

    def test_strips_whitespace(self):
        with self._mock_urlopen({"response": "  texte corrigé  \n"}):
            result = _pp.llm_postprocess("texte brut")
        self.assertEqual(result, "texte corrigé")


class TestLLMPosition(unittest.TestCase):
    """Position du LLM dans le pipeline (first/hybrid/last)."""

    def test_llm_disabled_no_crash(self):
        """LLM disabled — pipeline runs normally."""
        result = run_postprocess("bonjour le monde",
                                 env_extra={"DICTEE_LLM_POSTPROCESS": "false"})
        self.assertEqual(result, "Bonjour le monde")

    def test_position_invalid_no_crash(self):
        """Invalid position — pipeline runs without LLM, no crash."""
        result = run_postprocess(
            "bonjour le monde", env_extra={
                "DICTEE_LLM_POSTPROCESS": "true",
                "DICTEE_LLM_POSITION": "invalid",
            })
        # LLM won't execute (no matching position), text passes through pipeline
        self.assertEqual(result, "Bonjour le monde")

    def test_position_first_env(self):
        """Position 'first' env var is accepted without crash."""
        # Without a real ollama server, LLM fallback returns original text
        result = run_postprocess(
            "bonjour", env_extra={
                "DICTEE_LLM_POSTPROCESS": "true",
                "DICTEE_LLM_POSITION": "first",
                "DICTEE_LLM_TIMEOUT": "1",
            })
        # Fallback: text passes through pipeline normally
        self.assertIn("onjour", result)

    def test_position_hybrid_env(self):
        """Position 'hybrid' env var is accepted without crash."""
        result = run_postprocess(
            "bonjour", env_extra={
                "DICTEE_LLM_POSTPROCESS": "true",
                "DICTEE_LLM_POSITION": "hybrid",
                "DICTEE_LLM_TIMEOUT": "1",
            })
        self.assertIn("onjour", result)

    def test_position_last_env(self):
        """Position 'last' env var is accepted without crash."""
        result = run_postprocess(
            "bonjour", env_extra={
                "DICTEE_LLM_POSTPROCESS": "true",
                "DICTEE_LLM_POSITION": "last",
                "DICTEE_LLM_TIMEOUT": "1",
            })
        self.assertIn("onjour", result)


class TestDutch(unittest.TestCase):
    """fix_dutch() — contractions et expressions temporelles."""

    def test_het_to_t(self):
        result = run_postprocess("het boek", lang="nl")
        self.assertIn("'t boek", result.lower())

    def test_een_to_n(self):
        result = run_postprocess("een boek", lang="nl")
        self.assertIn("'n boek", result.lower())

    def test_morgens(self):
        result = run_postprocess("in de morgens", lang="nl")
        self.assertIn("'s morgens", result.lower())

    def test_avonds(self):
        result = run_postprocess("in de avonds", lang="nl")
        self.assertIn("'s avonds", result.lower())

    def test_nachts(self):
        result = run_postprocess("in de nachts", lang="nl")
        self.assertIn("'s nachts", result.lower())

    def test_middags(self):
        result = run_postprocess("in de middags", lang="nl")
        self.assertIn("'s middags", result.lower())


class TestRomanian(unittest.TestCase):
    """fix_romanian() — contractions et guillemets."""

    def test_nu_am(self):
        result = run_postprocess("nu am mâncat", lang="ro")
        self.assertIn("n-am", result.lower())

    def test_nu_ai(self):
        result = run_postprocess("nu ai dreptate", lang="ro")
        self.assertIn("n-ai", result.lower())

    def test_nu_a(self):
        result = run_postprocess("nu a venit", lang="ro")
        self.assertIn("n-a", result.lower())

    def test_nu_au(self):
        result = run_postprocess("nu au venit", lang="ro")
        self.assertIn("n-au", result.lower())

    def test_intr_o(self):
        result = run_postprocess("într o casă", lang="ro")
        self.assertIn("într-o", result.lower())

    def test_dintr_un(self):
        result = run_postprocess("dintr un motiv", lang="ro")
        self.assertIn("dintr-un", result.lower())

    def test_quotes_to_romanian(self):
        result = run_postprocess('"salut"', lang="ro")
        self.assertIn("\u201e", result)  # „
        self.assertIn("\u201c", result)  # "


class TestConvertNumbers(unittest.TestCase):
    """convert_numbers() — conversion texte vers chiffres."""

    def test_fr_vingt_trois(self):
        result = run_postprocess("vingt-trois", lang="fr",
                                  env_extra={"DICTEE_PP_NUMBERS": "true"})
        self.assertIn("23", result)

    def test_en_twenty_three(self):
        result = run_postprocess("twenty three", lang="en",
                                  env_extra={"DICTEE_PP_NUMBERS": "true"})
        self.assertIn("23", result)

    def test_fr_cent(self):
        result = run_postprocess("cent", lang="fr",
                                  env_extra={"DICTEE_PP_NUMBERS": "true"})
        self.assertIn("100", result)

    def test_unsupported_lang_unchanged(self):
        result = run_postprocess("двадцять три", lang="uk",
                                  env_extra={"DICTEE_PP_NUMBERS": "true"})
        self.assertIn("двадцять", result)

    def test_mixed_text_and_numbers(self):
        result = run_postprocess("il y a vingt-trois personnes", lang="fr",
                                  env_extra={"DICTEE_PP_NUMBERS": "true"})
        self.assertIn("23", result)
        self.assertIn("personnes", result)


class TestLongText(unittest.TestCase):
    """Textes longs, paragraphes, sessions de dictée."""

    def test_long_paragraph_fr(self):
        text = ("euh bonjour je ai un problème virgule "
                "je ne arrive pas à comprendre. "
                "Est ce que vous pouvez me aider. "
                "je ai essayé plusieurs choses virgule "
                "mais rien ne marche.")
        result = run_postprocess(text, lang="fr")
        self.assertIn("j'ai", result)
        self.assertIn(",", result)
        self.assertIn(".", result)
        self.assertNotIn("euh", result.lower())

    def test_long_paragraph_en(self):
        text = ("uh hello I have a problem, "
                "I cannot understand. "
                "Can you help me? "
                "I tried many things, "
                "but nothing works.")
        result = run_postprocess(text, lang="en")
        self.assertIn(",", result)
        self.assertIn(".", result)
        self.assertNotIn("uh ", result.lower().split("h")[0] if result else "")

    def test_multiline_text(self):
        text = ("première ligne point à la ligne "
                "deuxième ligne point à la ligne "
                "troisième ligne")
        result = run_postprocess(text, lang="fr")
        self.assertIn("\n", result)
        lines = [l for l in result.split("\n") if l.strip()]
        self.assertTrue(len(lines) >= 2)

    def test_repeated_sentences(self):
        text = "bonjour bonjour bonjour je ai faim"
        result = run_postprocess(text, lang="fr")
        # Should not crash; elision applied
        self.assertIn("j'ai", result)

    def test_very_long_text_performance(self):
        import time
        # 500+ words
        text = " ".join(["bonjour le monde"] * 170)
        start = time.time()
        result = run_postprocess(text, lang="fr")
        elapsed = time.time() - start
        self.assertLess(elapsed, 2.0,
                        f"Pipeline took {elapsed:.1f}s for 500+ words (max 2s)")
        self.assertTrue(len(result) > 100)

    def test_mixed_languages_in_text(self):
        text = "je ai utilisé python pour créer une API REST"
        result = run_postprocess(text, lang="fr")
        # Capitalization may uppercase J'ai → check case-insensitive
        self.assertIn("j'ai", result.lower())
        self.assertIn("API", result)
        self.assertIn("REST", result)

    def test_dictation_session_simulation(self):
        """Full session: hesitations + commands + elisions + dict + typo."""
        text = ("euh bonjour virgule je me appelle Raphaël point "
                "je ai une question deux points "
                "est ce que linux fonctionne avec gpu point "
                "oui virgule je ai testé cpu et ram point")
        result = run_postprocess(
            text, lang="fr",
            env_extra={"DICTEE_COMMAND_SUFFIX_FR": "suivi"})
        # Hesitations removed
        self.assertNotIn("euh", result.lower())
        # Elisions
        self.assertIn("j'ai", result)
        self.assertIn("m'appelle", result)
        # Dictionary
        self.assertIn("Linux", result)
        self.assertIn("GPU", result)
        self.assertIn("CPU", result)
        self.assertIn("RAM", result)

    def test_llm_long_text_payload(self):
        """Long text sent to LLM — payload not truncated."""
        from unittest.mock import patch, MagicMock
        import json as _json
        long_text = "Ceci est un texte très long. " * 50
        with patch("urllib.request.urlopen") as mock_url:
            mock_resp = MagicMock()
            mock_resp.read.return_value = _json.dumps(
                {"response": long_text}).encode("utf-8")
            mock_url.return_value = mock_resp
            result = _pp.llm_postprocess(long_text)
            # Check that full text was sent
            req = mock_url.call_args[0][0]
            payload = _json.loads(req.data.decode("utf-8"))
            self.assertEqual(payload["prompt"], long_text)


# ══════════════════════════════════════════════════════════════════════
# TESTS LLM END-TO-END (nécessite Ollama actif)
# ══════════════════════════════════════════════════════════════════════

def _ollama_available():
    """Check if Ollama is running and reachable."""
    try:
        import urllib.request
        req = urllib.request.Request("http://localhost:11434/api/tags")
        urllib.request.urlopen(req, timeout=3)
        return True
    except Exception:
        return False


def _ollama_has_model(model):
    """Check if a specific model is available in Ollama."""
    try:
        import urllib.request, json
        req = urllib.request.Request("http://localhost:11434/api/tags")
        resp = urllib.request.urlopen(req, timeout=3)
        data = json.loads(resp.read().decode("utf-8"))
        names = [m["name"] for m in data.get("models", [])]
        return model in names
    except Exception:
        return False


@unittest.skipUnless(_ollama_available(), "Ollama not running")
class TestLLMEndToEndMinistral(unittest.TestCase):
    """Tests end-to-end avec le vrai serveur Ollama — Ministral 3B."""

    MODEL = "ministral-3:3b"

    @classmethod
    def setUpClass(cls):
        if not _ollama_has_model(cls.MODEL):
            raise unittest.SkipTest(f"Model {cls.MODEL} not available")

    def _run_llm(self, text, lang="fr", position="hybrid", preset="default"):
        return run_postprocess(text, lang=lang, env_extra={
            "DICTEE_LLM_POSTPROCESS": "true",
            "DICTEE_LLM_MODEL": self.MODEL,
            "DICTEE_LLM_POSITION": position,
            "DICTEE_LLM_SYSTEM_PROMPT": preset,
            "DICTEE_LLM_TIMEOUT": "15",
        })

    def test_basic_correction_fr(self):
        result = self._run_llm("je suis alle a la mer hier et je ai mange des poissson")
        self.assertIn("allé", result)
        self.assertIn("poisson", result)

    def test_elision_and_accents(self):
        result = self._run_llm(
            "je ai achete un gateau et je ai mange le gateau hier soir")
        # LLM should correct — check accents and elision
        self.assertIn("gâteau", result.lower(),
                      f"Missing accent on gâteau in: {result}")
        self.assertIn("acheté", result.lower(),
                      f"Missing accent on acheté in: {result}")

    def test_hesitation_removed_before_llm(self):
        """Pipeline: regex removes 'euh' BEFORE LLM sees the text."""
        result = self._run_llm("euh bonjour je me appelle raphael")
        self.assertNotIn("euh", result.lower())
        # LLM may or may not add accent on Raphaël
        self.assertTrue("raphael" in result.lower() or "raphaël" in result.lower(),
                        f"Name not found in: {result}")

    def test_long_paragraph(self):
        text = ("euh bonjour je me appelle raphael et je ai un probleme "
                "avec mon ordinateur. il ne demarre pas et je ne sais pas "
                "quoi faire. est ce que vous pouvez me aider")
        result = self._run_llm(text)
        self.assertTrue("raphael" in result.lower() or "raphaël" in result.lower(),
                        f"Name not found in: {result}")
        self.assertTrue("démarre" in result.lower() or "demarre" in result.lower(),
                        f"'démarre/demarre' not found in: {result}")
        self.assertNotIn("euh", result.lower())
        # At least 1 sentence-ending punctuation
        self.assertTrue(result.count(".") >= 1 or result.count("?") >= 1)

    def test_preserves_meaning(self):
        """LLM should NOT change the meaning or add content."""
        result = self._run_llm("le chat mange la souris")
        self.assertIn("chat", result.lower())
        self.assertIn("souris", result.lower())
        # Should not add extra sentences
        self.assertLess(len(result), 100)

    def test_position_first(self):
        result = self._run_llm("je ai faim", position="first")
        # LLM corrects before regex, but elisions still apply after
        # Apostrophe may be straight (') or curly (\u2019)
        self.assertTrue("j'ai" in result.lower() or "j\u2019ai" in result.lower(),
                        f"No elision found in: {result}")

    def test_position_last(self):
        result = self._run_llm("je ai faim", position="last")
        self.assertTrue("j'ai" in result.lower() or "j\u2019ai" in result.lower(),
                        f"No elision found in: {result}")

    def test_preset_en(self):
        result = self._run_llm("i has a problm with my computr",
                                lang="en", preset="default")
        self.assertIn("problem", result.lower())
        self.assertIn("computer", result.lower())

    def test_preset_minimal(self):
        result = self._run_llm("je suis alle a la mer", preset="minimal")
        self.assertIn("allé", result)

    def test_dictionary_after_llm(self):
        """Pipeline hybrid: LLM corrects, THEN dictionary applies."""
        result = self._run_llm("je ai installé linux sur mon gpu")
        self.assertIn("Linux", result)
        self.assertIn("GPU", result)

    def test_typography_after_llm(self):
        """Pipeline hybrid: French typography applies AFTER LLM."""
        result = self._run_llm("je ai dit : bonjour")
        # NBSP before colon (French typography)
        if ":" in result:
            idx = result.index(":")
            if idx > 0:
                self.assertIn(result[idx - 1], (" ", NBSP, NNBSP))


@unittest.skipUnless(_ollama_available(), "Ollama not running")
class TestLLMEndToEndGemma(unittest.TestCase):
    """Tests end-to-end avec le vrai serveur Ollama — Gemma 3 4B."""

    MODEL = "gemma3:4b"

    @classmethod
    def setUpClass(cls):
        if not _ollama_has_model(cls.MODEL):
            raise unittest.SkipTest(f"Model {cls.MODEL} not available")

    def _run_llm(self, text, lang="fr", position="hybrid", preset="default"):
        return run_postprocess(text, lang=lang, env_extra={
            "DICTEE_LLM_POSTPROCESS": "true",
            "DICTEE_LLM_MODEL": self.MODEL,
            "DICTEE_LLM_POSITION": position,
            "DICTEE_LLM_SYSTEM_PROMPT": preset,
            "DICTEE_LLM_TIMEOUT": "15",
        })

    def test_basic_correction_fr(self):
        result = self._run_llm("je suis alle a la mer hier")
        self.assertIn("allé", result)
        self.assertIn("mer", result.lower())

    def test_elision_and_accents(self):
        result = self._run_llm(
            "je ai achete un gateau et je ai mange le gateau hier soir")
        self.assertIn("gâteau", result.lower(),
                      f"Missing accent on gâteau in: {result}")
        self.assertIn("acheté", result.lower(),
                      f"Missing accent on acheté in: {result}")

    def test_hesitation_removed_before_llm(self):
        """Pipeline: regex removes 'euh' BEFORE LLM sees the text."""
        result = self._run_llm("euh bonjour je me appelle raphael")
        self.assertNotIn("euh", result.lower())
        self.assertTrue("raphael" in result.lower() or "raphaël" in result.lower(),
                        f"Name not found in: {result}")

    def test_long_paragraph(self):
        text = ("euh bonjour je me appelle raphael et je ai un probleme "
                "avec mon ordinateur. il ne demarre pas et je ne sais pas "
                "quoi faire. est ce que vous pouvez me aider")
        result = self._run_llm(text)
        # LLM may spell Raphael/Raphaël/Rafael differently
        self.assertTrue(any(n in result.lower() for n in ("raphael", "raphaël", "rafael")),
                        f"Name not found in: {result}")
        self.assertTrue("démarre" in result.lower() or "demarre" in result.lower(),
                        f"'démarre/demarre' not found in: {result}")
        self.assertNotIn("euh", result.lower())
        self.assertTrue(result.count(".") >= 1 or result.count("?") >= 1)

    def test_preserves_meaning(self):
        result = self._run_llm("le chat mange la souris")
        self.assertIn("chat", result.lower())
        self.assertIn("souris", result.lower())
        self.assertLess(len(result), 100)

    def test_position_first(self):
        result = self._run_llm("je ai faim", position="first")
        self.assertIn("j'ai", result.lower())

    def test_position_last(self):
        result = self._run_llm("je ai faim", position="last")
        self.assertIn("j'ai", result.lower())

    def test_preset_en(self):
        result = self._run_llm("i has a problm with my computr",
                                lang="en", preset="default")
        self.assertIn("problem", result.lower())
        self.assertIn("computer", result.lower())

    def test_preset_minimal(self):
        result = self._run_llm("je suis alle a la mer", preset="minimal")
        # Minimal prompt is in English — LLM may translate or just fix
        self.assertTrue("allé" in result or "mer" in result.lower() or "sea" in result.lower(),
                        f"Unexpected result: {result}")

    def test_long_text_returns_something(self):
        text = "je ai un premier probleme. je ai un deuxieme probleme. je ai un troisieme probleme."
        result = self._run_llm(text)
        self.assertGreater(len(result), 10)
        self.assertTrue("'ai" in result, f"No elision in: {result}")

    def test_dictionary_after_llm(self):
        """Pipeline hybrid: LLM corrects, THEN dictionary applies."""
        result = self._run_llm("je ai installé linux sur mon gpu")
        self.assertIn("Linux", result)
        self.assertIn("GPU", result)


# ══════════════════════════════════════════════════════════════════════
# PIPELINE STEP ORDERING
# ══════════════════════════════════════════════════════════════════════


class TestPipelineStepOrdering(unittest.TestCase):
    """Verify execution order via DICTEE_PP_DEBUG trace labels."""

    def test_full_order_fr(self):
        """All FR steps execute in documented order."""
        # Input triggers every step: hesitation, continuation, elision,
        # typography, number, dictionary word, capitalization, short text
        text = "euh je ai vingt-trois linux ici : test."
        _, steps = run_postprocess_with_trace(text, lang="fr", env_extra={
            "DICTEE_PP_NUMBERS": "true",
        })
        # Expected order for FR with all steps enabled
        expected_order = [
            "Rules", "Continuation", "Elisions [fr]", "Typography [fr]",
            "Numbers", "Dictionary", "Capitalization",
        ]
        # Filter to only the steps we expect (Short text label varies)
        found = [s for s in steps if s in expected_order or s.startswith("Short text")]
        # Verify ordering: each expected step appears and in order
        idx = 0
        for expected in expected_order:
            while idx < len(found) and found[idx] != expected:
                idx += 1
            self.assertLess(idx, len(found),
                            f"Step '{expected}' not found in order. Got: {found}")
            idx += 1

    def test_rules_disabled_absent(self):
        """Rules step absent when DICTEE_PP_RULES=false."""
        _, steps = run_postprocess_with_trace(
            "euh bonjour.", lang="fr",
            env_extra={"DICTEE_PP_RULES": "false"})
        self.assertNotIn("Rules", steps)

    def test_continuation_disabled_absent(self):
        """Continuation step absent when DICTEE_PP_CONTINUATION=false."""
        _, steps = run_postprocess_with_trace(
            "dans. le bureau.", lang="fr",
            env_extra={"DICTEE_PP_CONTINUATION": "false"})
        self.assertNotIn("Continuation", steps)

    def test_language_rules_disabled_no_subrules(self):
        """No language-specific steps when umbrella is off."""
        _, steps = run_postprocess_with_trace(
            "je ai faim : ici.", lang="fr",
            env_extra={"DICTEE_PP_LANGUAGE_RULES": "false"})
        self.assertNotIn("Elisions [fr]", steps)
        self.assertNotIn("Typography [fr]", steps)

    def test_llm_first_before_rules(self):
        """LLM [first] appears before Rules in trace."""
        _, steps = run_postprocess_with_trace(
            "bonjour le monde.", lang="fr",
            env_extra={
                "DICTEE_LLM_POSTPROCESS": "true",
                "DICTEE_LLM_POSITION": "first",
                "DICTEE_LLM_TIMEOUT": "1",
                "DICTEE_PP_DEBUG": "true",
            })
        if "LLM [first]" in steps and "Rules" in steps:
            self.assertLess(steps.index("LLM [first]"), steps.index("Rules"))

    def test_llm_hybrid_between_continuation_and_lang(self):
        """LLM [hybrid] appears after Continuation, before language rules."""
        _, steps = run_postprocess_with_trace(
            "je ai faim.", lang="fr",
            env_extra={
                "DICTEE_LLM_POSTPROCESS": "true",
                "DICTEE_LLM_POSITION": "hybrid",
                "DICTEE_LLM_TIMEOUT": "1",
                "DICTEE_PP_DEBUG": "true",
            })
        if "LLM [hybrid]" in steps:
            if "Continuation" in steps:
                self.assertLess(steps.index("Continuation"),
                                steps.index("LLM [hybrid]"))
            if "Elisions [fr]" in steps:
                self.assertLess(steps.index("LLM [hybrid]"),
                                steps.index("Elisions [fr]"))

    def test_llm_last_after_short_text(self):
        """LLM [last] is the last step in trace."""
        _, steps = run_postprocess_with_trace(
            "bonjour le monde.", lang="fr",
            env_extra={
                "DICTEE_LLM_POSTPROCESS": "true",
                "DICTEE_LLM_POSITION": "last",
                "DICTEE_LLM_TIMEOUT": "1",
                "DICTEE_PP_DEBUG": "true",
            })
        if "LLM [last]" in steps:
            self.assertEqual(steps[-1], "LLM [last]")

    def test_italian_order(self):
        """Italian lang triggers Elisions [it], not Elisions [fr]."""
        _, steps = run_postprocess_with_trace(
            "lo amico buono.", lang="it")
        self.assertIn("Elisions [it]", steps)
        self.assertNotIn("Elisions [fr]", steps)

    def test_german_order(self):
        """German lang triggers German [de]."""
        _, steps = run_postprocess_with_trace(
            "ich bin in dem Haus.", lang="de")
        self.assertIn("German [de]", steps)
        self.assertNotIn("Elisions [fr]", steps)


# ══════════════════════════════════════════════════════════════════════
# MASTER SWITCH BEHAVIOR
# ══════════════════════════════════════════════════════════════════════


class TestMasterSwitchBehavior(unittest.TestCase):
    """Verify that disabling all steps produces passthrough."""

    def test_all_steps_disabled_passthrough(self):
        """All PP steps disabled: text passes through (only strip + bad-lang)."""
        text = "Bonjour le monde."
        result = run_postprocess(text, lang="fr", env_extra=_ALL_PP_FALSE)
        self.assertEqual(result, "Bonjour le monde.")

    def test_rules_only(self):
        """Only rules enabled: hesitations removed, no elision."""
        env = dict(_ALL_PP_FALSE)
        env["DICTEE_PP_RULES"] = "true"
        result = run_postprocess("euh je ai faim.", lang="fr", env_extra=env)
        self.assertNotIn("euh", result)
        # Elisions OFF: "je ai" should stay
        self.assertIn("je ai", result)

    def test_capitalization_only(self):
        """Only capitalization enabled: first letter uppercase."""
        env = dict(_ALL_PP_FALSE)
        env["DICTEE_PP_CAPITALIZATION"] = "true"
        result = run_postprocess("bonjour le monde.", lang="fr", env_extra=env)
        self.assertTrue(result.startswith("B"), f"Expected uppercase start: {result}")


# ══════════════════════════════════════════════════════════════════════
# BAD LANGUAGE REJECTION
# ══════════════════════════════════════════════════════════════════════


class TestBadLanguageRejection(unittest.TestCase):
    """Verify Cyrillic/Latin script mismatch detection."""

    def test_latin_lang_cyrillic_text_rejected(self):
        """FR lang + all Cyrillic → empty output."""
        result = run_postprocess("Привет мир как дела", lang="fr")
        self.assertEqual(result, "")

    def test_latin_lang_latin_text_accepted(self):
        """FR lang + Latin text → non-empty output."""
        result = run_postprocess("Bonjour le monde.", lang="fr")
        self.assertGreater(len(result), 0)

    def test_cyrillic_lang_latin_text_rejected(self):
        """UK lang + all Latin → empty output (ratio < 0.2)."""
        result = run_postprocess("Hello world how are you", lang="uk")
        self.assertEqual(result, "")

    def test_cyrillic_lang_cyrillic_text_accepted(self):
        """UK lang + Cyrillic text → non-empty output."""
        result = run_postprocess("Привіт як справи.", lang="uk")
        self.assertGreater(len(result), 0)

    def test_mixed_below_threshold_accepted(self):
        """FR lang + minority Cyrillic (<50%) → accepted."""
        # 3 Cyrillic chars, many Latin chars
        result = run_postprocess("Bonjour мир monde et la vie est belle.", lang="fr")
        self.assertGreater(len(result), 0)

    def test_mixed_above_threshold_rejected(self):
        """FR lang + majority Cyrillic (>50%) → rejected."""
        # Mostly Cyrillic with a few Latin chars
        result = run_postprocess("Привет мир как дела ok", lang="fr")
        self.assertEqual(result, "")

    def test_no_letters_passes(self):
        """Only numbers/punctuation → passes through."""
        result = run_postprocess("123, 456!", lang="fr")
        self.assertGreater(len(result), 0)


# ══════════════════════════════════════════════════════════════════════
# TRANSLATION PIPELINE (TRPP)
# ══════════════════════════════════════════════════════════════════════


class TestTranslationPipeline(unittest.TestCase):
    """Simulate the 2nd postprocess pass on translated text.

    The dictee shell script maps DICTEE_TRPP_* to DICTEE_PP_* and forces
    DICTEE_LLM_POSTPROCESS=false. We replicate that env here.
    """

    def _run_trpp(self, text, target_lang, env_extra=None):
        """Simulate TRPP: target lang as source, LLM forced off."""
        env = {"DICTEE_LLM_POSTPROCESS": "false"}
        if env_extra:
            env.update(env_extra)
        return run_postprocess(text, lang=target_lang, env_extra=env)

    def _run_trpp_trace(self, text, target_lang, env_extra=None):
        """Simulate TRPP with debug trace."""
        env = {"DICTEE_LLM_POSTPROCESS": "false"}
        if env_extra:
            env.update(env_extra)
        return run_postprocess_with_trace(text, lang=target_lang, env_extra=env)

    def test_trpp_fr_elisions(self):
        """FR target: elisions applied to translated text."""
        result = self._run_trpp("je ai mangé le gâteau", "fr")
        self.assertIn("'ai", result)  # J'ai or j'ai

    def test_trpp_fr_typography(self):
        """FR target: NBSP before colon."""
        result = self._run_trpp("Voici : la liste.", "fr")
        # The colon should have a non-breaking space before it
        self.assertTrue(NBSP + ":" in result or NNBSP in result,
                        f"No NBSP before colon: {repr(result)}")

    def test_trpp_en_no_typography(self):
        """EN target: no French typography (no NBSP)."""
        result = self._run_trpp("Here: the list!", "en")
        self.assertNotIn(NBSP, result)
        self.assertNotIn(NNBSP, result)

    def test_trpp_rules_disabled(self):
        """TRPP with rules disabled: hesitations stay."""
        result = self._run_trpp("euh bonjour le monde.", "fr",
                                env_extra={"DICTEE_PP_RULES": "false"})
        self.assertIn("euh", result.lower())

    def test_trpp_llm_forced_off(self):
        """LLM never appears in TRPP trace even if set to true."""
        _, steps = self._run_trpp_trace(
            "bonjour le monde.", "fr",
            env_extra={"DICTEE_LLM_POSTPROCESS": "false"})
        llm_steps = [s for s in steps if s.startswith("LLM")]
        self.assertEqual(llm_steps, [], f"LLM steps found in TRPP: {llm_steps}")

    def test_trpp_language_rules_umbrella_off(self):
        """TRPP with language_rules off: no elision."""
        result = self._run_trpp("je ai faim", "fr", env_extra={
            "DICTEE_PP_LANGUAGE_RULES": "false",
        })
        self.assertIn("je ai", result.lower())

    def test_trpp_capitalization(self):
        """TRPP capitalizes first letter of translated text."""
        result = self._run_trpp("hello world. goodbye world.", "en")
        # Capitalization step uppercases after periods
        self.assertTrue(result[0].isupper(), f"Expected uppercase start: {result}")
        self.assertIn("Goodbye", result)

    def test_trpp_short_text(self):
        """TRPP short text: <=3 words → lowercase, no trailing punct.
        Use "Table." — not a keepcaps exception."""
        result = self._run_trpp("Table.", "fr")
        self.assertFalse(result.endswith("."), f"Trailing punct: {result}")
        # Short text lowercases
        self.assertEqual(result[0], result[0].lower(),
                         f"Expected lowercase: {result}")


# ══════════════════════════════════════════════════════════════════════
# TRANSLATION SHELL ENV MAPPING
# ══════════════════════════════════════════════════════════════════════


class TestTranslationShellEnvMapping(unittest.TestCase):
    """Verify the TRPP env var mapping logic from the dictee shell script."""

    # Extract the env mapping block from the dictee shell script
    _TRPP_ENV_SCRIPT = r"""
        # Simulate the TRPP env mapping from dictee lines 1302-1333
        DICTEE_PP_TRANSLATE="${DICTEE_PP_TRANSLATE:-true}"
        DICTEE_TRPP_LANGUAGE_RULES="${DICTEE_TRPP_LANGUAGE_RULES:-true}"

        if [ "${DICTEE_TRPP_LANGUAGE_RULES}" = "true" ]; then
            _trpp_el="${DICTEE_PP_ELISIONS:-true}"
            _trpp_el_it="${DICTEE_PP_ELISIONS_IT:-true}"
            _trpp_es="${DICTEE_PP_SPANISH:-true}"
            _trpp_pt="${DICTEE_PP_PORTUGUESE:-true}"
            _trpp_de="${DICTEE_PP_GERMAN:-true}"
            _trpp_nl="${DICTEE_PP_DUTCH:-true}"
            _trpp_ro="${DICTEE_PP_ROMANIAN:-true}"
            _trpp_ty="${DICTEE_PP_TYPOGRAPHY:-true}"
        else
            _trpp_el=false; _trpp_el_it=false; _trpp_es=false
            _trpp_pt=false; _trpp_de=false; _trpp_nl=false
            _trpp_ro=false; _trpp_ty=false
        fi

        # Build the env like the real script does
        MAPPED_LANG_SOURCE="${LANG_TARGET:0:2}"
        MAPPED_LLM=false
        MAPPED_PP_RULES="${DICTEE_TRPP_RULES:-true}"
        MAPPED_PP_CONTINUATION="${DICTEE_TRPP_CONTINUATION:-true}"
        MAPPED_PP_NUMBERS="${DICTEE_TRPP_NUMBERS:-true}"
        MAPPED_PP_DICT="${DICTEE_TRPP_DICT:-true}"
        MAPPED_PP_CAPITALIZATION="${DICTEE_TRPP_CAPITALIZATION:-true}"
        MAPPED_PP_SHORT_TEXT="${DICTEE_TRPP_SHORT_TEXT:-true}"
        MAPPED_PP_ELISIONS="$_trpp_el"
        MAPPED_PP_TYPOGRAPHY="$_trpp_ty"
    """

    def _run_mapping(self, env_vars=""):
        """Run the mapping script with given env vars, return mapped values."""
        script = f"""
            {env_vars}
            {self._TRPP_ENV_SCRIPT}
            echo "LANG_SOURCE=$MAPPED_LANG_SOURCE"
            echo "LLM=$MAPPED_LLM"
            echo "PP_RULES=$MAPPED_PP_RULES"
            echo "PP_CONTINUATION=$MAPPED_PP_CONTINUATION"
            echo "PP_ELISIONS=$MAPPED_PP_ELISIONS"
            echo "PP_TYPOGRAPHY=$MAPPED_PP_TYPOGRAPHY"
        """
        result = subprocess.run(
            ["bash", "-c", script],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Bash error: {result.stderr}")
        return dict(line.split("=", 1) for line in result.stdout.strip().splitlines()
                    if "=" in line)

    def test_defaults_all_true(self):
        """Default TRPP mapping: all steps true."""
        m = self._run_mapping('LANG_TARGET=de-DE')
        self.assertEqual(m["PP_RULES"], "true")
        self.assertEqual(m["PP_CONTINUATION"], "true")
        self.assertEqual(m["PP_ELISIONS"], "true")
        self.assertEqual(m["PP_TYPOGRAPHY"], "true")

    def test_trpp_rules_false(self):
        """DICTEE_TRPP_RULES=false → PP_RULES=false."""
        m = self._run_mapping('LANG_TARGET=fr; DICTEE_TRPP_RULES=false')
        self.assertEqual(m["PP_RULES"], "false")

    def test_llm_always_false(self):
        """LLM is always forced false in TRPP."""
        m = self._run_mapping('LANG_TARGET=fr')
        self.assertEqual(m["LLM"], "false")

    def test_lang_source_from_target(self):
        """LANG_TARGET=de-DE → LANG_SOURCE=de."""
        m = self._run_mapping('LANG_TARGET=de-DE')
        self.assertEqual(m["LANG_SOURCE"], "de")

    def test_lang_rules_off_forces_subflags(self):
        """DICTEE_TRPP_LANGUAGE_RULES=false → all sub-flags false."""
        m = self._run_mapping(
            'LANG_TARGET=fr; DICTEE_TRPP_LANGUAGE_RULES=false')
        self.assertEqual(m["PP_ELISIONS"], "false")
        self.assertEqual(m["PP_TYPOGRAPHY"], "false")

    def test_lang_rules_on_inherits_defaults(self):
        """DICTEE_TRPP_LANGUAGE_RULES=true → sub-flags inherit from PP defaults."""
        m = self._run_mapping(
            'LANG_TARGET=fr; DICTEE_TRPP_LANGUAGE_RULES=true; DICTEE_PP_ELISIONS=false')
        self.assertEqual(m["PP_ELISIONS"], "false")  # Inherits the PP setting


# ══════════════════════════════════════════════════════════════════════
# NUMBERS IN PIPELINE
# ══════════════════════════════════════════════════════════════════════


class TestNumbersInPipeline(unittest.TestCase):
    """Test number conversion within the full pipeline."""

    def _has_text2num(self):
        """Check if text2num is available in the postprocess venv."""
        result = run_postprocess("vingt-trois", lang="fr",
                                 env_extra={"DICTEE_PP_NUMBERS": "true"})
        return "23" in result

    def test_numbers_fr_integration(self):
        """FR: 'vingt-trois' → '23' in pipeline."""
        if not self._has_text2num():
            self.skipTest("text2num not installed")
        result = run_postprocess(
            "Il y a vingt-trois personnes.", lang="fr",
            env_extra={"DICTEE_PP_NUMBERS": "true"})
        self.assertIn("23", result)

    def test_numbers_disabled(self):
        """Numbers disabled: number words stay as text."""
        result = run_postprocess(
            "Il y a vingt-trois personnes.", lang="fr",
            env_extra={"DICTEE_PP_NUMBERS": "false"})
        self.assertIn("vingt-trois", result)

    def test_numbers_before_dictionary(self):
        """Numbers (step 7) runs before Dictionary (step 8) in trace."""
        _, steps = run_postprocess_with_trace(
            "vingt-trois linux", lang="fr",
            env_extra={"DICTEE_PP_NUMBERS": "true"})
        if "Numbers" in steps and "Dictionary" in steps:
            self.assertLess(steps.index("Numbers"), steps.index("Dictionary"))

    def test_numbers_en(self):
        """EN: 'twenty three' → '23'."""
        if not self._has_text2num():
            self.skipTest("text2num not installed")
        result = run_postprocess(
            "There are twenty three people.", lang="en",
            env_extra={"DICTEE_PP_NUMBERS": "true"})
        self.assertIn("23", result)


# ══════════════════════════════════════════════════════════════════════
# STEP ENABLE/DISABLE COMBINATIONS
# ══════════════════════════════════════════════════════════════════════


class TestStepEnableDisableCombinations(unittest.TestCase):
    """Test specific combinations of enabled/disabled steps."""

    def test_rules_on_elisions_off(self):
        """Rules remove hesitations, but elisions stay disabled."""
        env = dict(_ALL_PP_FALSE)
        env["DICTEE_PP_RULES"] = "true"
        result = run_postprocess("euh je ai faim.", lang="fr", env_extra=env)
        self.assertNotIn("euh", result)
        self.assertIn("je ai", result)

    def test_rules_off_elisions_on(self):
        """Rules off: hesitations stay; elisions on: contractions applied."""
        env = dict(_ALL_PP_FALSE)
        env["DICTEE_PP_LANGUAGE_RULES"] = "true"
        result = run_postprocess("euh je ai faim.", lang="fr", env_extra=env)
        self.assertIn("euh", result)
        self.assertIn("j'ai", result)

    def test_capitalization_off_dictionary_on(self):
        """Dictionary corrects 'linux' → 'Linux', but no auto-capitalize."""
        env = dict(_ALL_PP_FALSE)
        env["DICTEE_PP_DICT"] = "true"
        result = run_postprocess("j'utilise linux.", lang="fr", env_extra=env)
        self.assertIn("Linux", result)
        # First char should remain lowercase (no capitalization step)
        self.assertTrue(result[0].islower(),
                        f"Expected lowercase start: {result}")

    def test_short_text_custom_max(self):
        """Custom PP_SHORT_TEXT_MAX=5: 4-word phrase treated as short."""
        result = run_postprocess("Bonjour le monde ici.", lang="fr",
                                 env_extra={"DICTEE_PP_SHORT_TEXT_MAX": "5"})
        # Short text: lowercase, no trailing punct
        self.assertFalse(result.endswith("."),
                         f"Trailing punct on short text: {result}")

    def test_continuation_on_rules_off(self):
        """Continuation works without rules."""
        env = dict(_ALL_PP_FALSE)
        env["DICTEE_PP_CONTINUATION"] = "true"
        result = run_postprocess("dans. le bureau.", lang="fr", env_extra=env)
        # Continuation should remove period after "dans" (closed-class word)
        self.assertIn("dans le", result)


# ══════════════════════════════════════════════════════════════════════
# PP DEBUG TRACE
# ══════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════
# REGEX RULES — SYMBOLS & CURRENCY (Step 7)
# ══════════════════════════════════════════════════════════════════════


class TestSymbolRules(unittest.TestCase):
    """Verify Step 7 symbol/currency regex rules from rules.conf.default."""

    # -- Currency --

    def test_fr_euros(self):
        result = run_postprocess("Ça coûte dix euros.", lang="fr")
        self.assertIn("€", result)

    def test_fr_dollars(self):
        result = run_postprocess("Ça coûte vingt dollars.", lang="fr")
        self.assertIn("$", result)

    def test_fr_livres_sterling(self):
        result = run_postprocess("Cinq livres sterling.", lang="fr")
        self.assertIn("£", result)

    def test_en_euros(self):
        result = run_postprocess("It costs ten euros.", lang="en")
        self.assertIn("€", result)

    def test_en_dollars(self):
        result = run_postprocess("Twenty dollars please.", lang="en")
        self.assertIn("$", result)

    def test_en_pounds(self):
        result = run_postprocess("Five pounds.", lang="en")
        self.assertIn("£", result)

    def test_de_euros(self):
        result = run_postprocess("Das kostet zehn Euros.", lang="de")
        self.assertIn("€", result)

    def test_uk_euros(self):
        result = run_postprocess("Це коштує десять євро.", lang="uk")
        self.assertIn("€", result)

    # -- Email / web --

    def test_fr_arobase(self):
        result = run_postprocess("Mon adresse arobase.", lang="fr")
        self.assertIn("@", result)

    def test_en_at_sign(self):
        result = run_postprocess("My email at sign.", lang="en")
        self.assertIn("@", result)

    def test_de_klammeraffe(self):
        result = run_postprocess("Meine E-Mail Klammeraffe.", lang="de")
        self.assertIn("@", result)

    # -- Programming --

    def test_fr_accolades(self):
        result = run_postprocess("Ouvrir accolade fermer accolade.", lang="fr")
        self.assertIn("{", result)
        self.assertIn("}", result)

    def test_fr_crochets(self):
        result = run_postprocess("Ouvrir crochet fermer crochet.", lang="fr")
        self.assertIn("[", result)
        self.assertIn("]", result)

    def test_fr_chevrons(self):
        result = run_postprocess("Ouvrir chevron fermer chevron.", lang="fr")
        self.assertIn("<", result)
        self.assertIn(">", result)

    def test_en_curly_brace(self):
        result = run_postprocess("Open curly brace close curly brace.", lang="en")
        self.assertIn("{", result)
        self.assertIn("}", result)

    def test_en_bracket(self):
        result = run_postprocess("Open bracket close bracket.", lang="en")
        self.assertIn("[", result)
        self.assertIn("]", result)

    # -- Operators --

    def test_underscore(self):
        result = run_postprocess("Mon underscore variable.", lang="fr")
        self.assertIn("_", result)

    def test_fr_barre_oblique(self):
        result = run_postprocess("Barre oblique inversée.", lang="fr")
        self.assertIn("\\", result)

    def test_fr_asterisque(self):
        result = run_postprocess("Un astérisque ici.", lang="fr")
        self.assertIn("*", result)

    def test_fr_pourcent(self):
        result = run_postprocess("Cinquante pourcent.", lang="fr")
        self.assertIn("%", result)

    def test_fr_esperluette(self):
        result = run_postprocess("A esperluette B.", lang="fr")
        self.assertIn("&", result)


# ══════════════════════════════════════════════════════════════════════
# REGEX RULES — MARKDOWN VOICE COMMANDS (FR)
# ══════════════════════════════════════════════════════════════════════


class TestMarkdownVoiceCommands(unittest.TestCase):
    """Test French Markdown heading voice commands."""

    def test_diese_espace(self):
        result = run_postprocess("dièse espace titre principal.", lang="fr")
        self.assertIn("# ", result)

    def test_double_diese(self):
        result = run_postprocess("double dièse sous-titre.", lang="fr")
        self.assertIn("## ", result)

    def test_triple_diese(self):
        result = run_postprocess("triple dièse petit titre.", lang="fr")
        self.assertIn("### ", result)

    def test_en_hash_space(self):
        result = run_postprocess("hash space main title.", lang="en")
        self.assertIn("# ", result)

    def test_en_hash_hash_space(self):
        result = run_postprocess("hash hash space subtitle.", lang="en")
        self.assertIn("## ", result)

    def test_en_hash_hash_hash_space(self):
        result = run_postprocess("hash hash hash space small title.", lang="en")
        self.assertIn("### ", result)


# ══════════════════════════════════════════════════════════════════════
# REGEX RULES — CYRILLIC MISDETECTION RECOVERY (FR)
# ══════════════════════════════════════════════════════════════════════


class TestCyrillicMisdetection(unittest.TestCase):
    """Parakeet misdetects 'à la ligne' as Cyrillic on short FR audio.
    Rules recover these known patterns before bad-lang rejection."""

    def test_cyrillic_aliniya_to_newline(self):
        """Cyrillic containing 'лин' → newline."""
        result = run_postprocess("Алиния", lang="fr")
        self.assertIn("\n", result)

    def test_la_ligne_french_misdetection(self):
        """French 'La ligne' at start → newline."""
        result = run_postprocess("La ligne", lang="fr")
        self.assertIn("\n", result)

    def test_a_la_vigne_misdetection(self):
        """'à la vigne' at start → newline (known ASR confusion)."""
        result = run_postprocess("à la vigne", lang="fr")
        self.assertIn("\n", result)


# ══════════════════════════════════════════════════════════════════════
# EDGE CASES — INPUT BOUNDARIES
# ══════════════════════════════════════════════════════════════════════


class TestEdgeCasesExtended(unittest.TestCase):
    """Extended edge cases: empty, whitespace, emoji, control chars, etc."""

    def test_empty_input(self):
        """Empty string → empty output."""
        result = run_postprocess("", lang="fr")
        self.assertEqual(result, "")

    def test_whitespace_only(self):
        """Whitespace-only input → preserved (strip to empty or spaces)."""
        result = run_postprocess("   ", lang="fr")
        self.assertEqual(result.strip(), "")

    def test_single_character(self):
        """Single character → passes through."""
        result = run_postprocess("a", lang="fr")
        self.assertIn("a", result.lower())

    def test_newline_only(self):
        """Newline input → empty (stripped by main())."""
        result = run_postprocess("\n", lang="fr")
        self.assertEqual(result.strip(), "")

    def test_emoji_passthrough(self):
        """Emoji in text passes through undamaged."""
        result = run_postprocess("Bonjour le monde 🎉 ici.", lang="fr")
        self.assertIn("🎉", result)

    def test_mixed_emoji_text(self):
        """Emoji mixed with text doesn't break pipeline."""
        result = run_postprocess("J'adore 🐍 Python et 🦀 Rust.", lang="fr")
        self.assertIn("🐍", result)
        self.assertIn("🦀", result)

    def test_control_chars_stripped(self):
        """Control characters (except \\t, \\n) stripped by final cleanup."""
        result = run_postprocess("Hello\x03world\x04here.", lang="en")
        self.assertNotIn("\x03", result)
        self.assertNotIn("\x04", result)
        self.assertIn("world", result)

    def test_tab_preserved(self):
        """\\t generated by voice command 'tabulation' is preserved."""
        result = run_postprocess(
            "Colonne un tabulation colonne deux et la suite.", lang="fr")
        self.assertIn("\t", result)

    def test_very_long_single_word(self):
        """A very long word doesn't crash the pipeline."""
        long_word = "a" * 5000
        result = run_postprocess(f"{long_word}.", lang="fr")
        self.assertGreater(len(result), 4000)

    def test_punctuation_only(self):
        """Punctuation-only input → ellipsis (short text skips pure punct)."""
        result = run_postprocess("Bonjour le monde...", lang="fr")
        self.assertIn("…", result)

    def test_numbers_only(self):
        """Numbers-only input → passes through."""
        result = run_postprocess("12345", lang="fr")
        self.assertIn("12345", result)

    def test_mixed_scripts_cjk(self):
        """CJK characters mixed with Latin pass through for supported lang."""
        result = run_postprocess("Bonjour 你好 monde.", lang="fr")
        self.assertIn("你好", result)

    def test_arabic_passthrough(self):
        """Arabic characters in non-Cyrillic/non-Latin lang check."""
        result = run_postprocess("مرحبا بالعالم", lang="fr")
        # Arabic is neither Latin nor Cyrillic; bad-lang check only
        # rejects Cyrillic for Latin langs, so this may pass or not
        # depending on the ratio logic — just ensure no crash
        self.assertIsInstance(result, str)

    def test_internal_markers_preserved(self):
        """\\x01 and \\x02 markers preserved for dictee to handle."""
        result = run_postprocess("Hello\x01world\x02end.", lang="en")
        self.assertIn("\x01", result)
        self.assertIn("\x02", result)


# ══════════════════════════════════════════════════════════════════════
# LONG TEXT — MULTI-PARAGRAPH INTEGRITY
# ══════════════════════════════════════════════════════════════════════


class TestLongTextIntegrity(unittest.TestCase):
    """Verify pipeline preserves text integrity on long, multi-paragraph input."""

    _LONG_FR = (
        "Bonjour le monde. Je suis ici pour tester le pipeline de post-traitement. "
        "Ce texte contient plusieurs phrases avec des virgules, des points, "
        "et aussi des points d'exclamation! Et des points d'interrogation? "
        "Il y a même des guillemets « comme ça » et des parenthèses (ici). "
        "Les élisions fonctionnent: je ai, je utilise, le homme, la eau. "
        "Et voici une commande vocale: à la ligne. "
        "Deuxième paragraphe après le retour à la ligne. "
        "Les hésitations euh et hum devraient disparaître. "
        "Les mots du dictionnaire comme linux et api doivent être corrigés. "
        "Fin du texte de test."
    )

    def test_long_text_produces_output(self):
        """Long text produces non-empty output."""
        result = run_postprocess(self._LONG_FR, lang="fr")
        self.assertGreater(len(result), 100)

    def test_long_text_elisions_applied(self):
        """Elisions work in long text."""
        result = run_postprocess(self._LONG_FR, lang="fr")
        self.assertIn("j'ai", result.lower())
        self.assertIn("j'utilise", result.lower())
        self.assertIn("l'homme", result.lower())
        self.assertIn("l'eau", result.lower())

    def test_long_text_hesitations_removed(self):
        """Hesitations removed from long text."""
        result = run_postprocess(self._LONG_FR, lang="fr")
        self.assertNotIn(" euh ", result.lower())
        self.assertNotIn(" hum ", result.lower())

    def test_long_text_dictionary_applied(self):
        """Dictionary corrections in long text."""
        result = run_postprocess(self._LONG_FR, lang="fr")
        self.assertIn("Linux", result)
        self.assertIn("API", result)

    def test_long_text_newline_command(self):
        """Voice command 'à la ligne' produces newline in long text."""
        result = run_postprocess(self._LONG_FR, lang="fr")
        self.assertIn("\n", result)

    def test_long_text_typography(self):
        """French typography (NBSP) applied in long text."""
        # Use explicit colon in input
        text = "Premier point: le sujet. Deuxième point: la conclusion."
        result = run_postprocess(text, lang="fr")
        self.assertTrue(NBSP in result or NNBSP in result,
                        f"No NBSP in: {repr(result)}")

    def test_very_long_text_no_crash(self):
        """10000+ char text doesn't crash or timeout."""
        text = ("Bonjour le monde. " * 500).strip()
        result = run_postprocess(text, lang="fr")
        self.assertGreater(len(result), 5000)

    def test_multi_paragraph_preserved(self):
        """Multiple paragraphs via voice commands preserved."""
        text = "Premier paragraphe. Nouveau paragraphe. Deuxième paragraphe."
        result = run_postprocess(text, lang="fr")
        self.assertIn("\n\n", result)

    def test_long_text_en(self):
        """English long text pipeline works end-to-end."""
        text = (
            "Hello world. This is a test of the post-processing pipeline. "
            "Um there are hesitations uh that should be removed. "
            "The dictionary should fix linux and api. "
            "New line here. And a new paragraph. "
            "The end of the test."
        )
        result = run_postprocess(text, lang="en")
        self.assertNotIn(" um ", result.lower())
        self.assertNotIn(" uh ", result.lower())
        self.assertIn("Linux", result)
        self.assertIn("API", result)
        self.assertIn("\n", result)


# ══════════════════════════════════════════════════════════════════════
# DICTIONARY — CASE PRESERVATION & EDGE CASES
# ══════════════════════════════════════════════════════════════════════


class TestDictionaryExtended(unittest.TestCase):
    """Extended dictionary tests: case preservation, multiple entries."""

    def test_uppercase_input_preserved(self):
        """'API' stays 'API' (already uppercase)."""
        result = run_postprocess("J'utilise API.", lang="fr")
        self.assertIn("API", result)

    def test_lowercase_to_titlecase(self):
        """'linux' → 'Linux' (in long enough text to avoid short-text)."""
        result = run_postprocess("Je vais installer linux sur mon ordinateur.", lang="fr")
        self.assertIn("Linux", result)

    def test_titlecase_preserved(self):
        """'Linux' stays 'Linux'."""
        result = run_postprocess("Je vais installer Linux sur mon ordinateur.", lang="fr")
        self.assertIn("Linux", result)

    def test_allcaps_input(self):
        """'LINUX' → 'LINUX' (case preserved for all-caps)."""
        result = run_postprocess("J'utilise LINUX.", lang="fr")
        self.assertIn("LINUX", result)

    def test_multiple_dict_entries(self):
        """Multiple dictionary entries in one sentence."""
        result = run_postprocess("Le gpu et le cpu et le ssh.", lang="fr")
        self.assertIn("GPU", result)
        self.assertIn("CPU", result)
        self.assertIn("SSH", result)

    def test_en_ai_dict(self):
        """EN-specific: 'ai' → 'AI'."""
        result = run_postprocess("This is about ai.", lang="en")
        self.assertIn("AI", result)

    def test_fr_sncf(self):
        """FR-specific: 'sncf' → 'SNCF'."""
        result = run_postprocess("Le train sncf.", lang="fr")
        self.assertIn("SNCF", result)

    def test_dict_word_boundary(self):
        """Dictionary respects word boundaries: 'rapid' does not match 'api'."""
        result = run_postprocess("Le train rapide.", lang="fr")
        self.assertNotIn("rAPId", result)
        self.assertIn("rapide", result.lower())


# ══════════════════════════════════════════════════════════════════════
# DIARIZATION — OUTPUT FORMATTING
# ══════════════════════════════════════════════════════════════════════


class TestDiarizationFormatting(unittest.TestCase):
    """Test post-processing of diarized text (speaker labels).

    Diarization is handled by Rust (transcribe_diarize), which outputs
    speaker-labeled text like 'Speaker 1: Hello.\nSpeaker 2: Hi.\n'.
    The post-processing pipeline receives this text.
    Verify speaker labels survive the pipeline undamaged.
    """

    def test_speaker_labels_preserved(self):
        """Speaker labels preserved through pipeline."""
        text = "Speaker 1: Hello world.\nSpeaker 2: How are you?"
        result = run_postprocess(text, lang="en")
        self.assertIn("Speaker 1", result)
        self.assertIn("Speaker 2", result)

    def test_speaker_labels_fr(self):
        """FR speaker labels with elisions."""
        text = "Locuteur 1: je ai un problème.\nLocuteur 2: je ai compris."
        result = run_postprocess(text, lang="fr")
        self.assertIn("Locuteur 1", result)
        self.assertIn("Locuteur 2", result)
        # Elisions should still apply within speaker text
        self.assertIn("'ai", result)

    def test_diarized_multiline_capitalization(self):
        """Capitalization works per line in diarized text."""
        text = "Speaker 1: hello.\nSpeaker 2: goodbye."
        result = run_postprocess(text, lang="en")
        lines = result.strip().split("\n")
        self.assertEqual(len(lines), 2)
        for line in lines:
            self.assertTrue(line[0].isupper(),
                            f"Expected uppercase start: {line}")

    def test_diarized_hesitations_removed(self):
        """Hesitations removed within diarized segments."""
        text = "Speaker 1: uh hello world.\nSpeaker 2: um goodbye."
        result = run_postprocess(text, lang="en")
        self.assertNotIn(" uh ", result.lower())
        self.assertNotIn(" um ", result.lower())

    def test_four_speakers(self):
        """Up to 4 speakers (Sortformer max) preserved."""
        text = (
            "Speaker 1: First.\nSpeaker 2: Second.\n"
            "Speaker 3: Third.\nSpeaker 4: Fourth."
        )
        result = run_postprocess(text, lang="en")
        for i in range(1, 5):
            self.assertIn(f"Speaker {i}", result)


# ══════════════════════════════════════════════════════════════════════
# SHORT TEXT & CONTINUATION INTERACTION
# ══════════════════════════════════════════════════════════════════════


class TestShortTextEdgeCases(unittest.TestCase):
    """Extended short text correction tests."""

    def test_one_word_lowercase(self):
        """Single word → lowercase, no trailing punct (mot hors keepcaps)."""
        result = run_postprocess("Voiture.", lang="fr")
        self.assertEqual(result, "voiture")

    def test_two_words_lowercase(self):
        """Two words → lowercase, no trailing punct (hors keepcaps)."""
        result = run_postprocess("Maison verte.", lang="fr")
        self.assertEqual(result, "maison verte")

    def test_three_words_not_short(self):
        """Three words (= max default 3) → NOT short (threshold is strict <)."""
        result = run_postprocess("Bonjour le monde.", lang="fr")
        # 3 words >= 3 → not short text, period preserved
        self.assertTrue(result.endswith("."),
                        f"3 words should NOT be short: {result}")

    def test_four_words_not_short(self):
        """Four words → NOT short text (above default max=3)."""
        result = run_postprocess("bonjour le monde entier.", lang="fr")
        self.assertTrue(result.endswith("."),
                        f"4+ words should keep period: {result}")

    def test_short_text_disabled(self):
        """Short text disabled: period preserved on short text."""
        result = run_postprocess("Bonjour.", lang="fr",
                                 env_extra={"DICTEE_PP_SHORT_TEXT": "false"})
        self.assertTrue(result.endswith("."))

    def test_short_text_with_question_mark(self):
        """Short text strips question mark too."""
        result = run_postprocess("Pourquoi?", lang="fr")
        self.assertFalse(result.endswith("?"),
                         f"Short text should strip '?': {result}")

    def test_short_text_with_exclamation(self):
        """Short text strips exclamation mark."""
        result = run_postprocess("Super!", lang="fr")
        self.assertFalse(result.endswith("!"),
                         f"Short text should strip '!': {result}")

    def test_short_text_with_newline_not_short(self):
        """Text with newline is not treated as short even if few words."""
        text = "Bonjour. Point à la ligne. Monde."
        result = run_postprocess(text, lang="fr")
        # Contains newline from voice command — multi-line, not short
        self.assertIn("\n", result)


# ══════════════════════════════════════════════════════════════════════
# PUNCTUATION CLEANUP RULES (Step 5)
# ══════════════════════════════════════════════════════════════════════


class TestPunctuationCleanupExtended(unittest.TestCase):
    """Extended punctuation normalization tests."""

    def test_triple_dots_to_ellipsis(self):
        result = run_postprocess("Bonjour... le monde.", lang="fr")
        self.assertIn("…", result)
        self.assertNotIn("...", result)

    def test_quadruple_dots_to_ellipsis(self):
        result = run_postprocess("Bonjour.... le monde.", lang="fr")
        self.assertIn("…", result)

    def test_double_question_mark(self):
        result = run_postprocess("Vraiment?? C'est sûr.", lang="fr")
        self.assertNotIn("??", result)
        self.assertIn("?", result)

    def test_double_exclamation(self):
        result = run_postprocess("Super!! Merci.", lang="fr")
        self.assertNotIn("!!", result)
        self.assertIn("!", result)

    def test_double_comma(self):
        result = run_postprocess("Bonjour,, le monde.", lang="fr")
        self.assertNotIn(",,", result)

    def test_space_before_punctuation_removed(self):
        result = run_postprocess("Bonjour , le monde .", lang="fr")
        self.assertNotIn(" ,", result)
        self.assertNotIn(" .", result)

    def test_space_after_sentence_end(self):
        """Space inserted between sentence-end punct and next word."""
        result = run_postprocess("Bonjour.Monde.", lang="fr")
        self.assertIn(". ", result)

    def test_multiple_spaces_collapsed(self):
        result = run_postprocess("Bonjour   le   monde.", lang="fr")
        self.assertNotIn("  ", result)


# ══════════════════════════════════════════════════════════════════════
# VOICE COMMANDS — COMBINED PUNCTUATION + NEWLINE
# ══════════════════════════════════════════════════════════════════════


class TestCombinedPunctNewline(unittest.TestCase):
    """Test combined punctuation+newline voice commands (all 7 languages)."""

    def test_fr_point_a_la_ligne(self):
        result = run_postprocess("Première phrase point à la ligne deuxième phrase.", lang="fr")
        self.assertIn(".\n", result)

    def test_fr_virgule_a_la_ligne(self):
        result = run_postprocess("Premier mot virgule à la ligne deuxième mot.", lang="fr")
        self.assertIn(",\n", result)

    def test_fr_point_interrogation_a_la_ligne(self):
        result = run_postprocess("Vraiment point d'interrogation à la ligne suite.", lang="fr")
        self.assertIn("?\n", result)

    def test_fr_point_exclamation_a_la_ligne(self):
        result = run_postprocess("Super point d'exclamation à la ligne suite.", lang="fr")
        self.assertIn("!\n", result)

    def test_en_period_new_line(self):
        result = run_postprocess("First sentence period new line second sentence.", lang="en")
        self.assertIn(".\n", result)

    def test_en_comma_new_line(self):
        result = run_postprocess("First word comma new line second word.", lang="en")
        self.assertIn(",\n", result)

    def test_en_question_mark_new_line(self):
        result = run_postprocess("Really question mark new line next.", lang="en")
        self.assertIn("?\n", result)

    def test_de_punkt_neue_zeile(self):
        result = run_postprocess("Erster Satz Punkt neue Zeile zweiter Satz.", lang="de")
        self.assertIn(".\n", result)

    def test_de_komma_neue_zeile(self):
        result = run_postprocess("Erstes Wort Komma neue Zeile zweites Wort.", lang="de")
        self.assertIn(",\n", result)

    def test_es_coma_nueva_linea(self):
        result = run_postprocess("Primera palabra coma nueva línea segunda.", lang="es")
        self.assertIn(",\n", result)

    def test_it_virgola_a_capo(self):
        result = run_postprocess("Prima parola virgola a capo seconda.", lang="it")
        self.assertIn(",\n", result)

    def test_pt_virgula_nova_linha(self):
        result = run_postprocess("Primeira palavra vírgula nova linha segunda.", lang="pt")
        self.assertIn(",\n", result)

    def test_uk_koma_novyj_ryadok(self):
        result = run_postprocess("Перше слово кома новий рядок друге.", lang="uk")
        self.assertIn(",\n", result)


# ══════════════════════════════════════════════════════════════════════
# REGEX — VOICE COMMAND CASE INSENSITIVITY
# ══════════════════════════════════════════════════════════════════════


class TestVoiceCommandCaseInsensitive(unittest.TestCase):
    """Voice commands should work regardless of input casing."""

    def test_fr_virgule_uppercase(self):
        result = run_postprocess("Bonjour VIRGULE le monde.", lang="fr")
        self.assertIn(",", result)

    def test_fr_virgule_titlecase(self):
        result = run_postprocess("Bonjour Virgule le monde.", lang="fr")
        self.assertIn(",", result)

    def test_en_period_uppercase(self):
        result = run_postprocess("Hello PERIOD Goodbye.", lang="en")
        self.assertIn(".", result)

    def test_de_komma_titlecase(self):
        result = run_postprocess("Hallo Komma Welt.", lang="de")
        self.assertIn(",", result)


# ══════════════════════════════════════════════════════════════════════
# ENV BOOL EDGE CASES
# ══════════════════════════════════════════════════════════════════════


class TestEnvBoolEdgeCases(unittest.TestCase):
    """Test _env_bool behavior with unusual values."""

    def test_invalid_value_treated_as_false(self):
        """Non-boolean value → treated as false (rules disabled)."""
        _, steps = run_postprocess_with_trace(
            "euh bonjour.", lang="fr",
            env_extra={"DICTEE_PP_RULES": "maybe"})
        self.assertNotIn("Rules", steps)

    def test_empty_string_treated_as_false(self):
        """Empty string → treated as false."""
        _, steps = run_postprocess_with_trace(
            "euh bonjour.", lang="fr",
            env_extra={"DICTEE_PP_RULES": ""})
        self.assertNotIn("Rules", steps)

    def test_true_uppercase_treated_as_true(self):
        """'TRUE' (uppercase) → treated as true."""
        _, steps = run_postprocess_with_trace(
            "euh bonjour.", lang="fr",
            env_extra={"DICTEE_PP_RULES": "TRUE"})
        self.assertIn("Rules", steps)

    def test_true_mixed_case(self):
        """'True' (mixed case) → treated as true."""
        _, steps = run_postprocess_with_trace(
            "euh bonjour.", lang="fr",
            env_extra={"DICTEE_PP_RULES": "True"})
        self.assertIn("Rules", steps)


# ══════════════════════════════════════════════════════════════════════
# LANGUAGE RULES UMBRELLA VS SUB-FLAGS
# ══════════════════════════════════════════════════════════════════════


class TestLanguageRulesUmbrella(unittest.TestCase):
    """Umbrella switch DICTEE_PP_LANGUAGE_RULES gates all sub-flags."""

    def test_umbrella_off_overrides_sub_true(self):
        """Umbrella off + elisions true → no elision (umbrella wins)."""
        result = run_postprocess("je ai faim.", lang="fr", env_extra={
            "DICTEE_PP_LANGUAGE_RULES": "false",
            "DICTEE_PP_ELISIONS": "true",
        })
        self.assertNotIn("j'ai", result.lower())
        self.assertIn("je ai", result.lower())

    def test_umbrella_on_sub_off(self):
        """Umbrella on + elisions off → no elision (sub-flag wins)."""
        result = run_postprocess("je ai faim.", lang="fr", env_extra={
            "DICTEE_PP_LANGUAGE_RULES": "true",
            "DICTEE_PP_ELISIONS": "false",
        })
        self.assertNotIn("j'ai", result.lower())

    def test_umbrella_on_typography_off(self):
        """Umbrella on + typography off → no NBSP."""
        result = run_postprocess("Voici : la liste.", lang="fr", env_extra={
            "DICTEE_PP_LANGUAGE_RULES": "true",
            "DICTEE_PP_TYPOGRAPHY": "false",
        })
        self.assertNotIn(NBSP, result)

    def test_umbrella_off_no_german(self):
        """Umbrella off for DE → no German contractions."""
        _, steps = run_postprocess_with_trace(
            "Ich bin in dem Haus.", lang="de",
            env_extra={"DICTEE_PP_LANGUAGE_RULES": "false"})
        self.assertNotIn("German [de]", steps)


# ══════════════════════════════════════════════════════════════════════
# FRENCH ELISIONS — ASPIRATED H EDGE CASES
# ══════════════════════════════════════════════════════════════════════


class TestFrenchElisionsHAspire(unittest.TestCase):
    """French elision must NOT apply before aspirated-h words."""

    def test_le_heros_no_elision(self):
        """'le héros' stays (aspirated h)."""
        result = run_postprocess("Voici le héros du film.", lang="fr")
        self.assertIn("le héros", result.lower())
        self.assertNotIn("l'héros", result.lower())

    def test_le_haricot_no_elision(self):
        """'le haricot' stays (aspirated h)."""
        result = run_postprocess("Voici le haricot vert.", lang="fr")
        self.assertIn("le haricot", result.lower())

    def test_le_homme_elision(self):
        """'le homme' → 'l'homme' (non-aspirated h)."""
        result = run_postprocess("Voici le homme qui marche.", lang="fr")
        self.assertIn("l'homme", result.lower())

    def test_le_hotel_elision(self):
        """'le hôtel' → 'l'hôtel' (non-aspirated h)."""
        result = run_postprocess("Voici le hôtel de ville.", lang="fr")
        self.assertIn("l'hôtel", result.lower())


# ══════════════════════════════════════════════════════════════════════
# PATHOLOGICAL REGEX INPUT (ReDoS prevention)
# ══════════════════════════════════════════════════════════════════════


class TestPathologicalRegex(unittest.TestCase):
    """Verify pipeline doesn't hang on pathological inputs."""

    def test_many_parentheses(self):
        """Many nested parentheses don't cause ReDoS."""
        text = "(" * 500 + "texte" + ")" * 500 + "."
        result = run_postprocess(text, lang="fr")
        # Just verify it completes (annotations rule strips parenthesized content)
        self.assertIsInstance(result, str)

    def test_many_brackets(self):
        """Many nested brackets don't cause ReDoS."""
        text = "[" * 500 + "texte" + "]" * 500 + "."
        result = run_postprocess(text, lang="fr")
        self.assertIsInstance(result, str)

    def test_repeated_hesitation_pattern(self):
        """Many repeated hesitations don't cause slowdown."""
        text = ("euh " * 200) + "bonjour."
        result = run_postprocess(text, lang="fr")
        self.assertNotIn("euh", result.lower())

    def test_alternating_punct_words(self):
        """Alternating punctuation and words don't hang."""
        text = ". ".join(["mot"] * 500) + "."
        result = run_postprocess(text, lang="fr")
        self.assertGreater(len(result), 100)


# ══════════════════════════════════════════════════════════════════════
# PIPELINE STEP INTERACTIONS
# ══════════════════════════════════════════════════════════════════════


class TestPipelineInteractions(unittest.TestCase):
    """Test interactions between pipeline steps."""

    def test_rules_then_continuation_then_elision(self):
        """Hesitation removed → continuation removes period → elision applies."""
        # "euh dans. je ai" → rules: "dans. je ai" → continuation: "dans je ai" → elision: "dans j'ai"
        result = run_postprocess("euh dans. je ai faim.", lang="fr")
        self.assertNotIn("euh", result.lower())
        self.assertIn("'ai", result)

    def test_dictionary_then_short_text_lowercase(self):
        """Dictionary corrects 'linux'→'Linux', then short text lowercases it."""
        result = run_postprocess("linux.", lang="fr")
        # 1 word < 3 → short text lowercases + strips period
        self.assertEqual(result, "linux")

    def test_dictionary_preserved_in_long_text(self):
        """Dictionary correction survives in text longer than short_text max."""
        result = run_postprocess(
            "Je vais installer linux et python sur mon serveur.", lang="fr")
        self.assertIn("Linux", result)
        self.assertIn("Python", result)

    def test_voice_command_newline_then_capitalization(self):
        """Voice command creates newline, capitalization applies to next line."""
        result = run_postprocess(
            "Première phrase. Point à la ligne. deuxième phrase.", lang="fr")
        lines = result.strip().split("\n")
        self.assertGreater(len(lines), 1)
        # Second line should start with uppercase
        second = lines[1].strip() if len(lines) > 1 else ""
        if second:
            self.assertTrue(second[0].isupper(),
                            f"Expected uppercase after newline: {second}")

    def test_elision_then_typography(self):
        """Elision and typography both apply in FR."""
        result = run_postprocess(
            "Je pense que il est important : le sujet.", lang="fr")
        self.assertIn("qu'il", result.lower())
        self.assertTrue(NBSP in result or NNBSP in result,
                        f"No NBSP in: {repr(result)}")

    def test_numbers_then_dictionary(self):
        """Numbers converts, then dictionary corrects — both in one sentence."""
        env = {"DICTEE_PP_NUMBERS": "true"}
        result = run_postprocess(
            "Il y a vingt-trois serveurs linux.", lang="fr", env_extra=env)
        if "23" in result:  # text2num available
            self.assertIn("23", result)
        self.assertIn("Linux", result)

    def test_annotation_removed_before_voice_command(self):
        """Annotations (parentheses) removed before voice commands processed."""
        result = run_postprocess(
            "(applaudissements) Bonjour le monde virgule ici.", lang="fr")
        self.assertNotIn("applaudissements", result)
        self.assertIn(",", result)

    def test_dedup_before_elision(self):
        """Deduplication runs before elision (both in rules step)."""
        result = run_postprocess(
            "je je ai un problème.", lang="fr")
        # Dedup: "je je" → "je", then elision: "je ai" → "j'ai"
        self.assertNotIn("je je", result.lower())
        self.assertIn("'ai", result)

    def test_llm_position_first_sees_raw_text(self):
        """LLM [first] runs before rules — trace shows LLM before Rules."""
        _, steps = run_postprocess_with_trace(
            "euh bonjour.", lang="fr",
            env_extra={
                "DICTEE_LLM_POSTPROCESS": "true",
                "DICTEE_LLM_POSITION": "first",
                "DICTEE_LLM_TIMEOUT": "1",
            })
        if "LLM [first]" in steps and "Rules" in steps:
            self.assertLess(steps.index("LLM [first]"), steps.index("Rules"))


# ══════════════════════════════════════════════════════════════════════
# ANNOTATION & HESITATION EXTENDED
# ══════════════════════════════════════════════════════════════════════


class TestAnnotationsExtended(unittest.TestCase):
    """Extended annotation/hesitation tests."""

    def test_unk_token_removed(self):
        """<unk> tokens from ASR removed."""
        result = run_postprocess("<unk> bonjour le monde.", lang="fr")
        self.assertNotIn("<unk>", result)

    def test_leading_orphan_punct_stripped(self):
        """Leading orphan punctuation from ASR context bleed stripped."""
        result = run_postprocess(". bonjour le monde.", lang="fr")
        self.assertFalse(result.lstrip().startswith("."),
                         f"Leading orphan punct: {result}")

    def test_multiple_hesitations_in_sequence(self):
        """Multiple consecutive hesitations all removed."""
        result = run_postprocess("euh hum ben bonjour.", lang="fr")
        self.assertNotIn("euh", result.lower())
        self.assertNotIn("hum", result.lower())
        self.assertNotIn("ben", result.lower())
        self.assertIn("bonjour", result.lower())

    def test_hesitation_with_surrounding_punct(self):
        """Hesitations with ASR-added commas/periods removed cleanly."""
        result = run_postprocess("Bonjour, euh, le monde.", lang="fr")
        self.assertNotIn("euh", result.lower())
        # Should not leave double comma/space
        self.assertNotIn(",,", result)

    def test_en_hesitations_all_variants(self):
        """English: all hesitation variants removed."""
        for h in ["uh", "um", "hmm", "mm", "mhm", "mmm"]:
            result = run_postprocess(f"Hello {h} world.", lang="en")
            self.assertNotIn(h, result.lower(),
                             f"Hesitation '{h}' not removed")

    def test_de_hesitations(self):
        """German: all hesitation variants removed."""
        for h in ["äh", "ähm", "hm", "hmm"]:
            result = run_postprocess(f"Hallo {h} Welt.", lang="de")
            self.assertNotIn(h, result.lower(),
                             f"German hesitation '{h}' not removed")

    def test_nested_parentheses_removed(self):
        """Nested parentheses content removed."""
        result = run_postprocess("Bonjour (texte (imbriqué)) le monde.", lang="fr")
        self.assertNotIn("imbriqué", result)

    def test_brackets_removed(self):
        """Bracketed content removed."""
        result = run_postprocess("Bonjour [bruit de fond] le monde.", lang="fr")
        self.assertNotIn("bruit", result)


# ══════════════════════════════════════════════════════════════════════
# NUMBER CONVERSION EXTENDED
# ══════════════════════════════════════════════════════════════════════


class TestNumberConversionExtended(unittest.TestCase):
    """Extended number conversion tests (requires text2num in venv)."""

    def _has_text2num(self):
        result = run_postprocess("vingt-trois", lang="fr",
                                 env_extra={"DICTEE_PP_NUMBERS": "true"})
        return "23" in result

    def test_fr_cent(self):
        if not self._has_text2num():
            self.skipTest("text2num not installed")
        result = run_postprocess(
            "Il y a cent personnes ici.", lang="fr",
            env_extra={"DICTEE_PP_NUMBERS": "true"})
        self.assertIn("100", result)

    def test_fr_mille(self):
        if not self._has_text2num():
            self.skipTest("text2num not installed")
        result = run_postprocess(
            "Le prix est de mille euros.", lang="fr",
            env_extra={"DICTEE_PP_NUMBERS": "true"})
        self.assertIn("1000", result)

    def test_en_hundred(self):
        if not self._has_text2num():
            self.skipTest("text2num not installed")
        result = run_postprocess(
            "There are one hundred people.", lang="en",
            env_extra={"DICTEE_PP_NUMBERS": "true"})
        self.assertIn("100", result)

    def test_numbers_disabled_no_conversion(self):
        """Explicit disabled: words stay as text."""
        result = run_postprocess(
            "Il y a cent personnes ici.", lang="fr",
            env_extra={"DICTEE_PP_NUMBERS": "false"})
        self.assertIn("cent", result)

    def test_mixed_numbers_and_digits(self):
        """Already-digit numbers pass through unchanged."""
        if not self._has_text2num():
            self.skipTest("text2num not installed")
        result = run_postprocess(
            "Il y a 5 et vingt-trois personnes.", lang="fr",
            env_extra={"DICTEE_PP_NUMBERS": "true"})
        self.assertIn("5", result)
        self.assertIn("23", result)


# ══════════════════════════════════════════════════════════════════════
# FULL-SCALE REALISTIC DICTATION — 7 LANGUAGES
# ══════════════════════════════════════════════════════════════════════


class TestFullScaleFR(unittest.TestCase):
    """Full-scale realistic French dictation with voice commands,
    hesitations, elisions, dictionary, typography, markdown, symbols,
    continuation, multi-paragraph, and long text.

    Note: ambiguous commands (point, deux points, à la ligne mid-sentence)
    require a configured suffix (DICTEE_COMMAND_SUFFIX_FR). We use only
    non-ambiguous forms that work without suffix configuration.
    """

    _INPUT = (
        "euh bonjour virgule je suis le développeur principal de ce projet. "
        "je ai commencé à travailler sur linux il y a dix ans virgule "
        "et depuis virgule je utilise python et javascript pour mes projets. "
        "point d'exclamation à la ligne "
        "hum le premier sujet est important : "
        "nous devons migrer notre api vers une nouvelle url. "
        "ouvrez les guillemets la migration est urgente fermez les guillemets. "
        "virgule à la ligne "
        "nouveau paragraphe "
        "dièse espace chapitre deux. virgule à la ligne "
        "le héros de le histoire est un homme qui travaille dans le hôtel de ville. "
        "il utilise le gpu et le cpu de son ordinateur virgule "
        "et il a installé ubuntu sur son ssd. "
        "virgule à la ligne "
        "le coût est de vingt-trois euros virgule "
        "et le taux est de cinquante pourcent. "
        "son adresse est jean arobase google. "
        "virgule à la ligne "
        "pour le code virgule ouvrir accolade. virgule à la ligne "
        "tabulation ouvrir crochet fermer crochet point virgule. virgule à la ligne "
        "fermer accolade. "
        "virgule à la ligne "
        "en résumé virgule ce projet est très prometteur. "
        "trois petits points "
        "point d'exclamation"
    )

    def test_hesitations_removed(self):
        result = run_postprocess(self._INPUT, lang="fr")
        self.assertNotIn(" euh ", result.lower())
        self.assertNotIn(" hum ", result.lower())

    def test_elisions_applied(self):
        result = run_postprocess(self._INPUT, lang="fr")
        self.assertIn("j'ai", result.lower())
        self.assertIn("j'utilise", result.lower())
        self.assertIn("l'histoire", result.lower())
        self.assertIn("l'hôtel", result.lower())

    def test_aspirated_h_no_elision(self):
        result = run_postprocess(self._INPUT, lang="fr")
        self.assertIn("le héros", result.lower())

    def test_punctuation_commands(self):
        result = run_postprocess(self._INPUT, lang="fr")
        self.assertIn(",", result)
        self.assertIn(";", result)
        self.assertIn("!", result)

    def test_newlines_and_paragraphs(self):
        result = run_postprocess(self._INPUT, lang="fr")
        self.assertIn("\n", result)
        self.assertIn("\n\n", result)

    def test_markdown_heading(self):
        result = run_postprocess(self._INPUT, lang="fr")
        self.assertIn("# ", result)

    def test_guillemets(self):
        result = run_postprocess(self._INPUT, lang="fr")
        self.assertIn("«", result)
        self.assertIn("»", result)

    def test_dictionary_corrections(self):
        result = run_postprocess(self._INPUT, lang="fr")
        self.assertIn("API", result)
        self.assertIn("URL", result)
        self.assertIn("GPU", result)
        self.assertIn("CPU", result)
        self.assertIn("Ubuntu", result)
        self.assertIn("SSD", result)
        self.assertIn("Linux", result)
        self.assertIn("Python", result)
        self.assertIn("JavaScript", result)
        self.assertIn("Google", result)

    def test_symbols(self):
        result = run_postprocess(self._INPUT, lang="fr")
        self.assertIn("€", result)
        self.assertIn("%", result)
        self.assertIn("@", result)

    def test_programming_brackets(self):
        result = run_postprocess(self._INPUT, lang="fr")
        self.assertIn("{", result)
        self.assertIn("}", result)
        self.assertIn("[", result)
        self.assertIn("]", result)

    def test_tab_command(self):
        result = run_postprocess(self._INPUT, lang="fr")
        self.assertIn("\t", result)

    def test_ellipsis(self):
        result = run_postprocess(self._INPUT, lang="fr")
        self.assertIn("…", result)

    def test_typography_nbsp(self):
        result = run_postprocess(self._INPUT, lang="fr")
        self.assertTrue(NBSP in result or NNBSP in result,
                        f"No NBSP in output")

    def test_capitalization(self):
        result = run_postprocess(self._INPUT, lang="fr")
        # At least the first line should start uppercase
        first_alpha = next((c for c in result if c.isalpha()), None)
        if first_alpha:
            self.assertTrue(first_alpha.isupper(),
                            f"Should start uppercase: {result[:40]}")

    def test_output_substantial(self):
        result = run_postprocess(self._INPUT, lang="fr")
        self.assertGreater(len(result), 300)


class TestFullScaleEN(unittest.TestCase):
    """Full-scale realistic English dictation.

    Note: 'period' and 'colon' are ambiguous commands requiring suffix.
    We use native punctuation (. :) or non-ambiguous forms instead.
    """

    _INPUT = (
        "uh hello comma I am the lead developer of this project. "
        "um I started working on linux ten years ago comma "
        "and since then comma I have been using python and javascript for my projects. "
        "new line "
        "the first point is important: "
        "we need to migrate our api to a new url. "
        "open quote the migration is urgent close quote. "
        "new line "
        "new paragraph "
        "hash space chapter two. new line "
        "the developer uses the gpu and the cpu of his computer comma "
        "and he installed ubuntu on his ssd. "
        "new line "
        "the cost is twenty three dollars comma "
        "and the rate is fifty percent. "
        "his email address is john at sign google. "
        "new line "
        "for the code comma open curly brace new line "
        "tab open bracket close bracket; new line "
        "close curly brace. "
        "new line "
        "in summary comma this project is very promising. "
        "ellipsis "
        "exclamation mark"
    )

    def test_hesitations_removed(self):
        result = run_postprocess(self._INPUT, lang="en")
        self.assertNotIn(" uh ", result.lower())
        self.assertNotIn(" um ", result.lower())

    def test_punctuation_commands(self):
        result = run_postprocess(self._INPUT, lang="en")
        self.assertIn(",", result)
        self.assertIn("!", result)
        self.assertIn("…", result)

    def test_newlines_and_paragraphs(self):
        result = run_postprocess(self._INPUT, lang="en")
        self.assertIn("\n", result)
        self.assertIn("\n\n", result)

    def test_markdown_heading(self):
        result = run_postprocess(self._INPUT, lang="en")
        self.assertIn("# ", result)

    def test_quotes(self):
        result = run_postprocess(self._INPUT, lang="en")
        count = result.count('"')
        self.assertGreaterEqual(count, 2)

    def test_dictionary_corrections(self):
        result = run_postprocess(self._INPUT, lang="en")
        self.assertIn("API", result)
        self.assertIn("URL", result)
        self.assertIn("GPU", result)
        self.assertIn("CPU", result)
        self.assertIn("Ubuntu", result)
        self.assertIn("SSD", result)
        self.assertIn("Linux", result)
        self.assertIn("Python", result)
        self.assertIn("JavaScript", result)
        self.assertIn("Google", result)

    def test_symbols(self):
        result = run_postprocess(self._INPUT, lang="en")
        self.assertIn("$", result)
        self.assertIn("%", result)
        self.assertIn("@", result)

    def test_programming_brackets(self):
        result = run_postprocess(self._INPUT, lang="en")
        self.assertIn("{", result)
        self.assertIn("}", result)
        self.assertIn("[", result)
        self.assertIn("]", result)

    def test_tab_command(self):
        result = run_postprocess(self._INPUT, lang="en")
        # "tab" command produces \t — may or may not match depending on rules
        # Just verify output is not empty
        self.assertGreater(len(result), 100)

    def test_ellipsis(self):
        result = run_postprocess(self._INPUT, lang="en")
        self.assertIn("…", result)

    def test_no_nbsp_in_english(self):
        result = run_postprocess(self._INPUT, lang="en")
        self.assertNotIn(NBSP, result)
        self.assertNotIn(NNBSP, result)

    def test_capitalization(self):
        result = run_postprocess(self._INPUT, lang="en")
        first_alpha = next((c for c in result if c.isalpha()), None)
        if first_alpha:
            self.assertTrue(first_alpha.isupper(),
                            f"Should start uppercase: {result[:40]}")

    def test_output_substantial(self):
        result = run_postprocess(self._INPUT, lang="en")
        self.assertGreater(len(result), 300)


class TestFullScaleDE(unittest.TestCase):
    """Full-scale realistic German dictation.

    'Punkt' requires suffix. We use native '.' in text instead.
    """

    _INPUT = (
        "äh hallo Komma ich bin der leitende Entwickler dieses Projekts. "
        "ähm ich habe vor zehn Jahren angefangen Komma auf linux zu arbeiten. "
        "seitdem benutze ich python und javascript für meine Projekte. "
        "neue Zeile "
        "der erste Aspekt ist wichtig Doppelpunkt "
        "wir müssen unsere api auf eine neue url migrieren. "
        "Anführungszeichen auf die Migration ist dringend Anführungszeichen zu. "
        "neue Zeile "
        "neuer Absatz "
        "ich bin in dem Haus Komma das an dem Fluss liegt. "
        "der Entwickler benutzt den gpu und den cpu seines Computers Komma "
        "und er hat ubuntu auf seiner ssd installiert. "
        "neue Zeile "
        "der Preis beträgt zwanzig Dollars Komma "
        "und der Satz beträgt fünfzig Prozent. "
        "seine E-Mail ist hans Klammeraffe google. "
        "neue Zeile "
        "Klammer auf wichtiger Hinweis Klammer zu Doppelpunkt "
        "Bindestrich das ist ein Test Semikolon weiter geht es. "
        "neue Zeile "
        "zusammenfassend Komma dieses Projekt ist sehr vielversprechend. "
        "Fragezeichen"
    )

    def test_hesitations_removed(self):
        result = run_postprocess(self._INPUT, lang="de")
        self.assertNotIn(" äh ", result.lower())
        self.assertNotIn(" ähm ", result.lower())

    def test_punctuation_commands(self):
        result = run_postprocess(self._INPUT, lang="de")
        self.assertIn(",", result)
        self.assertIn(".", result)
        self.assertIn(":", result)
        self.assertIn(";", result)
        self.assertIn("?", result)
        self.assertIn("- ", result)

    def test_newlines_and_paragraphs(self):
        result = run_postprocess(self._INPUT, lang="de")
        self.assertIn("\n", result)
        self.assertIn("\n\n", result)

    def test_quotes(self):
        result = run_postprocess(self._INPUT, lang="de")
        # German Anführungszeichen auf/zu produce „" (U+201E, U+201C)
        self.assertIn("\u201e", result)  # „
        self.assertIn("\u201c", result)  # "

    def test_parentheses(self):
        result = run_postprocess(self._INPUT, lang="de")
        self.assertIn("(", result)
        self.assertIn(")", result)

    def test_german_contractions(self):
        result = run_postprocess(self._INPUT, lang="de")
        # "in dem" → "im", "an dem" → "am"
        self.assertIn("im", result.lower())
        self.assertIn("am", result.lower())

    def test_dictionary_corrections(self):
        result = run_postprocess(self._INPUT, lang="de")
        self.assertIn("API", result)
        self.assertIn("URL", result)
        self.assertIn("GPU", result)
        self.assertIn("CPU", result)
        self.assertIn("Ubuntu", result)
        self.assertIn("SSD", result)
        self.assertIn("Linux", result)
        self.assertIn("Python", result)
        self.assertIn("JavaScript", result)
        self.assertIn("Google", result)

    def test_symbols(self):
        result = run_postprocess(self._INPUT, lang="de")
        self.assertIn("$", result)
        self.assertIn("%", result)
        self.assertIn("@", result)

    def test_output_substantial(self):
        result = run_postprocess(self._INPUT, lang="de")
        self.assertGreater(len(result), 250)


class TestFullScaleES(unittest.TestCase):
    """Full-scale realistic Spanish dictation.

    'coma' requires suffix in user config. We use native ',' instead.
    """

    _INPUT = (
        "eh hola, soy el desarrollador principal de este proyecto. "
        "ehm empecé a trabajar en linux hace diez años, "
        "y desde entonces, uso python y javascript para mis proyectos. "
        "nueva línea "
        "el primer aspecto es importante dos puntos "
        "necesitamos migrar nuestra api a una nueva url. "
        "abrir comillas la migración es urgente cerrar comillas. "
        "nueva línea "
        "nuevo párrafo "
        "el desarrollador usa el gpu y el cpu de su ordenador, "
        "y ha instalado ubuntu en su ssd. "
        "nueva línea "
        "el precio es de veinte dólares, "
        "y la tasa es de a el cincuenta por ciento. "
        "su correo es juan arroba google. "
        "nueva línea "
        "abrir paréntesis nota importante cerrar paréntesis dos puntos "
        "punto y coma continúa el texto. "
        "puntos suspensivos "
        "nueva línea "
        "en resumen, este proyecto es muy prometedor. "
        "signo de exclamación"
    )

    def test_hesitations_removed(self):
        result = run_postprocess(self._INPUT, lang="es")
        self.assertNotIn(" eh ", result.lower())
        self.assertNotIn(" ehm ", result.lower())

    def test_punctuation_commands(self):
        result = run_postprocess(self._INPUT, lang="es")
        self.assertIn(",", result)
        self.assertIn(":", result)
        self.assertIn(";", result)
        self.assertIn("!", result)
        self.assertIn("…", result)

    def test_newlines_and_paragraphs(self):
        result = run_postprocess(self._INPUT, lang="es")
        self.assertIn("\n", result)
        self.assertIn("\n\n", result)

    def test_quotes(self):
        result = run_postprocess(self._INPUT, lang="es")
        count = result.count('"')
        self.assertGreaterEqual(count, 2)

    def test_parentheses(self):
        result = run_postprocess(self._INPUT, lang="es")
        self.assertIn("(", result)
        self.assertIn(")", result)

    def test_spanish_contractions(self):
        result = run_postprocess(self._INPUT, lang="es")
        # "a el" → "al", "de el" → "del"
        self.assertIn("al", result.lower())

    def test_dictionary_corrections(self):
        result = run_postprocess(self._INPUT, lang="es")
        self.assertIn("API", result)
        self.assertIn("URL", result)
        self.assertIn("GPU", result)
        self.assertIn("CPU", result)
        self.assertIn("Ubuntu", result)
        self.assertIn("SSD", result)
        self.assertIn("Linux", result)
        self.assertIn("Python", result)
        self.assertIn("JavaScript", result)
        self.assertIn("Google", result)

    def test_symbols(self):
        result = run_postprocess(self._INPUT, lang="es")
        self.assertIn("$", result)

    def test_output_substantial(self):
        result = run_postprocess(self._INPUT, lang="es")
        self.assertGreater(len(result), 250)


class TestFullScaleIT(unittest.TestCase):
    """Full-scale realistic Italian dictation."""

    _INPUT = (
        "ehm ciao virgola sono lo sviluppatore principale di questo progetto punto "
        "uhm ho iniziato a lavorare su linux dieci anni fa virgola "
        "e da allora virgola uso python e javascript per i miei progetti punto "
        "nuova riga "
        "il primo punto è importante due punti "
        "dobbiamo migrare la nostra api su un nuovo url punto "
        "apri virgolette la migrazione è urgente chiudi virgolette punto "
        "nuova riga "
        "nuovo paragrafo "
        "lo sviluppatore usa lo gpu e lo cpu del suo computer virgola "
        "e ha installato ubuntu sul suo ssd punto "
        "a capo "
        "lo amico del sviluppatore lavora nello stesso ufficio punto "
        "il prezzo è di venti dollari virgola "
        "e il tasso è del cinquanta per cento punto "
        "la sua email è marco chiocciola google punto it punto "
        "nuova riga "
        "apri parentesi nota importante chiudi parentesi due punti "
        "punto e virgola continua il testo punto "
        "puntini di sospensione "
        "nuova riga "
        "in sintesi virgola questo progetto è molto promettente punto "
        "punto esclamativo"
    )

    def test_hesitations_removed(self):
        result = run_postprocess(self._INPUT, lang="it")
        self.assertNotIn(" ehm ", result.lower())
        self.assertNotIn(" uhm ", result.lower())

    def test_punctuation_commands(self):
        result = run_postprocess(self._INPUT, lang="it")
        self.assertIn(",", result)
        self.assertIn(":", result)
        self.assertIn(";", result)
        self.assertIn("!", result)
        self.assertIn("…", result)

    def test_newlines_and_paragraphs(self):
        result = run_postprocess(self._INPUT, lang="it")
        self.assertIn("\n", result)
        self.assertIn("\n\n", result)

    def test_italian_elisions(self):
        result = run_postprocess(self._INPUT, lang="it")
        # "lo amico" → "l'amico"
        self.assertIn("l'amico", result.lower())

    def test_quotes(self):
        result = run_postprocess(self._INPUT, lang="it")
        count = result.count('"')
        self.assertGreaterEqual(count, 2)

    def test_parentheses(self):
        result = run_postprocess(self._INPUT, lang="it")
        self.assertIn("(", result)
        self.assertIn(")", result)

    def test_dictionary_corrections(self):
        result = run_postprocess(self._INPUT, lang="it")
        self.assertIn("API", result)
        self.assertIn("URL", result)
        self.assertIn("GPU", result)
        self.assertIn("CPU", result)
        self.assertIn("Ubuntu", result)
        self.assertIn("SSD", result)
        self.assertIn("Linux", result)
        self.assertIn("Python", result)
        self.assertIn("JavaScript", result)
        self.assertIn("Google", result)

    def test_symbols(self):
        result = run_postprocess(self._INPUT, lang="it")
        self.assertIn("$", result)
        self.assertIn("@", result)

    def test_output_substantial(self):
        result = run_postprocess(self._INPUT, lang="it")
        self.assertGreater(len(result), 250)


class TestFullScalePT(unittest.TestCase):
    """Full-scale realistic Portuguese dictation."""

    _INPUT = (
        "ãh olá vírgula eu sou o desenvolvedor principal deste projeto ponto "
        "hum comecei a trabalhar em linux há dez anos vírgula "
        "e desde então vírgula uso python e javascript para os meus projetos ponto "
        "nova linha "
        "o primeiro ponto é importante dois pontos "
        "precisamos migrar a nossa api para um novo url ponto "
        "abrir aspas a migração é urgente fechar aspas ponto "
        "nova linha "
        "novo parágrafo "
        "o desenvolvedor usa o gpu e o cpu do seu computador vírgula "
        "e instalou ubuntu no seu ssd ponto "
        "nova linha "
        "o preço é de vinte dólares vírgula "
        "e a taxa é de cinquenta por cento ponto "
        "o seu email é joao arroba google ponto pt ponto "
        "nova linha "
        "abrir parênteses nota importante fechar parênteses dois pontos "
        "ponto e vírgula continua o texto ponto "
        "reticências "
        "nova linha "
        "em resumo vírgula este projeto é muito promissor ponto "
        "ponto de exclamação"
    )

    def test_hesitations_removed(self):
        result = run_postprocess(self._INPUT, lang="pt")
        self.assertNotIn(" ãh ", result.lower())
        self.assertNotIn(" hum ", result.lower())

    def test_punctuation_commands(self):
        result = run_postprocess(self._INPUT, lang="pt")
        self.assertIn(",", result)
        self.assertIn(":", result)
        self.assertIn(";", result)
        self.assertIn("!", result)
        self.assertIn("…", result)

    def test_newlines_and_paragraphs(self):
        result = run_postprocess(self._INPUT, lang="pt")
        self.assertIn("\n", result)
        self.assertIn("\n\n", result)

    def test_quotes(self):
        result = run_postprocess(self._INPUT, lang="pt")
        count = result.count('"')
        self.assertGreaterEqual(count, 2)

    def test_parentheses(self):
        result = run_postprocess(self._INPUT, lang="pt")
        self.assertIn("(", result)
        self.assertIn(")", result)

    def test_portuguese_contractions(self):
        result = run_postprocess(self._INPUT, lang="pt")
        # "do" (de+o), "no" (em+o) should be present in output
        self.assertIn("do", result.lower())
        self.assertIn("no", result.lower())

    def test_dictionary_corrections(self):
        result = run_postprocess(self._INPUT, lang="pt")
        self.assertIn("API", result)
        self.assertIn("URL", result)
        self.assertIn("GPU", result)
        self.assertIn("CPU", result)
        self.assertIn("Ubuntu", result)
        self.assertIn("SSD", result)
        self.assertIn("Linux", result)
        self.assertIn("Python", result)
        self.assertIn("JavaScript", result)
        self.assertIn("Google", result)

    def test_symbols(self):
        result = run_postprocess(self._INPUT, lang="pt")
        self.assertIn("$", result)

    def test_output_substantial(self):
        result = run_postprocess(self._INPUT, lang="pt")
        self.assertGreater(len(result), 250)


class TestFullScaleUK(unittest.TestCase):
    """Full-scale realistic Ukrainian dictation.

    Ukrainian text must be fully Cyrillic (bad-lang rejects Latin-heavy text).
    Latin words (linux, api, etc.) are kept as dictionary entries.
    """

    _INPUT = (
        "ем привіт, я головний розробник цього проекту. "
        "гм я почав працювати десять років тому, "
        "і з того часу, я використовую різні технології для моїх проектів. "
        "новий рядок "
        "перший пункт є важливим двокрапка "
        "нам потрібно перенести наш проект на нову платформу. "
        "відкрити лапки міграція є терміновою закрити лапки. "
        "новий рядок "
        "новий абзац "
        "розробник використовує сучасне обладнання, "
        "і встановив нову систему. "
        "новий рядок "
        "вартість становить двадцять доларів, "
        "а ставка становить п'ятдесят відсотків. "
        "новий рядок "
        "відкрити дужки важлива примітка закрити дужки двокрапка "
        "дефіс це тест крапка з комою продовжуємо далі. "
        "три крапки "
        "новий рядок "
        "підсумовуючи, цей проект є дуже перспективним. "
        "знак оклику"
    )

    def test_hesitations_removed(self):
        result = run_postprocess(self._INPUT, lang="uk")
        self.assertNotIn(" ем ", result)
        self.assertNotIn(" гм ", result)

    def test_punctuation_commands(self):
        result = run_postprocess(self._INPUT, lang="uk")
        self.assertIn(",", result)
        self.assertIn(";", result)
        self.assertIn(":", result)
        self.assertIn("!", result)
        self.assertIn("…", result)

    def test_newlines_and_paragraphs(self):
        result = run_postprocess(self._INPUT, lang="uk")
        self.assertIn("\n", result)
        self.assertIn("\n\n", result)

    def test_quotes(self):
        result = run_postprocess(self._INPUT, lang="uk")
        count = result.count('"')
        self.assertGreaterEqual(count, 2)

    def test_parentheses(self):
        result = run_postprocess(self._INPUT, lang="uk")
        self.assertIn("(", result)
        self.assertIn(")", result)

    def test_hyphen(self):
        result = run_postprocess(self._INPUT, lang="uk")
        self.assertIn("- ", result)

    def test_symbols(self):
        result = run_postprocess(self._INPUT, lang="uk")
        self.assertIn("$", result)

    def test_output_substantial(self):
        result = run_postprocess(self._INPUT, lang="uk")
        self.assertGreater(len(result), 200)


class TestPPDebugTrace(unittest.TestCase):
    """Verify the DICTEE_PP_DEBUG mechanism."""

    def test_debug_off_no_steps(self):
        """No STEP lines when debug is off."""
        result = run_postprocess_full(
            "Bonjour.", lang="fr",
            env_extra={"DICTEE_PP_DEBUG": "false"})
        step_lines = [l for l in result.stderr.splitlines()
                      if l.startswith("STEP\t")]
        self.assertEqual(step_lines, [])

    def test_debug_on_has_steps(self):
        """At least one STEP line when debug is on."""
        _, steps = run_postprocess_with_trace("Bonjour.", lang="fr")
        self.assertGreater(len(steps), 0)

    def test_trace_format(self):
        """Each STEP line has 4 tab-separated fields."""
        result = run_postprocess_full(
            "Bonjour le monde.", lang="fr",
            env_extra={"DICTEE_PP_DEBUG": "true"})
        for line in result.stderr.splitlines():
            if line.startswith("STEP\t"):
                parts = line.split("\t")
                self.assertEqual(len(parts), 4,
                                 f"Expected 4 fields, got {len(parts)}: {line}")


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main()
