#!/usr/bin/env python3
"""Optional browser checks and screenshots. Install Playwright separately."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import threading

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server import make_server


@contextmanager
def running_server(path):
    with make_server(path, port=0) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            thread.join(timeout=5)


def assert_layout(page):
    problems = page.evaluate("""() => {
      const board = document.getElementById('board');
      const result = [];
      if (document.documentElement.scrollWidth > innerWidth ||
          document.documentElement.scrollHeight > innerHeight) result.push('document overflow');
      for (const el of board.querySelectorAll('.panel,.money,.board-header')) {
        const r = el.getBoundingClientRect();
        if (r.left < -1 || r.top < -1 || r.right > innerWidth+1 || r.bottom > innerHeight+1)
          result.push('outside viewport: '+el.className);
        if (el.scrollWidth > el.clientWidth+1 || el.scrollHeight > el.clientHeight+1)
          result.push('panel overflow: '+(el.dataset.detail||el.className));
      }
      for (const selector of ['.panel-head','.wait-route','.wait-stage','.wait-alert',
                               '.wait-age','.schedule-time','.hand-when','.money-value']) {
        for (const el of board.querySelectorAll(selector)) {
          if (el.scrollWidth > el.clientWidth+1)
            result.push('unintended clipping: '+selector);
        }
      }
      return result;
    }""")
    assert not problems, problems


def browser_checks(page, path, demo):
    page.evaluate("""() => {
      window.__calls=0;
      const original=window.fetch;
      window.fetch=(...args)=>{window.__calls++;return original(...args);};
    }""")
    page.clock.run_for(60010)
    assert page.evaluate("window.__calls") >= 1, "Minute polling did not run"
    page.clock.pause_at(datetime.fromtimestamp(page.evaluate('Date.now()') / 1000 + 1,
                                               timezone.utc))
    changed = json.loads(json.dumps(demo))
    changed["decisions"][0]["what"] = "A changed choice"
    changed["hands"][0]["when"] = "12:30"
    changed["requests"][0]["blocked"] = True
    path.write_text(json.dumps(changed), encoding="utf-8")
    page.evaluate("tick()")
    assert page.locator('.decision-title.chg').count() == 1
    assert page.locator('.hand-when.chg').count() == 1
    assert page.locator('.wait-alert .chg').count() == 1
    assert page.locator('.wait-alert').first.inner_text() in ('Blocked', '막힘')
    page.clock.run_for(799)
    assert page.locator('.decision-title.chg').count() == 1
    page.clock.run_for(1)
    assert page.locator('.decision-title.chg').count() == 0
    assert page.locator('.chg').count() == 0

    # Repeated notices about one work item merge into one line.
    changed['notices'][0]['work_id'] = 'same-work'
    changed['notices'][1]['work_id'] = 'same-work'
    path.write_text(json.dumps(changed), encoding="utf-8")
    page.evaluate("tick()")
    assert page.locator('.notice-row').count() == 2

    # Escape content before rendering, including the detail view.
    changed['decisions'][0]['what'] = '<img src=x onerror=alert(1)>'
    path.write_text(json.dumps(changed), encoding="utf-8")
    page.evaluate("tick()")
    assert page.locator('.decision-title img').count() == 0
    page.locator('[data-detail=decision]').click()
    assert page.locator('#detail-content img').count() == 0
    page.keyboard.press('Escape')

    # Long content and supplemental schedule rows cannot overlap other sections.
    changed['decisions'][0]['what'] = 'A long title ' * 40
    changed['money'] = '2030-06-18 / Demo sales $1,234 / 7 orders'
    for item in changed['schedule']:
        item['extra'] = 'Supplemental context'
    for item in changed['hands']:
        item['title'] = 'Long task name ' * 20
    path.write_text(json.dumps(changed), encoding="utf-8")
    page.evaluate("tick()")
    assert_layout(page)
    assert page.locator('.schedule-row').count() == 3

    # Failure after success retains the last snapshot with an explicit warning.
    path.write_text('{broken', encoding="utf-8")
    page.evaluate("tick()")
    assert page.locator('.freshness.bad').count() == 1
    assert page.locator('.decision-title').count() == 1
    # A cold load with no file must never claim the sections are empty.
    path.unlink()
    page.reload(wait_until='networkidle')
    assert page.locator('.freshness.bad').count() == 1
    assert page.locator('.panel').count() == 0
    path.write_text(json.dumps(demo), encoding="utf-8")
    page.evaluate("tick()")
    assert page.locator('.freshness.bad').count() == 0

    # Empty states are only shown for successfully loaded, empty arrays.
    empty = {**demo, **{k:[] for k in ('decisions','hands','notices','schedule','requests','teams')}, 'money':None}
    path.write_text(json.dumps(empty), encoding="utf-8")
    page.evaluate("tick()")
    assert page.locator('.empty').count() == 6
    assert page.locator('.money-value').inner_text() in ('Not yet tallied', '집계 전')
    assert_layout(page)


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit('Install the optional tool: python3 -m pip install playwright\n'
                         'Then: python3 -m playwright install chromium')
    (ROOT / 'docs').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as folder, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for lang, filename in (('en','demo.json'), ('ko','demo.ko.json')):
                demo = json.loads((ROOT / 'demo' / filename).read_text(encoding='utf-8'))
                path = Path(folder) / filename
                path.write_text(json.dumps(demo), encoding='utf-8')
                with running_server(path) as base:
                    context = browser.new_context(viewport={'width':2048,'height':1536},
                                                  timezone_id='UTC', locale='en-GB')
                    page = context.new_page()
                    errors, addresses = [], []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.on('console', lambda message: errors.append(message.text) if message.type=='error' else None)
                    page.on('request', lambda request: addresses.append(request.url))
                    page.clock.install(time=datetime.fromtimestamp(demo['now'], timezone.utc))
                    page.goto(f'{base}/pad?lang={lang}', wait_until='networkidle')
                    page.locator('.team-row').first.wait_for()
                    page.evaluate('document.fonts.ready')
                    assert_layout(page)
                    target = ROOT / 'docs' / f'screenshot-{lang}.png'
                    page.screenshot(path=str(target))
                    print(f'Created docs/{target.name} (2048x1536)')
                    page.set_viewport_size({'width':1170,'height':878})
                    page.wait_for_timeout(150)
                    assert_layout(page)
                    page.set_viewport_size({'width':1536,'height':2048})
                    page.wait_for_timeout(150)
                    assert_layout(page)
                    if lang == 'en':
                        target = ROOT / 'docs' / 'screenshot-portrait.png'
                        page.screenshot(path=str(target))
                        print('Created docs/screenshot-portrait.png (1536x2048)')
                    page.set_viewport_size({'width':768,'height':1024})
                    page.wait_for_timeout(150)
                    assert_layout(page)
                    page.set_viewport_size({'width':2048,'height':1536})
                    page.wait_for_timeout(150)
                    browser_checks(page,path,demo)
                    assert not errors, errors
                    assert all(url.startswith(base+'/') for url in addresses), addresses
                    context.close()
                    print(f'Browser checks passed ({lang}): layouts, refresh, changes, failure, recovery, empty states, local requests only')
        finally:
            browser.close()


if __name__ == '__main__':
    main()
