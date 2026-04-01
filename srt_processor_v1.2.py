"""
SRT Processor — Sincronizador de Roteiro Alemão por Frase
==========================================================
Recebe um SRT de legenda automática (alemão) + roteiro organizado por
parágrafos e gera um novo SRT com os timestamps corretos por frase do
roteiro — permitindo sincronizar a edição sem entender o idioma.

Convenção de nomes:
  srt1.srt  +  r1.txt  →  p1.srt
  srt2.srt  +  r2.txt  →  p2.srt
  ...

O roteiro (r#.txt) deve ter uma linha por parágrafo.
Cada parágrafo é dividido em frases pela pontuação (.!?).
"""

import sys
import tkinter as tk
from tkinter import filedialog, messagebox
from datetime import datetime
from difflib import SequenceMatcher
import re
import os


# ─── SRT Parsing ─────────────────────────────────────────────────────────────

def parse_srt(srt_text):
    """Parse SRT content into list of {start, end, text} dicts."""
    srt_text = srt_text.lstrip('\ufeff')  # Remove BOM
    srt_text = srt_text.replace('\r\n', '\n').replace('\r', '\n')
    pattern = re.compile(
        r"(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.+?)(?=\n\d+\n|\Z)",
        re.DOTALL
    )
    entries = []
    for match in pattern.findall(srt_text.strip()):
        entries.append({
            "start": datetime.strptime(match[1], "%H:%M:%S,%f"),
            "end":   datetime.strptime(match[2], "%H:%M:%S,%f"),
            "text":  match[3].replace('\n', ' ').strip()
        })
    return entries


def format_srt_time(dt):
    return dt.strftime("%H:%M:%S,%f")[:-3]


# ─── Text Helpers ─────────────────────────────────────────────────────────────

def normalizar_texto(texto):
    """Lowercase, remove punctuation, collapse whitespace."""
    texto = texto.lower()
    texto = re.sub(r'[^\w\s]', ' ', texto)
    texto = re.sub(r'\s+', ' ', texto)
    return texto.strip()


def similar(a, b):
    return SequenceMatcher(None, a, b).ratio()


def coverage_score(par_clean, trecho):
    """
    One-directional coverage: fraction of par_clean characters matched in trecho.

    Unlike SequenceMatcher.ratio() (symmetric), this score never decreases as
    trecho grows — it only improves when new content matches more of par_clean.
    This fixes the false early-stop in expandir_bloco.
    """
    if not par_clean:
        return 0.0
    matcher = SequenceMatcher(None, par_clean, trecho, autojunk=False)
    matched = sum(t.size for t in matcher.get_matching_blocks())
    return matched / len(par_clean)


# ─── Abbreviation-aware sentence splitting ───────────────────────────────────

_ABBREVS = re.compile(
    r'\b(bzw|usw|ggf|etc|z\.B|u\.a|d\.h|vgl|ca|sog|evtl|inkl|exkl|'
    r'Dr|Prof|Nr|Abs|Art|Kap|hrsg|bsp|lt|ggü|bzgl|m\.E|o\.ä)\.',
    re.IGNORECASE
)

def separar_em_frases_par(texto):
    """Split paragraph into sentences, protecting German abbreviations."""
    placeholder = "\x00"
    protected = _ABBREVS.sub(lambda m: m.group(0).replace('.', placeholder), texto)
    partes = re.split(r'(?<=[.!?])\s+', protected.strip())
    return [p.replace(placeholder, '.').strip() for p in partes if p.strip()]


# ─── Paragraph Range Detection ───────────────────────────────────────────────

