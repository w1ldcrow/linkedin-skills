import pytest

from tools.voicecheck import (
    LIMITS,
    Violation,
    check,
    find_banned_phrases,
    find_emojis,
    main,
)


class TestFindEmojis:
    def test_clean_text_has_no_violations(self):
        assert find_emojis("Escrevi um MCP server em Python nesta semana.") == []

    def test_detects_rocket(self):
        violations = find_emojis("Lancei o projeto 🚀")
        assert len(violations) == 1
        assert violations[0].rule == "emoji"
        assert "🚀" in violations[0].excerpt

    def test_detects_check_mark_and_heart(self):
        violations = find_emojis("Feito ✅ e curtido ❤")
        assert len(violations) == 2

    def test_detects_flag_regional_indicators(self):
        assert len(find_emojis("Direto do Brasil 🇧🇷")) == 2

    def test_em_dash_and_bullets_are_not_emojis(self):
        assert find_emojis("Item — outro item • terceiro item…") == []

    def test_accented_portuguese_is_not_an_emoji(self):
        assert find_emojis("Configuração, manutenção e ação são coisas distintas.") == []


class TestFindBannedPhrases:
    @pytest.mark.parametrize(
        "text,rule_detail",
        [
            ("Achei interessante. Comenta aí!", "engagement bait"),
            ("Isso muda tudo. Concorda?", "engagement bait"),
            ("Não é sobre a linguagem. É sobre o problema.", "antithesis construction"),
            ("Spoiler: não funcionou.", "clickbait marker"),
            ("Plot twist: o bug era meu.", "clickbait marker"),
            ("Uma solução revolucionária para filas.", "unearned superlative"),
            ("Humildemente, recebi a promoção.", "false humility"),
            ("Feliz em anunciar que entrei na nova empresa.", "announcement cliche"),
            ("5 lições que aprendi migrando para Postgres.", "listicle hook"),
            ("No mundo de hoje, tudo é assíncrono.", "LLM tell"),
            ("Vale ressaltar que o teste falhou.", "LLM tell"),
            ("Ótimo post, Maria!", "empty comment"),
        ],
    )
    def test_detects_banned_phrase(self, text, rule_detail):
        violations = find_banned_phrases(text)
        assert len(violations) >= 1
        assert violations[0].rule == "banned_phrase"
        assert violations[0].detail == rule_detail

    def test_detection_is_case_insensitive(self):
        assert len(find_banned_phrases("SPOILER: deu certo.")) == 1

    def test_clean_portuguese_passes(self):
        text = "Troquei Celery por RQ em um worker de 40 mil jobs por dia. A latência caiu pela metade."
        assert find_banned_phrases(text) == []

    def test_violation_carries_the_matched_excerpt(self):
        violations = find_banned_phrases("Bom dia. Plot twist: era cache.")
        assert violations[0].excerpt.lower() == "plot twist"


class TestEnglishBannedPhrases:
    @pytest.mark.parametrize(
        "text,rule_detail",
        [
            ("Interesting stuff. Thoughts?", "engagement bait"),
            ("This changes everything. Agree?", "engagement bait"),
            ("Let that sink in.", "engagement bait"),
            ("It's not about the language. It's about the problem.", "antithesis construction"),
            ("It’s not about tools. It’s about people.", "antithesis construction"),
            ("Hot take: monoliths are fine.", "clickbait marker"),
            ("Unpopular opinion: tests are optional.", "clickbait marker"),
            ("Here's the thing about queues.", "clickbait marker"),
            ("A revolutionary approach to queues.", "unearned superlative"),
            ("The results were mind-blowing.", "unearned superlative"),
            ("I'm humbled to receive this award.", "false humility"),
            ("Thrilled to announce I joined a new team.", "announcement cliche"),
            ("Excited to share our launch.", "announcement cliche"),
            ("I failed many times until I understood queues.", "manufactured vulnerability"),
            ("5 lessons I learned migrating to Postgres.", "listicle hook"),
            ("3 things nobody tells you about Kafka.", "listicle hook"),
            ("In today's fast-paced world, everything is async.", "LLM tell"),
            ("It's worth noting that the test failed.", "LLM tell"),
            ("Let's delve into the internals.", "LLM tell"),
            ("Great post, Maria!", "empty comment"),
            ("Congrats on the post!", "empty comment"),
        ],
    )
    def test_detects_english_banned_phrase(self, text, rule_detail):
        violations = find_banned_phrases(text)
        assert len(violations) >= 1
        assert violations[0].rule == "banned_phrase"
        assert violations[0].detail == rule_detail

    def test_clean_english_passes(self):
        text = (
            "I swapped Celery for RQ in a worker that handles 40k jobs a day. "
            "Median latency went from 800ms to 410ms, which was a side effect, not the goal."
        )
        assert find_banned_phrases(text) == []

    def test_english_words_do_not_fire_on_portuguese(self):
        text = "Migrei o worker para RQ e a latência caiu para 410ms. O resto ficou igual."
        assert find_banned_phrases(text) == []


