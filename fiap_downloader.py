"""
FIAP Downloader
===============
Baixa automaticamente:
  1. Trabalhos  — anexos do professor + arquivos entregues
  2. Materiais  — apostilas de todas as disciplinas e subpastas

Estrutura de saída:
  fiap_downloads/
    trabalhos/
      01 - cloud strategy/
        01 - Trabalho tal (nota 10)/
          anexos_professor/
            enunciado.pdf
          entregue/
            meu_arquivo.rar
    materiais_aula/
      Advanced Data Modeling Eduardo Ferreira Galego/
        29ABD-AdvDataModeling-2025JUN-Modulo5.pdf
      Stream Processing Pipelines/
        Lab_ConfiguracaoAzure.pdf
        Aula1210/
          27ABD_-_01_- Aula 01.pdf

Como usar:
  1. pip install requests beautifulsoup4
  2. Exporte cookies do browser para cookies.txt (extensão "Get cookies.txt LOCALLY")
  3. python fiap_downloader.py
"""

import re
import time
import logging
from pathlib import Path
from urllib.parse import urljoin, unquote, quote

import requests
from bs4 import BeautifulSoup

# =============================================================================
# CONFIGURAÇÃO
# =============================================================================

COOKIES_FILE = "cookies.txt"
OUTPUT_DIR   = "fiap_downloads"
DELAY        = 1.0   # segundos entre requisições

BASE_ON1      = "https://on1.fiap.com.br"
BASE_PROG     = BASE_ON1 + "/programas"
BASE_APOSTILAS = BASE_PROG + "/login/alunos_2004/apostilas_2007"

# Trabalhos
LIST_URL     = BASE_PROG + "/login/alunos_2004/entregaTrabalho/lista.asp?titulo_secao=Entrega+de+Trablaho"
WORK_URL     = BASE_PROG + "/login/alunos_2004/entregaTrabalho/verTrabalho.asp?titulo_secao=Entrega+de+Trablaho"
TRAB_DL_URL  = BASE_ON1  + "/Controle404/download.php"

# Apostilas
ESTRUTURA_URL  = BASE_APOSTILAS + "/_estrutura.asp"
ARQUIVOS_URL   = BASE_APOSTILAS + "/_arquivos.asp"
PASTA_URL      = BASE_APOSTILAS + "/_arquivosPasta.asp"
DOWNLOAD_URL   = BASE_APOSTILAS + "/download.asp"

# =============================================================================
# LOGGING
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("fiap_downloader.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# =============================================================================
# UTILITÁRIOS GERAIS
# =============================================================================

def sanitize(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    name = re.sub(r"\s+", " ", name)
    return name.strip()[:100]


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
            session.cookies.set(name.strip(), value.strip(),
                                domain=domain.strip(), path=path.strip())
            count += 1
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": BASE_PROG + "/",
        "Origin":  BASE_ON1,
    })
    log.info(f"✓ {count} cookies carregados de '{COOKIES_FILE}'")
    return session


def check_session(html: str) -> bool:
    return not ("top.location.href" in html and len(html) < 500)


def ajax_post(session: requests.Session, url: str, payload: dict) -> str:
    resp = session.post(url, data=payload, timeout=30)
    resp.raise_for_status()
    body = resp.text
    if "|" in body[:100]:
        body = body[body.index("|") + 1:]
    return body


def safe_download(session: requests.Session, url: str, filepath: Path,
                  method: str = "GET", data: dict = None) -> bool:
    """Baixa arquivo para filepath. Pula se já existe."""
    if filepath.exists():
        log.info(f"    [SKIP] {filepath.name}")
        return True
    try:
        if method == "GET":
            resp = session.get(url, stream=True, timeout=60, allow_redirects=True)
        else:
            resp = session.post(url, data=data, stream=True, timeout=60, allow_redirects=True)

        resp.raise_for_status()

        ct = resp.headers.get("Content-Type", "")
        if "text/html" in ct:
            log.warning(f"    [ERRO] Retornou HTML — sessão expirada ou link inválido: {url}")
            return False

        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        kb = filepath.stat().st_size / 1024
        log.info(f"    ✓ {filepath.name}  ({kb:.0f} KB)")
        return True

    except Exception as e:
        log.error(f"    ✗ {filepath.name}: {e}")
        return False


