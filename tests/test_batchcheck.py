import pytest

from tools.batchcheck import check_batch, main


def batch(*texts):
    return list(enumerate(texts, start=1))


def filler(i, paragraphs=None):
    """A draft made of words unique to `i`: trips no cross-draft rule."""
    n = paragraphs or (2 + i % 2)
    return "\n\n".join(
        " ".join(f"p{i}x{j}w{k}" for k in range(6)) for j in range(n)
    )


CLEAN_A = (
    "Passei a semana trocando o Celery por RQ.\n\n"
    "A fila caiu de 800ms para 410ms.\n\n"
    "Se o seu worker está estável, não mexa."
)
CLEAN_B = (
    "Todo iniciante pergunta qual linguagem escolher.\n\n"
    "Escolha o problema primeiro. A linguagem vem depois, e Python serve bem.\n\n"
    "Um projeto seu vale mais que dez tutoriais.\n\n"
    "Comece pequeno."
)
CLEAN_C = "O deploy quebrou na sexta às 18h.\n\nO log apontava timeout no Postgres."


class TestCleanBatch:
    def test_distinct_drafts_pass(self):
        assert check_batch(batch(CLEAN_A, CLEAN_B, CLEAN_C)) == []

    def test_fewer_than_two_drafts_pass(self):
        assert check_batch(batch(CLEAN_A)) == []
        assert check_batch([]) == []


class TestDuplicateOpening:
    def test_same_first_two_words_within_a_week_flags(self):
        drafts = batch(
            "Passei a semana no Celery.\n\n" + filler(1),
            filler(2),
            filler(3),
            "Passei a noite no deploy.\n\n" + filler(4),
        )
        rules = [v.rule for v in check_batch(drafts)]
        assert "duplicate_opening" in rules

    def test_same_opening_far_apart_is_fine(self):
        # A feed-sized batch of fillers trips the shape and length rules by
        # design; this test only asserts the opening-duplicate rules stay
        # quiet when the repeat is beyond the window.
        texts = ["Passei a semana no Celery.\n\n" + filler(1)]
        texts += [filler(i) for i in range(2, 12)]
        texts += ["Passei a noite no deploy.\n\n" + filler(12)]
        rules = {v.rule for v in check_batch(batch(*texts))}
        assert "duplicate_opening" not in rules
        assert "consecutive_opening" not in rules

    def test_adjacent_same_two_words_flags_once_not_twice(self):
        drafts = batch(
            "Passei a semana no Celery.\n\n" + filler(1),
            "Passei a noite no deploy.\n\n" + filler(2),
        )
        violations = check_batch(drafts)
        assert [v.rule for v in violations] == ["duplicate_opening"]

    def test_detail_names_both_slots(self):
        drafts = batch(
            "Passei a semana no Celery.\n\n" + filler(1),
            "Passei a noite no deploy.\n\n" + filler(2),
        )
        detail = check_batch(drafts)[0].detail
        assert "1" in detail and "2" in detail


class TestConsecutiveOpening:
    def test_same_first_word_on_consecutive_days_flags(self):
        drafts = batch(
            "Python muda devagar.\n\n" + filler(1),
            "Python resolve o resto.\n\n" + filler(2),
        )
        rules = [v.rule for v in check_batch(drafts)]
        assert rules == ["consecutive_opening"]

    def test_same_first_word_with_a_day_between_is_fine(self):
        drafts = batch(
            "Python muda devagar.\n\n" + filler(1),
            filler(2),
            "Python resolve o resto.\n\n" + filler(3),
        )
        assert check_batch(drafts) == []


class TestRepeatedPhrase:
    def test_shared_five_word_phrase_flags_once_per_pair(self):
        shared = "a complexidade da ferramenta compete com o problema"
        drafts = batch(
            filler(1) + f"\n\n{shared}.",
            filler(2),
            filler(3) + f"\n\nQuando {shared}, troque.",
        )
        violations = [v for v in check_batch(drafts) if v.rule == "repeated_phrase"]
        assert len(violations) == 1
        assert "1" in violations[0].detail and "3" in violations[0].detail

    def test_distinct_phrasing_is_fine(self):
        assert check_batch(batch(CLEAN_A, CLEAN_B)) == []


class TestUniformStructure:
    def test_three_consecutive_drafts_with_same_paragraph_count_flag(self):
        drafts = batch(
            filler(1, paragraphs=3),
            filler(2, paragraphs=3),
            filler(3, paragraphs=3),
        )
        violations = [v for v in check_batch(drafts) if v.rule == "uniform_structure"]
        assert len(violations) == 1

    def test_two_consecutive_with_same_count_are_fine(self):
        drafts = batch(
            filler(1, paragraphs=3),
            filler(2, paragraphs=3),
            filler(3, paragraphs=4),
        )
        assert check_batch(drafts) == []