CLEAN_ENGLISH_POST = (
    "I spent the week swapping Celery for RQ in a worker that processes 40k jobs a day. "
    "The motivation was not performance; it was being able to read the retry code without "
    "opening 3 files. Celery solves far more problems than I have, and that generality "
    "shows up in the configuration. RQ has a smaller surface: one queue, one worker, one "
    "decorator. The migration took two days, one of them spent rewriting integration tests "
    "that depended on eager mode. Median latency dropped from 800ms to 410ms, but that is a "
    "side effect, not the goal. If your worker is already stable on Celery there is no "
    "reason to touch it. The swap only pays off when the tool's complexity starts competing "
    "with the problem's complexity. Celery remains an excellent piece of engineering. "
    "It just was not the piece this project needed."
)


class TestEnglishPost:
    def test_clean_english_post_passes_every_rule(self):
        assert check(CLEAN_ENGLISH_POST, kind="post") == []

    def test_english_post_ending_in_question_is_flagged(self):
        text = CLEAN_ENGLISH_POST.rsplit(".", 1)[0] + ". Would you do it differently?"
        assert [v.rule for v in check(text, kind="post")] == ["ends_with_question"]

    def test_english_empty_comment_is_flagged(self):
        violations = check("Great post! Really enjoyed reading this one, thanks for sharing it with us.", kind="comment")
        assert any(v.detail == "empty comment" for v in violations)


CLEAN_POST = (
    "Passei a semana trocando o Celery por RQ em um worker que processa 40 mil jobs por dia. "
    "A motivação não foi performance, foi conseguir ler o código de retry sem abrir 3 arquivos. "
    "O Celery resolve muito mais problemas do que eu tenho, e essa generalidade aparece na "
    "configuração. RQ tem uma superfície menor: uma fila, um worker, um decorator. "
    "A migração levou dois dias, sendo um dia inteiro só para reescrever os testes de "
    "integração que dependiam do eager mode. A latência mediana caiu de 800ms para 410ms, "
    "mas isso é efeito colateral, não o objetivo. O ganho real foi outro: quando um job falha "
    "às 3 da manhã, agora eu entendo o stack trace na primeira leitura. "
    "Se o seu worker já está estável no Celery, não existe motivo para mexer. A troca só se "
    "paga quando a complexidade da ferramenta passa a competir com a complexidade do "
    "problema, e esse ponto chega em time pequeno muito antes do que a documentação sugere. "
    "Continuo achando o Celery uma peça excelente de engenharia. "
    "Ele só não era a peça que esse projeto pedia."
)

VAGUE_POST = (
    "Venho pensando bastante sobre a natureza do trabalho de engenharia e sobre como "
    "a gente constrói coisas ao longo do tempo. Existe uma tensão permanente entre "
    "resolver o problema de hoje e preparar terreno para o problema de amanhã, e eu "
    "não acho que exista resposta definitiva para isso. O que aprendi é que a escolha "
    "depende muito mais do contexto do time do que de qualquer princípio abstrato. "
    "Times pequenos podem se dar ao luxo de errar rápido e corrigir depois. Times "
    "grandes carregam o peso de cada decisão por muito mais tempo, então a mesma "
    "escolha tem custos completamente diferentes dependendo de onde você está sentado. "
    "Talvez a única regra que sobreviva seja perguntar quem vai manter aquilo daqui a "
    "alguns meses, e se essa pessoa vai entender a intenção por trás da escolha sem "
    "precisar de arqueologia. Quando a resposta é sim, costumo seguir em frente. "
    "Sigo tentando encontrar o equilíbrio, sem pressa de chegar a uma conclusão."
)


