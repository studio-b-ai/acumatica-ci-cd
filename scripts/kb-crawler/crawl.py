#!/usr/bin/env python3
"""Acumatica Help Wiki crawler → studiob-knowledge (Qdrant).

Modes:
  discover  — re-discover all guide roots from help.acumatica.com landing page (requires Playwright)
  enumerate [slugs...]  — walk each guide's /ui/helptree/{pid} tree, record every pageid
  fetch [slugs...]      — fetch each pageid (cached; only new pages are re-downloaded)
  ingest [slugs...]     — chunk + embed + upsert to studiob-knowledge
  all [slugs...]        — enumerate + fetch + ingest for given slugs (or all new)
  monthly               — full monthly refresh: enumerate every guide, fetch deltas, ingest
  list                  — show all known guides + node counts

State files (relative to this script):
  guides.json            — root pageid + tree_guid per guide
  state/tree_nodes.json  — full tree enumeration
  pages/{pid}.json       — cached page content

Env vars required for ingest:
  QDRANT_URL, VOYAGE_API_KEY
"""
import os, sys, json, time, re, uuid, ssl, argparse
import urllib.request, http.cookiejar, urllib.error
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from glob import glob

try:
    import certifi
    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CTX = ssl.create_default_context()

import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(ROOT, "state")
PAGES_DIR = os.path.join(ROOT, "pages")
GUIDES_PATH = os.path.join(ROOT, "guides.json")
TREE_NODES_PATH = os.path.join(STATE_DIR, "tree_nodes.json")
os.makedirs(STATE_DIR, exist_ok=True)
os.makedirs(PAGES_DIR, exist_ok=True)

BOILERPLATE = {
    "refresh","tools","get link","dac schema browser","trace...","about...",
    "upload xml file","choose file:","cancel","about acumatica",
    "profiler","update history","expand all","collapse all","locales",
    "get file link","report typo","print","export","plain text","word","[edit]",
    "in this topic","[hide/show]","close","send report","ok","note",
    "translations","copy to clipboard (ctrl+c)","internal link :","external link:",
    "public link:","public link :","external link :","internal link:",
    "back to top","max 25000kb","upload",
}

# -------- helpers --------

def make_session():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cj),
        urllib.request.HTTPSHandler(context=SSL_CTX),
    )
    op.addheaders = [("User-Agent","studiob-kb-crawler/1.0"),("Accept","application/json, text/javascript, */*")]
    op.open("https://help.acumatica.com/Main", timeout=30).read()
    return op

def load_guides():
    with open(GUIDES_PATH) as f:
        raw = json.load(f)
    out = {}
    for slug, meta in raw.items():
        if not meta.get("root_pageid") or not meta.get("tree_guid"):
            continue
        out[slug] = {
            "tree_guid": meta["tree_guid"],
            "root_pageid": meta["root_pageid"],
            "title": meta.get("label") or meta.get("title", slug),
            "edition": meta.get("edition", "unknown"),
        }
    return out

def load_tree_nodes():
    if os.path.exists(TREE_NODES_PATH):
        return json.load(open(TREE_NODES_PATH))
    return {}

def save_tree_nodes(d):
    tmp = TREE_NODES_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=2)
    os.replace(tmp, TREE_NODES_PATH)

# -------- enumerate --------

def tree_get(opener, url, tries=3):
    for i in range(tries):
        try:
            return json.loads(opener.open(url, timeout=30).read())
        except urllib.error.HTTPError as e:
            if e.code == 401 and i == 0:
                opener.open("https://help.acumatica.com/Main", timeout=20).read(); continue
            if i == tries - 1: raise
            time.sleep(1+i)
        except Exception:
            if i == tries - 1: raise
            time.sleep(1+i)

