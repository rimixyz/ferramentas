@echo off
chcp 65001 >nul 2>&1
title Separador de HTML v3.0
color 0F

:: Verificar Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  [ERRO] Python nao encontrado!
    echo  Instale: https://www.python.org/downloads/
    echo  Marque "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

:: Se arrastou arquivo(s) pra cima do .bat
if not "%~1"=="" (
    echo.
    echo  ══════════════════════════════════════
    echo     SEPARADOR DE HTML v3.0
    echo  ══════════════════════════════════════
    echo.
    echo  Arquivo: %~nx1
    echo.

    python "%~dp0separador.py" "%~1" -f

    echo.
    echo  Pressione qualquer tecla para fechar...
    pause >nul
    exit /b 0
)

:: Menu interativo
:menu
cls
echo.
echo  ══════════════════════════════════════════════
echo     SEPARADOR DE HTML v3.0
echo  ══════════════════════════════════════════════
echo.
echo   [1] Separar arquivo HTML
echo   [2] Separar com opcoes avancadas
echo   [3] Processar todos os HTML de uma pasta
echo   [4] Ajuda
echo   [5] Sair
echo.
set /p "op=  Escolha [1-5]: "

if "%op%"=="1" goto simples
if "%op%"=="2" goto avancado
if "%op%"=="3" goto pasta
if "%op%"=="4" goto ajuda
if "%op%"=="5" exit /b 0

echo  Opcao invalida!
timeout /t 2 >nul
goto menu

:simples
echo.
echo  Voce pode arrastar o arquivo pra ca:
echo.
set /p "HTML=  Caminho do HTML: "
set "HTML=%HTML:"=%"

if "%HTML%"=="" (
    echo  [ERRO] Caminho vazio!
    timeout /t 2 >nul
    goto menu
)

if not exist "%HTML%" (
    echo  [ERRO] Arquivo nao encontrado!
    timeout /t 2 >nul
    goto menu
)

echo.
python "%~dp0separador.py" "%HTML%"
echo.
pause
goto menu

:avancado
echo.
set /p "HTML=  Caminho do HTML: "
set "HTML=%HTML:"=%"

if not exist "%HTML%" (
    echo  [ERRO] Arquivo nao encontrado!
    timeout /t 2 >nul
    goto menu
)

echo.
set /p "SAIDA=  Diretorio de saida (Enter = ./separado): "
set /p "CSS=  Nome do CSS (Enter = style.css): "
set /p "JS=  Nome do JS (Enter = script.js): "
echo.

set "CMD=python "%~dp0separador.py" "%HTML%""
if not "%SAIDA%"=="" set "CMD=%CMD% -o "%SAIDA%""
if not "%CSS%"=="" set "CMD=%CMD% --css %CSS%"
if not "%JS%"=="" set "CMD=%CMD% --js %JS%"

echo  Executando...
echo.
%CMD%
echo.
pause
goto menu

:pasta
echo.
set /p "PASTA=  Caminho da pasta: "
set "PASTA=%PASTA:"=%"

if not exist "%PASTA%\" (
    echo  [ERRO] Pasta nao encontrada!
    timeout /t 2 >nul
    goto menu
)

echo.
echo  Processando todos os .html em: %PASTA%
echo  ─────────────────────────────────────────
echo.

set "count=0"
for %%f in ("%PASTA%\*.html") do (
    echo  ■ Processando: %%~nxf
    
    python "%~dp0separador.py" "%%f" -o "%PASTA%\%%~nf_separado" -f
    
    set /a count+=1
    echo.
)

if %count%==0 (
    echo  Nenhum arquivo .html encontrado na pasta!
) else (
    echo  ═══════════════════════════════════════
    echo  Concluido! %count% arquivo(s) processado(s).
)

echo.
pause
goto menu

:ajuda
cls
echo.
echo  ══════════════════════════════════════════════
echo                     AJUDA
echo  ══════════════════════════════════════════════
echo.
echo  O QUE FAZ:
echo    Pega um HTML com CSS e JS embutidos
echo    e separa em 3 arquivos organizados.
echo.
echo  FORMAS DE USAR:
echo    1. Duplo clique no .bat (menu interativo)
echo    2. Arrastar o .html pra cima do .bat
echo    3. Opcao 3 do menu: pasta inteira
echo.
echo  O QUE TRATA:
echo    + Scripts externos (src=) - mantidos
echo    + JSON/LD+JSON - mantidos
echo    + style media="print" - vira @media
echo    + script type="module" - preservado
echo    + Conteudo em noscript/template - ignorado
echo    + Comentarios HTML - ignorados
echo    + CDATA (XHTML) - limpo
echo    + UTF-8 BOM - detectado
echo    + Encoding automatico
echo    + Escrita atomica (anti-corrupcao)
echo    + NUNCA sobrescreve o original
echo.
echo  ESTRUTURA:
echo    Coloque na mesma pasta:
echo      separador.py  (script Python)
echo      separar.bat   (este arquivo)
echo.
echo  ══════════════════════════════════════════════
echo.
pause
goto menu