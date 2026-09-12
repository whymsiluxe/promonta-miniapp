from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "frontend" / "app.html"
CONTRACTS_JS = ROOT / "frontend" / "js" / "contracts.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_contracts_module_is_loaded_before_app_bootstrap():
    src = _source(APP_HTML)

    assert '<script src="js/contracts.js"></script>' in src
    assert src.index('<script src="js/contracts.js"></script>') < src.index("<script>\n// Mängel")


def test_contracts_logic_is_not_inline_in_app_html():
    src = _source(APP_HTML)

    assert "async function initContractsView()" not in src
    assert "async function openContractDetail(" not in src
    assert 'onclick="openContractDetail' not in src


def test_contract_cards_use_dataset_listener_not_inline_handler():
    src = _source(CONTRACTS_JS)

    assert 'data-contract-id="${esc(c.id)}"' in src
    assert "querySelectorAll('.contract-card[data-contract-id]')" in src
    assert "addEventListener('click', () => openContractDetail(card.dataset.contractId))" in src
    assert 'onclick="openContractDetail' not in src