class TestLimits:
    def test_every_kind_has_limits(self):
        assert set(LIMITS) == {"post", "comment", "headline", "about", "note"}

    def test_post_window_matches_the_spec(self):
        # Wide on purpose: length variety is policed per-batch by batchcheck,
        # not per-post here. 2900 leaves margin under LinkedIn's 3000 cap.
        assert LIMITS["post"] == (300, 2900)

    def test_headline_and_about_match_linkedin_caps(self):
        assert LIMITS["headline"][1] == 220
        assert LIMITS["about"][1] == 2600

    def test_connection_note_stays_in_the_always_safe_range(self):
        assert LIMITS["note"][1] == 200


class TestCheck:
    def test_clean_post_passes(self):
        assert check(CLEAN_POST, kind="post") == []

    def test_rejects_unknown_kind(self):
        with pytest.raises(ValueError, match="unknown kind"):
            check("texto", kind="tweet")

    def test_flags_post_that_is_too_short(self):
        violations = check("Curto demais, mas com 1 número.", kind="post")
        assert any(v.rule == "length" for v in violations)

    def test_flags_post_that_is_too_long(self):
        text = CLEAN_POST
        while len(text) <= 2900:
            text += " " + CLEAN_POST
        violations = check(text, kind="post")
        assert any(v.rule == "length" for v in violations)

    def test_flags_post_ending_in_a_question(self):
        text = CLEAN_POST[:-1].rsplit(".", 1)[0] + ". Você faria diferente?"
        violations = check(text, kind="post")
        assert [v.rule for v in violations] == ["ends_with_question"]

    def test_headline_may_end_in_a_question_mark_free_statement(self):
        assert check("Dev Full-stack Pleno em Python e backend", kind="headline") == []

    def test_flags_more_than_three_hashtags(self):
        text = CLEAN_POST + " #python #backend #mcp #devops"
        assert any(v.rule == "hashtags" for v in check(text, kind="post"))

    def test_flags_uppercase_hashtags(self):
        text = CLEAN_POST + " #Python"
        assert any(v.rule == "hashtags" for v in check(text, kind="post"))

    def test_three_lowercase_hashtags_pass(self):
        text = CLEAN_POST + " #python #backend #mcp"
        assert check(text, kind="post") == []

    def test_flags_post_with_no_concrete_specific(self):
        violations = check(VAGUE_POST, kind="post")
        assert [v.rule for v in violations] == ["no_concrete"]

    def test_emoji_and_banned_phrase_rules_apply_to_comments(self):
        violations = check("Ótimo post! 🚀", kind="comment")
        rules = {v.rule for v in violations}
        assert "emoji" in rules
        assert "banned_phrase" in rules

    def test_concreteness_is_not_required_for_headlines(self):
        assert check("Desenvolvedor full-stack focado em backend", kind="headline") == []


class TestMain:
    def test_returns_zero_for_clean_input(self, tmp_path, capsys):
        path = tmp_path / "post.txt"
        path.write_text(CLEAN_POST, encoding="utf-8")
        assert main([str(path), "--kind", "post"]) == 0
        assert "OK" in capsys.readouterr().out

    def test_returns_one_and_prints_each_violation(self, tmp_path, capsys):
        path = tmp_path / "post.txt"
        path.write_text("Ótimo post! 🚀", encoding="utf-8")
        assert main([str(path), "--kind", "comment"]) == 1
        out = capsys.readouterr().out
        assert "emoji" in out
        assert "banned_phrase" in out

    def test_returns_two_for_a_missing_file(self, tmp_path, capsys):
        assert main([str(tmp_path / "nope.txt"), "--kind", "post"]) == 2
        assert "not found" in capsys.readouterr().err
