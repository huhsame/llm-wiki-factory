@echo off
chcp 65001 >nul
rem llm-wiki-inbox nightly collect. Fetch only: no judging, no wiki pages.
rem Put this file in <wiki folder>\.inbox\ . WIKI is worked out from that location,
rem so a Korean wiki folder name is fine and nothing has to be typed twice.
rem Fill in PY and SKILL below with full paths. Claude works both of them out for you.
rem SKILL is normally %USERPROFILE%\.claude\skills\llm-wiki-inbox
for %%I in ("%~dp0..") do set "WIKI=%%~fI"
set "SKILL=C:\Users\me\.claude\skills\llm-wiki-inbox"
set "PY=C:\Users\me\AppData\Local\Programs\Python\Python312\python.exe"

set "LOG=%~dp0collect.log"
echo [%date% %time%] start >> "%LOG%"
"%PY%" "%SKILL%\scripts\mail_fetch.py"    --wiki "%WIKI%" --all >> "%LOG%" 2>&1
set "RC1=%ERRORLEVEL%"
"%PY%" "%SKILL%\scripts\kakao_collect.py" --wiki "%WIKI%" --all >> "%LOG%" 2>&1
set "RC2=%ERRORLEVEL%"
echo [%date% %time%] end mail=%RC1% kakao=%RC2% >> "%LOG%"
rem 0 = both fine. 2 = one of them is stuck; look at the last lines of collect.log.
if not "%RC1%"=="0" exit /b %RC1%
exit /b %RC2%