class TestMain:
    def test_reports_violations_and_exits_1(self, tmp_path, capsys):
        (tmp_path / "01.txt").write_text("Passei a semana aqui.\n\n" + filler(1), encoding="utf-8")
        (tmp_path / "02.txt").write_text("Passei a noite ali.\n\n" + filler(2), encoding="utf-8")
        assert main([str(tmp_path)]) == 1
        assert "duplicate_opening" in capsys.readouterr().out

    def test_clean_directory_exits_0(self, tmp_path):
        (tmp_path / "01.txt").write_text(CLEAN_A, encoding="utf-8")
        (tmp_path / "02.txt").write_text(CLEAN_B, encoding="utf-8")
        assert main([str(tmp_path)]) == 0

    def test_orders_drafts_by_slot_number_not_string_order(self, tmp_path):
        (tmp_path / "02.txt").write_text("Python resolve o resto.\n\n" + filler(1), encoding="utf-8")
        (tmp_path / "10.txt").write_text(filler(2), encoding="utf-8")
        (tmp_path / "11.txt").write_text("Python muda devagar.\n\n" + filler(3), encoding="utf-8")
        assert main([str(tmp_path)]) == 0

    def test_single_draft_exits_0(self, tmp_path):
        (tmp_path / "01.txt").write_text(CLEAN_A, encoding="utf-8")
        assert main([str(tmp_path)]) == 0

    def test_missing_directory_exits_2(self, tmp_path):
        assert main([str(tmp_path / "nope")]) == 2

    def test_non_numeric_filename_exits_2(self, tmp_path):
        (tmp_path / "rascunho.txt").write_text(CLEAN_A, encoding="utf-8")
        assert main([str(tmp_path)]) == 2


from tools.batchcheck import check_batch_warnings, classify_ending, classify_opening


class TestShapeClassifiers:
    def test_question_wins_over_everything(self):
        assert classify_opening("Quanto custa 3 retries, você sabe?") == "pergunta"

    def test_digit_beats_person_markers(self):
        assert classify_opening("Passei 3 dias nisso.") == "numero"

    def test_first_person(self):
        assert classify_opening("Passei a semana no worker.") == "eu"

    def test_direct_address(self):
        assert classify_opening("Seu deploy merece cuidado.") == "voce"

    def test_claim_is_the_fallback(self):
        assert classify_opening("Arquitetura é decisão adiada.") == "afirmacao"

    def test_ending_bands(self):
        assert classify_ending("Primeira frase longa. Curto.") == "curta"
        assert classify_ending("Fecho. " + "palavra " * 15 + "fim.") == "media"
        assert classify_ending("Fecho. " + "palavra " * 25 + "fim.") == "longa"


class TestShapeRules:
    def test_small_batches_skip_shape_rules(self):
        texts = [filler(i) for i in range(1, 8)]  # 7 drafts, all one shape
        rules = {v.rule for v in check_batch(batch(*texts))}
        assert not rules & {"opening_shape_run", "opening_shape_mix",
                            "ending_shape_run", "ending_shape_mix", "pet_phrase"}

    def test_feed_sized_monotone_batch_flags_shapes(self):
        texts = [filler(i) for i in range(1, 10)]  # 9 drafts, all one shape
        rules = {v.rule for v in check_batch(batch(*texts))}
        assert "opening_shape_run" in rules
        assert "opening_shape_mix" in rules
        assert "ending_shape_run" in rules
        assert "ending_shape_mix" in rules

    def test_pet_phrase_fails_at_four_drafts_not_three(self):
        texts = [filler(i) for i in range(1, 10)]
        for i in (0, 2, 4):
            texts[i] += "\n\nO teste de mesa."
        assert "pet_phrase" not in {v.rule for v in check_batch(batch(*texts))}
        texts[6] += "\n\nO teste de mesa."
        assert "pet_phrase" in {v.rule for v in check_batch(batch(*texts))}

    def test_all_stopword_trigrams_are_not_pet_phrases(self):
        texts = [filler(i) for i in range(1, 10)]
        for i in (0, 2, 4, 6):
            texts[i] += "\n\nMas o que se vê."  # "o que se" is pure glue
        grams = [v.excerpt for v in check_batch(batch(*texts)) if v.rule == "pet_phrase"]
        assert "o que se" not in grams


class TestLengthRules:
    def test_uniform_sizes_flag_for_a_feed_sized_batch(self):
        texts = [filler(i, paragraphs=2) for i in range(1, 10)]
        rules = {v.rule for v in check_batch(batch(*texts))}
        assert "uniform_length" in rules
        assert "length_run" in rules

    def test_mixed_sizes_pass_the_length_rules(self):
        texts = [filler(i, paragraphs=2 if i % 2 else 8) for i in range(1, 10)]
        rules = {v.rule for v in check_batch(batch(*texts))}
        assert "uniform_length" not in rules
        assert "length_run" not in rules


class TestWarnings:
    def test_filler_spread_and_forming_pet_phrases_warn(self):
        texts = [filler(i) for i in range(1, 10)]
        for i in (0, 2, 4, 6):
            texts[i] += "\n\nIsso importa de verdade."
        rules = {v.rule for v in check_batch_warnings(batch(*texts))}
        assert "filler_spread" in rules

    def test_warnings_stay_silent_below_the_shape_floor(self):
        texts = [filler(i) + "\n\nIsso importa de verdade." for i in range(1, 5)]
        assert check_batch_warnings(batch(*texts)) == []
