@echo off
REM Double-click or run from CMD to start Neo4j in Podman (calls start_neo4j_podman.ps1).
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_neo4j_podman.ps1" %*
exit /b %ERRORLEVEL%
