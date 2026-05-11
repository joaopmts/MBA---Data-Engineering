# FIAP Downloader

A Python automation tool to automatically download and organize **assignments** and **course materials** from the FIAP student portal (`on1.fiap.com.br`).

---

## Features

- Downloads all **submitted assignments** (including professor attachments and your submission)
- Downloads all **course materials** (PDFs, slides, notebooks, ZIPs, etc.)
- Organizes everything into auto-numbered folders by subject
- Resumes where it left off — already downloaded files are skipped (`[SKIP]`)
- Detects expired sessions and prompts you to renew cookies
- Sanitizes filenames for Windows compatibility

---

## Output Structure

```
fiap_downloads/
├── trabalhos/
│   ├── 01 - Cloud Strategy/
│   │   ├── 01 - Assignment Name (nota 10)/
│   │   │   ├── anexos_professor/
│   │   │   │   └── instructions.pdf
│   │   │   └── entregue/
│   │   │       └── my_submission.rar
│   │   └── 02 - Another Assignment (aguardando nota)/
│   └── 02 - Data Pipelines/
└── materiais_aula/
    ├── 01 - Advanced Data Modeling/
    │   └── slides.pdf
    ├── 02 - Cloud Strategy/
    └── ...
```

---

## Requirements

- Python 3.10+

```bash
pip install requests beautifulsoup4
```

---

## Usage

### 1. Export your browser cookies

The script needs session cookies from an authenticated portal session.

1. Log in at `https://on.fiap.com.br`
2. Navigate to:
   ```
   https://on1.fiap.com.br/programas/login/alunos_2004/entregaTrabalho/lista.asp?titulo_secao=Entrega+de+Trablaho
   ```
3. Open DevTools (`F12`) → **Console** tab
4. Paste the script below and press Enter:

```javascript
(async () => {
    let rows = [];
    rows.push('# Netscape HTTP Cookie File');
    rows.push('# https://curl.se/docs/http-cookies.html');
    rows.push('');
    for (let cookie of document.cookie.split(';')) {
        let [name, ...val] = cookie.trim().split('=');
        rows.push([
            'on1.fiap.com.br','TRUE','/','FALSE','2147483647',
            name.trim(), val.join('=').trim()
        ].join('\t'));
    }
    let blob = new Blob([rows.join('\n')], {type: 'text/plain'});
    let a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'cookies.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
})();
```

5. Save the generated `cookies.txt` in the same folder as `fiap_downloader.py`

> **Cookies expire.** If you see `[SESSÃO EXPIRADA]` during execution, log in again, re-export the cookies, and re-run the script. Already downloaded files will be skipped automatically.

---

### 2. Run the script

```bash
python fiap_downloader.py
```

Both modules run automatically — course materials first, then assignments.

---

## How it works

### Module 1 — Assignments (`trabalhos/`)

Iterates through all 4 tabs of the portal's assignment list:

| Tab | Status |
|-----|--------|
| Corrigidos | Graded by the professor |
| Entregues | Submitted, awaiting grade |
| Pendentes | Deadline still open |
| Não entregue | Deadline passed without submission |

For each assignment found, it downloads:
- **`anexos_professor/`** — files and instructions attached by the professor
- **`entregue/`** — your submission (when available)

### Module 2 — Course Materials (`materiais_aula/`)

- Fetches the full list of subjects via AJAX from the course materials portal
- Recursively navigates each subject's folder tree (max depth: 10 levels)
- Downloads all available files, preserving the original folder hierarchy

---

## Notes

- **1.5s delay** between requests to avoid overloading the portal
- Idempotent execution — can be run multiple times without duplicating files
- Compatible with Windows (invalid filename characters are removed)
