@echo off
rem Tache planifiee : journal T-60 d'une journee de matchs du top 5 (ADR-0010).
rem Usage : t60.cmd AAAA-MM-JJ [--dry-run]
rem   AAAA-MM-JJ : jour des matchs (UTC).
rem   --dry-run  : simulation d'apres les listes du brut, aucune requete.
rem La commande tourne jusqu'au dernier coup d'envoi du jour et empeche la mise
rem en veille automatique : laisser le portable ouvert, branche, session ouverte.
rem Journal d'execution : data\logs\t60_AAAA-MM-JJ.log (dossier ignore par Git).
rem Mode d'emploi : docs\realisation\03_collecte\README.md, section "Taches planifiees".
setlocal
title FootPredictor - journal T-60 du %~1, ne pas fermer cette fenetre
if "%~1"=="" (
  echo Usage : t60.cmd AAAA-MM-JJ [--dry-run]
  exit /b 2
)
cd /d "%~dp0..\.." || exit /b 2
set "UV=%USERPROFILE%\.local\bin\uv.exe"
if not exist "%UV%" set "UV=uv"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "COLLECT=python -m foot_predictor.collect.api_football"
rem Plafond d'appels (budget valide : 80 par tache ; pire cas simule : 73).
set "MAX_REQUESTS=80"
if not exist data\logs mkdir data\logs
set "LOG=data\logs\t60_%~1.log"

echo ==== %date% %time% debut t60 %* >> "%LOG%"
if /i "%~2"=="--dry-run" (
  "%UV%" run %COLLECT% t60 --date %~1 --max-requests %MAX_REQUESTS% --dry-run >> "%LOG%" 2>&1
  "%UV%" run %COLLECT% lock-status >> "%LOG%" 2>&1
  goto fin
)
rem --wait-lock : le 12 octobre, attendre la fin du refresh du matin (2 heures au plus).
"%UV%" run %COLLECT% --wait-lock 120 t60 --date %~1 --max-requests %MAX_REQUESTS% >> "%LOG%" 2>&1
if errorlevel 1 goto erreur

:fin
echo ==== %date% %time% fin >> "%LOG%"
exit /b 0

:erreur
echo ==== %date% %time% ERREUR (code %errorlevel%) : voir les lignes ci-dessus >> "%LOG%"
exit /b 1
