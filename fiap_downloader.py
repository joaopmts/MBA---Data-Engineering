"""
FIAP Downloader
===============
Baixa automaticamente:
  1. Trabalhos (com auto-descoberta de IDs via lista)
  2. Materiais de aula (apostilas por disciplina)

Estrutura de pastas gerada:
  fiap_downloads/
    trabalhos/
      01 - cloud strategy/
        01 - Trabalho tal (nota 10)/
          anexos_professor/
            enunciado.pdf
          entregue/
            meu_arquivo.rar
    materiais_aula/
      01 - Cloud Strategy/
        aula01_slides.pdf
        apostila.pdf

Como usar:
  1. pip install requests beautifulsoup4
  2. Exporte seus cookies do browser para cookies.txt (formato Netscape/Tab-separated)
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
OUTPUT_DIR   = "fiap_downloads"
DELAY        = 1.5          # segundos entre requisições

# --- URLs base ---
BASE_ON1        = "https://on1.fiap.com.br"
BASE_PROG       = BASE_ON1 + "/programas"
BASE_APOSTILAS  = BASE_PROG + "/login/alunos_2004/apostilas_2007"

# Trabalhos
LIST_URL     = BASE_PROG + "/login/alunos_2004/entregaTrabalho/lista.asp?titulo_secao=Entrega+de+Trablaho"
WORK_URL     = BASE_PROG + "/login/alunos_2004/entregaTrabalho/verTrabalho.asp?titulo_secao=Entrega+de+Trablaho"
DOWNLOAD_URL = BASE_ON1  + "/Controle404/download.php"

# Apostilas
ESTRUTURA_URL         = BASE_APOSTILAS + "/_estrutura.asp"
ARQUIVOS_URL          = BASE_APOSTILAS + "/_arquivos.asp"
ARQUIVOS_PASTA_URL    = BASE_APOSTILAS + "/_arquivosPasta.asp"
DOWNLOAD_ASP_URL      = BASE_APOSTILAS + "/download.asp"
DOWNLOAD_OUTRO_URL    = BASE_APOSTILAS + "/DownloadOutraExtensao.asp"

# =============================================================================
# UTILITÁRIOS
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
            session.cookies.set(name.strip(), value.strip(),
                                domain=domain.strip(), path=path.strip())
            count += 1
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": LIST_URL,
        "Origin": BASE_ON1,
    })
    print(f"  {count} cookies carregados.")
    return session


def check_session(html: str) -> bool:
    """Retorna False se a sessão expirou."""
    return not ("top.location.href" in html and len(html) < 500)


def download_file(session: requests.Session, url: str, dest: Path,
                  method: str = "GET", data: dict = None) -> bool:
    """Baixa um arquivo para dest. Resolve redirect intermediário se necessário."""
    if dest.exists():
        print(f"    [SKIP] {dest.name}")
        return True
    try:
        # Alguns links passam por página intermediária com form GET
        if method == "GET":
            probe = session.get(url, timeout=30)
            if "download.php" in probe.text and "frmDownload" in probe.text:
                soup = BeautifulSoup(probe.text, "html.parser")
                form = soup.find("form", {"name": "frmDownload"})
                if form:
                    file_input = form.find("input", {"name": "file"})
                    if file_input:
                        url = BASE_ON1 + form.get("action", "") + "?file=" + file_input.get("value", "")
            resp = session.get(url, stream=True, timeout=60)
        else:
            resp = session.post(url, data=data, stream=True, timeout=60,
                                allow_redirects=True)

        resp.raise_for_status()
        ct = resp.headers.get("Content-Type", "")
        if "text/html" in ct:
            print(f"    [ERRO] Retornou HTML (sessão expirada ou link inválido)")
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


# =============================================================================
# MÓDULO 1 — TRABALHOS
# =============================================================================

def discover_trabalho_ids(session: requests.Session) -> list[int]:
    """
    Busca IDs de trabalhos nas 4 abas da lista:
      arquivado=0 → Entregues
      arquivado=1 → Corrigidos
      arquivado=2 → Pendentes
      arquivado=3 → Não entregue
    """
    print("\nBuscando IDs de trabalhos...")

    ABAS = {0: "Entregues", 1: "Corrigidos", 2: "Pendentes", 3: "Não entregue"}
    base_list = BASE_PROG + "/login/alunos_2004/entregaTrabalho/lista.asp"
    ids = set()

    for arquivado, nome in ABAS.items():
        url  = f"{base_list}?arquivado={arquivado}&titulo_secao=Entrega+de+Trablaho"
        resp = session.get(url, timeout=30)
        if not check_session(resp.text):
            print("  [SESSÃO EXPIRADA] Atualize o cookies.txt.")
            return []

        # IDs estão em: href="javascript:fAcessaListaTrabalhos(XXXXX);"
        found = re.findall(r'fAcessaListaTrabalhos\((\d+)\)', resp.text)
        found = [int(x) for x in found]
        ids.update(found)
        print(f"  Aba '{nome}': {len(found)} trabalhos")
        time.sleep(DELAY)

    ids = sorted(ids)
    print(f"  Total: {len(ids)} trabalhos únicos")
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
        "nota": "", "anexos": [], "entregue": None
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
                        "url": urljoin(BASE_ON1, href)
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
                        "url": urljoin(BASE_ON1, href)
                    }
                    break

    return info


def process_trabalho(session, trabalho_id, base_dir, disc_counter, atv_counter):
    resp = session.post(WORK_URL, data={"codigoTrabalho": trabalho_id}, timeout=30)
    if resp.status_code != 200:
        print(f"  [ERRO HTTP] status {resp.status_code}")
        return ""
    if not check_session(resp.text):
        print("  [SESSÃO EXPIRADA] Atualize o cookies.txt e rode novamente.")
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

    print(f"  Matéria : {disc}")
    print(f"  Título  : {titulo}")
    print(f"  Nota    : {nota}")

    if info["anexos"]:
        print(f"  Anexos professor ({len(info['anexos'])}):")
        for arq in info["anexos"]:
            dest = atv_folder / "anexos_professor" / sanitize(arq["nome"])
            real_url = resolve_download_url_trabalho(session, arq["url"])
            download_file(session, real_url, dest)
            time.sleep(DELAY)
    else:
        print("  Sem anexos do professor.")

    if info["entregue"]:
        print("  Arquivo entregue:")
        dest = atv_folder / "entregue" / sanitize(info["entregue"]["nome"])
        real_url = resolve_download_url_trabalho(session, info["entregue"]["url"])
        download_file(session, real_url, dest)
        time.sleep(DELAY)
    else:
        print("  Sem arquivo entregue.")

    return disc


def run_trabalhos(session: requests.Session, base_dir: Path):
    print("\n" + "=" * 60)
    print("MÓDULO 1 — TRABALHOS")
    print("=" * 60)

    trabalhos_dir = base_dir / "trabalhos"
    trabalhos_dir.mkdir(exist_ok=True)

    ids = discover_trabalho_ids(session)
    if not ids:
        print("Nenhum trabalho encontrado.")
        return

    disc_counter = {}
    atv_counter  = {}
    erros        = []

    for i, tid in enumerate(ids, 1):
        print(f"\n[{i}/{len(ids)}] ID {tid}")
        print("-" * 40)
        try:
            disc = process_trabalho(session, tid, trabalhos_dir,
                                    disc_counter, atv_counter)
            if not disc:
                erros.append(tid)
        except Exception as e:
            print(f"  [EXCEÇÃO] {e}")
            erros.append(tid)
        time.sleep(DELAY)

    print(f"\nTrabalhos concluídos. Pasta: {trabalhos_dir.resolve()}")
    if erros:
        print(f"IDs com erro: {erros}")


# =============================================================================
# MÓDULO 2 — MATERIAIS DE AULA (APOSTILAS)
# =============================================================================

def parse_disciplinas(html: str) -> list[dict]:
    """
    Extrai disciplinas do HTML retornado por _estrutura.asp.
    Cada disciplina tem: nome, professor, ajax_params (string de POST para _arquivos.asp)
    """
    soup = BeautifulSoup(html, "html.parser")
    disciplinas = []

    for div in soup.find_all("div", class_="i-apostilas-item"):
        span = div.find("span", class_="i-apostilas-label")
        if not span:
            continue

        # Pega o título da disciplina
        title_span = span.find("span", class_="i-apostilas-label-title")
        if not title_span:
            continue
        nome = title_span.get_text(strip=True)

        # Pega o professor
        sub_span = span.find("span", class_="i-apostilas-label-subtitle")
        professor = sub_span.get_text(strip=True) if sub_span else ""

        # Extrai os parâmetros AJAX do onclick
        onclick = span.get("onclick", "")
        # Formato: fPasta(...,'intCurso=209&intCursoAno=2025&...','')
        m = re.search(r"'(intCurso=[^']+)'", onclick)
        if not m:
            continue
        ajax_params = m.group(1).replace("&amp;", "&")

        disciplinas.append({
            "nome": nome,
            "professor": professor,
            "ajax_params": ajax_params
        })

    return disciplinas


def parse_arquivos(html: str) -> list[dict]:
    """
    Extrai arquivos do HTML retornado por _arquivos.asp / _arquivosPasta.asp.
    Prioridade:
      1. /updown/ — funciona sempre com sessão (arquivos novos e subpastas)
      2. download.php?file= — link legado (disciplinas raiz)
    O Formato 2 (comentários HTML com download.php) foi removido pois gera 404 no S3.
    """
    from urllib.parse import unquote, quote
    soup = BeautifulSoup(html, "html.parser")
    arquivos = []
    vistos = set()

    # Prioridade 1: /updown/ — cobre subpastas e arquivos novos
    for url_m in re.finditer(r'href="/updown/([^"]+)"', html):
        file_path = unquote(url_m.group(1))
        nome = Path(file_path).name
        if nome in vistos:
            continue
        vistos.add(nome)
        url = BASE_ON1 + "/updown/" + quote(url_m.group(1), safe="/")
        arquivos.append({"nome": nome, "tipo": "direto", "params": {"url": url}})

    # Prioridade 2: download.php?file= — disciplinas raiz sem /updown/
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if "download.php" not in href or "file=" not in href:
            continue
        m = re.search(r'file=([^&]+)', href)
        if not m:
            continue
        nome = unquote(Path(m.group(1)).name)
        if nome in vistos:
            continue
        vistos.add(nome)
        url = href if href.startswith("http") else BASE_ON1 + "/programas/" + href.lstrip("./")
        arquivos.append({"nome": nome, "tipo": "direto", "params": {"url": url}})

    return arquivos


def download_apostila_arquivo(session: requests.Session, arq: dict, dest: Path) -> bool:
    """Baixa um arquivo de apostila via link direto (download.php ou /updown/)."""
    if dest.exists():
        print(f"    [SKIP] {dest.name}")
        return True

    try:
        url = arq["params"]["url"]

        resp = session.get(url, stream=True, timeout=60, allow_redirects=True)

        resp.raise_for_status()

        ct = resp.headers.get("Content-Type", "")
        if "text/html" in ct:
            print(f"    [ERRO] Retornou HTML em vez de arquivo")
            return False

        # Tenta pegar nome do Content-Disposition
        cd = resp.headers.get("Content-Disposition", "")
        m = re.search(r'filename[^;=\n]*=(["\']?)([^"\'\n]+)\1', cd)
        if m:
            nome_cd = sanitize(m.group(2).strip())
            if nome_cd:
                dest = dest.parent / nome_cd

        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        size_kb = dest.stat().st_size // 1024
        print(f"    [OK] {dest.name} ({size_kb} KB)")
        return True
    except Exception as e:
        print(f"    [ERRO] {arq['nome']} -> {e}")
        return False


def parse_subpastas(html: str) -> list[dict]:
    """
    Extrai subpastas do HTML retornado por _arquivos.asp ou _arquivosPasta.asp.
    Subpastas têm intCodPasta no onclick e são carregadas via _arquivosPasta.asp.
    """
    soup = BeautifulSoup(html, "html.parser")
    pastas = []

    for div in soup.find_all("div", class_="i-apostilas-item"):
        span = div.find("span", class_="i-apostilas-label", onclick=True)
        if not span:
            continue
        onclick = span.get("onclick", "")
        # Subpastas têm ajaxPasta (5º argumento do fPasta) com intCodPasta
        m = re.search(r"'(intCurso=[^']*intCodPasta=\d+[^']*)'", onclick)
        if not m:
            continue
        pasta_params = m.group(1).replace("&amp;", "&")
        title = span.find("span", class_="i-apostilas-label-title")
        nome = title.get_text(strip=True) if title else f"pasta_{len(pastas)+1}"
        pastas.append({"nome": nome, "pasta_params": pasta_params})

    return pastas


def download_disciplina(session: requests.Session, params_dict: dict,
                        dest_dir: Path, erros: list, depth: int = 0):
    """
    Recursivamente baixa arquivos e subpastas de uma disciplina/pasta.
    depth controla o nível de recursão (proteção contra loops infinitos).
    """
    if depth > 10:
        print("  [AVISO] Profundidade máxima atingida, abortando recursão.")
        return

    indent = "  " * (depth + 1)

    # Escolhe endpoint: _arquivos.asp para disciplina raiz, _arquivosPasta.asp para subpastas
    url = ARQUIVOS_PASTA_URL if "intCodPasta" in params_dict else ARQUIVOS_URL

    resp = session.post(url, data=params_dict, timeout=30)
    time.sleep(DELAY)

    arq_html = resp.text
    if "|" in arq_html[:100]:
        arq_html = arq_html[arq_html.index("|") + 1:]

    # Baixa arquivos diretos desta pasta
    arquivos = parse_arquivos(arq_html)
    if arquivos:
        print(f"{indent}{len(arquivos)} arquivo(s):")
        for arq in arquivos:
            dest = dest_dir / sanitize(arq["nome"])
            ok = download_apostila_arquivo(session, arq, dest)
            if not ok:
                erros.append(str(dest))
            time.sleep(DELAY)

    # Processa subpastas recursivamente
    subpastas = parse_subpastas(arq_html)
    for pasta in subpastas:
        pasta_params = dict(p.split("=", 1) for p in pasta["pasta_params"].split("&") if "=" in p)
        pasta_params["intAno"] = ""
        pasta_params["local"]  = "div_dummy"
        pasta_dir = dest_dir / sanitize(pasta["nome"])
        pasta_dir.mkdir(exist_ok=True)
        print(f"{indent}📁 {pasta['nome']}/")
        download_disciplina(session, pasta_params, pasta_dir, erros, depth + 1)


def run_apostilas(session: requests.Session, base_dir: Path):
    print("\n" + "=" * 60)
    print("MÓDULO 2 — MATERIAIS DE AULA")
    print("=" * 60)

    apostilas_dir = base_dir / "materiais_aula"
    apostilas_dir.mkdir(exist_ok=True)

    # Busca estrutura de disciplinas
    print("\nBuscando disciplinas...")
    resp = session.post(ESTRUTURA_URL, data={"ano": ""}, timeout=30)
    if not check_session(resp.text):
        print("  [SESSÃO EXPIRADA] Atualize o cookies.txt.")
        return

    html = resp.text
    if "|" in html[:50]:
        html = html[html.index("|") + 1:]

    disciplinas = parse_disciplinas(html)
    if not disciplinas:
        print("  Nenhuma disciplina encontrada.")
        return

    print(f"  {len(disciplinas)} disciplinas encontradas.")

    erros = []
    for i, disc in enumerate(disciplinas, 1):
        nome   = disc["nome"]
        prof   = disc["professor"]
        params = disc["ajax_params"]

        print(f"\n[{i}/{len(disciplinas)}] {nome}")
        if prof:
            print(f"  Professor: {prof}")

        disc_dir = apostilas_dir / f"{i:02d} - {sanitize(nome)}"
        disc_dir.mkdir(exist_ok=True)

        params_dict = dict(p.split("=", 1) for p in params.split("&") if "=" in p)
        params_dict["intAno"] = ""
        params_dict["local"]  = "div_dummy"

        download_disciplina(session, params_dict, disc_dir, erros, depth=0)

    print(f"\nMateriais concluídos. Pasta: {apostilas_dir.resolve()}")
    if erros:
        print(f"Erros:\n" + "\n".join(erros))


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("FIAP Downloader")
    print("=" * 60)

    if not Path(COOKIES_FILE).exists():
        print(f"[ERRO] {COOKIES_FILE} não encontrado.")
        return

    session  = load_session()
    base_dir = Path(OUTPUT_DIR)
    base_dir.mkdir(exist_ok=True)

    run_apostilas(session, base_dir)
    run_trabalhos(session, base_dir)

    print("\n" + "=" * 60)
    print(f"Tudo concluído! Arquivos em: {base_dir.resolve()}")


if __name__ == "__main__":
    main()