# =============================================================================
# MÓDULO 1 — TRABALHOS  (lógica original preservada)
# =============================================================================

def discover_trabalho_ids(session: requests.Session) -> list:
    log.info("\nBuscando IDs de trabalhos...")
    ABAS = {0: "Entregues", 1: "Corrigidos", 2: "Pendentes", 3: "Não entregue"}
    base_list = BASE_PROG + "/login/alunos_2004/entregaTrabalho/lista.asp"
    ids = set()

    for arquivado, nome in ABAS.items():
        url  = f"{base_list}?arquivado={arquivado}&titulo_secao=Entrega+de+Trablaho"
        resp = session.get(url, timeout=30)
        if not check_session(resp.text):
            log.warning("  [SESSÃO EXPIRADA] Atualize o cookies.txt.")
            return []
        found = re.findall(r"fAcessaListaTrabalhos\((\d+)\)", resp.text)
        found = [int(x) for x in found]
        ids.update(found)
        log.info(f"  Aba '{nome}': {len(found)} trabalhos")
        time.sleep(DELAY)

    ids = sorted(ids)
    log.info(f"  Total: {len(ids)} trabalhos únicos")
    return ids


def resolve_download_url_trabalho(session: requests.Session, url: str) -> str:
    resp = session.get(url, timeout=30)
    if "download.php" not in resp.text:
        return url
    soup = BeautifulSoup(resp.text, "html.parser")
    form = soup.find("form", {"name": "frmDownload"})
    if not form:
        return url
    file_input = form.find("input", {"name": "file"})
    if not file_input:
        return url
    return BASE_ON1 + form.get("action", "") + "?file=" + file_input.get("value", "")


def parse_work_page(html: str, trabalho_id: int) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    info = {
        "id": trabalho_id, "disciplina": "", "titulo": "",
        "nota": "", "anexos": [], "entregue": None,
    }

    textarea = soup.find("textarea", class_="i-title-info-trabalho-on")
    if textarea:
        partes = textarea.get_text().split("/")
        if len(partes) >= 2:
            info["disciplina"] = partes[1].strip().lower()

    for inp in soup.find_all("input", {"type": "text", "readonly": True}):
        parent = (inp.find_parent("div", class_="i-form-column") or
                  inp.find_parent("div", class_="i-form-group"))
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
                    info["anexos"].append({
                        "nome": a.get_text(strip=True),
                        "url":  urljoin(BASE_ON1, href),
                    })

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
                    info["entregue"] = {
                        "nome": nome,
                        "url":  urljoin(BASE_ON1, href),
                    }
                    break

    return info


def process_trabalho(session, trabalho_id, base_dir, disc_counter, atv_counter):
    resp = session.post(WORK_URL, data={"codigoTrabalho": trabalho_id}, timeout=30)
    if resp.status_code != 200:
        log.error(f"  [ERRO HTTP] status {resp.status_code}")
        return ""
    if not check_session(resp.text):
        log.warning("  [SESSÃO EXPIRADA] Atualize o cookies.txt.")
        return ""

    info   = parse_work_page(resp.text, trabalho_id)
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

    log.info(f"  Matéria : {disc}")
    log.info(f"  Título  : {titulo}")
    log.info(f"  Nota    : {nota}")

    if info["anexos"]:
        log.info(f"  Anexos professor ({len(info['anexos'])}):")
        for arq in info["anexos"]:
            dest     = atv_folder / "anexos_professor" / sanitize(arq["nome"])
            real_url = resolve_download_url_trabalho(session, arq["url"])
            safe_download(session, real_url, dest)
            time.sleep(DELAY)
    else:
        log.info("  Sem anexos do professor.")

    if info["entregue"]:
        log.info("  Arquivo entregue:")
        dest     = atv_folder / "entregue" / sanitize(info["entregue"]["nome"])
        real_url = resolve_download_url_trabalho(session, info["entregue"]["url"])
        safe_download(session, real_url, dest)
        time.sleep(DELAY)
    else:
        log.info("  Sem arquivo entregue.")

    return disc


