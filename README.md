# MBA Data Engineering — FIAP 29ABD

Repository containing assignments, labs, and projects developed throughout the MBA in Data Engineering at FIAP, class 29ABD (2025/2026).

## Disciplines

| # | Discipline | Topics |
|---|-----------|--------|
| 01 | Cloud Strategy | Cloud types, service models, FinOps, CAPEX/OPEX |
| 02 | Data Pipelines | Kafka, NiFi, Sqoop |
| 03 | Stream Processing Pipelines | Apache Spark, Spark Structured Streaming |
| 04 | Relational Database & Advanced SQL | Advanced SQL, query optimization |
| 05 | NoSQL Documental & Text Search | MongoDB Atlas, aggregation pipelines, vector/text indexes |
| 06 | Columnar & Time Series Databases | Apache Cassandra, CQL |
| 07 | Databases for GenAI | VectorDB, ChatBot simulation |
| 08 | Generative AI | Product classifier with GenAI |
| 09 | Data Science | Logistic regression, linear regression, data mining |
| 10 | Data Governance | Master data management |
| 11 | Data Engineering Programming | Payment report challenge |
| 12 | Graph Databases & Analytics | Neo4j, GDS, PageRank, Louvain, Airbnb dataset |
| 13 | Microservices, APIs & Webhooks | Microservices architecture |
| 14 | Advanced Data Modeling | Modeling activities |
| 15 | Agile Database Project | Final project |
| 16 | Distributed Data Processing & Storage | Big data processing |
| 17 | Cloud Engineering | Final project |
| 18 | Data Analytics Architecture | Maria Bank data strategy |

## Stack

![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white)
![Apache Spark](https://img.shields.io/badge/Apache_Spark-E25A1C?style=flat&logo=apachespark&logoColor=white)
![Kafka](https://img.shields.io/badge/Apache_Kafka-231F20?style=flat&logo=apachekafka&logoColor=white)
![MongoDB](https://img.shields.io/badge/MongoDB-47A248?style=flat&logo=mongodb&logoColor=white)
![Neo4j](https://img.shields.io/badge/Neo4j-008CC1?style=flat&logo=neo4j&logoColor=white)
![Databricks](https://img.shields.io/badge/Databricks-FF3621?style=flat&logo=databricks&logoColor=white)
![SQL](https://img.shields.io/badge/SQL-4479A1?style=flat&logo=postgresql&logoColor=white)

## Downloading the assignments locally

The `fiap_downloader.py` script downloads all assignments from the FIAP portal automatically, organized by discipline.

### Requirements

```bash
pip install requests beautifulsoup4
```

### Step 1 — Export cookies from Firefox

1. Open Firefox and go to:
   ```
   https://on1.fiap.com.br/programas/login/alunos_2004/entregaTrabalho/lista.asp?arquivado=1&titulo_secao=Entrega+de+Trablaho
   ```
2. Log in if prompted
3. Open DevTools: **F12** → **Console** tab
4. Paste and run the following script:

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

5. `cookies.txt` will be downloaded automatically

### Step 2 — Add session cookie manually

The console script cannot capture `HttpOnly` cookies. To add the session cookie:

1. In DevTools → **Storage** tab → **Cookies** → `on1.fiap.com.br`
2. Copy the value of `ASP.NET_SessionId`
3. Add this line at the top of `cookies.txt`:
   ```
   on1.fiap.com.br	TRUE	/	FALSE	2147483647	ASP.NET_SessionId	YOUR_VALUE_HERE
   ```

### Step 3 — Run

Place `fiap_downloader.py` and `cookies.txt` in the same folder and run:

```bash
python fiap_downloader.py
```

> **Note:** The session expires after ~20 minutes. If you see `[SESSÃO EXPIRADA]`, re-export `cookies.txt` and run again — already downloaded files will be skipped automatically.

## About

- **Institution:** FIAP
- **Program:** MBA in Data Engineering
- **Class:** 29ABD — 2025/2026