def enumerate_one(slug, info, verbose=True):
    opener = make_session()
    root_pid = info["root_pageid"]
    try:
        top = tree_get(opener, f"https://help.acumatica.com/ui/helptree/{info['tree_guid']}?selected={root_pid}")
    except Exception as e:
        print(f"  [{slug}] FAIL top-level: {e}")
        return {}
    all_nodes = {}
    for n in top:
        pid = n["path"].lower()
        all_nodes[pid] = {"text": n["text"], "hasChildren": bool(n.get("hasChildren")), "parent": None, "depth": 0}
    queue = [pid for pid, m in all_nodes.items() if m["hasChildren"]]
    visited = set()
    t0 = time.time()
    while queue:
        pid = queue.pop(0)
        if pid in visited: continue
        visited.add(pid)
        try:
            kids = tree_get(opener, f"https://help.acumatica.com/ui/helptree/{pid}")
        except Exception as e:
            if verbose: print(f"  [{slug}] ! children({pid[:8]}) {type(e).__name__}: {e}")
            continue
        for k in kids:
            kpid = k["path"].lower()
            if kpid in all_nodes: continue
            all_nodes[kpid] = {
                "text": k["text"],
                "hasChildren": bool(k.get("hasChildren")),
                "parent": pid,
                "depth": all_nodes[pid]["depth"] + 1,
            }
            if k.get("hasChildren"):
                queue.append(kpid)
        if verbose and len(visited) % 50 == 0:
            print(f"  [{slug}] expanded={len(visited):5d} total={len(all_nodes):6d} q={len(queue):5d} ({time.time()-t0:.0f}s)", flush=True)
        time.sleep(0.04)
    all_nodes.setdefault(root_pid.lower(), {"text": info["title"], "hasChildren": True, "parent": None, "depth": 0})
    print(f"  [{slug}] DONE {len(all_nodes)} nodes ({time.time()-t0:.0f}s)", flush=True)
    return all_nodes

def do_enumerate(slugs):
    guides = load_guides()
    existing = load_tree_nodes()
    targets = slugs or [s for s in guides if s not in existing]
    if not targets:
        print("Nothing to enumerate.")
        return
    print(f"Enumerating {len(targets)} guides")
    for slug in targets:
        if slug not in guides:
            print(f"  [{slug}] UNKNOWN — skipping")
            continue
        info = guides[slug]
        print(f"\n===== {info['title']} ({slug}) =====")
        nodes = enumerate_one(slug, info)
        if nodes:
            existing[slug] = {
                "tree_guid": info["tree_guid"],
                "root_pageid": info["root_pageid"],
                "title": info["title"],
                "edition": info["edition"],
                "nodes": nodes,
            }
            save_tree_nodes(existing)
    print(f"\nEnumeration complete. {sum(len(v['nodes']) for v in existing.values())} total nodes across {len(existing)} guides.")

# -------- fetch --------

def fetch_raw(opener, pid, tries=3):
    url = f"https://help.acumatica.com/Wiki/Show.aspx?pageid={pid}&HideScript=On"
    for i in range(tries):
        try:
            return opener.open(url, timeout=30).read().decode("utf-8", errors="replace")
        except Exception:
            if i == tries - 1: raise
            time.sleep(1+i)

def clean(raw):
    soup = BeautifulSoup(raw, "lxml")
    title = (soup.title.string or "").strip() if soup.title else ""
    for t in soup(["script","style","noscript"]):
        t.decompose()
    wikis = soup.find_all("div", class_="wiki")
    main = wikis[0] if wikis else (soup.body or soup)
    text = main.get_text("\n", strip=True)
    lines = []
    prev_blank = False
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            if not prev_blank:
                lines.append("")
            prev_blank = True
            continue
        low = s.lower()
        if low in BOILERPLATE or low.startswith("screen id cst") or low.startswith("screen id "):
            continue
        s = re.sub(r"\[anchor\|#_[0-9a-f-]+\]", "", s)
        s = re.sub(r"\{br\}|\{TOC\}|\{S:\w+\}", "", s)
        if not s.strip():
            continue
        lines.append(s)
        prev_blank = False
    text = "\n".join(lines).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text, title

import threading
_tls = threading.local()

