import re
from pathlib import Path
from services.orchestrator.app.llm.vertex import MockVertexAIClient, CHECKOUT_FILL_ACTIONS

SRC = Path(__file__).resolve().parents[3] / "demo" / "shophive" / "frontend" / "src"
PAGES = {"", "product/air-max-90", "product/jordan-1", "cart", "checkout", "orders", "settings"}

def _id_patterns():
    text = "\n".join(p.read_text(encoding="utf-8") for p in SRC.rglob("*.tsx"))
    literal = set(re.findall(r'data-ghost-id="([^"]+)"', text))
    templates = [
        re.compile("^" + ".+".join(re.escape(part) for part in re.split(r"\$\{[^}]+\}", t)) + "$")
        for t in re.findall(r'data-ghost-id={`([^`]+)`}', text)
    ]
    return literal, templates

def _actions():
    for fixture in MockVertexAIClient.FIXTURES.values():
        yield from fixture.get("actions", [])
    yield from CHECKOUT_FILL_ACTIONS

def test_every_fixture_target_exists_in_demo():
    literal, templates = _id_patterns()
    for action in _actions():
        ids = [action["target_id"]] if "target_id" in action else []
        ids += [s["target_id"] for s in action.get("steps", [])]
        for target_id in ids:
            assert target_id in literal or any(t.match(target_id) for t in templates), target_id
        if action["type"] == "navigate":
            assert action["target_page"] in PAGES, action["target_page"]
