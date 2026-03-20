#!/usr/bin/env python3
"""
Separador de HTML v3.0 — Versão blindada
Extrai <script> e <style> inline de um arquivo HTML
e salva em arquivos separados com referências automáticas.
"""

import re
import os
import sys
import json
import hashlib
import argparse
import tempfile
import shutil
from pathlib import Path
from datetime import datetime


# ═══════════════════════════════════════════════════════
#  PARSER MANUAL (mais robusto que HTMLParser pra isso)
# ═══════════════════════════════════════════════════════

class BlocoExtraido:
    """Representa um bloco <style> ou <script> extraído."""

    def __init__(self, tipo, conteudo, atributos_str, atributos_dict,
                 posicao_inicio, posicao_fim, texto_original):
        self.tipo = tipo                    # 'style' ou 'script'
        self.conteudo = conteudo            # conteúdo interno
        self.atributos_str = atributos_str  # string crua dos atributos
        self.atributos_dict = atributos_dict
        self.posicao_inicio = posicao_inicio
        self.posicao_fim = posicao_fim
        self.texto_original = texto_original  # bloco completo original

    @property
    def media(self):
        return self.atributos_dict.get('media', None)

    @property
    def tipo_script(self):
        return self.atributos_dict.get('type', '').lower().strip()

    @property
    def tem_src(self):
        return 'src' in self.atributos_dict

    @property
    def eh_module(self):
        return self.tipo_script == 'module'

    @property
    def eh_js_valido(self):
        """Verifica se é JavaScript válido para extrair."""
        if self.tipo != 'script':
            return False
        if self.tem_src:
            return False
        if not self.conteudo.strip():
            return False

        tipos_js = {'', 'text/javascript', 'application/javascript', 'module'}
        if self.tipo_script and self.tipo_script not in tipos_js:
            return False

        return True

    @property
    def eh_style_valido(self):
        """Verifica se é um <style> válido para extrair."""
        if self.tipo != 'style':
            return False
        if not self.conteudo.strip():
            return False
        return True

    @property
    def esta_no_head(self):
        """Heurística: se a posição é antes do <body>."""
        return self._regiao == 'head'

    _regiao = 'body'  # será definido pelo extrator


def parse_atributos(attr_string):
    """Parse robusto de atributos HTML."""
    attrs = {}
    if not attr_string:
        return attrs

    padrao = re.compile(
        r'(\w[\w\-]*)'
        r'(?:\s*=\s*'
        r'(?:"([^"]*)"'
        r"|'([^']*)'"
        r'|(\S+)))?',
        re.IGNORECASE
    )

    for m in padrao.finditer(attr_string):
        nome = m.group(1).lower()
        valor = m.group(2) or m.group(3) or m.group(4) or ''
        attrs[nome] = valor

    return attrs