def _fetch_worker(task):
    slug, pid, tree_text, depth, force = task
    out_path = os.path.join(PAGES_DIR, f"{pid}.json")
    if os.path.exists(out_path) and not force:
        return (pid, "cached", 0)
    op = getattr(_tls, "opener", None)
    if op is None:
        op = _tls.opener = make_session()
    try:
        raw = fetch_raw(op, pid)
        text, title = clean(raw)
    except Exception as e:
        return (pid, f"err:{e}", 0)
    if len(text) < 200:
        return (pid, f"short:{len(text)}", 0)
    with open(out_path, "w") as f:
        json.dump({
            "pageid": pid,
            "title": title,
            "tree_text": tree_text,
            "guide": slug,
            "depth": depth,
            "text": text,
            "fetched_at": int(time.time()),
        }, f)
    return (pid, "ok", len(text))

def do_fetch(slugs, parallelism=10, force=False):
    data = load_tree_nodes()
    if slugs:
        slugs = [s for s in slugs if s in data]
    else:
        slugs = list(data.keys())
    tasks = []
    for slug in slugs:
        for pid, meta in data[slug]["nodes"].items():
            tasks.append((slug, pid, meta["text"], meta["depth"], force))
    print(f"{len(tasks)} pages queued (parallelism={parallelism}, force={force})")
    ok = short = err = cached = done = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=parallelism) as ex:
        futures = [ex.submit(_fetch_worker, t) for t in tasks]
        for fut in as_completed(futures):
            pid, status, chars = fut.result()
            done += 1
            if status == "ok": ok += 1
            elif status == "cached": cached += 1
            elif status.startswith("short"): short += 1
            else: err += 1
            if done % 100 == 0:
                print(f"  [{done}/{len(tasks)}] ok={ok} cached={cached} short={short} err={err} ({time.time()-t0:.0f}s)", flush=True)
    print(f"\nFetch done. ok={ok} cached={cached} short={short} err={err}  total={done}  ({time.time()-t0:.0f}s)")

# -------- ingest --------

def chunk_text(text, chunk_size=1800, overlap=200):
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, cur, cur_len = [], [], 0
    for p in paras:
        if cur_len + len(p) + 2 > chunk_size and cur:
            chunks.append("\n\n".join(cur))
            tail = chunks[-1][-overlap:]
            cur = [tail, p]
            cur_len = len(tail) + len(p) + 2
        else:
            cur.append(p); cur_len += len(p) + 2
    if cur:
        chunks.append("\n\n".join(cur))
    out = []
    for c in chunks:
        if len(c) <= chunk_size * 1.3:
            out.append(c)
        else:
            for i in range(0, len(c), chunk_size - overlap):
                out.append(c[i:i+chunk_size])
    return [c for c in out if len(c.strip()) >= 100]

