@echo off
echo Getting to the correct Directory...
cd "C:\Users\ryani\Coding Projects\Habit Tracker Website"

echo giving copmuter time to connect to network
timeout /t 30 >nul

echo running program
"C:\Users\ryani\Coding Projects\News Aggregator\.venv\Scripts\python.exe" main.py

echo Little ending cooldown before sleep
timeout /t 10 >nul

echo Putting computer to sleep...
powershell -command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Application]::SetSuspendState('Suspend', $false, $false)"