def run_trabalhos(session: requests.Session, base_dir: Path):
    log.info("\n" + "=" * 60)
    log.info("MÓDULO 1 — TRABALHOS")
    log.info("=" * 60)

    trabalhos_dir = base_dir / "trabalhos"
    trabalhos_dir.mkdir(exist_ok=True)

    ids = discover_trabalho_ids(session)
    if not ids:
        log.info("Nenhum trabalho encontrado.")
        return

    disc_counter = {}
    atv_counter  = {}
    erros        = []

    for i, tid in enumerate(ids, 1):
        log.info(f"\n[{i}/{len(ids)}] ID {tid}")
        log.info("-" * 40)
        try:
            disc = process_trabalho(session, tid, trabalhos_dir, disc_counter, atv_counter)
            if not disc:
                erros.append(tid)
        except Exception as e:
            log.error(f"  [EXCEÇÃO] {e}")
            erros.append(tid)
        time.sleep(DELAY)

    log.info(f"\nTrabalhos concluídos. Pasta: {trabalhos_dir.resolve()}")
    if erros:
        log.warning(f"IDs com erro: {erros}")


# =============================================================================
# MÓDULO 2 — MATERIAIS DE AULA  (lógica nova, completa)
# =============================================================================

def parse_raiz(html: str) -> list[dict]:
    """
    Extrai disciplinas da resposta de _estrutura.asp.
    Retorna apenas entradas com ajax preenchido (disciplinas folha).
    """
    soup = BeautifulSoup(html, "html.parser")
    disciplinas = []
    seen = set()

    for tag in soup.find_all(onclick=True):
        onclick = tag.get("onclick", "")
        if "fPasta" not in onclick:
            continue
        m = re.search(
            r"fPasta\([^,]+,[^,]+,\s*'([^']*)',\s*'([^']*)',\s*'([^']*)'\s*\)",
            onclick,
        )
        if not m:
            continue
        div_id = m.group(1)
        ajax   = m.group(2)
        if not ajax or div_id in seen:
            continue
        seen.add(div_id)

        label = tag.get_text(separator=" ", strip=True)[:100]
        disciplinas.append({"div": div_id, "ajax": ajax, "label": label})

    return disciplinas


def get_label_disc(html_raiz: str, div_id: str) -> str:
    """Extrai label limpo da disciplina a partir do HTML raiz."""
    soup = BeautifulSoup(html_raiz, "html.parser")
    base_id = div_id.replace("all", "")
    tag = soup.find(id=base_id)
    if tag:
        # Pega só o texto do span de highlight (nome da disciplina)
        highlight = tag.find("span", class_="i-apostilas-label-highlight")
        if highlight:
            return highlight.get_text(strip=True)
        return tag.get_text(separator=" ", strip=True)[:80]
    return div_id