def do_ingest(slugs=None, delete_prior=False):
    QDRANT_URL = os.environ["QDRANT_URL"]
    VOYAGE_API_KEY = os.environ["VOYAGE_API_KEY"]
    COLLECTION = "studiob-knowledge"
    TOPIC = "acumatica-help-wiki"
    BATCH = 64

    guides = load_guides()
    if delete_prior:
        print("Deleting prior acumatica-help chunks...")
        for topic_val in ("inventory-planning-mrp-drp", TOPIC):
            r = requests.post(
                f"{QDRANT_URL}/collections/{COLLECTION}/points/delete?wait=true",
                json={"filter": {"must": [{"key": "topic", "match": {"value": topic_val}}]}},
                timeout=60,
            )
            print(f"  {topic_val}: {r.status_code}")

    files = sorted(glob(os.path.join(PAGES_DIR, "*.json")))
    if slugs:
        wanted = set(slugs)
        files = [f for f in files if json.load(open(f)).get("guide") in wanted]
    print(f"{len(files)} pages to ingest")
    ingested_at = int(time.time())

    all_chunks = []
    for f in files:
        d = json.load(open(f))
        pid = d["pageid"]
        title = (d.get("title") or d.get("tree_text") or "").strip()
        text = d["text"]
        guide_slug = d.get("guide","")
        ginfo = guides.get(guide_slug, {"title": guide_slug, "edition": "unknown"})
        chunks = chunk_text(text)
        for idx, c in enumerate(chunks):
            payload = {
                "domain": "acumatica",
                "client": None,
                "source": "acumatica-help-wiki",
                "source_type": "help-wiki",
                "topic": TOPIC,
                "guide": ginfo["title"],
                "guide_slug": guide_slug,
                "edition": ginfo["edition"],
                "title": title,
                "pageid": pid,
                "tree_depth": d.get("depth", 0),
                "source_url": f"https://help.acumatica.com/Help?ScreenId=ShowWiki&pageid={pid}",
                "chunkIndex": idx,
                "chunkCount": len(chunks),
                "hasCode": False,
                "text": c,
                "ingested_at": ingested_at,
            }
            all_chunks.append((payload, c))
    print(f"{len(all_chunks)} chunks to embed")

    for i in range(0, len(all_chunks), BATCH):
        batch = all_chunks[i:i+BATCH]
        texts = [b[1] for b in batch]
        r = requests.post("https://api.voyageai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {VOYAGE_API_KEY}","Content-Type":"application/json"},
            json={"input": texts, "model": "voyage-3", "input_type": "document"},
            timeout=120)
        r.raise_for_status()
        vectors = [d["embedding"] for d in r.json()["data"]]
        points = [{"id": str(uuid.uuid4()), "vector": v, "payload": p[0]} for p, v in zip(batch, vectors)]
        r2 = requests.put(f"{QDRANT_URL}/collections/{COLLECTION}/points?wait=true",
            json={"points": points}, timeout=120)
        r2.raise_for_status()
        if (i // BATCH) % 10 == 0 or i + BATCH >= len(all_chunks):
            print(f"  upserted {min(i+BATCH, len(all_chunks))}/{len(all_chunks)}", flush=True)
        time.sleep(0.15)
    print("Ingest done.")

# -------- monthly refresh --------

def do_monthly():
    print(f"=== MONTHLY REFRESH @ {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
    # Back up existing tree state and re-enumerate from scratch to catch new pages + deletions
    if os.path.exists(TREE_NODES_PATH):
        os.rename(TREE_NODES_PATH, TREE_NODES_PATH + f".bak-{int(time.time())}")
    do_enumerate([])  # empty = all guides
    do_fetch([], parallelism=10)  # cache-aware; only new/missing pages re-downloaded
    do_ingest(None, delete_prior=True)
    print("=== MONTHLY REFRESH COMPLETE ===")

# -------- cli --------

def main():
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["discover","enumerate","fetch","ingest","all","monthly","list"])
    p.add_argument("slugs", nargs="*")
    p.add_argument("--force", action="store_true", help="re-fetch even cached pages")
    p.add_argument("--delete-prior", action="store_true", help="delete prior topic before ingest")
    p.add_argument("--parallelism", type=int, default=10)
    args = p.parse_args()

    if args.cmd == "list":
        guides = load_guides()
        tree = load_tree_nodes()
        total_nodes = 0
        for slug, info in sorted(guides.items()):
            n = len(tree.get(slug, {}).get("nodes", {})) if slug in tree else 0
            total_nodes += n
            print(f"  {slug:28} {info['edition']:15} {n:6d} nodes  {info['title']}")
        print(f"\nTotal guides: {len(guides)}  |  Total nodes: {total_nodes}")
        return
    if args.cmd == "enumerate":
        do_enumerate(args.slugs)
    elif args.cmd == "fetch":
        do_fetch(args.slugs, parallelism=args.parallelism, force=args.force)
    elif args.cmd == "ingest":
        do_ingest(args.slugs or None, delete_prior=args.delete_prior)
    elif args.cmd == "all":
        do_enumerate(args.slugs)
        do_fetch(args.slugs, parallelism=args.parallelism)
        do_ingest(args.slugs or None, delete_prior=args.delete_prior)
    elif args.cmd == "monthly":
        do_monthly()

if __name__ == "__main__":
    main()
