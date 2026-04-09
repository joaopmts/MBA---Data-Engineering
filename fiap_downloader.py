"""
FIAP Trabalhos Downloader
=========================
Baixa todos os arquivos de trabalhos organizados por matéria.

Estrutura de pastas:
  fiap_trabalhos/
    01 - cloud strategy/
      01 - Cloud daqui a 10 anos (nota 10)/
        anexos_professor/
          enunciado.pdf
        entregue/
          meu_arquivo.rar

Como usar:
1. pip install requests beautifulsoup4
2. Coloque cookies.txt na mesma pasta
3. python fiap_downloader.py
"""

import re
import time
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from urllib.parse import urljoin

# =============================================================================
# CONFIGURAÇÃO
# =============================================================================

COOKIES_FILE = "cookies.txt"
OUTPUT_DIR   = "fiap_trabalhos"
DELAY        = 1.5

BASE_URL     = "https://on1.fiap.com.br/programas/"
LIST_URL     = BASE_URL + "login/alunos_2004/entregaTrabalho/lista.asp?titulo_secao=Entrega+de+Trablaho"
WORK_URL     = BASE_URL + "login/alunos_2004/entregaTrabalho/verTrabalho.asp?titulo_secao=Entrega+de+Trablaho"
UPLOAD_BASE  = "https://on1.fiap.com.br"
DOWNLOAD_URL = "https://on1.fiap.com.br/Controle404/download.php"

TRABALHO_IDS = [
    # --- CORRIGIDOS ---
    59796, 59873, 60126, 59903, 60087, 60250, 60354, 60535, 60414,
    60376, 60377, 60378, 60406, 60501, 60524, 60764, 61004, 60840,
    60984, 60914, 61141, 61162, 61208, 61032, 61285, 61268, 61428,
    61687, 61805, 61806, 61807, 61808, 61809, 61810, 61811, 61812,
    61813, 61814, 61815, 61816, 61817, 61818, 61819, 61820, 61639,
    61995,
    # --- ENTREGUES (aguardando correção) ---
    61821, 61881, 61882, 61883, 61884, 61885, 61886, 61887, 61888,
    61889, 61890, 61891, 61892, 61893, 61894, 61895, 61920, 61921,
    61922, 61923, 61924, 61925, 61985, 62113, 62051, 62016, 62074,
    62137, 62109,
]

# =============================================================================
# FUNÇÕES
# =============================================================================

def sanitize(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    name = re.sub(r'\s+', ' ', name)
    return name.strip()[:80]


def load_session() -> requests.Session:
    session = requests.Session()
    count = 0
    with open(COOKIES_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 7:
                continue
            domain, _, path, secure, expires, name, value = parts[:7]
            session.cookies.set(name.strip(), value.strip(), domain=domain.strip(), path=path.strip())
            count += 1
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": LIST_URL,
    })
    print(f"  {count} cookies carregados.")
    return session


def resolve_download_url(session: requests.Session, url: str) -> str:
    """
    O portal retorna um HTML intermediário com um form GET para
    /Controle404/download.php?file=... — extrai e monta a URL real.
    """
    resp = session.get(url, timeout=30)
    if "download.php" not in resp.text:
        # já é direto
        return url
    soup = BeautifulSoup(resp.text, "html.parser")
    form = soup.find("form", {"name": "frmDownload"})
    if not form:
        return url
    action = form.get("action", "")
    file_input = form.find("input", {"name": "file"})
    if not file_input:
        return url
    file_val = file_input.get("value", "")
    real_url = f"https://on1.fiap.com.br{action}?file={file_val}"
    return real_url


def parse_work_page(html: str, trabalho_id: int) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    info = {"id": trabalho_id, "disciplina": "", "titulo": "", "nota": "", "anexos": [], "entregue": None}

    textarea = soup.find("textarea", class_="i-title-info-trabalho-on")
    if textarea:
        partes = textarea.get_text().split("/")
        if len(partes) >= 2:
            info["disciplina"] = partes[1].strip().lower()

    for inp in soup.find_all("input", {"type": "text", "readonly": True}):
        parent = inp.find_parent("div", class_="i-form-column") or inp.find_parent("div", class_="i-form-group")
        if not parent:
            continue
        label = parent.find("label")
        if not label:
            continue
        ltext = label.get_text(strip=True)
        val   = inp.get("value", "").strip()
        if "Título" in ltext and val:
            info["titulo"] = val
        elif "Nota" in ltext and val:
            info["nota"] = val

    for section in soup.find_all("div", class_="i-form-section"):
        title_div = section.find("div", class_="i-form-section-title")
        if not title_div:
            continue
        if "Arquivos Anexados" in title_div.get_text():
            for a in section.find_all("a", class_="i-content-list-link"):
                href = a.get("href", "").strip()
                if href:
                    info["anexos"].append({"nome": a.get_text(strip=True), "url": urljoin(UPLOAD_BASE, href)})

    for section in soup.find_all("div", class_="i-form-section"):
        title_div = section.find("div", class_="i-form-section-title")
        if not title_div:
            continue
        if "Outras Informações" in title_div.get_text():
            for a in section.find_all("a", class_="i-content-link"):
                href = a.get("href", "").strip()
                if href and "/updown/" in href:
                    nome = a.get_text(strip=True)
                    if "..." in nome:
                        nome = href.split("/")[-1]
                    info["entregue"] = {"nome": nome, "url": urljoin(UPLOAD_BASE, href)}
                    break

    return info


