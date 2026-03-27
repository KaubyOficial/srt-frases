import glob
import os
import re
import sys

DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads")
DESTINO_BASE = r"C:\Users\Administrador\Documents\F NOVO"

def encontrar_arquivo():
    padrao = os.path.join(DOWNLOADS, "F.*.AL.txt")
    arquivos = glob.glob(padrao)
    if not arquivos:
        print("Nenhum arquivo F.XXX.AL.txt encontrado na pasta Downloads.")
        sys.exit(1)
    if len(arquivos) > 1:
        print("Mais de um arquivo encontrado:")
        for i, a in enumerate(arquivos):
            print(f"  [{i+1}] {os.path.basename(a)}")
        escolha = input("Qual usar? (numero): ").strip()
        return arquivos[int(escolha) - 1]
    return arquivos[0]

def extrair_numero(nome_arquivo):
    base = os.path.basename(nome_arquivo)
    match = re.match(r"F\.(\d+)\.AL\.txt", base, re.IGNORECASE)
    if not match:
        print(f"Nome do arquivo fora do padrao esperado: {base}")
        sys.exit(1)
    return match.group(1)

def remover_separadores_paragrafo(texto):
    """Remove linhas que contem apenas * (separador de paragrafo),
    junto com as linhas em branco que as cercam, sem deixar espacos extras."""
    # Divide em blocos separados por linhas em branco
    # e descarta blocos que sao apenas *
    linhas = texto.split("\n")
    resultado = []
    i = 0
    while i < len(linhas):
        linha = linhas[i].strip()
        if linha == "*":
            # Remove linhas em branco antes (ja no resultado)
            while resultado and resultado[-1] == "":
                resultado.pop()
            # Pula linhas em branco depois
            i += 1
            while i < len(linhas) and linhas[i].strip() == "":
                i += 1
            # Adiciona uma linha em branco para separar os paragrafos
            resultado.append("")
            continue
        resultado.append(linhas[i])
        i += 1
    return "\n".join(resultado).strip()

def processar(caminho_arquivo):
    numero = extrair_numero(caminho_arquivo)

    with open(caminho_arquivo, "r", encoding="utf-8") as f:
        conteudo = f.read()

    # Remove BOM se houver
    conteudo = conteudo.lstrip("\ufeff")

    # Divide nas marcacoes ** (linha contendo apenas **)
    partes = re.split(r"\n\s*\*\*\s*\n", conteudo)

    # Fallback: ** sem linhas em branco ao redor
    if len(partes) < 2:
        partes = re.split(r"\s*\*\*\s*", conteudo)

    partes = [p.strip() for p in partes]
    partes = [p for p in partes if p]

    if len(partes) != 3:
        print(f"Atencao: esperado 3 partes, encontradas {len(partes)} apos dividir no '**'.")
        resposta = input("Continuar mesmo assim? (s/n): ").strip().lower()
        if resposta != "s":
            sys.exit(0)

    # Pasta destino: F NOVO\<numero>
    pasta_destino = os.path.join(DESTINO_BASE, numero)
    os.makedirs(pasta_destino, exist_ok=True)

    for i, parte in enumerate(partes, start=1):
        parte_limpa = remover_separadores_paragrafo(parte)

        nome_saida = f"R{i}.txt"
        caminho_saida = os.path.join(pasta_destino, nome_saida)

        with open(caminho_saida, "w", encoding="utf-8") as f:
            f.write(parte_limpa)

        print(f"Criado: {caminho_saida}")

    print(f"\nConcluido! {len(partes)} arquivo(s) salvos em: {pasta_destino}")

if __name__ == "__main__":
    arquivo = encontrar_arquivo()
    print(f"Arquivo encontrado: {os.path.basename(arquivo)}")
    processar(arquivo)
