
"""FII Full‑Audit – template
Baixa relatórios gerenciais (PDF) de cada FII, extrai métricas
básicas e envia resumo para Telegram ou grava em Markdown.
Compatível com GitHub Actions (Python 3.11).
"""
import os, re, sqlite3, requests, datetime, subprocess, json, tempfile
from pathlib import Path
import pdfplumber, pandas as pd

CONFIG_FILE = Path(__file__).with_name("config.yaml")

def load_cfg():
    import yaml
    with open(CONFIG_FILE, 'r', encoding='utf‑8') as f:
        return yaml.safe_load(f)

def slugify(s):
    return re.sub(r'[^A-Za-z0-9_\-]+', '_', s)

def download_rg(ticker, month):
    """Baixa RG PDF para um ticker/mês (ex.: 2025‑04)."""
    # exemplo para CSHG (VILG, BTLG...). Adapte p/ outros gestores
    url = f"https://www.cshg.com.br/wp-content/uploads/relatorios-gerenciais/{ticker.lower()}/{month}-relatorio-gerencial-{ticker.lower()}.pdf"
    dest = Path('pdf') / ticker / f"{month}.pdf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return dest
    r = requests.get(url, timeout=60)
    if r.status_code == 200 and r.headers['content-type'] == 'application/pdf':
        dest.write_bytes(r.content)
        print(f"[✓] {ticker} {month} baixado")
        return dest
    print(f"[!] Falhou {ticker} {month}: {r.status_code}")
    return None

def parse_pdf(path, ticker):
    """Extrai DY mês, PL e usa regex simples (ajuste conforme RG)."""
    data = {'ticker': ticker, 'pdf': path.name}
    try:
        with pdfplumber.open(path) as pdf:
            text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        dy = re.search(r"(?:Dividend Yield|DY).*?([\d,]+)%", text, re.I)
        pl = re.search(r"Patrim[oô]nio.*?R\$\s*([\d\.,]+)\s*milh?", text, re.I)
        data['dy_m'] = float(dy.group(1).replace(',', '.'))/100 if dy else None
        if pl:
            raw = pl.group(1).replace('.', '').replace(',', '.')
            data['pl'] = float(raw)*1e6 if 'milh' in pl.group(0).lower() else float(raw)
    except Exception as e:
        print("Erro parse", e)
    return data

def save_db(rows):
    con = sqlite3.connect('fii_audit.db')
    pd.DataFrame(rows).to_sql('metrics', con, if_exists='append', index=False)
    con.close()

def telegram_notify(msg, cfg):
    if not cfg.get('telegram_token'):
        return
    url = f"https://api.telegram.org/bot{cfg['telegram_token']}/sendMessage"
    requests.post(url, data={'chat_id': cfg['telegram_chat_id'], 'text': msg, 'parse_mode':'Markdown'})

def main():
    cfg = load_cfg()
    today = datetime.date.today()
    month = today.strftime('%Y-%m')
    rows = []
    for tk in cfg['tickers']:
        pdf = download_rg(tk, month)
        if pdf:
            rows.append(parse_pdf(pdf, tk))
    if rows:
        save_db(rows)
        summary = "\n".join(f"*{r['ticker']}* DY: {r.get('dy_m','?'):%}" for r in rows)
        telegram_notify(f"Auditoria FII – {month}\n"+summary, cfg)

if __name__ == '__main__':
    main()