def encontrar_inicio_paragrafo(srt_entries, par_clean, inicio_busca, usados):
    """Find paragraph start by matching first 7 words against SRT entries."""
    palavras = par_clean.split()[:7]
    if not palavras:
        return None
    texto_inicio = " ".join(palavras)
    melhor_pos = None
    melhor_score = 0
    limite = min(inicio_busca + 400, len(srt_entries))
    for i in range(inicio_busca, limite):
        if i in usados:
            continue
        # Combine current + next entry to handle paragraphs whose first words
        # are split across two SRT entries (e.g., "Im Jahr 2000" / "traf Saddam...")
        srt_texto = normalizar_texto(srt_entries[i]["text"])
        if i + 1 < len(srt_entries) and (i + 1) not in usados:
            srt_texto = srt_texto + " " + normalizar_texto(srt_entries[i + 1]["text"])
        srt_inicio = " ".join(srt_texto.split()[:7])
        score = similar(texto_inicio, srt_inicio)
        if score > melhor_score and score > 0.45:
            melhor_score = score
            melhor_pos = i
            if score > 0.92:
                break
    return melhor_pos


def expandir_bloco(srt_entries, par_clean, inicio_pos, usados, limite_max=150):
    """
    Expand block from inicio_pos until par_clean is fully covered.

    FIX vs. v1.1: uses coverage_score (one-directional) instead of
    SequenceMatcher.ratio() (symmetric). The old ratio would drop as trecho
    grew beyond par_clean length, causing a false early-stop even when the
    correct SRT entries hadn't been included yet.

    Stops when:
    - Coverage >= 0.92 (full match)
    - No improvement for 8+ entries AND trecho already 1.5x longer than par_clean
    """
    melhor_coverage = 0.0
    melhor_tamanho = 1
    sem_melhora = 0

    for tamanho in range(1, min(limite_max + 1, len(srt_entries) - inicio_pos + 1)):
        fim_pos = inicio_pos + tamanho - 1
        if any(i in usados for i in range(inicio_pos, fim_pos + 1)):
            break

        trecho = " ".join(
            normalizar_texto(srt_entries[i]["text"])
            for i in range(inicio_pos, fim_pos + 1)
        )
        cov = coverage_score(par_clean, trecho)

        if cov > melhor_coverage + 0.005:
            melhor_coverage = cov
            melhor_tamanho = tamanho
            sem_melhora = 0
        else:
            sem_melhora += 1

        if cov >= 0.92:
            break
        if sem_melhora >= 8 and len(trecho) > len(par_clean) * 1.5:
            break

    return melhor_tamanho, melhor_coverage


# ─── Sentence Distribution within SRT Range ──────────────────────────────────

def distribuir_frases_no_range(srt_entries, frases, inicio_range, fim_range):
    """
    Distribute sentences within the already-located SRT range for a paragraph.
    Guarantees each sentence stays within the range — no timestamp jumps.
    Uses coverage_score for per-sentence matching.
    """
    resultado = []
    pos_atual = inicio_range
    n_frases = len(frases)

    for i, frase in enumerate(frases):
        frase_clean = normalizar_texto(frase)
        is_last = (i == n_frases - 1)

        # Last sentence (or exhausted range): assign everything remaining
        if is_last or pos_atual > fim_range:
            bloco = srt_entries[pos_atual:fim_range + 1]
            if bloco:
                resultado.append({
                    "start": bloco[0]["start"],
                    "end":   bloco[-1]["end"],
                    "text":  frase.strip()
                })
            elif resultado:
                resultado.append({
                    "start": resultado[-1]["start"],
                    "end":   resultado[-1]["end"],
                    "text":  frase.strip()
                })
            # Handle remaining sentences if range ran out early
            if not is_last and resultado:
                for j in range(i + 1, n_frases):
                    resultado.append({
                        "start": resultado[-1]["start"],
                        "end":   resultado[-1]["end"],
                        "text":  frases[j].strip()
                    })
            break

        # Reserve 1 SRT entry per remaining sentence
        frases_restantes = n_frases - i - 1
        max_fim_frase = fim_range - frases_restantes

        melhor_score = 0.0
        melhor_tamanho = 1
        for tam in range(1, max_fim_frase - pos_atual + 2):
            fim_tent = pos_atual + tam - 1
            if fim_tent > max_fim_frase:
                break
            trecho = " ".join(
                normalizar_texto(srt_entries[j]["text"])
                for j in range(pos_atual, fim_tent + 1)
            )
            score = coverage_score(frase_clean, trecho)
            if score > melhor_score:
                melhor_score = score
                melhor_tamanho = tam
            if score >= 0.90:
                break
            if tam > 3 and melhor_score > 0.5 and score < melhor_score * 0.95:
                break

        fim_frase = pos_atual + melhor_tamanho - 1
        bloco = srt_entries[pos_atual:fim_frase + 1]
        resultado.append({
            "start": bloco[0]["start"],
            "end":   bloco[-1]["end"],
            "text":  frase.strip()
        })
        pos_atual = fim_frase + 1

    return resultado


