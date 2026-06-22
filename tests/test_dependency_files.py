from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _read_requirements(path: str) -> list[str]:
    return [
        line.strip()
        for line in (REPOSITORY_ROOT / path).read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def test_runtime_requirements_use_reachable_mysql_connector_package() -> None:
    requirements = _read_requirements("requirements.txt")

    assert "mysql-connector-python>=9.3,<10" in requirements
    assert not any(requirement.startswith("http://cdn.mysql.com/") for requirement in requirements)


def test_runtime_dependency_compatibility_pins_match_local_docker_baseline() -> None:
    requirements = set(_read_requirements("requirements.txt"))
    local_docker_requirements = set(_read_requirements("requirements.local-docker.txt"))

    compatibility_requirements = {
        "mysql-connector-python>=9.3,<10",
        "six>=1.17,<2",
        "sqlalchemy>=2,<3",
        "ujson>=5.13,<6",
    }

    assert compatibility_requirements <= requirements
    assert compatibility_requirements <= local_docker_requirements


def test_incremental_rating_dependency_stays_trueskill_compatible() -> None:
    requirements = _read_requirements("requirements.txt")
    local_docker_requirements = _read_requirements("requirements.local-docker.txt")

    assert "trueskill==0.4.4" in requirements
    assert "trueskill==0.4.4" in local_docker_requirements
    assert not any(requirement.startswith("openskill") for requirement in requirements)
    assert not any(requirement.startswith("openskill") for requirement in local_docker_requirements)
