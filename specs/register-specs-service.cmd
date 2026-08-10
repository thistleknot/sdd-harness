@echo off
REM register-specs-service.cmd — Install specs MCP as an NSSM service.
REM Run as Administrator.

set NSSM=C:\Users\user\.pi\bin\nssm.exe
set SVC=specs-mcp
set PYTHON=C:\Users\user\py310\Scripts\python.exe
set SCRIPT=C:\Users\user\.harness\specs\specs_mcp.py
set WORKDIR=C:\Users\user\.harness\specs
set LOGFILE=C:\Users\user\.harness\specs\specs-mcp.service.log

%NSSM% stop %SVC% 2>nul
%NSSM% remove %SVC% confirm 2>nul

%NSSM% install %SVC% %PYTHON%
%NSSM% set %SVC% AppParameters "%SCRIPT%"
%NSSM% set %SVC% AppDirectory "%WORKDIR%"
%NSSM% set %SVC% AppEnvironmentExtra PYTHONIOENCODING=utf-8 PYTHONUTF8=1 HOME=C:\Users\user USERPROFILE=C:\Users\user
%NSSM% set %SVC% AppStdout "%LOGFILE%"
%NSSM% set %SVC% AppStderr "%LOGFILE%"
%NSSM% set %SVC% AppRotateFiles 1
%NSSM% set %SVC% AppRotateOnline 1
%NSSM% set %SVC% AppRotateBytes 5242880
%NSSM% set %SVC% Start SERVICE_AUTO_START
%NSSM% set %SVC% AppExit Default Restart
%NSSM% set %SVC% AppRestartDelay 3000
%NSSM% set %SVC% AppThrottle 5000
%NSSM% set %SVC% DisplayName "Specs MCP Server"
%NSSM% set %SVC% Description "Harness spec tracker on 127.0.0.1:8057/mcp. SQLite source of truth with auto-rendered markdown."

%NSSM% start %SVC%
timeout /t 3 /nobreak >nul
%NSSM% status %SVC%
echo.
echo Done. Verify: curl http://127.0.0.1:8057/health