def encontrar_blocos(conteudo_html):
    """
    Encontra todos os blocos <style> e <script> no HTML.
    Usa abordagem por estado para lidar com edge cases.
    """
    blocos = []

    # Pré-processamento: encontrar posição do <body> para saber região
    body_match = re.search(r'<body[\s>]', conteudo_html, re.IGNORECASE)
    pos_body = body_match.start() if body_match else len(conteudo_html)

    # Encontrar blocos dentro de tags que devemos ignorar
    regioes_ignorar = set()
    tags_ignorar = ['noscript', 'template', 'iframe', 'textarea', 'xmp']
    for tag in tags_ignorar:
        for m in re.finditer(
            rf'<{tag}[\s>].*?</{tag}>',
            conteudo_html,
            re.DOTALL | re.IGNORECASE
        ):
            for pos in range(m.start(), m.end()):
                regioes_ignorar.add(pos)

    # Encontrar comentários HTML para ignorar
    for m in re.finditer(r'<!--.*?-->', conteudo_html, re.DOTALL):
        for pos in range(m.start(), m.end()):
            regioes_ignorar.add(pos)

    # ─── EXTRAIR <style> ───
    padrao_style = re.compile(
        r'(<style(\s[^>]*)?>)(.*?)(</style>)',
        re.DOTALL | re.IGNORECASE
    )

    for m in padrao_style.finditer(conteudo_html):
        if m.start() in regioes_ignorar:
            continue

        attr_str = m.group(2) or ''
        attrs = parse_atributos(attr_str)
        conteudo = m.group(3)

        # Limpar CDATA wrapper se existir
        conteudo = re.sub(r'/\*\s*<!\[CDATA\[\s*\*/', '', conteudo)
        conteudo = re.sub(r'/\*\s*\]\]>\s*\*/', '', conteudo)

        bloco = BlocoExtraido(
            tipo='style',
            conteudo=conteudo.strip(),
            atributos_str=attr_str.strip(),
            atributos_dict=attrs,
            posicao_inicio=m.start(),
            posicao_fim=m.end(),
            texto_original=m.group(0)
        )
        bloco._regiao = 'head' if m.start() < pos_body else 'body'
        blocos.append(bloco)

    # ─── EXTRAIR <script> ───
    # Regex especial que lida melhor com </script> dentro de strings
    padrao_script = re.compile(
        r'(<script(\s[^>]*)?>)(.*?)(</script>)',
        re.DOTALL | re.IGNORECASE
    )

    for m in padrao_script.finditer(conteudo_html):
        if m.start() in regioes_ignorar:
            continue

        attr_str = m.group(2) or ''
        attrs = parse_atributos(attr_str)
        conteudo = m.group(3)

        # Limpar CDATA wrapper se existir (XHTML)
        conteudo = re.sub(r'//\s*<!\[CDATA\[', '', conteudo)
        conteudo = re.sub(r'//\s*\]\]>', '', conteudo)
        conteudo = re.sub(r'/\*\s*<!\[CDATA\[\s*\*/', '', conteudo)
        conteudo = re.sub(r'/\*\s*\]\]>\s*\*/', '', conteudo)

        bloco = BlocoExtraido(
            tipo='script',
            conteudo=conteudo.strip(),
            atributos_str=attr_str.strip(),
            atributos_dict=attrs,
            posicao_inicio=m.start(),
            posicao_fim=m.end(),
            texto_original=m.group(0)
        )
        bloco._regiao = 'head' if m.start() < pos_body else 'body'
        blocos.append(bloco)

    return blocos


# ═══════════════════════════════════════════════════════
#  GERAÇÃO DOS ARQUIVOS
# ═══════════════════════════════════════════════════════

def gerar_css(blocos_style):
    """Gera o conteúdo do arquivo CSS, respeitando media queries."""
    partes = []

    for bloco in blocos_style:
        if not bloco.eh_style_valido:
            continue

        conteudo = bloco.conteudo

        # Se tem media attribute, wrappa com @media
        if bloco.media:
            linhas = conteudo.split('\n')
            indentado = '\n'.join('  ' + linha for linha in linhas)
            conteudo = f"@media {bloco.media} {{\n{indentado}\n}}"

        partes.append(conteudo)

    return "\n\n".join(partes) + "\n" if partes else ""


def gerar_js(blocos_script):
    """Gera o conteúdo do arquivo JS."""
    partes = []

    for bloco in blocos_script:
        if not bloco.eh_js_valido:
            continue
        partes.append(bloco.conteudo)

    return "\n\n".join(partes) + "\n" if partes else ""


def gerar_html_limpo(conteudo_original, blocos, nome_css, nome_js,
                     tem_css, tem_js, tem_module):
    """
    Gera o HTML limpo removendo blocos inline e inserindo referências.
    Remove de trás pra frente para não invalidar as posições.
    """
    html = conteudo_original

    # Ordenar blocos por posição DECRESCENTE (remove de trás pra frente)
    blocos_remover = sorted(
        [b for b in blocos if b.eh_style_valido or b.eh_js_valido],
        key=lambda b: b.posicao_inicio,
        reverse=True
    )

    for bloco in blocos_remover:
        inicio = bloco.posicao_inicio
        fim = bloco.posicao_fim

        # Expandir para incluir whitespace/newline ao redor
        while inicio > 0 and html[inicio - 1] in ' \t':
            inicio -= 1
        while fim < len(html) and html[fim] in ' \t':
            fim += 1
        if fim < len(html) and html[fim] == '\n':
            fim += 1

        html = html[:inicio] + html[fim:]

    # Inserir referências
    if tem_css:
        html = _inserir_css_ref(html, nome_css)

    if tem_js:
        if tem_module:
            html = _inserir_js_ref(html, nome_js, is_module=True)
        else:
            html = _inserir_js_ref(html, nome_js, is_module=False)

    # Limpar linhas vazias excessivas
    html = re.sub(r'\n{3,}', '\n\n', html)

    return html


