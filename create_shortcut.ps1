$ws = New-Object -ComObject WScript.Shell
$shortcut = $ws.CreateShortcut("C:\Users\jinyo\Desktop\Dashboard.lnk")
$shortcut.TargetPath = "C:\Users\jinyo\Desktop\claude_2603\run_dashboard.bat"
$shortcut.WorkingDirectory = "C:\Users\jinyo\Desktop\claude_2603"
$shortcut.WindowStyle = 1
$shortcut.Save()
Rename-Item "C:\Users\jinyo\Desktop\Dashboard.lnk" "연구동향 대시보드.lnk" -Force
Write-Host "done"
