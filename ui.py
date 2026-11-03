"""Explorador do olist.duckdb no navegador (extensão `ui` do DuckDB).

Executar com:  uv run python ui.py

SPEC E MOTIVOS

U1. O que faz
    Abre o olist.duckdb da raiz do projeto, instala e carrega a extensão ui
    (INSTALL ui; LOAD ui;) e chama CALL start_ui(), que sobe o servidor em
    http://localhost:4213 e abre o navegador. Por quê: explorar o banco
    visualmente em vez de ler tabela no terminal.

U2. Fica de pé até Ctrl+C
    A extensão serve enquanto a conexão estiver viva, então o script mantém
    o processo rodando, imprime a URL e "Ctrl+C para encerrar", e no Ctrl+C
    fecha a conexão e sai limpo, sem traceback.
    Por quê: o .duckdb aceita um único processo escrevendo. Com este script
    de pé, a ingestão falha com "Could not set lock on file". Saber
    exatamente como desligar o servidor faz parte da ferramenta.

U3. Não cria banco
    Se olist.duckdb não existir, avisa que é preciso rodar a ingestão antes
    e encerra com sys.exit(1). Não usa conectar() de pipeline/db.py, que
    cria o arquivo quando ele falta.
    Por quê: um banco vazio aberto no navegador parece ingestão quebrada.

U4. Separação
    Não importa pipeline/ingestao.py (nem nada de pipeline/), e a ingestão
    não importa este arquivo. A ingestão não depende da extensão ui.

U5. Saída na tela
    stdout reconfigurado para utf-8, pelo mesmo motivo da ingestão (acentos
    no Prompt de Comando do Windows).

CRITÉRIOS DE ACEITE
- uv run python ui.py abre o navegador em localhost:4213 e o schema raw
  aparece com as nove tabelas.
- Ctrl+C devolve o terminal sem traceback, e logo depois a ingestão roda
  sem erro de lock.
- Renomear olist.duckdb faz o script parar com a mensagem, sem criar
  arquivo novo.
"""

import sys
import time
from pathlib import Path

import duckdb

BANCO = Path(__file__).resolve().parent / "olist.duckdb"
URL = "http://localhost:4213"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    # Checagem antes de connect(): duckdb.connect criaria o arquivo vazio.
    if not BANCO.is_file():
        print(
            f"{BANCO} não existe. Rode a ingestão antes: "
            "uv run python -m pipeline.ingestao",
            file=sys.stderr,
        )
        sys.exit(1)

    con = duckdb.connect(str(BANCO))
    try:
        con.execute("INSTALL ui")
        con.execute("LOAD ui")
        con.execute("CALL start_ui()")
        print(f"Interface no ar em {URL}")
        print("Ctrl+C para encerrar")
        # Laço curto com sleep: no Windows, uma espera sem timeout
        # não é interrompida pelo Ctrl+C.
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nEncerrando...")
    finally:
        # Fechar a conexão derruba o servidor e libera o lock do arquivo.
        con.close()


if __name__ == "__main__":
    main()