def _inserir_css_ref(html, nome_css):
    """Insere <link> no lugar certo."""
    tag = f'  <link rel="stylesheet" href="{nome_css}">'

    # 1. Antes de </head>
    m = re.search(r'^([ \t]*)</head>', html, re.MULTILINE | re.IGNORECASE)
    if m:
        pos = m.start()
        indent = m.group(1)
        return html[:pos] + tag + '\n' + indent + html[pos:]

    # 2. Depois de <head>
    m = re.search(r'<head[^>]*>\n?', html, re.IGNORECASE)
    if m:
        pos = m.end()
        return html[:pos] + tag + '\n' + html[pos:]

    # 3. No topo
    return tag + '\n' + html


def _inserir_js_ref(html, nome_js, is_module=False):
    """Insere <script src> no lugar certo."""
    type_attr = ' type="module"' if is_module else ''
    tag = f'  <script src="{nome_js}"{type_attr}></script>'

    # 1. Antes de </body>
    m = re.search(r'^([ \t]*)</body>', html, re.MULTILINE | re.IGNORECASE)
    if m:
        pos = m.start()
        indent = m.group(1)
        return html[:pos] + tag + '\n' + indent + html[pos:]

    # 2. Antes de </html>
    m = re.search(r'^([ \t]*)</html>', html, re.MULTILINE | re.IGNORECASE)
    if m:
        pos = m.start()
        indent = m.group(1)
        return html[:pos] + tag + '\n' + indent + html[pos:]

    # 3. No final
    return html.rstrip() + '\n' + tag + '\n'


# ═══════════════════════════════════════════════════════
#  UTILITÁRIOS
# ═══════════════════════════════════════════════════════

def detectar_encoding(caminho):
    """Detecta encoding do arquivo."""
    with open(caminho, 'rb') as f:
        raw = f.read(4)

    # UTF-8 BOM
    if raw[:3] == b'\xef\xbb\xbf':
        return 'utf-8-sig'

    # UTF-16 BOM
    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
        return 'utf-16'

    # Tentar UTF-8
    try:
        with open(caminho, 'r', encoding='utf-8') as f:
            f.read()
        return 'utf-8'
    except UnicodeDecodeError:
        pass

    return 'latin-1'


def validar_nome(nome):
    """Valida nome de arquivo."""
    if not nome:
        return False, "Nome vazio"
    if len(nome) > 200:
        return False, "Nome muito longo"
    proibidos = set('<>:"|?*')
    for c in nome:
        if c in proibidos:
            return False, f"Caractere proibido: {c}"
    if nome.startswith('.'):
        return False, "Não pode começar com ponto"
    if '..' in nome:
        return False, "Não pode conter '..'"
    if '/' in nome or '\\' in nome:
        return False, "Não pode conter barras"
    return True, ""


def escrita_atomica(caminho, conteudo, encoding='utf-8'):
    """
    Escrita atômica: escreve em arquivo temporário primeiro,
    depois renomeia. Evita arquivo corrompido se der erro no meio.
    """
    caminho = Path(caminho)
    dir_pai = caminho.parent

    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=str(dir_pai),
            prefix='.tmp_',
            suffix=caminho.suffix
        )
        with os.fdopen(fd, 'w', encoding=encoding) as f:
            f.write(conteudo)

        # No Windows, precisa remover o destino antes
        if sys.platform == 'win32' and caminho.exists():
            caminho.unlink()

        shutil.move(tmp_path, str(caminho))

    except Exception:
        # Limpar temporário se deu erro
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        raise


def gerar_backup_nome(caminho_original, dir_saida):
    """Se já existem arquivos na saída, não sobrescreve sem avisar."""
    arquivos_existentes = []
    for ext in ('.css', '.js', '.html'):
        for f in dir_saida.iterdir():
            if f.suffix == ext and f.is_file():
                arquivos_existentes.append(f)
    return arquivos_existentes


# ═══════════════════════════════════════════════════════
#  PROCESSAMENTO PRINCIPAL
# ═══════════════════════════════════════════════════════

