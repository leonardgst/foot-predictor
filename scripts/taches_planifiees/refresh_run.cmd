@echo off
rem Tache planifiee : refresh de la saison 2026 (paliers P1 et P3), puis run plafonne.
rem Usage : refresh_run.cmd AAAA-MM-JJ [--dry-run]
rem   AAAA-MM-JJ : date du lancement, sert seulement a nommer le journal d'execution.
rem   --dry-run  : simulation (refresh --dry-run et run --dry-run), aucune requete.
rem Journal d'execution : data\logs\refresh_AAAA-MM-JJ.log (dossier ignore par Git).
rem Mode d'emploi : docs\realisation\03_collecte\README.md, section "Taches planifiees".
setlocal
title FootPredictor - refresh %~1 en cours, ne pas fermer cette fenetre
if "%~1"=="" (
  echo Usage : refresh_run.cmd AAAA-MM-JJ [--dry-run]
  exit /b 2
)
rem Racine du depot : deux dossiers au-dessus de ce script.
cd /d "%~dp0..\.." || exit /b 2
set "UV=%USERPROFILE%\.local\bin\uv.exe"
if not exist "%UV%" set "UV=uv"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "COLLECT=python -m foot_predictor.collect.api_football"
rem Plafond d'appels du run (budget valide : 250 par tache).
set "MAX_REQUESTS=250"
if not exist data\logs mkdir data\logs
set "LOG=data\logs\refresh_%~1.log"

echo ==== %date% %time% debut refresh_run %* >> "%LOG%"
if /i "%~2"=="--dry-run" (
  "%UV%" run %COLLECT% refresh --season 2026 --dry-run >> "%LOG%" 2>&1
  "%UV%" run %COLLECT% run --dry-run >> "%LOG%" 2>&1
  "%UV%" run %COLLECT% lock-status >> "%LOG%" 2>&1
  goto fin
)
rem --wait-lock : si une autre commande tient le verrou, attendre au plus 60 minutes.
"%UV%" run %COLLECT% --wait-lock 60 refresh --season 2026 --yes >> "%LOG%" 2>&1
if errorlevel 1 goto erreur
"%UV%" run %COLLECT% --wait-lock 60 run --max-requests %MAX_REQUESTS% >> "%LOG%" 2>&1
if errorlevel 1 goto erreur
"%UV%" run %COLLECT% status >> "%LOG%" 2>&1

:fin
echo ==== %date% %time% fin >> "%LOG%"
exit /b 0

:erreur
echo ==== %date% %time% ERREUR (code %errorlevel%) : voir les lignes ci-dessus >> "%LOG%"
exit /b 1