# ─── Main Aggregation ─────────────────────────────────────────────────────────

def agrupar_por_frases(srt_entries, paragrafos):
    """
    Two-pass approach:
    1. Locate SRT range for each paragraph (start detection + coverage expansion)
    2. Distribute individual sentences within that range
    """
    usados = set()
    resultado = []
    ultima_pos = 0

    for par in paragrafos:
        par_clean = normalizar_texto(par)
        if not par_clean:
            continue

        inicio_pos = encontrar_inicio_paragrafo(srt_entries, par_clean, ultima_pos, usados)

        if inicio_pos is None:
            # Fallback: broad search
            melhor_score = 0
            melhor_bloco = []
            for tam in range(1, min(51, len(srt_entries) - ultima_pos + 1)):
                for i in range(ultima_pos, len(srt_entries) - tam + 1):
                    if any(j in usados for j in range(i, i + tam)):
                        continue
                    trecho = " ".join(
                        normalizar_texto(srt_entries[j]["text"]) for j in range(i, i + tam)
                    )
                    score = similar(par_clean, trecho)
                    if score > melhor_score:
                        melhor_score = score
                        melhor_bloco = list(range(i, i + tam))
                        if score > 0.7:
                            break
                if melhor_score > 0.7:
                    break
            if not melhor_bloco or melhor_score <= 0.4:
                continue
            inicio_pos = melhor_bloco[0]
            tamanho = len(melhor_bloco)
            score = melhor_score
        else:
            tamanho, score = expandir_bloco(srt_entries, par_clean, inicio_pos, usados)

        if score <= 0.35:
            continue

        fim_pos = inicio_pos + tamanho - 1
        frases = separar_em_frases_par(par)
        n_frases = len(frases)

        # Guarantee at least 1 SRT entry per sentence
        while fim_pos - inicio_pos + 1 < n_frases:
            proximo = fim_pos + 1
            if proximo >= len(srt_entries) or proximo in usados:
                break
            fim_pos = proximo

        usados.update(range(inicio_pos, fim_pos + 1))
        ultima_pos = fim_pos + 1

        if n_frases <= 1:
            bloco = srt_entries[inicio_pos:fim_pos + 1]
            resultado.append({
                "start": bloco[0]["start"],
                "end":   bloco[-1]["end"],
                "text":  par.strip()
            })
        else:
            sub = distribuir_frases_no_range(srt_entries, frases, inicio_pos, fim_pos)
            resultado.extend(sub)

    for i, bloco in enumerate(resultado, start=1):
        bloco["index"] = i

    return resultado


# ─── File I/O ─────────────────────────────────────────────────────────────────