def processar(caminho_html, dir_saida=None, nome_css='style.css',
              nome_js='script.js', forcar=False):
    """Função principal."""

    caminho_html = Path(caminho_html).resolve()

    # ─── VALIDAÇÕES ───
    if not caminho_html.exists():
        print(f"\n❌ Arquivo não encontrado: {caminho_html}")
        sys.exit(1)

    if not caminho_html.is_file():
        print(f"\n❌ Não é um arquivo: {caminho_html}")
        sys.exit(1)

    if caminho_html.stat().st_size == 0:
        print(f"\n❌ Arquivo vazio: {caminho_html}")
        sys.exit(1)

    if caminho_html.stat().st_size > 50 * 1024 * 1024:  # 50MB
        print(f"\n❌ Arquivo muito grande (>50MB). Tem certeza que é HTML?")
        sys.exit(1)

    ok, erro = validar_nome(nome_css)
    if not ok:
        print(f"\n❌ Nome CSS inválido '{nome_css}': {erro}")
        sys.exit(1)

    ok, erro = validar_nome(nome_js)
    if not ok:
        print(f"\n❌ Nome JS inválido '{nome_js}': {erro}")
        sys.exit(1)

    if nome_css == nome_js:
        print(f"\n❌ CSS e JS não podem ter o mesmo nome: {nome_css}")
        sys.exit(1)

    # Diretório de saída
    if dir_saida:
        dir_saida = Path(dir_saida).resolve()
    else:
        dir_saida = caminho_html.parent / "separado"

    # Proteção contra sobrescrita do original
    caminho_html_saida = dir_saida / caminho_html.name
    if caminho_html_saida.resolve() == caminho_html.resolve():
        print("\n❌ Saída é o mesmo do original!")
        print(f"   Use: python separador.py {caminho_html.name} -o ./dist")
        sys.exit(1)

    # Criar diretório
    try:
        dir_saida.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        print(f"\n❌ Sem permissão para criar: {dir_saida}")
        sys.exit(1)
    except OSError as e:
        print(f"\n❌ Erro ao criar diretório: {e}")
        sys.exit(1)

    # Verificar se vai sobrescrever
    arquivos_saida = [dir_saida / nome_css, dir_saida / nome_js, caminho_html_saida]
    existentes = [a for a in arquivos_saida if a.exists()]
    if existentes and not forcar:
        print(f"\n⚠️  Arquivos já existem em {dir_saida}:")
        for a in existentes:
            print(f"   • {a.name}")
        resp = input("\nSobrescrever? (s/N): ").strip().lower()
        if resp not in ('s', 'sim', 'y', 'yes'):
            print("Cancelado.")
            sys.exit(0)

    # Testar escrita
    try:
        teste = dir_saida / ".teste_permissao"
        teste.write_text("teste")
        teste.unlink()
    except PermissionError:
        print(f"\n❌ Sem permissão de escrita em: {dir_saida}")
        sys.exit(1)

    # ─── LER ARQUIVO ───
    encoding = detectar_encoding(caminho_html)
    try:
        with open(caminho_html, 'r', encoding=encoding) as f:
            conteudo_original = f.read()
    except Exception as e:
        print(f"\n❌ Erro ao ler arquivo: {e}")
        sys.exit(1)

    if not conteudo_original.strip():
        print(f"\n❌ Arquivo contém apenas espaços em branco.")
        sys.exit(1)

    print(f"\n📄 Entrada:   {caminho_html}")
    print(f"📁 Saída:     {dir_saida}")
    print(f"📝 Encoding:  {encoding}")
    print(f"📏 Tamanho:   {len(conteudo_original):,} caracteres")
    print("─" * 55)

    # ─── ANALISAR ───
    try:
        blocos = encontrar_blocos(conteudo_original)
    except Exception as e:
        print(f"\n❌ Erro ao analisar HTML: {e}")
        sys.exit(1)

    blocos_style = [b for b in blocos if b.eh_style_valido]
    blocos_script = [b for b in blocos if b.eh_js_valido]

    # Scripts ignorados (info pro usuário)
    scripts_externos = [b for b in blocos if b.tipo == 'script' and b.tem_src]
    scripts_nao_js = [b for b in blocos
                      if b.tipo == 'script'
                      and not b.tem_src
                      and not b.eh_js_valido
                      and b.conteudo.strip()]

    if scripts_externos:
        print(f"ℹ️  {len(scripts_externos)} <script src=\"...\"> mantido(s) no HTML")

    if scripts_nao_js:
        tipos = set(b.tipo_script or 'sem type' for b in scripts_nao_js)
        print(f"ℹ️  {len(scripts_nao_js)} <script> não-JS ignorado(s): {', '.join(tipos)}")

    if not blocos_style and not blocos_script:
        print("\n⚠️  Nenhum <style> ou <script> inline encontrado.")
        print("   Nada para separar!")
        sys.exit(0)

    # Verificar se tem type="module"
    tem_module = any(b.eh_module for b in blocos_script)

    # Aviso sobre module misturado com não-module
    scripts_module = [b for b in blocos_script if b.eh_module]
    scripts_normal = [b for b in blocos_script if not b.eh_module]
    if scripts_module and scripts_normal:
        print("⚠️  Mix de scripts normais e type=\"module\" detectado!")
        print("   Todos serão combinados. Pode precisar de ajuste manual.")

    # ─── GERAR CSS ───
    tem_css = len(blocos_style) > 0
    if tem_css:
        css_final = gerar_css(blocos_style)
        try:
            escrita_atomica(dir_saida / nome_css, css_final)
        except Exception as e:
            print(f"\n❌ Erro ao salvar CSS: {e}")
            sys.exit(1)

        medias = [b.media for b in blocos_style if b.media]
        info_media = f" (media: {', '.join(medias)})" if medias else ""
        print(f"🎨 CSS → {nome_css}")
        print(f"   {len(blocos_style)} bloco(s), "
              f"{len(css_final):,} chars{info_media}")

    # ─── GERAR JS ───
    tem_js = len(blocos_script) > 0
    if tem_js:
        js_final = gerar_js(blocos_script)
        try:
            escrita_atomica(dir_saida / nome_js, js_final)
        except Exception as e:
            print(f"\n❌ Erro ao salvar JS: {e}")
            sys.exit(1)

        info_module = " (module)" if tem_module else ""
        print(f"⚡ JS  → {nome_js}")
        print(f"   {len(blocos_script)} bloco(s), "
              f"{len(js_final):,} chars{info_module}")

    # ─── GERAR HTML LIMPO ───
    try:
        html_limpo = gerar_html_limpo(
            conteudo_original, blocos,
            nome_css, nome_js,
            tem_css, tem_js, tem_module
        )
    except Exception as e:
        print(f"\n❌ Erro ao gerar HTML limpo: {e}")
        sys.exit(1)

    try:
        escrita_atomica(caminho_html_saida, html_limpo)
    except Exception as e:
        print(f"\n❌ Erro ao salvar HTML: {e}")
        sys.exit(1)

    print(f"📝 HTML → {caminho_html.name}")
    print(f"   {len(html_limpo):,} chars")

    # ─── RESUMO ───
    print("─" * 55)
    print(f"✅ Concluído!\n")

    total = 0
    for arq in sorted(dir_saida.iterdir()):
        if arq.is_file() and not arq.name.startswith('.'):
            tam = arq.stat().st_size
            total += tam
            icone = {'html': '📄', 'css': '🎨', 'js': '⚡'}.get(
                arq.suffix.lstrip('.'), '📎'
            )
            print(f"   {icone} {arq.name:<25s} {tam:>10,} bytes")

    print(f"   {'─' * 40}")
    print(f"   📦 Total: {total:>27,} bytes")
    print()

    return True


