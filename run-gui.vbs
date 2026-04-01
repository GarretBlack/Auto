Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
base = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = base & "\.venv\Scripts\pythonw.exe"
gui = base & "\gui.pyw"

If Not fso.FileExists(pythonw) Then
    MsgBox "Не найден pythonw.exe в .venv. Сначала выполните setup.ps1", 48, "Auto Scenario Studio"
    WScript.Quit 1
End If

If Not fso.FileExists(gui) Then
    MsgBox "Не найден gui.pyw", 48, "Auto Scenario Studio"
    WScript.Quit 1
End If

shell.Run """" & pythonw & """ """ & gui & """", 0, False