def gerar_srt_final(srt_path, roteiro_path, output_path):
    try:
        with open(srt_path, "r", encoding="utf-8") as f:
            srt_raw = f.read()
        with open(roteiro_path, "r", encoding="utf-8") as f:
            paragrafos = [p for p in f.read().split("\n") if p.strip()]
        srt = parse_srt(srt_raw)
        if not srt:
            return False, "SRT inválido ou vazio (verifique encoding UTF-8 e formato)"
        blocos = agrupar_por_frases(srt, paragrafos)
        if not blocos:
            return False, "Nenhum match encontrado (roteiro e SRT muito diferentes?)"
        with open(output_path, "w", encoding="utf-8") as f:
            for bloco in blocos:
                f.write(f"{bloco['index']}\n")
                f.write(f"{format_srt_time(bloco['start'])} --> {format_srt_time(bloco['end'])}\n")
                f.write(f"{bloco['text']}\n\n")
        return True, f"{len(blocos)} entradas geradas"
    except Exception as e:
        return False, str(e)


def encontrar_pares_de_arquivos(pasta):
    """Find matching srt#.srt + r#.txt pairs in folder."""
    srts = {}
    roteiros = {}
    for nome in os.listdir(pasta):
        base = nome.lower()
        if base.startswith('srt') and base.endswith('.srt'):
            nums = re.findall(r'srt(\d+)', base)
            if nums:
                srts[int(nums[0])] = nome
        elif base.startswith('r') and base.endswith('.txt'):
            nums = re.findall(r'^r(\d+)', base)
            if nums:
                roteiros[int(nums[0])] = nome
    return [(n, srts[n], roteiros[n]) for n in sorted(srts) if n in roteiros]


# ─── GUI ──────────────────────────────────────────────────────────────────────

def executar_na_pasta(pasta):
    pares = encontrar_pares_de_arquivos(pasta)
    if not pares:
        messagebox.showerror(
            "Nenhum par encontrado",
            "Nomeie os arquivos assim:\n\n"
            "  srt1.srt  +  r1.txt  →  p1.srt\n"
            "  srt2.srt  +  r2.txt  →  p2.srt\n\n"
            "O roteiro deve ser UTF-8 com uma linha por parágrafo."
        )
        return

    erros = []
    gerados = []
    for num, srt_nome, roteiro_nome in pares:
        srt_path     = os.path.join(pasta, srt_nome)
        roteiro_path = os.path.join(pasta, roteiro_nome)
        output_path  = os.path.join(pasta, f"p{num}.srt")
        ok, msg = gerar_srt_final(srt_path, roteiro_path, output_path)
        if ok:
            gerados.append(f"p{num}.srt — {msg}")
        else:
            erros.append(f"Par {num}: {msg}")

    partes = []
    if gerados:
        partes.append("Gerado com sucesso:\n" + "\n".join(f"  ✓ {g}" for g in gerados))
    if erros:
        partes.append("Erros:\n" + "\n".join(f"  ✗ {e}" for e in erros))

    if erros:
        messagebox.showerror("Concluído com erros", "\n\n".join(partes))
    else:
        messagebox.showinfo("Concluído!", "\n\n".join(partes))


def processar_pasta():
    pasta = filedialog.askdirectory(title="Selecione a pasta com os arquivos SRT e Roteiro")
    if not pasta:
        return
    executar_na_pasta(pasta)


root = tk.Tk()
root.title("SRT Processor — Sincronizador por Frase")
root.geometry("520x190")
root.resizable(False, False)

tk.Label(
    root,
    text="Sincroniza roteiro alemão com SRT automático — por frase.\n"
         "Nomeie: srt1.srt + r1.txt → p1.srt, srt2.srt + r2.txt → p2.srt ...",
    justify="center",
    wraplength=480
).pack(pady=20)

tk.Button(
    root,
    text="Selecionar Pasta e Processar",
    command=processar_pasta,
    bg="#2e7d32", fg="white",
    height=2, width=30,
    font=("Segoe UI", 10, "bold")
).pack(pady=10)

# Se receber pasta como argumento, processa direto e fecha a janela ao terminar
if len(sys.argv) > 1:
    pasta_arg = sys.argv[1]
    def processar_e_fechar():
        executar_na_pasta(pasta_arg)
        root.destroy()
    root.after(100, processar_e_fechar)

root.mainloop()
