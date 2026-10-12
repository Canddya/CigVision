"""Acceptance check for the factory line image interface and its configuration page."""
from pathlib import Path
import uuid

import httpx
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8002"
KEY = "line-acceptance-key-2026"
SAMPLE = ROOT / "CigYOLO" / "data" / "良好" / "Image00710.BMP"
OUTPUT = ROOT / "docs" / "acceptance" / "line-interface"


def check_api():
    client = httpx.Client(base_url=BASE, timeout=120)
    config = client.get("/api/line/config")
    assert config.status_code == 200, config.text
    original = config.json()
    disabled_config = client.put(
        "/api/line/config",
        json={
            "enabled": False,
            "line_name": original["line_name"],
            "device_code": original["device_code"],
        },
    )
    assert disabled_config.status_code == 200, disabled_config.text
    disabled = client.post(
        "/api/line/image",
        headers={"X-CigYOLO-Key": KEY},
        files={"image": (SAMPLE.name, SAMPLE.read_bytes(), "image/bmp")},
    )
    assert disabled.status_code == 503, disabled.text

    if not original["api_key_configured"]:
        missing_key = client.put(
            "/api/line/config",
            json={"enabled": True, "line_name": "验收包装线", "device_code": "QA-LINE-01"},
        )
        assert missing_key.status_code == 400, missing_key.text

    enabled = client.put(
        "/api/line/config",
        json={
            "enabled": True,
            "line_name": "验收包装线",
            "device_code": "QA-LINE-01",
            "new_api_key": KEY,
        },
    )
    assert enabled.status_code == 200 and enabled.json()["api_key_configured"]

    wrong_key = client.post(
        "/api/line/image",
        headers={"X-CigYOLO-Key": "wrong-key-wrong-key"},
        files={"image": (SAMPLE.name, SAMPLE.read_bytes(), "image/bmp")},
    )
    assert wrong_key.status_code == 401, wrong_key.text

    client_image_id = f"acceptance-{uuid.uuid4().hex}"
    headers = {"X-CigYOLO-Key": KEY, "X-Image-ID": client_image_id}
    inferred = client.post(
        "/api/line/image",
        headers=headers,
        files={"image": (SAMPLE.name, SAMPLE.read_bytes(), "image/bmp")},
    )
    assert inferred.status_code == 200, inferred.text
    result = inferred.json()
    assert result["accepted"] and result["result"] in {"良好", "缺陷"}
    assert 0 <= result["confidence"] <= 1

    duplicate = client.post(
        "/api/line/image",
        headers=headers,
        files={"image": (SAMPLE.name, SAMPLE.read_bytes(), "image/bmp")},
    )
    assert duplicate.status_code == 409, duplicate.text
    client.close()
    return result


def check_page():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        )
        desktop = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        desktop.on("pageerror", lambda error: errors.append(str(error)))
        desktop.goto(BASE, wait_until="networkidle")
        assert desktop.locator("#lineEntryStatus").inner_text() == "已启用"
        desktop.screenshot(path=OUTPUT / "desktop-entry.png", full_page=True)
        desktop.locator("#openLineConfig").click()
        desktop.locator("#lineConfig").wait_for(state="visible")
        assert desktop.locator("#lineEndpoint").inner_text() == f"{BASE}/api/line/image"
        assert desktop.locator("#lineConfigState").inner_text() == "已启用"
        desktop.locator("#lineName").fill("验收包装线-网页")
        desktop.locator("#saveLineConfig").click()
        desktop.locator("#lineSaveMessage").get_by_text("配置已保存并立即生效。").wait_for()
        assert desktop.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
        desktop.screenshot(path=OUTPUT / "desktop-config.png", full_page=True)

        mobile = browser.new_page(viewport={"width": 390, "height": 844})
        mobile.goto(BASE, wait_until="networkidle")
        mobile.locator("#openLineConfig").click()
        mobile.locator("#lineConfig").wait_for(state="visible")
        assert mobile.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
        mobile.screenshot(path=OUTPUT / "mobile-config.png", full_page=True)
        browser.close()
        assert not errors, errors


if __name__ == "__main__":
    prediction = check_api()
    check_page()
    print(
        "PASS",
        prediction["result"],
        f"confidence={prediction['confidence']:.4f}",
        f"elapsed_ms={prediction['elapsed_ms']}",
        f"batch={prediction['batch_id']}",
    )
