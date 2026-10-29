import copy
import json
from pathlib import Path

import pytest

from tools.cvtailor import build_index, check, render_html, tech_terms

SOURCE = {
    "name": "Ana Souza",
    "headline": "Desenvolvedora Back-end",
    "contact": ["Recife, PE", "ana@exemplo.com"],
    "links": ["github.com/ana"],
    "summary": "Desenvolvedora back-end desde 2022. Construí uma API em Python e FastAPI com 40 integrações.",
    "skills": [
        {"label": "Back-end", "items": "Python, FastAPI, PostgreSQL, Redis"},
        {"label": "Infra", "items": "Docker, Kubernetes, AWS, GitHub Actions (CI/CD)"},
    ],
    "experience": [
        {
            "title": "Desenvolvedora Back-end",
            "company": "Loja",
            "place": "São Paulo, SP (remoto)",
            "period": "01/2023 – 12/2025",
            "context": "E-commerce com time de 5 pessoas.",
            "bullets": [
                "Construí a API de pedidos em FastAPI com PostgreSQL, atendendo 300 lojas.",
                "Integrei 40 parceiros de frete e pagamento por API.",
                "Configurei deploy em Kubernetes na AWS com GitHub Actions.",
            ],
        }
    ],
    "education": [{"title": "Bacharelado em Física", "school": "UFPE, Recife, PE", "period": "2018 – 2021"}],
}


def tailored(**changes):
    resume = copy.deepcopy(SOURCE)
    resume.update(changes)
    return resume


def bullets(*lines):
    resume = copy.deepcopy(SOURCE)
    resume["experience"][0]["bullets"] = list(lines)
    return resume


class TestCheck:
    def test_the_source_passes_against_itself(self):
        assert check(SOURCE, SOURCE) == ([], [])

    def test_reordering_and_rewording_pass(self):
        resume = bullets(
            "Integrei por API 40 parceiros de frete e pagamento.",
            "Construí a API de pedidos em FastAPI com PostgreSQL, atendendo 300 lojas.",
            "Configurei deploy em Kubernetes na AWS com GitHub Actions.",
        )
        resume["skills"] = list(reversed(resume["skills"]))
        resume["summary"] = "Back-end em Python e FastAPI desde 2022, com 40 integrações por API."
        errors, _ = check(SOURCE, resume)
        assert errors == []

    def test_an_invented_number_fails(self):
        errors, _ = check(SOURCE, tailored(summary="Desenvolvedora back-end desde 2022, com 7 anos de API."))
        assert "number not in the source: 7" in errors

    def test_a_source_number_counting_something_else_fails(self):
        errors, _ = check(SOURCE, tailored(summary="Desenvolvedora back-end com 5 anos de experiência."))
        assert "number used for something else than in the source: 5 anos" in errors

    def test_a_number_inside_a_bigger_one_is_not_enough(self):
        errors, _ = check(SOURCE, tailored(summary="Construí APIs com 30 integrações."))
        assert "number not in the source: 30" in errors

    @pytest.mark.parametrize("claim, term", [
        ("Experiência com Kafka e filas.", "kafka"),
        ("APIs em Django.", "django"),
        ("Arquitetura de microsserviços.", "microsservicos"),
        ("Deploy com ArgoCD.", "argocd"),
        ("Integração via GraphQL.", "graphql"),
    ])
    def test_an_invented_technology_fails(self, claim, term):
        errors, _ = check(SOURCE, tailored(summary=claim))
        assert f"technology or practice not in the source: {term}" in errors

    def test_a_seniority_upgrade_fails(self):
        errors, _ = check(SOURCE, tailored(headline="Desenvolvedora Back-end Sênior"))
        assert "seniority word not in the source: senior" in errors

    def test_a_changed_employer_or_period_fails(self):
        resume = copy.deepcopy(SOURCE)
        resume["experience"][0]["period"] = "01/2021 – 12/2025"
        errors, _ = check(SOURCE, resume)
        assert any("period changed" in error for error in errors)

    def test_a_dropped_bullet_fails(self):
        errors, _ = check(SOURCE, bullets("Integrei 40 parceiros de frete e pagamento por API."))
        assert "experience 1: bullet count changed" in errors

    def test_a_new_skills_label_fails(self):
        resume = copy.deepcopy(SOURCE)
        resume["skills"].append({"label": "Mensageria", "items": "Redis"})
        errors, _ = check(SOURCE, resume)
        assert "skills label not in the source: Mensageria" in errors

    def test_contact_and_education_are_frozen(self):
        errors, _ = check(SOURCE, tailored(contact=["Recife, PE"], education=[]))
        assert "contact differs from the source" in errors
        assert "education differs from the source" in errors

    def test_a_bullet_with_no_source_counterpart_warns(self):
        resume = bullets(
            "Liderei a estratégia de produto junto a diretoria comercial.",
            "Integrei 40 parceiros de frete e pagamento por API.",
            "Configurei deploy em Kubernetes na AWS com GitHub Actions.",
        )
        _, warnings = check(SOURCE, resume)
        assert any("resembles no source bullet" in warning for warning in warnings)


class TestTechTerms:
    def test_finds_known_camelcase_acronyms_and_dotted_names(self):
        assert {"python", "fastapi", "aw", "node.j", "graphql"} <= tech_terms("Python, FastAPI, AWS, Node.js e GraphQL")

    def test_ignores_ordinary_capitalized_words(self):
        assert tech_terms("Construí a plataforma em Recife") == set()


class TestRender:
    def test_escapes_and_keeps_every_section(self):
        resume = tailored(summary="APIs <rápidas> & estáveis")
        page = render_html(resume)
        assert "APIs &lt;rápidas&gt; &amp; estáveis" in page
        for text in ("Ana Souza", "Competências", "Loja", "Bacharelado em Física", "github.com/ana"):
            assert text in page


class TestIndex:
    def test_lists_target_and_changes(self, tmp_path: Path):
        resume = tailored(target={"title": "Backend Python", "company": "Acme", "url": "https://x/1"},
                          changes=["Resumo abre com FastAPI"])
        (tmp_path / "01-acme-1.json").write_text(json.dumps(resume))
        index = build_index(tmp_path)
        assert "## 01-acme-1 — Backend Python · Acme" in index
        assert "- Resumo abre com FastAPI" in index
