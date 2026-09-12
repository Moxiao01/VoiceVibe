@echo off
rem Voice Vibe 打包第一步：生成 dist\VoiceVibe\（onedir）。
rem 第二步用 Inno Setup 封装安装包：
rem   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\voice_vibe.iss
cd /d "%~dp0.."
pyinstaller packaging\VoiceVibe.spec --noconfirm