def download_file(session: requests.Session, url: str, dest: Path) -> bool:
    """Resolve URL intermediária e baixa o arquivo real."""
    if dest.exists():
        print(f"    [SKIP] {dest.name}")
        return True
    try:
        # Resolve o redirect intermediário do portal
        real_url = resolve_download_url(session, url)
        print(f"    URL real: {real_url}")

        resp = session.get(real_url, stream=True, timeout=60)
        resp.raise_for_status()

        # Verifica se veio HTML em vez de arquivo
        ct = resp.headers.get("Content-Type", "")
        if "text/html" in ct:
            print(f"    [ERRO] Retornou HTML em vez de arquivo (sessão expirada?)")
            return False

        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        size_kb = dest.stat().st_size // 1024
        print(f"    [OK] {dest.name} ({size_kb} KB)")
        return True
    except Exception as e:
        print(f"    [ERRO] {url} -> {e}")
        return False


def process_trabalho(session, trabalho_id, base_dir, disc_counter, atv_counter):
    resp = session.post(WORK_URL, data={"codigoTrabalho": trabalho_id}, timeout=30)
    if resp.status_code != 200:
        print(f"  [ERRO HTTP] status {resp.status_code}")
        return ""

    if len(resp.text) < 500 or "top.location.href" in resp.text:
        print("  [SESSÃO EXPIRADA] Atualize o cookies.txt e rode novamente.")
        return ""

    info = parse_work_page(resp.text, trabalho_id)

    disc   = info["disciplina"] or f"desconhecida_{trabalho_id}"
    titulo = info["titulo"]     or f"trabalho_{trabalho_id}"
    nota   = f"nota {info['nota']}" if info["nota"] else "aguardando nota"

    if disc not in disc_counter:
        disc_counter[disc] = len(disc_counter) + 1
    disc_num = disc_counter[disc]

    if disc not in atv_counter:
        atv_counter[disc] = 0
    atv_counter[disc] += 1
    atv_num = atv_counter[disc]

    disc_folder = base_dir / f"{disc_num:02d} - {sanitize(disc)}"
    atv_folder  = disc_folder / f"{atv_num:02d} - {sanitize(titulo)} ({nota})"
    atv_folder.mkdir(parents=True, exist_ok=True)

    print(f"  Matéria : {disc}")
    print(f"  Título  : {titulo}")
    print(f"  Nota    : {nota}")
    print(f"  Pasta   : {atv_folder}")

    if info["anexos"]:
        print(f"  Anexos professor ({len(info['anexos'])}):")
        for arq in info["anexos"]:
            dest = atv_folder / "anexos_professor" / sanitize(arq["nome"])
            download_file(session, arq["url"], dest)
            time.sleep(DELAY)
    else:
        print("  Sem anexos do professor.")

    if info["entregue"]:
        print("  Arquivo entregue:")
        dest = atv_folder / "entregue" / sanitize(info["entregue"]["nome"])
        download_file(session, info["entregue"]["url"], dest)
        time.sleep(DELAY)
    else:
        print("  Sem arquivo entregue.")

    return disc


def main():
    print("FIAP Trabalhos Downloader")
    print("=" * 60)
    print(f"Total de trabalhos: {len(TRABALHO_IDS)}")

    if not Path(COOKIES_FILE).exists():
        print(f"[ERRO] {COOKIES_FILE} não encontrado.")
        return

    session      = load_session()
    base_dir     = Path(OUTPUT_DIR)
    base_dir.mkdir(exist_ok=True)
    disc_counter = {}
    atv_counter  = {}
    erros        = []

    for i, tid in enumerate(TRABALHO_IDS, 1):
        print(f"\n[{i}/{len(TRABALHO_IDS)}] ID {tid}")
        print("-" * 40)
        try:
            disc = process_trabalho(session, tid, base_dir, disc_counter, atv_counter)
            if not disc:
                erros.append(tid)
        except Exception as e:
            print(f"  [EXCEÇÃO] {e}")
            erros.append(tid)
        time.sleep(DELAY)

    print(f"\n{'='*60}")
    print(f"Concluído! Arquivos em: {base_dir.resolve()}")
    if erros:
        print(f"IDs com erro: {erros}")
    else:
        print("Todos os trabalhos processados sem erros!")


if __name__ == "__main__":
    main()