def parse_arquivos_bloco(html: str) -> list[dict]:
    """
    Extrai todos os arquivos de um bloco HTML.
    Cobre três padrões de link:
      1. <a href="login/.../download.php?file=...">  — GET direto
      2. <a href="/updown/...">                      — GET direto
      3. onclick="fDownload('id','codigo')"          — POST para download.asp
    """
    soup = BeautifulSoup(html, "html.parser")
    arquivos = []
    seen = set()

    for div in soup.find_all("div", class_="i-apostilas-subitem"):
        title_tag = div.find("span", class_="i-apostilas-link-title")
        sub_tag   = div.find("span", class_="i-apostilas-link-subtitle")
        if not title_tag:
            continue
        nome      = title_tag.get_text(strip=True)
        subtitulo = sub_tag.get_text(strip=True) if sub_tag else ""

        # Padrão 1: download.php?file=
        a1 = title_tag.find("a", href=re.compile(r"download\.php\?file="))
        if a1:
            href = a1["href"]
            url  = (BASE_PROG + "/" + href.lstrip("./")
                    if not href.startswith("http") else href)
            key  = url
            if key not in seen:
                seen.add(key)
                arquivos.append({
                    "nome":      nome,
                    "subtitulo": subtitulo,
                    "metodo":    "GET",
                    "url":       url,
                })
            continue

        # Padrão 2: /updown/
        a2 = title_tag.find("a", href=re.compile(r"/updown/"))
        if a2:
            url = BASE_ON1 + a2["href"]
            key = url
            if key not in seen:
                seen.add(key)
                arquivos.append({
                    "nome":      nome,
                    "subtitulo": subtitulo,
                    "metodo":    "GET",
                    "url":       url,
                })
            continue

        # Padrão 3: fDownload('id','codigo') no onclick do span
        span = div.find("span", onclick=re.compile(r"fDownload\("))
        if span:
            m = re.search(
                r"fDownload\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)",
                span.get("onclick", ""),
            )
            if m:
                key = m.group(1)
                if key not in seen:
                    seen.add(key)
                    arquivos.append({
                        "nome":      nome,
                        "subtitulo": subtitulo,
                        "metodo":    "POST_fDownload",
                        "id":        m.group(1),
                        "codigo":    m.group(2),
                    })

    return arquivos


def parse_subpastas_bloco(html: str) -> list[dict]:
    """
    Extrai subpastas de um bloco HTML.
    Cobre dois casos:
      - ajax preenchido  → chama _arquivos.asp
      - ajax vazio       → extrai intCodPasta do div_id e chama _arquivosPasta.asp
    """
    soup = BeautifulSoup(html, "html.parser")
    subpastas = []
    seen = set()

    for tag in soup.find_all(onclick=True):
        onclick = tag.get("onclick", "")
        if "fPasta" not in onclick:
            continue
        m = re.search(
            r"fPasta\([^,]+,[^,]+,\s*'([^']*)',\s*'([^']*)',\s*'([^']*)'\s*\)",
            onclick,
        )
        if not m:
            continue
        div_id     = m.group(1)
        ajax       = m.group(2)
        ajax_pasta = m.group(3)

        if div_id in seen:
            continue
        seen.add(div_id)

        # Extrai intCodPasta do div_id quando não há ajax
        cod_pasta = None
        if not ajax and not ajax_pasta:
            mp = re.search(r"_pasta(\d+)all$", div_id)
            if mp:
                cod_pasta = mp.group(1)

        label = tag.get_text(separator=" ", strip=True)[:80]
        subpastas.append({
            "div":        div_id,
            "ajax":       ajax,
            "ajax_pasta": ajax_pasta,
            "cod_pasta":  cod_pasta,
            "label":      label,
        })

    return subpastas


