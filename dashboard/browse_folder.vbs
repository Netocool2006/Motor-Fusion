' browse_folder.vbs - Opens native Windows folder picker dialog
' Called by dashboard server, writes result to a temp file
Dim resultFile
resultFile = WScript.Arguments(0)

Set objShell = CreateObject("Shell.Application")
Set objFolder = objShell.BrowseForFolder(0, "Seleccionar carpeta para Ingesta Masiva", &H50, 17)

Dim result
If Not objFolder Is Nothing Then
    result = objFolder.Self.Path
Else
    result = ""
End If

' Write result to temp file
Set fso = CreateObject("Scripting.FileSystemObject")
Set f = fso.CreateTextFile(resultFile, True)
f.Write result
f.Close