# ═══════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Separa <style> e <script> inline de um HTML em arquivos.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python separador.py index.html
  python separador.py index.html -o ./dist
  python separador.py index.html -o ./dist --css main.css --js app.js
  python separador.py index.html -f

Tratamentos:
  ✓ <style media="print">          → @media print { ... } no CSS
  ✓ <script type="module">         → <script src="x.js" type="module">
  ✓ <script src="externo.js">      → mantém intacto no HTML
  ✓ <script type="application/json"> → mantém intacto
  ✓ <style>/<script> em <noscript>  → ignora
  ✓ <style>/<script> em comentário  → ignora
  ✓ CDATA wrappers (XHTML)         → limpa
  ✓ UTF-8 BOM, UTF-16, Latin-1     → detecta
  ✓ Escrita atômica                 → não corrompe se crashar
  ✓ Não sobrescreve original        → saída em pasta separada
        """
    )

    parser.add_argument('html', help='Caminho do arquivo HTML')
    parser.add_argument('-o', '--output', help='Diretório de saída (padrão: ./separado)', default=None)
    parser.add_argument('--css', help='Nome do CSS (padrão: style.css)', default='style.css')
    parser.add_argument('--js', help='Nome do JS (padrão: script.js)', default='script.js')
    parser.add_argument('-f', '--force', help='Sobrescrever sem perguntar', action='store_true')

    args = parser.parse_args()
    processar(args.html, args.output, args.css, args.js, args.force)


if __name__ == '__main__':
    main()
