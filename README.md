# SRT Processor — Sincronizador de Roteiro por Frase

Pega o SRT de legenda automática de um vídeo em alemão e um roteiro organizado
em parágrafos, e gera um novo SRT com os timestamps corretos **por frase** —
permitindo sincronizar a edição sem entender o idioma.

## Como usar

1. Execute `srt_processor.py` com Python:
   ```
   python srt_processor.py
   ```
2. Clique em **Selecionar Pasta e Processar**
3. Escolha a pasta que contém os pares de arquivos
4. O resultado (`p#.srt`) será gerado na mesma pasta

## Convenção de nomes

| Entrada SRT         | Entrada Roteiro | Saída       |
|---------------------|-----------------|-------------|
| `srt1.srt`          | `r1.txt`        | `p1.srt`    |
| `srt2.srt`          | `r2.txt`        | `p2.srt`    |
| `srt10.srt`         | `r10.txt`       | `p10.srt`   |

## Formato dos arquivos

**SRT (`srt#.srt`):** Legenda automática padrão SRT, em alemão.
Salvar em **UTF-8** (com ou sem BOM — ambos são tratados).

**Roteiro (`r#.txt`):** Texto do roteiro, um parágrafo por linha.
- Cada parágrafo será dividido em frases pela pontuação (`.`, `!`, `?`)
- Abreviações alemãs comuns (`bzw.`, `usw.`, `z.B.`, etc.) são protegidas

**Saída (`p#.srt`):** SRT com uma entrada por frase, timestamps sincronizados com o SRT original.

## Pasta `exemplo/`

Contém `srt1.srt` e `r1.txt` de exemplo para testar.
Aponte a ferramenta para a pasta `exemplo/` para gerar `p1.srt` e validar.

## Como funciona

1. **Localiza o início de cada parágrafo** no SRT pelas primeiras palavras
2. **Expande o bloco** até cobrir o parágrafo inteiro — usando *coverage score*
   direcional (fração do parágrafo coberta pelo trecho), não similaridade
   simétrica, o que evita parar cedo demais
3. **Distribui as frases** dentro do range encontrado, associando cada frase
   ao subconjunto de entradas SRT que melhor corresponde a ela

## Requisitos

- Python 3.8+
- Apenas bibliotecas padrão (tkinter, difflib, re, datetime, os)

## Histórico

| Versão | Arquivo                    | Mudança                                      |
|--------|----------------------------|----------------------------------------------|
| 1.0    | `_old/srt_gui_v1.0.py`     | Apenas por parágrafo, sem separação por frase|
| 1.1    | `_old/srt_gui_frases_v1.1.py` | Adicionou separação por frase            |
| 2.0    | `srt_processor.py`         | Fix: coverage_score corrige parada prematura |