def expandir_e_baixar(
    session:     requests.Session,
    html:        str,
    disc_params: dict,
    dest_dir:    Path,
    erros:       list,
    depth:       int = 0,
    max_depth:   int = 8,
):
    """
    Recursivamente expande subpastas e baixa todos os arquivos encontrados.
    """
    if depth > max_depth:
        return

    indent = "  " * depth

    # ── Baixa arquivos diretos deste nível ──
    arquivos = parse_arquivos_bloco(html)
    for arq in arquivos:
        nome_arquivo = sanitize(arq["nome"])
        if "." not in nome_arquivo:
            nome_arquivo += ".bin"
        filepath = dest_dir / nome_arquivo

        # Evita sobrescrever com sufixo numérico
        counter = 1
        stem = filepath.stem
        while filepath.exists():
            filepath = dest_dir / f"{stem}_{counter}{filepath.suffix}"
            counter += 1

        dest_dir.mkdir(parents=True, exist_ok=True)
        time.sleep(DELAY)

        if arq["metodo"] == "GET":
            ok = safe_download(session, arq["url"], filepath)
        else:  # POST_fDownload
            ok = safe_download(
                session, DOWNLOAD_URL, filepath,
                method="POST",
                data={"a": arq["id"], "c": arq["codigo"]},
            )

        if not ok:
            erros.append(str(filepath))

    # ── Expande subpastas ──
    for sub in parse_subpastas_bloco(html):
        sub_dir = dest_dir / sanitize(sub["label"])
        log.info(f"{indent}  📁 {sub['label']}")
        time.sleep(DELAY)

        if sub["ajax"]:
            params = dict(x.split("=", 1) for x in sub["ajax"].split("&") if "=" in x)
            params["local"] = sub["div"]
            html_sub = ajax_post(session, ARQUIVOS_URL, params)

        elif sub["ajax_pasta"]:
            params = dict(x.split("=", 1) for x in sub["ajax_pasta"].split("&") if "=" in x)
            params["local"] = sub["div"]
            html_sub = ajax_post(session, PASTA_URL, params)

        elif sub["cod_pasta"]:
            # Monta params a partir dos da disciplina + intCodPasta
            params = dict(disc_params)
            params["intCodPasta"] = sub["cod_pasta"]
            params["local"]       = sub["div"]
            html_sub = ajax_post(session, PASTA_URL, params)

        else:
            continue

        expandir_e_baixar(session, html_sub, disc_params, sub_dir, erros, depth + 1)


def run_apostilas(session: requests.Session, base_dir: Path):
    log.info("\n" + "=" * 60)
    log.info("MÓDULO 2 — MATERIAIS DE AULA")
    log.info("=" * 60)

    apostilas_dir = base_dir / "materiais_aula"
    apostilas_dir.mkdir(exist_ok=True)

    # Busca estrutura raiz
    log.info("\nBuscando disciplinas...")
    html_raiz = ajax_post(session, ESTRUTURA_URL, {"ano": ""})

    if not check_session(html_raiz):
        log.warning("  [SESSÃO EXPIRADA] Atualize o cookies.txt.")
        return

    disciplinas = parse_raiz(html_raiz)
    if not disciplinas:
        log.warning("  Nenhuma disciplina encontrada.")
        return

    log.info(f"  {len(disciplinas)} disciplinas encontradas.")
    erros = []

    for i, disc in enumerate(disciplinas, 1):
        label = get_label_disc(html_raiz, disc["div"])
        log.info(f"\n[{i}/{len(disciplinas)}] {label}")

        disc_params = dict(x.split("=", 1) for x in disc["ajax"].split("&") if "=" in x)
        disc_params_req = dict(disc_params)
        disc_params_req["local"] = disc["div"]

        time.sleep(DELAY)
        html_disc = ajax_post(session, ARQUIVOS_URL, disc_params_req)

        disc_dir = apostilas_dir / sanitize(label)
        disc_dir.mkdir(parents=True, exist_ok=True)

        expandir_e_baixar(session, html_disc, disc_params, disc_dir, erros, depth=0)

    log.info(f"\nMateriais concluídos. Pasta: {apostilas_dir.resolve()}")
    if erros:
        log.warning(f"Arquivos com erro ({len(erros)}):")
        for e in erros:
            log.warning(f"  {e}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    log.info("FIAP Downloader")
    log.info("=" * 60)

    if not Path(COOKIES_FILE).exists():
        log.error(f"[ERRO] {COOKIES_FILE} não encontrado.")
        return

    session  = load_session()
    base_dir = Path(OUTPUT_DIR)
    base_dir.mkdir(exist_ok=True)

    run_apostilas(session, base_dir)
    run_trabalhos(session, base_dir)

    log.info("\n" + "=" * 60)
    log.info(f"Tudo concluído! Arquivos em: {base_dir.resolve()}")


if __name__ == "__main__":
    main()
